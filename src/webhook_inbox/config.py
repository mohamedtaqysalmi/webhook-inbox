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
DEFAULT_RATE_LIMIT_PER_MINUTE = 120
DEFAULT_RETENTION_DAYS = 7
DEFAULT_REPLAY_TIMEOUT_SECONDS = 10.0
DEFAULT_ALLOW_PRIVATE_REPLAY = False


class ConfigError(ValueError):
    """Raised at startup when environment configuration is invalid."""


def _parse_bool(raw: str) -> bool | None:
    value = raw.strip().lower()
    if value in ("1", "true", "yes", "on"):
        return True
    if value in ("0", "false", "no", "off"):
        return False
    return None


@dataclass(frozen=True)
class Settings:
    db_path: str = DEFAULT_DB_PATH
    max_body_bytes: int = DEFAULT_MAX_BODY_BYTES
    max_header_bytes: int = DEFAULT_MAX_HEADER_BYTES
    base_url: str = DEFAULT_BASE_URL
    rate_limit_per_minute: int = DEFAULT_RATE_LIMIT_PER_MINUTE
    retention_days: int = DEFAULT_RETENTION_DAYS
    replay_timeout_seconds: float = DEFAULT_REPLAY_TIMEOUT_SECONDS
    allow_private_replay_targets: bool = DEFAULT_ALLOW_PRIVATE_REPLAY

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        source = os.environ if env is None else env
        errors: list[str] = []

        def get(name: str, default: str) -> str:
            value = source.get(ENV_PREFIX + name, "").strip()
            return value or default

        def get_non_negative_int(name: str, default: int) -> int:
            raw = get(name, str(default))
            try:
                value = int(raw)
            except ValueError:
                errors.append(f"{ENV_PREFIX}{name} must be an integer, got {raw!r}")
                return default
            if value < 0:
                errors.append(f"{ENV_PREFIX}{name} must be >= 0, got {value}")
                return default
            return value

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

        def get_positive_float(name: str, default: float) -> float:
            raw = get(name, str(default))
            try:
                value = float(raw)
            except ValueError:
                errors.append(f"{ENV_PREFIX}{name} must be a number, got {raw!r}")
                return default
            if value <= 0:
                errors.append(f"{ENV_PREFIX}{name} must be greater than zero, got {value}")
                return default
            return value

        db_path = get("DB_PATH", DEFAULT_DB_PATH)
        max_body_bytes = get_positive_int("MAX_BODY_BYTES", DEFAULT_MAX_BODY_BYTES)
        max_header_bytes = get_positive_int("MAX_HEADER_BYTES", DEFAULT_MAX_HEADER_BYTES)
        base_url = get("BASE_URL", DEFAULT_BASE_URL).rstrip("/")
        rate_limit_per_minute = get_non_negative_int(
            "RATE_LIMIT_PER_MINUTE", DEFAULT_RATE_LIMIT_PER_MINUTE
        )
        retention_days = get_non_negative_int("RETENTION_DAYS", DEFAULT_RETENTION_DAYS)
        replay_timeout_seconds = get_positive_float(
            "REPLAY_TIMEOUT_SECONDS", DEFAULT_REPLAY_TIMEOUT_SECONDS
        )

        allow_private_raw = get(
            "ALLOW_PRIVATE_REPLAY_TARGETS",
            "true" if DEFAULT_ALLOW_PRIVATE_REPLAY else "false",
        )
        allow_private = _parse_bool(allow_private_raw)
        if allow_private is None:
            errors.append(
                f"{ENV_PREFIX}ALLOW_PRIVATE_REPLAY_TARGETS must be a boolean, "
                f"got {allow_private_raw!r}"
            )
            allow_private = DEFAULT_ALLOW_PRIVATE_REPLAY

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
            rate_limit_per_minute=rate_limit_per_minute,
            retention_days=retention_days,
            replay_timeout_seconds=replay_timeout_seconds,
            allow_private_replay_targets=allow_private,
        )
