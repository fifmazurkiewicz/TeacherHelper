"""Weryfikacja podpisu webhooków KIE (HMAC-SHA256, Base64).

https://docs.kie.ai/common-api/webhook-verification
"""

from __future__ import annotations

import base64
import hashlib
import hmac


def kie_expected_webhook_signature_b64(task_id: str, timestamp_seconds: str, secret: str) -> str:
    payload = f"{task_id}.{timestamp_seconds}".encode("utf-8")
    digest = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).digest()
    return base64.b64encode(digest).decode("ascii")


def verify_kie_webhook_signature(
    task_id: str | None,
    timestamp_seconds: str | None,
    received_signature_b64: str | None,
    secret: str | None,
) -> bool:
    """Gdy ``secret`` jest puste — pomijamy weryfikację (tylko dev)."""
    if not (secret or "").strip():
        return True
    if not task_id or not timestamp_seconds or not received_signature_b64:
        return False
    expected = kie_expected_webhook_signature_b64(task_id.strip(), timestamp_seconds.strip(), secret.strip())
    return hmac.compare_digest(expected, received_signature_b64.strip())
