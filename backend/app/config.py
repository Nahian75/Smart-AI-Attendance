"""Application configuration via pydantic-settings (all thresholds are env-var tunable per PRD §6.3)."""
import os
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

_WEAK_SECRET = "change-me-in-production"
_WEAK_FACE_KEY = "ZmFrZS1mZXJuZXQta2V5LXJlcGxhY2UtaW4tcHJvZHVjdGlvbg=="


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ENVIRONMENT: str = "development"
    SECRET_KEY: str = _WEAK_SECRET
    ACCESS_TOKEN_EXPIRE_HOURS: int = 8

    DATABASE_URL: str = "postgresql+asyncpg://attendance:attendance@localhost:5432/attendance_db"
    REDIS_URL: str = "redis://localhost:6379/0"

    @property
    def allowed_origins_list(self) -> list[str]:
        raw = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost")
        return [o.strip() for o in raw.split(",") if o.strip()]

    # ── Edge node ─────────────────────────────────────────────────────────
    # Shared secret used by edge nodes to authenticate event ingestion.
    # Must be set in production; generate with: openssl rand -hex 32
    EDGE_TOKEN: str = ""

    # ── Recognition thresholds (PRD §6.3 — all tunable per deployment) ──
    CONFIDENCE_THRESHOLD: float = 0.75   # below → unknown (robust balance of accuracy and speed)
    LIVENESS_THRESHOLD: float = 0.80     # PRD §6.3: 0.80
    COOLDOWN_MINUTES: int = 5            # per person per camera

    # ── Alert thresholds ──────────────────────────────────────────────────
    AFTER_HOURS_BUFFER_MIN: int = 30     # minutes outside shift before after-hours alert fires
    LOITERING_THRESHOLD_MIN: int = 10    # minutes near one camera before loitering alert

    # ── Notifications ─────────────────────────────────────────────────────
    SLACK_WEBHOOK_URL: str = ""          # VIP / blacklist Slack channel
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    ALERT_EMAIL_TO: str = ""

    # ── Storage / privacy ─────────────────────────────────────────────────
    SNAPSHOT_DIR: str = "/app/snapshots"
    FACE_ENCRYPTION_KEY: str = _WEAK_FACE_KEY
    EVENT_RETENTION_DAYS: int = 90       # face thumbnail + raw events purged after 90 days

    def validate_production_secrets(self) -> None:
        """Raise immediately on startup if dangerous defaults are used in production."""
        if self.ENVIRONMENT == "production":
            errors = []
            if self.SECRET_KEY == _WEAK_SECRET:
                errors.append("SECRET_KEY is still the default — set it to a random 64-char hex string.")
            if self.FACE_ENCRYPTION_KEY == _WEAK_FACE_KEY:
                errors.append("FACE_ENCRYPTION_KEY is still the default — generate a real Fernet key.")
            if not self.EDGE_TOKEN:
                errors.append("EDGE_TOKEN is empty — set a shared secret for edge-node authentication.")
            if errors:
                raise RuntimeError(
                    "PRODUCTION SECURITY ERROR — fix these before starting:\n" +
                    "\n".join(f"  • {e}" for e in errors)
                )


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.validate_production_secrets()
    return s


settings = get_settings()
