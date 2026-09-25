"""G2 Auth gate: register/login/refresh/expiry-rotation/logout/invalid/suspended.
G10 partial: rate limits, safe error envelope, role-escalation guard."""
from tests.conftest import auth, register_and_login


def test_health(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_register_login_me(client):
    data = register_and_login(client, "alice@example.com")
    assert data["user"]["role"] == "PATIENT"
    assert data["access_token"] and data["refresh_token"]
    r = client.get("/api/v1/auth/me", headers=auth(data["access_token"]))
    assert r.status_code == 200
    assert r.json()["pseudo_id"].startswith("PT-")  # HMAC pseudonym, never plain SHA-256


def test_invalid_credentials_audited_and_safe(client):
    register_and_login(client, "bob@example.com")
    r = client.post("/api/v1/auth/login",
                    json={"email": "bob@example.com", "password": "wrong-pass"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "UNAUTHORIZED"


def test_duplicate_email_conflict(client):
    register_and_login(client, "dupe@example.com")
    r = client.post("/api/v1/auth/register",
                    json={"email": "dupe@example.com", "password": "TestPass#123",
                          "full_name": "Dupe", "role": "PATIENT"})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "CONFLICT"


def test_role_escalation_blocked(client):
    r = client.post("/api/v1/auth/register",
                    json={"email": "evil@example.com", "password": "TestPass#123",
                          "full_name": "Evil", "role": "SYSTEM_ADMIN"})
    assert r.status_code == 403


def test_refresh_rotation_and_replay_rejected(client):
    data = register_and_login(client, "carol@example.com")
    r = client.post("/api/v1/auth/refresh", json={"refresh_token": data["refresh_token"]})
    assert r.status_code == 200
    new_refresh = r.json()["refresh_token"]
    # Replaying the rotated (already-consumed) refresh token must fail.
    r2 = client.post("/api/v1/auth/refresh", json={"refresh_token": data["refresh_token"]})
    assert r2.status_code == 401
    # The new refresh token still works.
    r3 = client.post("/api/v1/auth/refresh", json={"refresh_token": new_refresh})
    assert r3.status_code == 200


def test_logout_revokes_refresh(client):
    data = register_and_login(client, "dave@example.com")
    r = client.post("/api/v1/auth/logout", json={"refresh_token": data["refresh_token"]})
    assert r.status_code == 200
    r2 = client.post("/api/v1/auth/refresh", json={"refresh_token": data["refresh_token"]})
    assert r2.status_code == 401


def test_suspended_account_cannot_authenticate_or_use_tokens(client):
    data = register_and_login(client, "erin@example.com")
    admin = register_and_login(client, "admin@example.com", role="PATIENT")
    # Promote via seeded SYSTEM_ADMIN (dev seed) then suspend erin.
    seed_login = client.post("/api/v1/auth/login",
                             json={"email": "system-admin@example.com",
                                   "password": "SystemAdmin#2026"})
    assert seed_login.status_code == 200
    seed_token = seed_login.json()["access_token"]
    r = client.patch(f"/api/v1/admin/users/{data['user']['id']}/status",
                     json={"status": "SUSPENDED"}, headers=auth(seed_token))
    assert r.status_code == 200
    # Login denied while suspended.
    r2 = client.post("/api/v1/auth/login",
                     json={"email": "erin@example.com", "password": "TestPass#123"})
    assert r2.status_code == 401
    # Existing access token state unusable.
    r3 = client.get("/api/v1/auth/me", headers=auth(data["access_token"]))
    assert r3.status_code == 401
    assert admin["access_token"]


def test_admin_status_change_requires_system_admin(client):
    user = register_and_login(client, "frank@example.com")
    other = register_and_login(client, "gina@example.com")
    r = client.patch(f"/api/v1/admin/users/{other['user']['id']}/status",
                     json={"status": "SUSPENDED"}, headers=auth(user["access_token"]))
    assert r.status_code == 403


def test_auth_rate_limit_429(client):
    seen = []
    for _ in range(12):
        r = client.post("/api/v1/auth/login",
                        json={"email": "nobody@example.com", "password": "x"})
        seen.append(r.status_code)
    assert 429 in seen
    last = client.post("/api/v1/auth/login",
                       json={"email": "nobody@example.com", "password": "x"})
    assert last.status_code == 429
    assert last.json()["error"]["code"] == "RATE_LIMITED"
