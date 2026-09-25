"""Demo network seeding — faithful port of the verified console's seed.js.

ALL data is synthetic (no real PHI anywhere). Deterministic PRNG so the
network is reproducible run to run. Patients are users 1:1 patient_profiles
with synthetic attributes; research consent is the authoritative
research_consents entity (the profile flag is a non-authoritative cache).
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.hashing import gauss, sha256_hex, mulberry32
from ..core.security import patient_pseudo_id
from ..models.models import (
    CareRelationships, DoctorProfiles, MedicalRecords, Reports, Users,
    Hospitals, PatientProfiles, ResearchConsents,
)

SEED = 20260924  # same constant as the verified console

HOSPITALS = [
    {"code": "NCH", "name": "Nagpur Central Hospital", "city": "Nagpur", "type": "Multi-specialty", "patients": 120, "ageMean": 58, "ageSd": 12, "diseaseBias": {"heart": 0.9, "diabetes": 0.2, "stroke": 0.8, "kidney": 0.3}},
    {"code": "VHI", "name": "Vidarbha Heart Institute", "city": "Nagpur", "type": "Cardiac centre", "patients": 90, "ageMean": 55, "ageSd": 11, "diseaseBias": {"heart": 1.6, "diabetes": 0.3, "stroke": 0.2, "kidney": 0.1}},
    {"code": "WRC", "name": "Wardha Rural Clinic", "city": "Wardha", "type": "Primary care", "patients": 50, "ageMean": 34, "ageSd": 10, "diseaseBias": {"heart": -0.5, "diabetes": -0.7, "stroke": -0.8, "kidney": -0.6}},
    {"code": "ACH", "name": "Amravati City Hospital", "city": "Amravati", "type": "District hospital", "patients": 80, "ageMean": 46, "ageSd": 14, "diseaseBias": {"heart": 0.1, "diabetes": 0.4, "stroke": 0.0, "kidney": 0.5}},
]


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def _gen_patient(h, i, rng, codes):
    age = _clamp(round(h["ageMean"] + h["ageSd"] * gauss(rng)), 18, 90)
    bmi = round(22 + 5 * gauss(rng) + (1.5 if age > 55 else 0.0), 1)
    systolicBP = round(_clamp(112 + 0.45 * (age - 30) + 9 * gauss(rng), 90, 210))
    cholesterol = round(_clamp(185 + 22 * gauss(rng) + (bmi - 24) * 2, 120, 320))
    fastingGlucose = round(_clamp(92 + 16 * gauss(rng) + (bmi - 24) * 1.2, 70, 260))
    fastingInsulin = round(8 + 5 * gauss(rng) + max(0, fastingGlucose - 100) * 0.12, 1)
    familyHistory = 1 if rng() < 0.28 else 0
    smoker = 1 if rng() < (0.34 if h["code"] == "VHI" else 0.22) else 0
    hypertension = 1 if (systolicBP >= 140 or rng() < 0.12) else 0
    creatinine = round(0.9 + 0.25 * gauss(rng) + (0.15 if age > 60 else 0.0), 2)
    haemoglobin = round(13.5 + 1.4 * gauss(rng), 1)
    urineACR = round(_clamp(18 + 30 * gauss(rng) + (25 if fastingGlucose > 126 else 0), 5, 400))
    diabetic = 1 if fastingGlucose >= 126 else 0

    B = h["diseaseBias"]
    heartScore = -4.9 + 0.055 * age + 0.05 * bmi + 0.022 * (systolicBP - 120) + 0.009 * (cholesterol - 200) + 0.012 * (fastingGlucose - 100) + 0.9 * smoker + B["heart"] + gauss(rng) * 1.0
    diabScore = -4.5 + 0.03 * age + 0.09 * bmi + 0.035 * (fastingGlucose - 100) + 0.02 * (fastingInsulin - 8) + 0.7 * familyHistory + 0.008 * (systolicBP - 120) + B["diabetes"] + gauss(rng) * 0.7
    strokeScore = -6.4 + 0.07 * age + 1.1 * hypertension + 0.9 * (1 if (1 / (1 + pow(2.718281828459045, -heartScore))) > 0.5 else 0) + 0.01 * (fastingGlucose - 100) + 0.04 * bmi + 0.6 * smoker + B["stroke"] + gauss(rng) * 0.7
    kidneyScore = -4.1 + 0.04 * age + 0.012 * (systolicBP - 120) + 1.4 * (creatinine - 0.9) - 0.25 * (haemoglobin - 13.5) + 0.004 * (urineACR - 18) + 0.8 * diabetic + B["kidney"] + gauss(rng) * 0.7

    def sig(z):
        return 1 / (1 + pow(2.718281828459045, -z))

    research = rng() < 0.85
    shared_with = [h["code"]] + [c for c in codes if c != h["code"] and rng() < 0.4]
    return {
        "features": {
            "heart": [age, bmi, systolicBP, cholesterol, fastingGlucose, smoker],
            "diabetes": [age, bmi, fastingGlucose, fastingInsulin, familyHistory, systolicBP],
            "stroke": [age, hypertension, 1 if sig(heartScore) > 0.5 else 0, fastingGlucose, bmi, smoker],
            "kidney": [age, systolicBP, creatinine, haemoglobin, urineACR, diabetic],
        },
        "labels": {
            "heart": 1 if sig(heartScore) > 0.5 else 0,
            "diabetes": 1 if sig(diabScore) > 0.5 else 0,
            "stroke": 1 if sig(strokeScore) > 0.5 else 0,
            "kidney": 1 if sig(kidneyScore) > 0.5 else 0,
        },
        "research": research,
        "shared_with": shared_with,
    }


DEMO_PASSWORD_HASH = None  # filled lazily via hash_password


def seed_demo_accounts(db: Session) -> None:
    """Ready-to-demo accounts (idempotent): patient, doctor, an ACTIVE care
    relationship between them, and one pre-loaded encrypted report."""
    from sqlalchemy import select as _sel
    from . import files as files_svc
    from .audit import utcnow
    from ..core.security import hash_password

    def get_or_create(email, password, name, role, hospital_id=None, specialty=None):
        row = db.execute(_sel(Users).where(Users.email == email)).scalar_one_or_none()
        if row is not None:
            return row
        row = Users(email=email, password_hash=hash_password(password),
                    full_name=name, role=role, status="ACTIVE",
                    hospital_id=hospital_id)
        db.add(row)
        db.flush()
        if role == "PATIENT":
            db.add(PatientProfiles(user_id=row.id, pseudo_id=patient_pseudo_id(row.id)))
        elif role == "DOCTOR":
            db.add(DoctorProfiles(user_id=row.id, hospital_id=hospital_id,
                                  specialty=specialty))
        return row

    patient = get_or_create("patient@demo.com", "Demo@123", "Demo Patient (Asha)", "PATIENT")
    doctor = get_or_create("doctor@demo.com", "Demo@123", "Dr. Demo (R. Verma)",
                           "DOCTOR", specialty="General Medicine")

    rel = db.execute(_sel(CareRelationships).where(
        CareRelationships.patient_id == patient.id,
        CareRelationships.doctor_id == doctor.id)).scalar_one_or_none()
    if rel is None:
        db.add(CareRelationships(patient_id=patient.id, doctor_id=doctor.id,
                                 relationship_type="PRIMARY_CARE", status="ACTIVE"))

    record = db.execute(_sel(MedicalRecords).where(
        MedicalRecords.patient_id == patient.id,
        MedicalRecords.title == "Demo Blood Panel (pre-loaded)")).scalar_one_or_none()
    if record is None:
        record = MedicalRecords(patient_id=patient.id, record_type="BLOOD_REPORT",
                                title="Demo Blood Panel (pre-loaded)", status="ACTIVE")
        db.add(record)
        db.flush()
        nl = bytes([10])  # newline without escape-sequence nesting
        pdf = (b"%PDF-1.4" + nl
               + b"1 0 obj<</Type/Catalog>>endobj" + nl
               + b"2 0 obj<</Type/Page/Parent 3 0 R>>endobj" + nl
               + b"3 0 obj<</Type/Pages/Kids[2 0 R]/Count 1>>endobj" + nl
               + b"trailer<</Root 1 0 R>>" + nl
               + b"%%EOF" + nl
               + b"Demo report content. " * 40)
        files_svc.store_upload(db, record_id=record.id, filename="demo-report.pdf",
                               content_type="application/pdf", data=pdf)
        db.add(Reports(record_id=record.id, file_id=None, title="demo-report.pdf",
                       type="BLOOD_REPORT", status="ACTIVE"))
    db.commit()


def seed_network(db: Session) -> int:
    """Seed hospitals + synthetic patients + research consents. Idempotent:
    returns the hospital row-count already present (0 => seeded now)."""
    exists = db.execute(select(Hospitals.id).limit(1)).scalar_one_or_none()
    if exists is not None:
        return 1
    rng = mulberry32(SEED)
    codes = [h["code"] for h in HOSPITALS]
    hospital_rows = {}
    for h in HOSPITALS:  # pass 1: all hospitals first (shared_with may reference any)
        row = Hospitals(code=h["code"], name=h["name"], city=h["city"], type=h["type"],
                        active=True, node_address="0x" + sha256_hex("node:" + h["code"])[:12])
        db.add(row)
        db.flush()
        hospital_rows[h["code"]] = row
    for h in HOSPITALS:  # pass 2: patients + consents
        row = hospital_rows[h["code"]]

        for i in range(h["patients"]):
            p = _gen_patient(h, i, rng, codes)
            email_hash = sha256_hex(f"{h['code']}:{i}")[:16]
            email = f"pt-{email_hash}@patients.synthetic"
            user = Users(email=email, password_hash="!",
                         full_name=f"Synthetic patient {h['code']}-{i}",
                         role="PATIENT", status="ACTIVE", hospital_id=row.id)
            db.add(user)
            db.flush()
            db.add(PatientProfiles(
                user_id=user.id, pseudo_id=patient_pseudo_id(user.id),
                synthetic_attributes={"features": p["features"], "labels": p["labels"],
                                      "shared_with": p["shared_with"],
                                      "hospital": h["code"], "hospital_index": i},
                research_consent_cache=p["research"],
            ))
            if p["research"]:
                db.add(ResearchConsents(
                    patient_id=user.id, status="ACTIVE", scope="LOCAL_FL",
                    allowed_organizations=[hospital_rows[c].id for c in p["shared_with"]
                                           if c != h["code"]],
                ))
    db.commit()
    return 0
