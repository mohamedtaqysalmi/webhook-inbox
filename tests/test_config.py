import pytest

from webhook_inbox.config import ConfigError, Settings


def test_defaults() -> None:
    settings = Settings.from_env({})
    assert settings.db_path == "webhook_inbox.db"
    assert settings.max_body_bytes == 1024 * 1024
    assert settings.max_header_bytes == 16 * 1024
    assert settings.base_url == "http://localhost:8000"


def test_overrides_and_trailing_slash_stripped() -> None:
    settings = Settings.from_env(
        {
            "WEBHOOK_INBOX_DB_PATH": "/data/inbox.db",
            "WEBHOOK_INBOX_MAX_BODY_BYTES": "2048",
            "WEBHOOK_INBOX_MAX_HEADER_BYTES": "512",
            "WEBHOOK_INBOX_BASE_URL": "https://hooks.example.test/",
        }
    )
    assert settings.db_path == "/data/inbox.db"
    assert settings.max_body_bytes == 2048
    assert settings.max_header_bytes == 512
    assert settings.base_url == "https://hooks.example.test"


def test_reads_process_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEBHOOK_INBOX_MAX_BODY_BYTES", "99")
    assert Settings.from_env().max_body_bytes == 99


def test_all_problems_reported_together() -> None:
    with pytest.raises(ConfigError) as exc:
        Settings.from_env(
            {
                "WEBHOOK_INBOX_MAX_BODY_BYTES": "lots",
                "WEBHOOK_INBOX_MAX_HEADER_BYTES": "0",
                "WEBHOOK_INBOX_BASE_URL": "ftp://nope",
            }
        )
    message = str(exc.value)
    assert "MAX_BODY_BYTES must be an integer" in message
    assert "MAX_HEADER_BYTES must be greater than zero" in message
    assert "BASE_URL must be an http(s) URL" in message
