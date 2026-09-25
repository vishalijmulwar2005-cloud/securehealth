"""Federated learning API (TRD §16; Implementation Plan Phase 10).

Training/aggregation controls are role-restricted (HOSPITAL_ADMIN +
SYSTEM_ADMIN). Eligibility is gated by ACTIVE research_consents; participants
carry only counts/metrics/fingerprints — never raw records. Every round is
recorded through the ledger outbox as an AGGREGATION event.
"""
from fastapi import APIRouter, Depends, Query
import math
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...core.errors import APIError
from ...core.security import ROLE_HOSPITAL_ADMIN, ROLE_SYSTEM_ADMIN
from ...db.session import get_db
from ..deps import get_current_user
from ...models.models import (
    FederatedJobs, Hospitals, ModelUpdates, ModelVersions, PatientProfiles,
    ResearchConsents, Users,
)
from ...services import fl_engine, ledger as ledger_svc
from ...services.audit import audit
from ...services.ledger_outbox import enqueue, process_outbox
from ...services.model_store import load_model, save_artifact

router = APIRouter(prefix="/federated", tags=["federated"])

TRAIN_ROLES = {ROLE_HOSPITAL_ADMIN, ROLE_SYSTEM_ADMIN}


def _require_train_role(user) -> None:
    if user.role not in TRAIN_ROLES:
        raise APIError(403, "FORBIDDEN")


def _load_patients(db: Session) -> list[dict]:
    """Locally held synthetic records with consent gate (ACTIVE research_consents)."""
    consenting = {
        r.patient_id for r in db.execute(select(ResearchConsents).where(
            ResearchConsents.status == "ACTIVE")).scalars().all()
    }
    rows = db.execute(select(PatientProfiles, Users.hospital_id).join(
        Users, Users.id == PatientProfiles.user_id)).all()
    patients = []
    for profile, hospital_id in rows:
        attrs = profile.synthetic_attributes or {}
        patients.append({
            "hospital": attrs.get("hospital"),
            "consent_research": profile.user_id in consenting,
            "features": attrs.get("features") or {},
            "labels": attrs.get("labels") or {},
        })
    return patients


def _active_hospitals(db: Session) -> list[dict]:
    rows = db.execute(select(Hospitals).where(Hospitals.active.is_(True))).scalars().all()
    return [{"id": h.id, "code": h.code} for h in rows]


@router.get("/diseases")
def list_diseases() -> list:
    return fl_engine.DISEASES


@router.get("/summary")
def summary(db: Session = Depends(get_db)) -> list:
    out = []
    for d in fl_engine.DISEASES:
        model = load_model(db, d["key"])
        versions = db.execute(select(ModelVersions).where(
            ModelVersions.model_id == d["key"]).order_by(
            ModelVersions.version.desc())).scalars().all()
        out.append({
            "disease": d["key"], "name": d["name"], "version": model["version"],
            "fingerprint": model["fingerprint"],
            "cumulative_epsilon": round(model["cumulative_epsilon"], 4),
            "served_matches_ledger": ledger_svc.served_model_matches(
                db, disease=d["key"], fingerprint=model["fingerprint"])
            if model["fingerprint"] else False,
            "artifact_versions": len(versions),
        })
    return out


@router.get("/jobs")
def list_jobs(disease: str | None = Query(default=None), limit: int = Query(default=20, le=50),
              db: Session = Depends(get_db)) -> list:
    q = select(FederatedJobs).order_by(FederatedJobs.id.desc()).limit(limit)
    if disease:
        q = q.where(FederatedJobs.disease_model == disease)
    rows = db.execute(q).scalars().all()
    return [{"id": j.id, "disease": j.disease_model, "round": j.round,
             "config": j.config, "participants": j.participants, "metrics": j.metrics,
             "epsilon": j.epsilon, "cumulative_epsilon": j.cumulative_epsilon,
             "model_hash": j.model_hash, "block_index": j.block_index,
             "status": j.status, "created_at": j.created_at.isoformat()} for j in rows]


class RunBody(BaseModel):
    disease: str
    epochs: int = Field(default=3, ge=1, le=10)
    learning_rate: float = Field(default=0.1, ge=0.01, le=0.5)
    dp_enabled: bool = True
    noise_multiplier: float = Field(default=1.0, ge=0.1, le=3.0)
    clip_norm: float = Field(default=0.5, ge=0.1, le=2.0)
    rounds: int = Field(default=1, ge=1, le=20)


@router.post("/run")
def run_training(body: RunBody, user: Users = Depends(get_current_user),
                 db: Session = Depends(get_db)) -> dict:
    """Run N federated rounds. Role-restricted; consent-gated; AGGREGATION
    events go through the ledger outbox. Real measured wall time only."""
    _require_train_role(user)
    if body.disease not in fl_engine.DISEASE_KEYS:
        raise APIError(400, "VALIDATION_ERROR")
    model = load_model(db, body.disease)
    patients = _load_patients(db)
    hospitals = _active_hospitals(db)
    config = {"epochs": body.epochs, "learningRate": body.learning_rate,
              "dpEnabled": body.dp_enabled, "noiseMultiplier": body.noise_multiplier,
              "clipNorm": body.clip_norm}
    run_jobs = []
    for _ in range(body.rounds):
        result = fl_engine.run_round(disease_key=body.disease, config=config, model=model,
                                     patients=patients, active_hospitals=hospitals)
        job = FederatedJobs(
            disease_model=body.disease, round=result["version"], config=config,
            participants=result["participants"],  # counts/metrics/fingerprints only
            metrics={"accuracy": result["metrics"]["accuracy"],
                     "loss": result["metrics"]["loss"],
                     "f1": result["metrics"]["f1"],
                     "totalSamples": result["total_samples"],
                     "durationMs": result["duration_ms"]},
            epsilon=result["metrics"]["epsilon"],
            cumulative_epsilon=result["metrics"]["cumulativeEpsilon"],
            model_hash=result["model_hash"], status="COMPLETED",
        )
        db.add(job)
        db.flush()
        hospital_id_by_code = {h["code"]: h["id"] for h in hospitals}
        for p in result["participants"]:
            db.add(ModelUpdates(
                federated_job_id=job.id,
                hospital_id=hospital_id_by_code.get(p["hospital"]),
                version=str(result["version"]), update_hash=p["updateHash"],
                samples_count=p["samples"], clip_norm=body.clip_norm if body.dp_enabled else None,
                noise_sigma=body.noise_multiplier if body.dp_enabled else None,
                status="ACCEPTED",
            ))
        save_artifact(db, disease=body.disease, model=model)
        # Audit first, then the durable AGGREGATION outbox reference linked to
        # it — the worker stamps the mined block index back onto the audit row.
        audit_row = audit(db, actor_id=user.id, role=user.role, event_type="FL_ROUND",
                          target_type="FEDERATED_JOB", target_id=job.id, outcome="SUCCESS",
                          details={"disease": body.disease, "round": result["version"]})
        enqueue(db, event_type="AGGREGATION", ref=str(job.id),
                audit_event_id=audit_row.id,
                data={"disease": body.disease, "round": result["version"],
                      "samples": result["total_samples"],
                      "epsilon": result["metrics"]["epsilon"],
                      "cumulative_epsilon": result["metrics"]["cumulativeEpsilon"],
                      "model_hash": result["model_hash"],
                      "previous_model_hash": result["previous_model_hash"],
                      "dp": {"enabled": body.dp_enabled,
                             "sigma": body.noise_multiplier if body.dp_enabled else 0,
                             "clip_norm": body.clip_norm if body.dp_enabled else 0,
                             "epochs": body.epochs, "learning_rate": body.learning_rate},
                      "hospitals": [p["hospital"] for p in result["participants"]]})
        db.commit()
        run_jobs.append(job)

    # Dev/test: flush the outbox inline so the UI sees confirmed blocks
    # immediately; production relies on the durable worker instead.
    process_outbox(db)
    for job in run_jobs:  # stamp confirmed block indexes for the UI
        db.refresh(job)
    return {
        "disease": body.disease, "rounds_run": len(run_jobs),
        "latest": {"version": run_jobs[-1].round if run_jobs else None,
                   "model_hash": run_jobs[-1].model_hash if run_jobs else None,
                   "metrics": run_jobs[-1].metrics if run_jobs else None,
                   "participants": run_jobs[-1].participants if run_jobs else None,
                   "epsilon": run_jobs[-1].epsilon if run_jobs else None,
                   "cumulative_epsilon": run_jobs[-1].cumulative_epsilon if run_jobs else None,
                   "block_index": run_jobs[-1].block_index if run_jobs else None},
        "jobs": [j.id for j in run_jobs],
    }


class PredictBody(BaseModel):
    disease: str
    features: list[float] = Field(min_length=6, max_length=6)


@router.post("/predict")
def predict(body: PredictBody, user: Users = Depends(get_current_user),
            db: Session = Depends(get_db)) -> dict:
    """Labeled AI-assisted risk estimate from the verified shared model.
    Assistance only — never a diagnosis (PRD §14)."""
    _require_train_role(user)
    if body.disease not in fl_engine.DISEASE_KEYS:
        raise APIError(400, "VALIDATION_ERROR")
    model = load_model(db, body.disease)
    risk = fl_engine.predict_risk(body.disease, model, body.features)
    if risk is None:
        raise APIError(404, "NOT_FOUND", "Model is not trained yet")
    return {"risk": round(risk, 4), "model_version": model["version"],
            "fingerprint": model["fingerprint"],
            "notice": "AI-assisted statistical estimate, not a medical diagnosis."}


@router.get("/hospitals")
def hospital_network(db: Session = Depends(get_db),
                     user: Users = Depends(get_current_user)) -> list:
    """Per-hospital network stats (MedChain-style consortium view).
    Only aggregate summaries - never individual records."""
    conditions = {"heart": "heart", "diabetes": "diabetes", "stroke": "stroke", "kidney": "kidney"}
    out = []
    for h in db.execute(select(Hospitals).order_by(Hospitals.id)).scalars().all():
        profiles = db.execute(
            select(PatientProfiles, Users).join(Users, Users.id == PatientProfiles.user_id)
            .where(Users.hospital_id == h.id)).all()
        n = len(profiles)
        consents = {r.patient_id: r for r in db.execute(select(ResearchConsents)).scalars().all()
                    if r.status == "ACTIVE"}
        consenting = sum(1 for profile, u in profiles if profile.user_id in consents)
        ages, cond = [], {k: 0 for k in conditions}
        for profile, u in profiles:
            attrs = profile.synthetic_attributes or {}
            ages.append(attrs.get("features", {}).get("heart", [u.id % 90, 0, 0, 0, 0, 0])[0])
            for k in conditions:
                if attrs.get("labels", {}).get(k) == 1:
                    cond[k] += 1
        out.append({
            "id": h.id, "code": h.code, "name": h.name, "city": h.city, "type": h.type,
            "active": h.active, "node_address": h.node_address,
            "patients": n, "consented": round(consenting * 100 / n) if n else 0,
            "avg_age": round(sum(ages) / n) if ages else 0,
            "conditions": {k: round(v * 100 / n) if n else 0 for k, v in cond.items()},
        })
    return out


class ResetBody(BaseModel):
    disease: str


@router.post("/reset")
def reset_model(body: ResetBody, user: Users = Depends(get_current_user),
                db: Session = Depends(get_db)) -> dict:
    """Deliberate model reset: version 0, epsilon cleared, RESET ledger event."""
    _require_train_role(user)
    if body.disease not in fl_engine.DISEASE_KEYS:
        raise APIError(400, "VALIDATION_ERROR")
    from ..models.models import ModelVersions as MV
    from ..core.config import settings as s
    import os
    for row in db.execute(select(MV).where(MV.model_id == body.disease)).scalars().all():
        row.status = "SUPERSEDED"
        if row.artifact_reference:
            path = os.path.join(s.STORAGE_ROOT, row.artifact_reference.replace("/", os.sep))
            if os.path.exists(path):
                os.remove(path)
    audit_row = audit(db, actor_id=user.id, role=user.role, event_type="FL_RESET",
                      target_type="MODEL", outcome="SUCCESS",
                      details={"disease": body.disease})
    enqueue(db, event_type="RESET", ref=body.disease, audit_event_id=audit_row.id,
            data={"disease": body.disease, "note": "MODEL_RESET_TO_V0"})
    db.commit()
    process_outbox(db)
    return {"status": "reset", "disease": body.disease}
