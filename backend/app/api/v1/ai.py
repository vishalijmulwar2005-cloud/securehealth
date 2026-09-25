"""AI analysis API (TRD v4.1 §13/§15; PRD §14).

Same authorization boundary as the source report. Explicit async states;
original report is never modified; results are assistance-only artifacts.
"""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...core.errors import APIError
from ...db.session import get_db
from ...models.models import AiAnalyses, MedicalFiles, MedicalRecords, Reports, Users
from ..deps import get_current_user
from ...services import ai_worker
from ...services.audit import audit
from ...services.authorization import authorize_record_access

router = APIRouter(prefix="/ai", tags=["ai"])


def _report_for(db: Session, report_id: int) -> Reports:
    report = db.get(Reports, report_id)
    if report is None:
        raise APIError(404, "NOT_FOUND")
    return report


@router.post("/analyze/{report_id}", status_code=202)
def request_analysis(report_id: int, user: Users = Depends(get_current_user),
                     db: Session = Depends(get_db)) -> dict:
    report = _report_for(db, report_id)
    # AI access follows the SAME authorization boundary as the source report.
    authorize_record_access(db, user, report.record_id, action="AI_ANALYZE")
    existing = db.execute(select(AiAnalyses).where(
        AiAnalyses.report_id == report_id,
        AiAnalyses.status.in_(["QUEUED", "PROCESSING"]))).scalars().first()
    if existing is not None:
        raise APIError(409, "CONFLICT", "An analysis is already running")
    job = AiAnalyses(report_id=report_id, requested_by=user.id, status="QUEUED",
                     trace_id=uuid.uuid4().hex)
    db.add(job)
    audit(db, actor_id=user.id, role=user.role, event_type="AI_REQUEST",
          target_type="AI_ANALYSIS", target_id=job.id, outcome="SUCCESS")
    db.commit()
    return {"id": job.id, "status": job.status, "trace_id": job.trace_id}


@router.get("/analyses/{analysis_id}")
def get_analysis(analysis_id: int, user: Users = Depends(get_current_user),
                 db: Session = Depends(get_db)) -> dict:
    job = db.get(AiAnalyses, analysis_id)
    if job is None:
        raise APIError(404, "NOT_FOUND")
    report = _report_for(db, job.report_id)
    authorize_record_access(db, user, report.record_id, action="AI_VIEW")
    payload = {
        "id": job.id, "report_id": job.report_id, "status": job.status,
        "model_id": job.model_id, "model_version": job.model_version,
        "prompt_version": job.prompt_version, "trace_id": job.trace_id,
        "failure_category": job.failure_category,
        "created_at": job.created_at.isoformat(),
        "notice": "AI-generated information is for assistance and should be reviewed by a "
                  "qualified healthcare professional. Not a medical diagnosis.",
    }
    if job.status == "COMPLETED" and job.result_reference:
        payload["result"] = ai_worker.load_result(job.id, job.result_reference)
    return payload


@router.get("/by-report/{report_id}")
def analyses_for_report(report_id: int, user: Users = Depends(get_current_user),
                        db: Session = Depends(get_db)) -> list:
    report = _report_for(db, report_id)
    authorize_record_access(db, user, report.record_id, action="AI_VIEW")
    rows = db.execute(select(AiAnalyses).where(
        AiAnalyses.report_id == report_id).order_by(AiAnalyses.id.desc())).scalars().all()
    return [{"id": j.id, "status": j.status, "model_id": j.model_id,
             "model_version": j.model_version, "trace_id": j.trace_id,
             "failure_category": j.failure_category,
             "created_at": j.created_at.isoformat()} for j in rows]
