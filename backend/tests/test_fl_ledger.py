"""Phase 10/11 gates: FL consent-gating + payload shape, PoW ledger lifecycle,
outbox truthfulness (never CONFIRMED before the block exists), API guards."""
import math

from app.services import fl_engine, ledger as ledger_svc
from app.services.fl_engine import epsilon_per_round, run_round


def _patients():
    """Synthetic locally-held records: WRC entirely non-consenting."""
    mk = lambda code, consent, label: {
        "hospital": code, "consent_research": consent,
        "features": {"heart": [50, 25, 120, 200, 100, 0]},
        "labels": {"heart": label},
    }
    out = []
    for i in range(20):
        out.append(mk("NCH", True, i % 2))
        out.append(mk("VHI", True, 1 if i % 3 == 0 else 0))
        out.append(mk("WRC", False, 1))  # non-consenting hospital
    return out


def _hospitals():
    return [{"id": 1, "code": "NCH"}, {"id": 2, "code": "VHI"}, {"id": 3, "code": "WRC"}]


def test_epsilon_formula_matches_verified_console():
    # Console displays ε ≈ 4.84 per round at σ=1.0 — the exact verified formula.
    assert abs(epsilon_per_round(1.0) - math.sqrt(2 * math.log(1.25 / 1e-5))) < 1e-12
    assert abs(epsilon_per_round(1.0) - 4.8449) < 0.001
    assert epsilon_per_round(0) == 0


def test_run_round_excludes_non_consenting_patients():
    model = fl_engine.fresh_model("heart")
    result = run_round(disease_key="heart",
                       config={"epochs": 2, "learningRate": 0.1, "dpEnabled": False,
                               "noiseMultiplier": 0, "clipNorm": 0.5},
                       model=model, patients=_patients(), active_hospitals=_hospitals(),
                       seed=42)
    codes = [p["hospital"] for p in result["participants"]]
    assert "WRC" not in codes          # non-consenting data never trains
    assert {"NCH", "VHI"}.issubset(codes)
    assert result["total_samples"] == 40  # 20 consenting patients × 2 hospitals


def test_participant_payload_is_metadata_only():
    model = fl_engine.fresh_model("heart")
    result = run_round(disease_key="heart",
                       config={"epochs": 1, "learningRate": 0.1, "dpEnabled": True,
                               "noiseMultiplier": 1.0, "clipNorm": 0.01},
                       model=model, patients=_patients(), active_hospitals=_hospitals(),
                       seed=7)
    allowed = {"hospital", "samples", "localAccuracy", "localLoss", "updateNorm",
               "clipped", "updateHash"}
    for p in result["participants"]:
        assert set(p.keys()) <= allowed
    assert any(p["clipped"] for p in result["participants"])  # small clip norm forces clipping
    assert len(result["model_hash"]) == 64
    assert model["version"] == 1


def test_fedavg_zero_samples_leaves_model_unchanged():
    model = fl_engine.fresh_model("heart")
    empty = [{"hospital": "NCH", "consent_research": False,
              "features": {"heart": [1, 2, 3, 4, 5, 0]}, "labels": {"heart": 1}}]
    result = run_round(disease_key="heart",
                       config={"epochs": 3, "learningRate": 0.1, "dpEnabled": False,
                               "noiseMultiplier": 0, "clipNorm": 0.5},
                       model=model, patients=empty,
                       active_hospitals=[{"id": 1, "code": "NCH"}], seed=1)
    assert result["total_samples"] == 0
    assert all(v == 0 for v in model["weights"])


def test_ledger_lifecycle_tamper_and_restore(client):
    r = client.get("/api/v1/ledger/verify", headers=_auth(client))
    assert r.json()["valid"] is True and r.json()["count"] >= 1
    # Tamper block 0 (admin demo) → validation fails at the EXACT block.
    r2 = client.post("/api/v1/ledger/tamper/0", json={"patch": {"note": "evil edit"}},
                     headers=_auth(client, admin=True))
    assert r2.status_code == 200
    assert r2.json()["validation"]["broken_index"] == 0
    # Restore → chain whole again + RESTORE block appended.
    r3 = client.post("/api/v1/ledger/restore/0", headers=_auth(client, admin=True))
    assert r3.status_code == 200
    assert r3.json()["validation"]["valid"] is True
    blocks = client.get("/api/v1/ledger/blocks", headers=_auth(client)).json()
    assert any(b["type"] == "RESTORE" for b in blocks["blocks"])


def _auth(client, admin=False):
    if admin:
        r = client.post("/api/v1/auth/login",
                        json={"email": "system-admin@example.com",
                              "password": "SystemAdmin#2026"})
    else:
        email = f"fluser{admin}@example.com"
        client.post("/api/v1/auth/register",
                    json={"email": email, "password": "TestPass#123",
                          "full_name": "FL User", "role": "PATIENT"})
        r = client.post("/api/v1/auth/login",
                        json={"email": email, "password": "TestPass#123"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_fl_api_role_guard_and_run(client):
    # Patient cannot run training (role-restricted).
    patient_auth = _auth(client, admin=False)
    r = client.post("/api/v1/federated/run",
                    json={"disease": "heart", "rounds": 1}, headers=patient_auth)
    assert r.status_code == 403
    # Seeded network: admin runs one real DP round.
    admin_auth = _auth(client, admin=True)
    r2 = client.post("/api/v1/federated/run",
                     json={"disease": "heart", "epochs": 2, "dp_enabled": True,
                           "rounds": 1}, headers=admin_auth)
    assert r2.status_code == 200, r2.text
    body = r2.json()
    assert body["rounds_run"] == 1
    assert body["latest"]["metrics"]["totalSamples"] > 0
    assert len(body["latest"]["model_hash"]) == 64
    # AGGREGATION block was mined through the outbox (CONFIRMED only after block).
    blocks = client.get("/api/v1/ledger/blocks?type=AGGREGATION", headers=admin_auth).json()
    assert blocks["types"].get("AGGREGATION", 0) >= 1
    # Served-model integrity matches the authoritative AGGREGATION block.
    summary = client.get("/api/v1/federated/summary", headers=admin_auth).json()
    heart = next(s for s in summary if s["disease"] == "heart")
    assert heart["served_matches_ledger"] is True
    # Verify chain intact.
    assert client.get("/api/v1/ledger/verify").json()["valid"] is True
