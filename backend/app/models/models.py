"""Canonical database schema — full entity inventory per TRD v4.1 §11 and
Security & Database v4.1 §13. Every persistent entity has a stable primary key;
foreign keys enforce referential integrity; identity fields are UNIQUE.

Notes:
- `research_consents` is the authoritative research-consent state. The
  `research_consent_cache` flag on patient_profiles is explicitly
  NON-authoritative (derived cache only).
- `medical_files` records key_id/key_version so key rotation never makes old
  files undecryptable (Security & Database §7).
- ledger column names use block_index/block_hash ("index"/"hash" are reserved
  words; documented rename, same canonical fields).
- `auth_sessions` is the added entity required for explicit refresh-token
  revocation/rotation (master prompt §4: add missing entities that make the
  authorization model explicit).
"""
import datetime as dt

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index,
    Integer, JSON, String, Text, UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..core.security import (
    ROLE_DOCTOR, ROLE_HOSPITAL_ADMIN, ROLE_PATIENT, ROLE_REGULATOR, ROLE_SYSTEM_ADMIN,
)
from ..db.base import Base

ROLES = (ROLE_PATIENT, ROLE_DOCTOR, ROLE_HOSPITAL_ADMIN, ROLE_SYSTEM_ADMIN, ROLE_REGULATOR)
ACCOUNT_STATUSES = ("PENDING", "ACTIVE", "SUSPENDED", "DISABLED", "DELETED")
PERMISSION_STATUSES = ("PENDING", "ACTIVE", "REJECTED", "EXPIRED", "REVOKED", "CANCELLED")
RESEARCH_CONSENT_STATUSES = ("ACTIVE", "REVOKED", "EXPIRED")
RECORD_STATUSES = ("ACTIVE", "ARCHIVED", "DELETED")
ALLOWED_PERMISSION_DURATIONS = (7, 30, 90)  # Security & Database §11 / PRD §8


def _timestamps() -> tuple[Mapped[dt.datetime], Mapped[dt.datetime]]:
    return (
        mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False),
        mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
                      nullable=False),
    )


class Users(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE", nullable=False)
    hospital_id: Mapped[int | None] = mapped_column(ForeignKey("hospitals.id"), nullable=True)
    created_at: Mapped[dt.datetime] = _timestamps()[0]
    updated_at: Mapped[dt.datetime] = _timestamps()[1]
    __table_args__ = (
        CheckConstraint(f"role IN {ROLES}", name="valid_role"),
        CheckConstraint(f"status IN {ACCOUNT_STATUSES}", name="valid_status"),
        Index("ix_users_role_status", "role", "status"),
        Index("ix_users_hospital", "hospital_id"),
    )


class Hospitals(Base):
    __tablename__ = "hospitals"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    city: Mapped[str | None] = mapped_column(String(128))
    type: Mapped[str | None] = mapped_column(String(64))
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    node_address: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[dt.datetime] = _timestamps()[0]
    updated_at: Mapped[dt.datetime] = _timestamps()[1]


class PatientProfiles(Base):
    __tablename__ = "patient_profiles"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, nullable=False)
    pseudo_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    synthetic_attributes: Mapped[dict | None] = mapped_column(JSON)
    # NON-authoritative derived cache of research_consents (TRD §11); the
    # authoritative state is the research_consents table.
    research_consent_cache: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[dt.datetime] = _timestamps()[0]
    updated_at: Mapped[dt.datetime] = _timestamps()[1]


class DoctorProfiles(Base):
    __tablename__ = "doctor_profiles"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, nullable=False)
    hospital_id: Mapped[int | None] = mapped_column(ForeignKey("hospitals.id"))
    specialty: Mapped[str | None] = mapped_column(String(128))
    license_number: Mapped[str | None] = mapped_column(String(64))


class CareRelationships(Base):
    """Doctor-patient institutional relationship (master prompt §5).

    A doctor role alone NEVER grants access; where policy requires it, doctor
    access verifies the current ACTIVE relationship row.
    """
    __tablename__ = "care_relationships"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    hospital_id: Mapped[int | None] = mapped_column(ForeignKey("hospitals.id"))
    relationship_type: Mapped[str] = mapped_column(String(64), default="PRIMARY_CARE",
                                                    nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE", nullable=False)
    start_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True),
                                                  server_default=func.now(), nullable=False)
    end_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[dt.datetime] = _timestamps()[0]
    ended_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE','ENDED','CANCELLED')", name="valid_status"),
        Index("ix_care_relationships_patient_doctor_status", "patient_id", "doctor_id", "status"),
    )


class MedicalRecords(Base):
    __tablename__ = "medical_records"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    record_type: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE", nullable=False)
    created_at: Mapped[dt.datetime] = _timestamps()[0]
    updated_at: Mapped[dt.datetime] = _timestamps()[1]
    __table_args__ = (
        CheckConstraint(f"status IN {RECORD_STATUSES}", name="valid_status"),
        Index("ix_medical_records_patient_status_time", "patient_id", "status", "created_at"),
    )


class MedicalFiles(Base):
    __tablename__ = "medical_files"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    record_id: Mapped[int] = mapped_column(ForeignKey("medical_records.id"), nullable=False)
    storage_reference: Mapped[str] = mapped_column(String(512), nullable=False)  # server key, never public
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)  # SHA-256 of plaintext
    original_name: Mapped[str | None] = mapped_column(String(255))  # display only, never used for paths
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    key_id: Mapped[str] = mapped_column(String(64), nullable=False)  # encryption metadata (Security & DB §7)
    key_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[dt.datetime] = _timestamps()[0]
    updated_at: Mapped[dt.datetime] = _timestamps()[1]
    __table_args__ = (Index("ix_medical_files_checksum", "checksum"),)


class Reports(Base):
    __tablename__ = "reports"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    record_id: Mapped[int] = mapped_column(ForeignKey("medical_records.id"), nullable=False)
    file_id: Mapped[int | None] = mapped_column(ForeignKey("medical_files.id"))
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE", nullable=False)
    created_at: Mapped[dt.datetime] = _timestamps()[0]
    updated_at: Mapped[dt.datetime] = _timestamps()[1]
    __table_args__ = (Index("ix_reports_record_status", "record_id", "status"),)


class Permissions(Base):
    """Canonical access grant. State machine (TRD §9):
    PENDING -> ACTIVE -> REVOKED/EXPIRED; PENDING -> REJECTED; optional CANCELLED.
    PENDING never grants access; revocation/expiry block the next retrieval.
    """
    __tablename__ = "permissions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    recipient_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)  # e.g. RECORD_CONTAINER
    resource_id: Mapped[int | None] = mapped_column(Integer)  # NULL = patient-scoped grant
    permission_type: Mapped[str] = mapped_column(String(64), nullable=False)  # e.g. VIEW, VIEW_DOWNLOAD
    status: Mapped[str] = mapped_column(String(32), default="PENDING", nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    audit_ref: Mapped[str | None] = mapped_column(String(64))
    granted_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    rejected_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    start_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[dt.datetime] = _timestamps()[0]
    updated_at: Mapped[dt.datetime] = _timestamps()[1]
    __table_args__ = (
        CheckConstraint(f"status IN {PERMISSION_STATUSES}", name="valid_status"),
        # A permission must never be ACTIVE and REVOKED simultaneously (PRD §8.3)
        CheckConstraint("NOT (status = 'ACTIVE' AND revoked_at IS NOT NULL)", name="active_implies_not_revoked"),
        Index("ix_permissions_authz", "patient_id", "recipient_user_id", "resource_type",
              "resource_id", "status"),
    )


class ConsentRequests(Base):
    __tablename__ = "consent_requests"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    requester_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[int | None] = mapped_column(Integer)
    scope: Mapped[str] = mapped_column(String(64), nullable=False)
    purpose: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="PENDING", nullable=False)
    created_at: Mapped[dt.datetime] = _timestamps()[0]
    updated_at: Mapped[dt.datetime] = _timestamps()[1]
    __table_args__ = (
        CheckConstraint("status IN ('PENDING','APPROVED','REJECTED','CANCELLED')",
                        name="valid_status"),
        Index("ix_consent_requests_patient_status", "patient_id", "status"),
    )


class PermissionTargets(Base):
    __tablename__ = "permission_targets"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    permission_id: Mapped[int] = mapped_column(ForeignKey("permissions.id"), nullable=False)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)  # USER | ORGANIZATION
    target_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    organization_id: Mapped[int | None] = mapped_column(ForeignKey("hospitals.id"))
    __table_args__ = (
        CheckConstraint("(target_user_id IS NOT NULL) <> (organization_id IS NOT NULL)",
                        name="valid_target"),
    )


class ResearchConsents(Base):
    """Authoritative research-consent state; gates local FL participation."""
    __tablename__ = "research_consents"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    scope: Mapped[str | None] = mapped_column(String(255))
    allowed_organizations: Mapped[list | None] = mapped_column(JSON)
    start_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[dt.datetime] = _timestamps()[0]
    updated_at: Mapped[dt.datetime] = _timestamps()[1]
    __table_args__ = (
        CheckConstraint(f"status IN {RESEARCH_CONSENT_STATUSES}", name="valid_status"),
        Index("ix_research_consents_patient_status", "patient_id", "status"),
    )


class Prescriptions(Base):
    __tablename__ = "prescriptions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    record_id: Mapped[int | None] = mapped_column(ForeignKey("medical_records.id"))
    medication: Mapped[str] = mapped_column(String(255), nullable=False)
    dosage: Mapped[str | None] = mapped_column(String(128))
    instructions: Mapped[str | None] = mapped_column(Text)
    issued_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True),
                                                   server_default=func.now(), nullable=False)
    # Synthetic/demo prescriptions are not legally valid electronic prescriptions
    # (TRD §13 note); a compliant e-prescribing capability is future scope.


class AiAnalyses(Base):
    __tablename__ = "ai_analyses"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("reports.id"), nullable=False)
    requested_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="QUEUED", nullable=False)
    model_id: Mapped[str | None] = mapped_column(String(128))
    model_version: Mapped[str | None] = mapped_column(String(64))
    prompt_version: Mapped[str | None] = mapped_column(String(64))
    result_reference: Mapped[str | None] = mapped_column(String(512))
    trace_id: Mapped[str | None] = mapped_column(String(64))
    failure_category: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[dt.datetime] = _timestamps()[0]
    updated_at: Mapped[dt.datetime] = _timestamps()[1]
    __table_args__ = (
        CheckConstraint("status IN ('QUEUED','PROCESSING','COMPLETED','FAILED','TIMEOUT','CANCELLED')",
                        name="valid_status"),
        Index("ix_ai_analyses_report_status", "report_id", "status"),
    )


class Notifications(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str | None] = mapped_column(Text)
    read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    read_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[dt.datetime] = _timestamps()[0]
    __table_args__ = (Index("ix_notifications_user_read_time", "user_id", "read", "created_at"),)


class AccessLogs(Base):
    __tablename__ = "access_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(Integer)
    role: Mapped[str | None] = mapped_column(String(32))
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(64))
    resource_id: Mapped[int | None] = mapped_column(Integer)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)  # GRANTED | DENIED
    details: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True),
                                                    server_default=func.now(), nullable=False)
    block_ref: Mapped[str | None] = mapped_column(String(128))
    __table_args__ = (Index("ix_access_logs_actor_action_time", "actor_id", "action", "created_at"),
                       Index("ix_access_logs_resource", "resource_type", "resource_id"))


class AuditLogs(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(Integer)
    role: Mapped[str | None] = mapped_column(String(32))
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(64))
    target_id: Mapped[int | None] = mapped_column(Integer)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    details: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True),
                                                    server_default=func.now(), nullable=False)
    block_ref: Mapped[str | None] = mapped_column(String(128))
    __table_args__ = (Index("ix_audit_logs_event_time", "event_type", "created_at"),)


class LedgerBlocks(Base):
    __tablename__ = "ledger_blocks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    block_index: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    timestamp: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True),
                                                   server_default=func.now(), nullable=False)
    # Exact mining timestamp (ms) used in the canonical hash — DateTime storage
    # round-trips imprecisely across dialects, so the hash reuses this integer.
    timestamp_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    data_json: Mapped[dict | None] = mapped_column(JSON)  # metadata/fingerprints only, never clinical values
    previous_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    nonce: Mapped[int] = mapped_column(BigInteger, nullable=False)
    block_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)


class BlockchainEvents(Base):
    __tablename__ = "blockchain_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    audit_event_id: Mapped[int | None] = mapped_column(Integer)
    block_id: Mapped[int | None] = mapped_column(ForeignKey("ledger_blocks.id"))
    tx_reference: Mapped[str | None] = mapped_column(String(128))
    # Outbox payload: metadata-only event data (fingerprints/decisions/refs),
    # committed with the domain transaction and mined by the ledger worker.
    data_json: Mapped[dict | None] = mapped_column(JSON)
    state: Mapped[str] = mapped_column(String(32), nullable=False)  # QUEUED/SUBMITTED/PENDING/CONFIRMED/FAILED/TIMEOUT/UNKNOWN
    created_at: Mapped[dt.datetime] = _timestamps()[0]
    updated_at: Mapped[dt.datetime] = _timestamps()[1]
    __table_args__ = (Index("ix_blockchain_events_state", "state"),)


class FederatedJobs(Base):
    __tablename__ = "federated_jobs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    disease_model: Mapped[str | None] = mapped_column(String(64))
    round: Mapped[int | None] = mapped_column(Integer)
    config: Mapped[dict | None] = mapped_column(JSON)
    participants: Mapped[list | None] = mapped_column(JSON)
    metrics: Mapped[dict | None] = mapped_column(JSON)
    epsilon: Mapped[float | None] = mapped_column(Float)
    cumulative_epsilon: Mapped[float | None] = mapped_column(Float)
    model_hash: Mapped[str | None] = mapped_column(String(64))
    block_index: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), default="QUEUED", nullable=False)
    created_at: Mapped[dt.datetime] = _timestamps()[0]
    updated_at: Mapped[dt.datetime] = _timestamps()[1]
    __table_args__ = (Index("ix_federated_jobs_status_round", "status", "round"),)


class ModelUpdates(Base):
    __tablename__ = "model_updates"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    federated_job_id: Mapped[int] = mapped_column(ForeignKey("federated_jobs.id"), nullable=False)
    hospital_id: Mapped[int | None] = mapped_column(ForeignKey("hospitals.id"))
    version: Mapped[str | None] = mapped_column(String(64))
    update_hash: Mapped[str | None] = mapped_column(String(64))
    samples_count: Mapped[int | None] = mapped_column(Integer)
    clip_norm: Mapped[float | None] = mapped_column(Float)
    noise_sigma: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(32), default="PENDING", nullable=False)
    created_at: Mapped[dt.datetime] = _timestamps()[0]
    updated_at: Mapped[dt.datetime] = _timestamps()[1]
    __table_args__ = (Index("ix_model_updates_job_status", "federated_job_id", "status"),)


class ModelVersions(Base):
    __tablename__ = "model_versions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    model_id: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    artifact_reference: Mapped[str | None] = mapped_column(String(512))
    fingerprint: Mapped[str | None] = mapped_column(String(64))  # SHA-256; unique/indexed where authoritative
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE", nullable=False)
    created_at: Mapped[dt.datetime] = _timestamps()[0]
    __table_args__ = (UniqueConstraint("model_id", "version", name="uq_model_versions_model_version"),)


class AuthSessions(Base):
    """Added entity (master prompt §4) for explicit refresh-token
    revocation/rotation: logout invalidates the session jti."""
    __tablename__ = "auth_sessions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    jti: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    token_type: Mapped[str] = mapped_column(String(16), nullable=False)  # access | refresh
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[dt.datetime] = _timestamps()[0]
    __table_args__ = (Index("ix_auth_sessions_user_type", "user_id", "token_type"),)
