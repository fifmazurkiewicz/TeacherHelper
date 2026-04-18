from __future__ import annotations

import logging
from typing import Any

import httpx

from teacher_helper.config import get_settings

logger = logging.getLogger(__name__)


async def send_alert_webhook(payload: dict[str, Any]) -> bool:
    """Wysyła JSON POST na skonfigurowany URL (Slack, Discord, PagerDuty, własny webhook)."""
    url = get_settings().alert_webhook_url
    if not url:
        return False
    body = {
        "source": "teacher-helper",
        **payload,
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(url, json=body)
            if r.is_error:
                logger.warning("Webhook alert HTTP %s: %s", r.status_code, r.text[:500])
                return False
            return True
    except Exception:
        logger.exception("Webhook alert nie powiódł się")
        return False
