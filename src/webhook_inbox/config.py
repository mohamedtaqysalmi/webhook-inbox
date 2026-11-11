from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlparse

ENV_PREFIX = "WEBHOOK_INBOX_"

DEFAULT_DB_PATH = "webhook_inbox.db"
DEFAULT_MAX_BODY_BYTES = 1024 * 1024
DEFAULT_MAX_HEADER_BYTES = 16 * 1024
DEFAULT_BASE_URL = "http://localhost:8000"


class ConfigError(ValueError):
    """Raised at startup when environment configuration is invalid."""


@dataclass(frozen=True)
class Settings:
    db_path: str = DEFAULT_DB_PATH
    max_body_bytes: int = DEFAULT_MAX_BODY_BYTES
    max_header_bytes: int = DEFAULT_MAX_HEADER_BYTES
    base_url: str = DEFAULT_BASE_URL

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        source = os.environ if env is None else env
        errors: list[str] = []

        def get(name: str, default: str) -> str:
            value = source.get(ENV_PREFIX + name, "").strip()
            return value or default

        def get_positive_int(name: str, default: int) -> int:
            raw = get(name, str(default))
            try:
                value = int(raw)
            except ValueError:
                errors.append(f"{ENV_PREFIX}{name} must be an integer, got {raw!r}")
                return default
            if value <= 0:
                errors.append(f"{ENV_PREFIX}{name} must be greater than zero, got {value}")
                return default
            return value

        db_path = get("DB_PATH", DEFAULT_DB_PATH)
        max_body_bytes = get_positive_int("MAX_BODY_BYTES", DEFAULT_MAX_BODY_BYTES)
        max_header_bytes = get_positive_int("MAX_HEADER_BYTES", DEFAULT_MAX_HEADER_BYTES)
        base_url = get("BASE_URL", DEFAULT_BASE_URL).rstrip("/")

        parsed = urlparse(base_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            errors.append(f"{ENV_PREFIX}BASE_URL must be an http(s) URL, got {base_url!r}")

        if errors:
            raise ConfigError("invalid configuration: " + "; ".join(errors))
        return cls(
            db_path=db_path,
            max_body_bytes=max_body_bytes,
            max_header_bytes=max_header_bytes,
            base_url=base_url,
        )
