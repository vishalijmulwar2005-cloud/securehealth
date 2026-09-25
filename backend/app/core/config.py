"""SecureHealth care-platform settings (TRD v4.1 §4).

Environment/secret configuration only — never hardcoded production secrets.
Production guards live in main.create_app(): no SQLite/in-memory fallback,
no disabled security scanning, no default JWT secret.
"""
import base64
import json
import os

# Dev/test-only default Fernet key. Production MUST supply SECUREHEALTH_FILE_KEYS.
_DEV_FERNET_KEY = base64.urlsafe_b64encode(b"0" * 32).decode()


def _parse_file_keys(raw: str) -> dict:
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict) and parsed:
            return parsed
    except (ValueError, TypeError):
        pass
    return {"dev-1": _DEV_FERNET_KEY}


class Settings:
    def __init__(self) -> None:
        self.ENV = os.getenv("SECUREHEALTH_ENV", "development")

        # PostgreSQL is the canonical target (TRD §4); SQLite is a documented
        # dev/test convenience only and is refused in production (main.py guard).
        self.DATABASE_URL = os.getenv(
            "SECUREHEALTH_DATABASE_URL", "sqlite:///./dev.db"
        )

        self.JWT_SECRET = os.getenv("SECUREHEALTH_JWT_SECRET", "dev-only-insecure-secret")
        self.JWT_ALGORITHM = "HS256"  # Security & Database §3 baseline
        self.ACCESS_TOKEN_MINUTES = int(os.getenv("SECUREHEALTH_ACCESS_TOKEN_MINUTES", "30"))
        self.REFRESH_TOKEN_DAYS = int(os.getenv("SECUREHEALTH_REFRESH_TOKEN_DAYS", "7"))

        # key_id -> Fernet key; rotation keeps old files decryptable (Security & DB §7)
        self.FILE_KEYS = _parse_file_keys(os.getenv("SECUREHEALTH_FILE_KEYS", ""))
        self.ACTIVE_FILE_KEY_ID = os.getenv("SECUREHEALTH_ACTIVE_FILE_KEY_ID", "dev-1")

        # Protected bytes live outside any public/web root (Security & DB §8)
        self.STORAGE_ROOT = os.getenv("SECUREHEALTH_STORAGE_ROOT", "./data/protected_storage")
        self.QUARANTINE_ROOT = os.getenv("SECUREHEALTH_QUARANTINE_ROOT", "./data/quarantine")

        # Malware/security scanning is REQUIRED in production (Security & DB §8).
        # Modes: stub (dev/test placeholder) | clamav (deployment hook) | disabled
        # (dev-only bypass; refused in production).
        self.SECURITY_SCAN_MODE = os.getenv("SECUREHEALTH_SECURITY_SCAN_MODE", "stub")
        self.SECURITY_SCAN_FAIL = os.getenv("SECUREHEALTH_SECURITY_SCAN_FAIL", "")  # test hook

        self.MAX_FILE_SIZE_BYTES = int(os.getenv("SECUREHEALTH_MAX_FILE_SIZE", str(25 * 1024 * 1024)))

        # HMAC-SHA-256 server-side secret for pseudonymous patient IDs (Security & DB §7)
        self.PSEUDO_SECRET = os.getenv("SECUREHEALTH_PSEUDO_SECRET", "dev-only-pseudo-secret")

        # Sliding-window limits (TRD §7): auth 10/min/IP, general 120/min
        self.RATE_LIMIT_AUTH_PER_MIN = int(os.getenv("SECUREHEALTH_RATE_LIMIT_AUTH", "10"))
        self.RATE_LIMIT_GENERAL_PER_MIN = int(os.getenv("SECUREHEALTH_RATE_LIMIT_GENERAL", "120"))

        # CORS production allowlist (TRD §14)
        self.CORS_ORIGINS = [
            o for o in os.getenv("SECUREHEALTH_CORS_ORIGINS", "http://localhost:3000").split(",") if o
        ]

        self.REQUIRE_CARE_RELATIONSHIP = os.getenv(
            "SECUREHEALTH_REQUIRE_CARE_RELATIONSHIP", "1"
        ) not in ("0", "false", "False")

    @property
    def is_production(self) -> bool:
        return self.ENV == "production"


settings = Settings()
