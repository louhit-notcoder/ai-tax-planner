from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    environment: str
    database_url: str
    jwt_secret: str
    jwt_issuer: str
    access_token_minutes: int
    refresh_token_days: int
    expose_auth_tokens_in_response: bool
    app_base_url: str
    cors_origins: tuple[str, ...]
    cookie_samesite: str
    cookie_secure: bool
    encryption_key_hex: str
    blind_index_secret: str
    storage_backend: str
    local_storage_root: Path
    s3_endpoint_url: str | None
    s3_bucket: str | None
    s3_region: str
    s3_access_key_id: str | None
    s3_secret_access_key: str | None
    s3_kms_key_id: str | None
    redis_url: str
    rate_limit_backend: str
    clamd_host: str | None
    clamd_port: int
    malware_scan_required: bool
    max_upload_bytes: int
    schema_root: Path
    official_itr1_schema_url: str
    official_itr2_schema_url: str
    official_itr1_validation_url: str
    official_itr2_validation_url: str
    software_id: str
    software_version: str
    legal_source_root: Path
    embedding_base_url: str | None
    embedding_api_key: str | None
    embedding_model: str | None
    smtp_host: str | None
    smtp_port: int
    smtp_username: str | None
    smtp_password: str | None
    smtp_from_email: str | None
    smtp_use_tls: bool
    require_mfa_for_privileged_roles: bool
    allow_dev_bootstrap: bool
    dev_bootstrap_email: str | None
    dev_bootstrap_password: str | None

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    def validate(self) -> None:
        errors: list[str] = []
        if self.is_production:
            if len(self.jwt_secret) < 48:
                errors.append("JWT_SECRET must be at least 48 characters in production")
            if len(self.encryption_key_hex) != 64:
                errors.append("ENCRYPTION_KEY_HEX must contain 32 bytes encoded as 64 hex characters")
            if len(self.blind_index_secret) < 32:
                errors.append("BLIND_INDEX_SECRET must be at least 32 characters")
            if self.allow_dev_bootstrap:
                errors.append("ALLOW_DEV_BOOTSTRAP must be false in production")
            if self.expose_auth_tokens_in_response:
                errors.append("EXPOSE_AUTH_TOKENS_IN_RESPONSE must be false in production")
            if not self.app_base_url.startswith("https://"):
                errors.append("APP_BASE_URL must use HTTPS in production")
            if not self.smtp_host or not self.smtp_from_email:
                errors.append("SMTP_HOST and SMTP_FROM_EMAIL are required for production invitations")
            if not self.database_url.startswith(("postgresql://", "postgresql+psycopg://")):
                errors.append("DATABASE_URL must use PostgreSQL in production")
            if self.storage_backend == "local":
                errors.append("Local object storage is not permitted in production")
            if self.storage_backend == "s3" and not self.s3_bucket:
                errors.append("S3 bucket is required in production")
            if self.storage_backend == "s3" and self.s3_endpoint_url and not all([self.s3_access_key_id, self.s3_secret_access_key]):
                errors.append("Explicit S3 credentials are required for a custom S3 endpoint")
            if self.storage_backend == "s3" and not self.s3_endpoint_url and not self.s3_kms_key_id:
                errors.append("S3_KMS_KEY_ID is required for AWS production object storage")
            if not self.cors_origins or "*" in self.cors_origins:
                errors.append("Explicit CORS_ALLOWED_ORIGINS are required in production")
            if self.rate_limit_backend != "redis":
                errors.append("RATE_LIMIT_BACKEND must be redis in production")
            if self.malware_scan_required and not self.clamd_host:
                errors.append("CLAMD_HOST is required when malware scanning is mandatory")
        if errors:
            raise RuntimeError("Invalid Green Papaya configuration: " + "; ".join(errors))


def _csv(value: str) -> tuple[str, ...]:
    return tuple(item.strip().rstrip("/") for item in value.split(",") if item.strip())


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    root = Path(__file__).resolve().parents[2]
    environment = os.getenv("GREEN_PAPAYA_ENV", "development").strip().lower()
    default_db = "sqlite:///./green_papaya_v3.db" if environment != "production" else ""

    # Cookie policy. For a cross-site deployment (e.g. frontend on Vercel, API on
    # Render/other domain) browsers require SameSite=None AND Secure=True, otherwise
    # the auth cookie is dropped on cross-origin XHR and the user can never stay
    # logged in. Set COOKIE_SAMESITE=none for such deployments.
    cookie_samesite = os.getenv("COOKIE_SAMESITE", "lax").strip().lower()
    if cookie_samesite not in {"lax", "strict", "none"}:
        cookie_samesite = "lax"
    _cookie_secure_env = os.getenv("COOKIE_SECURE", "").strip().lower()
    if _cookie_secure_env in {"true", "1", "yes"}:
        cookie_secure = True
    elif _cookie_secure_env in {"false", "0", "no"}:
        cookie_secure = False
    else:
        # SameSite=None is invalid without Secure, so force Secure when None is used.
        cookie_secure = (environment == "production") or (cookie_samesite == "none")

    settings = Settings(
        environment=environment,
        database_url=os.getenv("DATABASE_URL", default_db),
        jwt_secret=os.getenv("JWT_SECRET", "development-only-change-this-secret-immediately-000000"),
        jwt_issuer=os.getenv("JWT_ISSUER", "green-papaya"),
        access_token_minutes=int(os.getenv("ACCESS_TOKEN_MINUTES", "30")),
        refresh_token_days=int(os.getenv("REFRESH_TOKEN_DAYS", "14")),
        expose_auth_tokens_in_response=os.getenv("EXPOSE_AUTH_TOKENS_IN_RESPONSE", "true" if environment != "production" else "false").lower() == "true",
        app_base_url=os.getenv("APP_BASE_URL", "http://localhost:3000").rstrip("/"),
        cors_origins=_csv(os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000")),
        cookie_samesite=cookie_samesite,
        cookie_secure=cookie_secure,
        encryption_key_hex=os.getenv("ENCRYPTION_KEY_HEX", "00" * 32),
        blind_index_secret=os.getenv("BLIND_INDEX_SECRET", "development-blind-index-secret-change-me"),
        storage_backend=os.getenv("STORAGE_BACKEND", "local").lower(),
        local_storage_root=Path(os.getenv("LOCAL_STORAGE_ROOT", str(root / ".local_storage"))).resolve(),
        s3_endpoint_url=os.getenv("S3_ENDPOINT_URL") or None,
        s3_bucket=os.getenv("S3_BUCKET") or None,
        s3_region=os.getenv("S3_REGION", "ap-south-1"),
        s3_access_key_id=os.getenv("S3_ACCESS_KEY_ID") or None,
        s3_secret_access_key=os.getenv("S3_SECRET_ACCESS_KEY") or None,
        s3_kms_key_id=os.getenv("S3_KMS_KEY_ID") or None,
        redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        rate_limit_backend=os.getenv("RATE_LIMIT_BACKEND", "memory" if environment != "production" else "redis").lower(),
        clamd_host=os.getenv("CLAMD_HOST") or None,
        clamd_port=int(os.getenv("CLAMD_PORT", "3310")),
        malware_scan_required=os.getenv("MALWARE_SCAN_REQUIRED", "false").lower() == "true",
        max_upload_bytes=int(os.getenv("MAX_UPLOAD_BYTES", str(50 * 1024 * 1024))),
        schema_root=Path(os.getenv("ITR_SCHEMA_ROOT", str(root / "backend" / "rules" / "official"))).resolve(),
        official_itr1_schema_url=os.getenv(
            "OFFICIAL_ITR1_SCHEMA_URL",
            "https://www.incometax.gov.in/iec/foportal/sites/default/files/2026-06/ITR-1_2026_Main_V1.1.json",
        ),
        official_itr2_schema_url=os.getenv(
            "OFFICIAL_ITR2_SCHEMA_URL",
            "https://www.incometax.gov.in/iec/foportal/sites/default/files/2026-06/ITR-2_2026_Main_V1.1.json",
        ),
        official_itr1_validation_url=os.getenv(
            "OFFICIAL_ITR1_VALIDATION_URL",
            "https://www.incometax.gov.in/iec/foportal/sites/default/files/2026-05/CBDT_e-Filing_ITR%201_Validation%20Rules_AY%202026-27.pdf",
        ),
        official_itr2_validation_url=os.getenv(
            "OFFICIAL_ITR2_VALIDATION_URL",
            "https://www.incometax.gov.in/iec/foportal/sites/default/files/2026-05/CBDT__e-Filing_ITR%202_Validation%20Rules_AY%202026-27_V1.0.pdf",
        ),
        software_id=os.getenv("ITR_SOFTWARE_ID", "SELF"),
        software_version=os.getenv("SOFTWARE_VERSION", "3.0.0"),
        legal_source_root=Path(os.getenv("LEGAL_SOURCE_ROOT", str(root / "backend" / "rules" / "legal"))).resolve(),
        embedding_base_url=os.getenv("EMBEDDING_BASE_URL") or None,
        embedding_api_key=os.getenv("EMBEDDING_API_KEY") or None,
        embedding_model=os.getenv("EMBEDDING_MODEL") or None,
        smtp_host=os.getenv("SMTP_HOST") or None,
        smtp_port=int(os.getenv("SMTP_PORT", "587")),
        smtp_username=os.getenv("SMTP_USERNAME") or None,
        smtp_password=os.getenv("SMTP_PASSWORD") or None,
        smtp_from_email=os.getenv("SMTP_FROM_EMAIL") or None,
        smtp_use_tls=os.getenv("SMTP_USE_TLS", "true").lower() == "true",
        require_mfa_for_privileged_roles=os.getenv("REQUIRE_MFA_FOR_PRIVILEGED_ROLES", "true").lower() == "true",
        allow_dev_bootstrap=os.getenv("ALLOW_DEV_BOOTSTRAP", "true").lower() == "true",
        dev_bootstrap_email=os.getenv("DEV_BOOTSTRAP_EMAIL") or None,
        dev_bootstrap_password=os.getenv("DEV_BOOTSTRAP_PASSWORD") or None,
    )
    settings.validate()
    return settings
