import base64
import hashlib
import hmac
from datetime import UTC, datetime

import pytest

from webhook_inbox.signatures import (
    SignatureError,
    compute_hmac,
    verify_github,
    verify_hmac,
    verify_stripe,
)

SECRET = "whsec_test_secret"
BODY = b'{"event":"ping","id":42}'
NOW = datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC)


def hex_sig(secret: str, message: bytes) -> str:
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def reason_of(excinfo: pytest.ExceptionInfo[SignatureError]) -> str:
    return excinfo.value.reason


class TestGithub:
    def test_published_example_vector(self) -> None:
        # Example from GitHub's webhook documentation.
        verify_github(
            "It's a Secret to Everybody",
            b"Hello, World!",
            "sha256=757107ea0eb2509fc211221cce984b8a37570b6d7586c22c46f4379c8b043e17",
        )

    def test_valid_signature(self) -> None:
        verify_github(SECRET, BODY, "sha256=" + hex_sig(SECRET, BODY))

    def test_secret_may_be_bytes(self) -> None:
        verify_github(SECRET.encode(), BODY, "sha256=" + hex_sig(SECRET, BODY))

    def test_wrong_secret(self) -> None:
        with pytest.raises(SignatureError) as exc:
            verify_github("other", BODY, "sha256=" + hex_sig(SECRET, BODY))
        assert reason_of(exc) == "mismatch"

    def test_tampered_body(self) -> None:
        header = "sha256=" + hex_sig(SECRET, BODY)
        with pytest.raises(SignatureError) as exc:
            verify_github(SECRET, BODY + b" ", header)
        assert reason_of(exc) == "mismatch"

    @pytest.mark.parametrize("header", [None, ""])
    def test_missing_header(self, header: str | None) -> None:
        with pytest.raises(SignatureError) as exc:
            verify_github(SECRET, BODY, header)
        assert reason_of(exc) == "missing"

    @pytest.mark.parametrize("header", ["sha1=abcd", "sha256=", "abcd", "sha256=zz"])
    def test_malformed_header(self, header: str) -> None:
        with pytest.raises(SignatureError) as exc:
            verify_github(SECRET, BODY, header)
        assert reason_of(exc) == "malformed"


class TestGenericHmac:
    def test_hex(self) -> None:
        verify_hmac(SECRET, BODY, hex_sig(SECRET, BODY))

    def test_hex_with_prefix(self) -> None:
        verify_hmac(SECRET, BODY, "v0=" + hex_sig(SECRET, BODY), prefix="v0=")

    def test_base64(self) -> None:
        digest = hmac.new(SECRET.encode(), BODY, hashlib.sha256).digest()
        verify_hmac(SECRET, BODY, base64.b64encode(digest).decode(), encoding="base64")

    def test_sha512(self) -> None:
        digest = hmac.new(SECRET.encode(), BODY, hashlib.sha512).hexdigest()
        verify_hmac(SECRET, BODY, digest, algorithm="sha512")

    def test_wrong_secret(self) -> None:
        with pytest.raises(SignatureError) as exc:
            verify_hmac("other", BODY, hex_sig(SECRET, BODY))
        assert reason_of(exc) == "mismatch"

    def test_tampered_body(self) -> None:
        with pytest.raises(SignatureError) as exc:
            verify_hmac(SECRET, b"{}", hex_sig(SECRET, BODY))
        assert reason_of(exc) == "mismatch"

    def test_missing_prefix(self) -> None:
        with pytest.raises(SignatureError) as exc:
            verify_hmac(SECRET, BODY, hex_sig(SECRET, BODY), prefix="v0=")
        assert reason_of(exc) == "malformed"

    def test_bad_encodings(self) -> None:
        with pytest.raises(SignatureError) as exc:
            verify_hmac(SECRET, BODY, "not hex!")
        assert reason_of(exc) == "malformed"
        with pytest.raises(SignatureError) as exc:
            verify_hmac(SECRET, BODY, "***", encoding="base64")
        assert reason_of(exc) == "malformed"

    def test_missing_signature(self) -> None:
        with pytest.raises(SignatureError) as exc:
            verify_hmac(SECRET, BODY, None)
        assert reason_of(exc) == "missing"

    def test_unknown_encoding_is_a_programming_error(self) -> None:
        with pytest.raises(ValueError, match="encoding"):
            verify_hmac(SECRET, BODY, "aa", encoding="rot13")

    def test_compute_hmac_matches_hashlib(self) -> None:
        assert compute_hmac(SECRET, BODY).hex() == hex_sig(SECRET, BODY)


class TestStripe:
    @staticmethod
    def header(ts: int, secret: str = SECRET, body: bytes = BODY) -> str:
        return f"t={ts},v1={hex_sig(secret, f'{ts}.'.encode() + body)}"

    @staticmethod
    def clock() -> datetime:
        return NOW

    def test_valid(self) -> None:
        verify_stripe(SECRET, BODY, self.header(int(NOW.timestamp())), clock=self.clock)

    def test_within_tolerance_edges(self) -> None:
        ts = int(NOW.timestamp())
        verify_stripe(SECRET, BODY, self.header(ts - 300), clock=self.clock)
        verify_stripe(SECRET, BODY, self.header(ts + 300), clock=self.clock)

    def test_expired(self) -> None:
        with pytest.raises(SignatureError) as exc:
            verify_stripe(SECRET, BODY, self.header(int(NOW.timestamp()) - 301), clock=self.clock)
        assert reason_of(exc) == "expired"

    def test_timestamp_too_far_in_future(self) -> None:
        with pytest.raises(SignatureError) as exc:
            verify_stripe(SECRET, BODY, self.header(int(NOW.timestamp()) + 301), clock=self.clock)
        assert reason_of(exc) == "expired"

    def test_custom_tolerance(self) -> None:
        header = self.header(int(NOW.timestamp()) - 30)
        with pytest.raises(SignatureError):
            verify_stripe(SECRET, BODY, header, tolerance_seconds=10, clock=self.clock)
        verify_stripe(SECRET, BODY, header, tolerance_seconds=60, clock=self.clock)

    def test_wrong_secret(self) -> None:
        header = self.header(int(NOW.timestamp()), secret="other")
        with pytest.raises(SignatureError) as exc:
            verify_stripe(SECRET, BODY, header, clock=self.clock)
        assert reason_of(exc) == "mismatch"

    def test_tampered_body(self) -> None:
        header = self.header(int(NOW.timestamp()))
        with pytest.raises(SignatureError) as exc:
            verify_stripe(SECRET, BODY + b"x", header, clock=self.clock)
        assert reason_of(exc) == "mismatch"

    def test_altered_timestamp_breaks_signature(self) -> None:
        ts = int(NOW.timestamp())
        sig = hex_sig(SECRET, f"{ts}.".encode() + BODY)
        with pytest.raises(SignatureError) as exc:
            verify_stripe(SECRET, BODY, f"t={ts + 1},v1={sig}", clock=self.clock)
        assert reason_of(exc) == "mismatch"

    def test_any_v1_may_match_for_secret_rotation(self) -> None:
        ts = int(NOW.timestamp())
        good = hex_sig(SECRET, f"{ts}.".encode() + BODY)
        header = f"t={ts},v1={'0' * 64},v0=ignored,v1={good}"
        verify_stripe(SECRET, BODY, header, clock=self.clock)

    def test_expired_wins_only_after_signature_checks_out(self) -> None:
        # A forged old timestamp reports mismatch, not expired.
        old = int(NOW.timestamp()) - 10_000
        with pytest.raises(SignatureError) as exc:
            verify_stripe(SECRET, BODY, f"t={old},v1={'0' * 64}", clock=self.clock)
        assert reason_of(exc) == "mismatch"

    @pytest.mark.parametrize(
        "header",
        ["v1=abcd", "t=notanumber,v1=abcd", "t=100", "t=100,v1=zz"],
    )
    def test_malformed(self, header: str) -> None:
        with pytest.raises(SignatureError) as exc:
            verify_stripe(SECRET, BODY, header, clock=self.clock)
        assert reason_of(exc) == "malformed"

    def test_missing(self) -> None:
        with pytest.raises(SignatureError) as exc:
            verify_stripe(SECRET, BODY, None, clock=self.clock)
        assert reason_of(exc) == "missing"

    def test_default_clock_is_real_time(self) -> None:
        with pytest.raises(SignatureError) as exc:
            verify_stripe(SECRET, BODY, self.header(1_000_000_000))
        assert reason_of(exc) == "mismatch" or reason_of(exc) == "expired"
