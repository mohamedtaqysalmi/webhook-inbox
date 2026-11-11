"""Verification helpers for common webhook signature schemes.

All comparisons use hmac.compare_digest. The helpers raise SignatureError with a
short reason code instead of returning a bool, so callers can tell an expired
Stripe timestamp from a bad signature.
"""

from __future__ import annotations

import base64
import binascii
import hmac
from collections.abc import Callable
from datetime import UTC, datetime

Clock = Callable[[], datetime]

DEFAULT_STRIPE_TOLERANCE_SECONDS = 300


class SignatureError(Exception):
    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _key(secret: str | bytes) -> bytes:
    return secret.encode("utf-8") if isinstance(secret, str) else secret


def compute_hmac(secret: str | bytes, message: bytes, algorithm: str = "sha256") -> bytes:
    return hmac.new(_key(secret), message, algorithm).digest()


def _matches(expected: bytes, provided: bytes) -> bool:
    return hmac.compare_digest(expected, provided)


def _decode_hex(value: str) -> bytes | None:
    try:
        return bytes.fromhex(value.strip())
    except ValueError:
        return None


def _decode_base64(value: str) -> bytes | None:
    try:
        return base64.b64decode(value.strip(), validate=True)
    except (binascii.Error, ValueError):
        return None


def verify_github(secret: str | bytes, body: bytes, signature_header: str | None) -> None:
    """Check an X-Hub-Signature-256 header (`sha256=<hex>`) against the raw body."""
    if not signature_header:
        raise SignatureError("missing", "X-Hub-Signature-256 header is missing")
    scheme, _, digest = signature_header.partition("=")
    if scheme != "sha256" or not digest:
        raise SignatureError("malformed", "expected a header of the form sha256=<hex digest>")
    provided = _decode_hex(digest)
    if provided is None:
        raise SignatureError("malformed", "signature is not valid hex")
    if not _matches(compute_hmac(secret, body), provided):
        raise SignatureError("mismatch", "signature does not match")


def verify_hmac(
    secret: str | bytes,
    body: bytes,
    signature: str | None,
    *,
    algorithm: str = "sha256",
    encoding: str = "hex",
    prefix: str = "",
) -> None:
    """Generic HMAC check over the raw body.

    `prefix` is stripped from the header value first (for example `sha256=`).
    `encoding` is `hex` or `base64`.
    """
    if encoding not in ("hex", "base64"):
        raise ValueError("encoding must be 'hex' or 'base64'")
    if not signature:
        raise SignatureError("missing", "signature is missing")
    if prefix:
        if not signature.startswith(prefix):
            raise SignatureError("malformed", f"signature does not start with {prefix!r}")
        signature = signature[len(prefix) :]
    provided = _decode_hex(signature) if encoding == "hex" else _decode_base64(signature)
    if provided is None:
        raise SignatureError("malformed", f"signature is not valid {encoding}")
    if not _matches(compute_hmac(secret, body, algorithm), provided):
        raise SignatureError("mismatch", "signature does not match")


def verify_stripe(
    secret: str | bytes,
    body: bytes,
    signature_header: str | None,
    *,
    tolerance_seconds: int = DEFAULT_STRIPE_TOLERANCE_SECONDS,
    clock: Clock = _utc_now,
) -> None:
    """Check a Stripe-style header: `t=<unix seconds>,v1=<hex>[,v1=<hex>...]`.

    The signed payload is `<t>.<raw body>`. Any matching v1 value is accepted, which
    allows secret rotation. The timestamp must be within tolerance of the clock in
    either direction.
    """
    if not signature_header:
        raise SignatureError("missing", "signature header is missing")

    timestamp: int | None = None
    candidates: list[bytes] = []
    for part in signature_header.split(","):
        key, _, value = part.strip().partition("=")
        if key == "t":
            try:
                timestamp = int(value)
            except ValueError:
                raise SignatureError("malformed", "timestamp is not an integer") from None
        elif key == "v1":
            decoded = _decode_hex(value)
            if decoded is not None:
                candidates.append(decoded)
    if timestamp is None:
        raise SignatureError("malformed", "header has no t= timestamp")
    if not candidates:
        raise SignatureError("malformed", "header has no valid v1= signature")

    expected = compute_hmac(secret, f"{timestamp}.".encode() + body)
    # Check every candidate without short-circuiting on the first hit.
    matched = False
    for candidate in candidates:
        matched |= _matches(expected, candidate)
    if not matched:
        raise SignatureError("mismatch", "signature does not match")

    age = abs(clock().timestamp() - timestamp)
    if age > tolerance_seconds:
        raise SignatureError("expired", f"timestamp is outside the {tolerance_seconds}s tolerance")
