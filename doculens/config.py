"""Application settings with safety checks.

Settings come from environment variables prefixed with ``DOCULENS_`` (or a git-ignored
``.env`` file). Unsafe combinations fail fast at startup instead of running silently.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PLACEHOLDER_SECRETS = {"", "change-me", "changeme", "secret", "dev", "test"}
MIN_SECRET_LEN = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DOCULENS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: Literal["development", "test", "production"] = "development"
    secret_key: str = Field(default="", repr=False)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    cors_origins: str = "http://localhost:5173"

    max_upload_mb: int = Field(default=10, ge=1, le=50)
    max_image_pixels: int = Field(default=40_000_000, ge=10_000, le=200_000_000)
    max_pdf_pages: int = Field(default=3, ge=1, le=20)
    rate_limit_per_minute: int = Field(default=30, ge=1, le=10_000)

    upload_dir: Path = Path("var/uploads")
    upload_ttl_minutes: int = Field(default=30, ge=1, le=24 * 60)

    trust_proxy: bool = False

    @field_validator("cors_origins")
    @classmethod
    def _no_wildcard(cls, v: str) -> str:
        origins = [o.strip() for o in v.split(",") if o.strip()]
        for o in origins:
            if o == "*" or "*" in o:
                raise ValueError("Wildcard CORS origins are not allowed; list exact origins.")
            if not (o.startswith("http://") or o.startswith("https://")):
                raise ValueError(f"CORS origin must start with http:// or https://: {o!r}")
            if o.endswith("/"):
                raise ValueError(f"CORS origin must not end with '/': {o!r}")
        return ",".join(origins)

    @model_validator(mode="after")
    def _production_safety(self) -> Settings:
        if self.env != "production":
            return self
        if self.secret_key.strip().lower() in PLACEHOLDER_SECRETS:
            raise ValueError("DOCULENS_SECRET_KEY must be set to a real value in production.")
        if len(self.secret_key) < MIN_SECRET_LEN:
            raise ValueError(f"DOCULENS_SECRET_KEY must be at least {MIN_SECRET_LEN} characters.")
        if self.log_level == "DEBUG":
            raise ValueError("DEBUG logging is not allowed in production.")
        for o in self.cors_origin_list:
            if not o.startswith("https://"):
                raise ValueError(f"Production CORS origins must use https: {o!r}")
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [o for o in self.cors_origins.split(",") if o]

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def max_request_bytes(self) -> int:
        # Multipart framing adds a little overhead on top of the file itself.
        return self.max_upload_bytes + 64 * 1024

    @property
    def is_production(self) -> bool:
        return self.env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
