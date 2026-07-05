"""
AuraFlow — Application Configuration
All config comes from environment variables. Never hardcode values.
"""
from functools import lru_cache
from typing import List, Optional
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env.local",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── App ───────────────────────────────────────────────────────────
    APP_VERSION: str = "0.1.0"
    APP_SECRET: str
    ENVIRONMENT: str = "development"
    PLATFORM_NAME: str = "AuraFlow"
    PLATFORM_DOMAIN: str = "auraflow.fit"
    APP_URL: str = "https://app.auraflow.fit"
    API_URL: str = "https://api.auraflow.fit"

    # ── CORS & Hosts ──────────────────────────────────────────────────
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "https://app.auraflow.fit",
        "https://auraflow.fit",
    ]
    ALLOWED_HOSTS: List[str] = ["api.auraflow.fit", "auraflow.fit", "localhost", "127.0.0.1", "auraflow_api"]

    # ── Database ──────────────────────────────────────────────────────
    DATABASE_URL: str
    DATABASE_POOL_SIZE: int = 40
    DATABASE_MAX_OVERFLOW: int = 40

    # ── Redis ─────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_CACHE_TTL: int = 300
    FEATURE_FLAGS_CACHE_TTL: int = 300

    # ── JWT Auth ──────────────────────────────────────────────────────
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30  # 30 min — refresh-token rotation extends sessions
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    SESSION_IDLE_TIMEOUT_MINUTES: int = 30


    # ── Stripe ────────────────────────────────────────────────────────
    STRIPE_PUBLISHABLE_KEY: Optional[str] = None
    STRIPE_SECRET_KEY: Optional[str] = None
    STRIPE_WEBHOOK_SECRET: Optional[str] = None
    STRIPE_CONNECT_CLIENT_ID: Optional[str] = None
    STRIPE_PLATFORM_FEE_PERCENT: float = 1.25

    # ── SendGrid ──────────────────────────────────────────────────────
    SENDGRID_API_KEY: Optional[str] = None
    SENDGRID_FROM_EMAIL: str = "hello@example.com"
    SENDGRID_FROM_NAME: str = "AuraFlow"

    # ── Mux ───────────────────────────────────────────────────────────
    MUX_TOKEN_ID: Optional[str] = None
    MUX_TOKEN_SECRET: Optional[str] = None
    MUX_WEBHOOK_SECRET: Optional[str] = None

    # ── Anthropic ─────────────────────────────────────────────────────
    ANTHROPIC_API_KEY: Optional[str] = None
    ANTHROPIC_MODEL: str = "claude-sonnet-4-6"
    ANTHROPIC_MODEL_FAST: str = "claude-haiku-4-5-20251001"
    ANTHROPIC_MAX_TOKENS: int = 4096

    # ── HeyGen / D-ID (Milestone Videos) ────────────────────────────────
    HEYGEN_API_KEY: Optional[str] = None
    DID_API_KEY: Optional[str] = None
    HEYGEN_AVATAR_ID: str = "default"

    # ── Backblaze B2 ──────────────────────────────────────────────────
    B2_ACCOUNT_ID: Optional[str] = None
    B2_APPLICATION_KEY: Optional[str] = None
    B2_BUCKET_BACKUPS: str = "auraflow-backups"
    B2_BUCKET_ASSETS: str = "auraflow-assets"
    B2_ENDPOINT: str = "https://s3.us-west-002.backblazeb2.com"

    # ── OpenAI (Whisper STT) ──────────────────────────────────────────
    OPENAI_API_KEY: Optional[str] = None

    # ── Twilio ────────────────────────────────────────────────────────
    TWILIO_ACCOUNT_SID: Optional[str] = None
    TWILIO_AUTH_TOKEN: Optional[str] = None
    TWILIO_PHONE_NUMBER: Optional[str] = None

    # ── Google OAuth (YouTube uploads + Google Ads) ────────────────────
    GOOGLE_CLIENT_ID: Optional[str] = None
    GOOGLE_CLIENT_SECRET: Optional[str] = None

    # ── Google Ads ────────────────────────────────────────────────────
    GOOGLE_ADS_DEVELOPER_TOKEN: Optional[str] = None
    GOOGLE_ADS_LOGIN_CUSTOMER_ID: Optional[str] = None

    # ── Meta/Facebook Ads ───────────────────────────────────────────
    META_APP_ID: Optional[str] = None
    META_APP_SECRET: Optional[str] = None

    # ── Zoom ──────────────────────────────────────────────────────────
    ZOOM_ACCOUNT_ID: Optional[str] = None
    ZOOM_CLIENT_ID: Optional[str] = None
    ZOOM_CLIENT_SECRET: Optional[str] = None
    ZOOM_WEBHOOK_SECRET: Optional[str] = None

    # ── Gusto Payroll ─────────────────────────────────────────────────
    GUSTO_CLIENT_ID: Optional[str] = None
    GUSTO_CLIENT_SECRET: Optional[str] = None
    GUSTO_REDIRECT_URI: Optional[str] = None

    # ── QuickBooks Payroll ────────────────────────────────────────────
    QB_CLIENT_ID: Optional[str] = None
    QB_CLIENT_SECRET: Optional[str] = None
    QB_REDIRECT_URI: Optional[str] = None
    QB_ENVIRONMENT: str = "sandbox"

    # ── Square ─────────────────────────────────────────────────────────
    # Legacy single-account fields (kept for backward compat with the
    # current one-off card-charge endpoint). The dual-run migration to
    # OAuth-connected merchant accounts uses the OAUTH-prefixed fields
    # below instead.
    SQUARE_ACCESS_TOKEN: Optional[str] = None
    SQUARE_APPLICATION_ID: Optional[str] = None
    SQUARE_LOCATION_ID: Optional[str] = None
    SQUARE_ENVIRONMENT: str = "sandbox"  # sandbox | production
    # KinovaAI's OWN Square account — receives 1% app_fee on every
    # studio's member-side payment AND hosts the KinovaAI studio
    # platform subscriptions ($99/mo + token overage invoices).
    SQUARE_PLATFORM_ACCESS_TOKEN: Optional[str] = None
    SQUARE_PLATFORM_LOCATION_ID: Optional[str] = None
    # OAuth platform credentials — studios connect their own Square
    # accounts via the Code Flow. Secret + webhook signature key are
    # encrypted at rest using APP_SECRET (see app.core.encryption).
    SQUARE_OAUTH_APPLICATION_ID: Optional[str] = None
    SQUARE_OAUTH_APPLICATION_SECRET: Optional[str] = None
    SQUARE_OAUTH_REDIRECT_URI: Optional[str] = None
    SQUARE_WEBHOOK_SIGNATURE_KEY: Optional[str] = None
    SQUARE_WEBHOOK_NOTIFICATION_URL: Optional[str] = None  # full URL Square POSTs to

    # ── Sentry ────────────────────────────────────────────────────────
    SENTRY_DSN_API: Optional[str] = None
    SENTRY_ENVIRONMENT: str = "development"
    SENTRY_TRACES_SAMPLE_RATE: float = 0.1

    # ── Health Data Encryption ──────────────────────────────────────────
    HEALTH_DATA_ENCRYPTION_KEY: Optional[str] = None  # Fernet key (base64-encoded 32 bytes)

    # ── Backup ────────────────────────────────────────────────────────
    BACKUP_TIMEOUT_SECONDS: int = 1800  # 30 minutes default for pg_dump

    # ── Platform Admin Alerts ───────────────────────────────────────────
    PLATFORM_ADMIN_ALERT_EMAIL: str = "alerts@example.com"
    SUPPORT_ESCALATION_EMAIL: str = "alerts@example.com"
    SENDGRID_INBOUND_WEBHOOK_SECRET: Optional[str] = None
    BACKUP_ENCRYPTION_KEY: Optional[str] = None

    # ── Meta Page Access ─────────────────────────────────────────────
    META_PAGE_ACCESS_TOKEN: Optional[str] = None
    META_PAGE_ID: Optional[str] = None
    INSTAGRAM_BUSINESS_ACCOUNT_ID: Optional[str] = None

    # ── SMTP Fallback (Purelymail) ──────────────────────────────────
    SMTP_HOST: str = "smtp.purelymail.com"
    SMTP_PORT: int = 465
    SMTP_USE_TLS: bool = True
    SMTP_USERNAME: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_FROM_EMAIL: str = "alerts@example.com"
    SMTP_FROM_NAME: str = "AuraFlow"
    # Where the sales reply poller escalates interested/question leads the AI
    # can't confidently answer on its own.
    SALES_ESCALATION_EMAIL: str = "alerts@example.com"

    # ── Self-host billing mode (open core) ────────────────────────────────
    # 'self'    : operator uses their OWN Square/Stripe directly (no platform fee)
    # 'managed' : route Square billing through the AuraFlow managed billing broker
    #             (1% platform fee applied server-side by the broker)
    AURAFLOW_BILLING_MODE: str = "self"
    AURAFLOW_BROKER_URL: Optional[str] = None      # e.g. https://api.auraflow.fit
    AURAFLOW_BROKER_API_KEY: Optional[str] = None  # af_broker_...

    # ── Logging ───────────────────────────────────────────────────────
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"  # "json" or "text"

    APP_SECRET_FINGERPRINT: Optional[str] = None

    @field_validator("APP_SECRET", mode="before")
    @classmethod
    def validate_app_secret(cls, v):
        if isinstance(v, str) and len(v) < 32:
            raise ValueError("APP_SECRET must be at least 32 characters")
        return v

    def validate_production_fingerprint(self) -> None:
        """Refuse to start if the loaded APP_SECRET does not match the committed
        production fingerprint.

        This is the last line of defense against deploying the wrong .env file.
        Every credential in the database (Stripe keys, SMTP passwords, Zoom secrets,
        SendGrid keys, etc.) is encrypted with APP_SECRET. If a container boots with
        the wrong value, decryption silently fails and purchases / emails / zoom
        links all break. Crashing on startup surfaces the mistake immediately
        instead of letting bad traffic flow.
        """
        import hashlib, sys
        if self.ENVIRONMENT != "production":
            return
        if not self.APP_SECRET_FINGERPRINT:
            return
        actual = hashlib.sha256(self.APP_SECRET.encode()).hexdigest()[:16]
        if actual != self.APP_SECRET_FINGERPRINT:
            sys.stderr.write(
                f"\n\n[FATAL] APP_SECRET fingerprint mismatch — refusing to start.\n"
                f"  expected: {self.APP_SECRET_FINGERPRINT}\n"
                f"  actual:   {actual}\n"
                f"  This container was booted with the wrong .env file. Every\n"
                f"  database credential is encrypted with APP_SECRET, so running\n"
                f"  with the wrong value breaks purchases, emails, Stripe, Zoom.\n"
                f"  Fix: redeploy with `-f docker-compose.prod.yml --env-file .env.prod`.\n\n"
            )
            sys.exit(78)  # EX_CONFIG

    def validate_production_phi_key(self) -> None:
        """Refuse to start in production if HEALTH_DATA_ENCRYPTION_KEY is
        missing OR doesn't produce a valid Fernet cipher.

        Counterpart to validate_production_fingerprint but for PHI. Without
        this key, writes to `*_enc` shadow columns silently store plaintext
        (the HIPAA 2C dual-mode degrades to no-op encryption). That's a
        compliance failure we must not boot into.

        Dev/test environments bypass — local work without the key still
        runs, just without encryption.
        """
        import sys
        if self.ENVIRONMENT != "production":
            return
        if not self.HEALTH_DATA_ENCRYPTION_KEY:
            sys.stderr.write(
                "\n\n[FATAL] HEALTH_DATA_ENCRYPTION_KEY missing in production.\n"
                "  HIPAA 2C dual-mode requires a Fernet key. Without it, every\n"
                "  write to members.phone_enc / date_of_birth_enc / etc. would\n"
                "  silently store PHI plaintext. That violates §164.312(a)(2)(iv).\n"
                "  Fix: add HEALTH_DATA_ENCRYPTION_KEY to .env.prod (generate\n"
                "  with `python -c \"from cryptography.fernet import Fernet; "
                "print(Fernet.generate_key().decode())\"`) and redeploy.\n\n"
            )
            sys.exit(78)
        # Validate the key actually works as a Fernet cipher (catches
        # truncation / bad copy-paste).
        try:
            from cryptography.fernet import Fernet
            Fernet(self.HEALTH_DATA_ENCRYPTION_KEY.encode("utf-8"))
        except Exception as exc:
            sys.stderr.write(
                f"\n\n[FATAL] HEALTH_DATA_ENCRYPTION_KEY is not a valid Fernet key.\n"
                f"  Error: {exc}\n"
                f"  Fernet keys are base64-encoded 32-byte values. Regenerate\n"
                f"  with `python -c \"from cryptography.fernet import Fernet; "
                f"print(Fernet.generate_key().decode())\"`.\n"
                f"  Do NOT change the key if PHI is already encrypted with the\n"
                f"  current one — you'd lose the ability to decrypt.\n\n"
            )
            sys.exit(78)

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v

    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT == "development"

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
settings.validate_production_fingerprint()
settings.validate_production_phi_key()
