import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from webhook_inbox.signatures import SignatureError, verify_github, verify_hmac, verify_stripe

VECTORS_PATH = Path(__file__).parent.parent / "site" / "signature-vectors.json"
CASES = json.loads(VECTORS_PATH.read_text(encoding="utf-8"))["cases"]


def verify(case: dict[str, str], body: bytes, signature: str) -> None:
    mode = case["mode"]
    if mode == "github":
        verify_github(case["secret"], body, signature)
    elif mode == "stripe":
        now = datetime.fromtimestamp(int(case["timestamp"]), tz=UTC)
        verify_stripe(case["secret"], body, signature, clock=lambda: now)
    else:
        verify_hmac(
            case["secret"],
            body,
            signature,
            algorithm=case["algorithm"],
            encoding="hex" if mode == "hmac-hex" else "base64",
        )


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_python_helper_accepts_the_vector_the_site_computes(case: dict[str, str]) -> None:
    verify(case, case["body"].encode("utf-8"), case["expected"])


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_python_helper_rejects_a_tampered_body(case: dict[str, str]) -> None:
    with pytest.raises(SignatureError):
        verify(case, case["body"].encode("utf-8") + b" ", case["expected"])
