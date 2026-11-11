import socket
from unittest.mock import patch

import pytest

from webhook_inbox.ssrf import ReplayTargetError, validate_replay_url


def test_rejects_non_http_schemes() -> None:
    with pytest.raises(ReplayTargetError) as exc:
        validate_replay_url("ftp://example.com/x")
    assert exc.value.reason == "scheme"


def test_rejects_empty_and_credentials() -> None:
    with pytest.raises(ReplayTargetError) as exc:
        validate_replay_url("   ")
    assert exc.value.reason == "invalid"
    with pytest.raises(ReplayTargetError) as exc:
        validate_replay_url("https://user:pass@example.com/")
    assert exc.value.reason == "credentials"


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/hook",
        "http://10.0.0.8/hook",
        "http://192.168.1.1/hook",
        "http://169.254.169.254/latest/meta-data",
        "http://[::1]/",
        "http://localhost/hook",
    ],
)
def test_blocks_private_targets_by_default(url: str) -> None:
    with pytest.raises(ReplayTargetError) as exc:
        validate_replay_url(url)
    assert exc.value.reason == "private"


def test_allows_private_when_configured() -> None:
    assert (
        validate_replay_url("http://127.0.0.1/hook", allow_private=True) == "http://127.0.0.1/hook"
    )


def test_public_hostname_ok() -> None:
    with patch("webhook_inbox.ssrf.socket.getaddrinfo") as mock_getaddrinfo:
        mock_getaddrinfo.return_value = [
            (0, 0, 0, "", ("93.184.216.34", 0)),
        ]
        assert (
            validate_replay_url("https://example.com/hooks?x=1") == "https://example.com/hooks?x=1"
        )


def test_hostname_resolving_to_private_is_blocked() -> None:
    with patch("webhook_inbox.ssrf.socket.getaddrinfo") as mock_getaddrinfo:
        mock_getaddrinfo.return_value = [
            (0, 0, 0, "", ("10.1.2.3", 0)),
        ]
        with pytest.raises(ReplayTargetError) as exc:
            validate_replay_url("https://evil.example/hook")
        assert exc.value.reason == "private"


def test_dns_failure() -> None:
    with patch(
        "webhook_inbox.ssrf.socket.getaddrinfo",
        side_effect=socket.gaierror(socket.EAI_NONAME, "name"),
    ):
        with pytest.raises(ReplayTargetError) as exc:
            validate_replay_url("https://does-not-resolve.invalid/x")
        assert exc.value.reason == "dns"
