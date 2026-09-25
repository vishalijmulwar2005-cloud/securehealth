"""AI analysis engine (TRD v4.1 §15).

The approved provider/model boundary lives here: `analyze_report` is the
deployment plug-in point. The bundled implementation is a deterministic,
offline synthetic-demo analyzer (no external service, no PHI egress) so the
asynchronous workflow, traceability and safety labeling are fully exercised.
Real deployments swap this for the approved provider without touching the
workflow — output is ALWAYS treated as untrusted application data, never a
diagnosis, and the original report is never modified.
"""
import hashlib
import json


def analyze_report(*, report: dict) -> dict:
    """Synthetic placeholder analyzer — deterministic from the report's content
    fingerprint. Returns a structured AI-assisted interpretation artifact.

    report: {mime_type, size, checksum, record_type, title, trace_id}
    """
    seed_material = "|".join([report["checksum"], report["record_type"], report["title"],
                              str(report["size"])])
    digest = hashlib.sha256(seed_material.encode()).hexdigest()

    observations = {
        "BLOOD_REPORT": [
            "Report structure parsed; numeric result panels located.",
            "Reference-range comparison is part of clinician review, not this estimate.",
        ],
        "XRAY": [
            "Imaging document indexed; AI-assisted reading is assistance only.",
            "Quality indicators computed for the reviewing professional.",
        ],
        "SCAN": ["Imaging document indexed; metadata extraction complete."],
        "PRESCRIPTION": ["Prescription document parsed for pharmacy-review support."],
        "GENERAL": ["Document parsed and indexed for assisted review."],
    }.get(report["record_type"], ["Document parsed and indexed for assisted review."])

    metrics = {
        "confidence_index": round(0.62 + (int(digest[:4], 16) % 300) / 1000, 3),  # 0.62–0.92
        "pages_estimated": max(1, report["size"] // 45000),
        "keyfindings_hash": digest[:32],
    }
    summary = (
        f"AI-assisted preliminary reading of '{report['title']}' completed. "
        "Structured observations are ready for review by a qualified healthcare "
        "professional. This estimate is not a medical diagnosis."
    )
    return {
        "summary": summary,
        "observations": observations,
        "metrics": metrics,
        "model": {"id": "securehealth-demo-analyzer", "version": "1.0", "prompt_version": "v1"},
        "disclaimer": "AI-generated information is for assistance and should be reviewed "
                      "by a qualified healthcare professional.",
    }


def result_json_bytes(result: dict) -> bytes:
    return json.dumps(result, indent=2).encode()
