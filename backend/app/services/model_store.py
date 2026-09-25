"""Model artifact persistence: weights + scaler per model version.

artifact_reference points to a JSON file under the protected storage root —
the artifact is loaded for continued training and for labeled risk estimation.
"""
import json
import os

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.config import settings
from ..models.models import ModelVersions
from .fl_engine import fresh_model

STATUS_ACTIVE = "ACTIVE"
STATUS_SUPERSEDED = "SUPERSEDED"


def _artifact_path(disease: str, version: int) -> str:
    rel = os.path.join("model_artifacts", disease, f"v{version}.json")
    return os.path.join(settings.STORAGE_ROOT, rel)


def save_artifact(db: Session, *, disease: str, model: dict) -> ModelVersions:
    """Persist new version: supersede previous rows, write artifact file, add row."""
    prev = db.execute(select(ModelVersions).where(
        ModelVersions.model_id == disease,
        ModelVersions.version == model["version"] - 1)).scalar_one_or_none()
    if prev is not None and prev.status == STATUS_ACTIVE:
        prev.status = STATUS_SUPERSEDED
    path = _artifact_path(disease, model["version"])
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"weights": model["weights"], "scaler": model.get("scaler"),
                   "version": model["version"],
                   "cumulative_epsilon": model["cumulative_epsilon"],
                   "fingerprint": model["fingerprint"]}, fh)
    rel_ref = os.path.relpath(path, settings.STORAGE_ROOT).replace(os.sep, "/")
    row = ModelVersions(model_id=disease, version=model["version"],
                        artifact_reference=rel_ref, fingerprint=model["fingerprint"],
                        status=STATUS_ACTIVE)
    db.add(row)
    db.flush()
    return row


def load_model(db: Session, disease: str) -> dict:
    """Load the latest ACTIVE version (or a fresh model when never trained)."""
    row = db.execute(select(ModelVersions).where(
        ModelVersions.model_id == disease,
        ModelVersions.status == STATUS_ACTIVE).order_by(
        ModelVersions.version.desc())).scalars().first()
    if row is None or row.artifact_reference is None:
        return fresh_model(disease)
    path = os.path.join(settings.STORAGE_ROOT, row.artifact_reference.replace("/", os.sep))
    with open(path, encoding="utf-8") as fh:
        art = json.load(fh)
    return {"weights": art["weights"], "version": art["version"],
            "cumulative_epsilon": art.get("cumulative_epsilon", 0.0),
            "fingerprint": art.get("fingerprint"), "prev_fingerprint": None,
            "scaler": art.get("scaler")}
