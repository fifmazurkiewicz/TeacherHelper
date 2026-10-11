from html import escape

import httpx

from teacher_helper.config import get_settings


async def notify_pending_account(account_email: str) -> None:
    settings = get_settings()
    if not settings.resend_api_key:
        raise RuntimeError("RESEND_API_KEY is not configured")
    async with httpx.AsyncClient(timeout=5) as client:
        response = await client.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {settings.resend_api_key}"},
            json={
                "from": settings.resend_from,
                "to": [settings.resend_mail],
                "subject": "TeacherHelper: nowe konto do akceptacji",
                "text": f"Nowe konto: {account_email}\n\nOtwórz panel administratora: https://teacherhelper.fmazurkiewicz.dev/admin/users",
                "html": f"""<p>Nowe konto oczekuje na akceptację w <strong>TeacherHelper</strong>.</p>
<p><strong>Konto:</strong> {escape(account_email)}</p>
<p><a href=\"https://teacherhelper.fmazurkiewicz.dev/admin/users\">Otwórz panel administratora</a></p>""",
            },
        )
    response.raise_for_status()
