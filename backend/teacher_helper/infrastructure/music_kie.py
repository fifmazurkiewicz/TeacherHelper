"""Adapter KIE.ai Suno — ``POST /api/v1/generate`` i ``GET /api/v1/generate/record-info``.

Dokumentacja: https://docs.kie.ai/suno-api/generate-music
"""

from __future__ import annotations

import json
import logging
from dataclasses import replace
from typing import Any

import httpx

from teacher_helper.use_cases.ports import MusicGeneratorPort, MusicSubmitRequest, MusicSubmitResult

logger = logging.getLogger(__name__)

# Zgodnie z dokumentacją KIE (Get Music Task Details)
KIE_TERMINAL_FAIL_STATUSES = frozenset({
    "CREATE_TASK_FAILED",
    "GENERATE_AUDIO_FAILED",
    "CALLBACK_EXCEPTION",
    "SENSITIVE_WORD_ERROR",
})

# Gdy pojawi się audioUrl w sunoData — można pobrać MP3 (nie czekać wyłącznie na SUCCESS).
KIE_STATUSES_WITH_POSSIBLE_AUDIO = frozenset({"FIRST_SUCCESS", "SUCCESS"})

KIE_TITLE_MAX = 80
_NON_CUSTOM_PROMPT_MAX = 500
_ALLOWED_MODELS = frozenset({"V4", "V4_5", "V4_5PLUS", "V4_5ALL", "V5", "V5_5"})


def _normalize_model(model: str) -> str:
    m = (model or "V4_5ALL").strip()
    return m if m in _ALLOWED_MODELS else "V4_5ALL"


def _prompt_style_limits(model: str) -> tuple[int, int]:
    """(max_prompt, max_style) dla trybu custom — wg tabeli modeli w dokumentacji."""
    if _normalize_model(model) == "V4":
        return 3000, 200
    return 5000, 1000


def _kie_envelope_ok(payload: dict[str, Any]) -> tuple[bool, str | None]:
    if "code" not in payload:
        return True, None
    raw = payload.get("code")
    try:
        code_int = int(raw) if raw is not None else -1
    except (TypeError, ValueError):
        code_int = -1
    if code_int == 200:
        return True, None
    msg = payload.get("msg") or payload.get("message") or str(payload)[:800]
    return False, str(msg)


def _extract_kie_task_id(payload: dict[str, Any]) -> str | None:
    data = payload.get("data")
    if isinstance(data, dict):
        tid = data.get("taskId") or data.get("task_id")
        if tid is not None and str(tid).strip():
            return str(tid).strip()
    tid = payload.get("taskId") or payload.get("task_id")
    if tid is not None and str(tid).strip():
        return str(tid).strip()
    return None


def parse_task_record(payload: dict[str, Any]) -> tuple[str | None, list[str], str | None]:
    """Parsuje odpowiedź ``GET .../record-info`` → (status, audioUrls, komunikat_błędu)."""
    if payload.get("_http_error"):
        return None, [], str(payload.get("_body", "Błąd HTTP"))[:800]
    ok, err = _kie_envelope_ok(payload)
    if not ok:
        return None, [], err or "record-info: code != 200"
    data = payload.get("data")
    if not isinstance(data, dict):
        return None, [], "brak pola data"
    status = data.get("status")
    st = str(status).strip() if status is not None else None
    urls: list[str] = []
    resp = data.get("response")
    if isinstance(resp, dict):
        suno = resp.get("sunoData") or resp.get("suno_data")
        if isinstance(suno, list):
            for item in suno:
                if isinstance(item, dict):
                    u = item.get("audioUrl") or item.get("audio_url")
                    if u:
                        urls.append(str(u).strip())
    err_msg: str | None = None
    if st in KIE_TERMINAL_FAIL_STATUSES:
        err_msg = str(
            data.get("errorMessage") or data.get("error_message") or st or "",
        ).strip() or st
    return st, urls, err_msg


def build_kie_generate_body(req: MusicSubmitRequest) -> dict[str, Any]:
    """Buduje JSON żądania zgodnie z OpenAPI Suno (wymagane: prompt, customMode, instrumental, model, callBackUrl)."""
    model = _normalize_model(req.model)
    cb = (req.call_back_url or "").strip()
    if not cb:
        raise ValueError("missing_call_back_url")

    if not req.custom_mode:
        prompt = (req.prompt or "").strip()[:_NON_CUSTOM_PROMPT_MAX]
        if not prompt:
            raise ValueError("empty_prompt_non_custom")
        return {
            "prompt": prompt,
            "customMode": False,
            "instrumental": bool(req.instrumental),
            "model": model,
            "callBackUrl": cb,
        }

    pmax, smax = _prompt_style_limits(model)
    title = ((req.title or "TeacherHelper track").strip())[:KIE_TITLE_MAX]
    style = ((req.style or "Educational pop for children, cheerful, classroom-friendly").strip())[:smax]
    raw_prompt = (req.prompt or "").strip()

    instrumental = bool(req.instrumental)
    if instrumental:
        prompt = (raw_prompt[:pmax] if raw_prompt else f"Instrumental track matching style «{style}» and title «{title}».")
    else:
        if not raw_prompt:
            raw_prompt = f"[Verse]\n{title}\n\n[Chorus]\n{style}"
        prompt = raw_prompt[:pmax]

    body: dict[str, Any] = {
        "prompt": prompt,
        "customMode": True,
        "instrumental": instrumental,
        "model": model,
        "callBackUrl": cb,
        "style": style,
        "title": title,
    }
    if req.negative_tags:
        body["negativeTags"] = str(req.negative_tags).strip()[:500]
    if req.vocal_gender:
        vg = str(req.vocal_gender).strip().lower()
        if vg in ("m", "f"):
            body["vocalGender"] = vg
    if req.style_weight is not None:
        body["styleWeight"] = float(req.style_weight)
    if req.weirdness_constraint is not None:
        body["weirdnessConstraint"] = float(req.weirdness_constraint)
    if req.audio_weight is not None:
        body["audioWeight"] = float(req.audio_weight)
    if req.persona_id:
        body["personaId"] = str(req.persona_id).strip()[:200]
    if req.persona_model:
        body["personaModel"] = str(req.persona_model).strip()[:200]
    return body


async def download_audio_url(url: str, *, timeout: float = 180.0, max_bytes: int = 80 * 1024 * 1024) -> bytes:
    """Pobiera plik audio z URL zwróconego przez KIE (np. ``audioUrl``)."""
    u = (url or "").strip()
    if not u:
        raise ValueError("empty_audio_url")
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        r = await client.get(u)
        r.raise_for_status()
        data = r.content
    if len(data) > max_bytes:
        raise ValueError("audio_response_too_large")
    return data


class KieMusicGenerator(MusicGeneratorPort):
    """Klient https://api.kie.ai — generate + record-info."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.kie.ai",
        *,
        default_callback_url: str | None = None,
        default_negative_tags: str | None = None,
        default_vocal_gender: str | None = None,
        default_style_weight: float | None = None,
        default_weirdness_constraint: float | None = None,
        default_audio_weight: float | None = None,
        default_persona_id: str | None = None,
        default_persona_model: str | None = None,
    ) -> None:
        self._api_key = api_key
        self._base = base_url.rstrip("/")
        self._generate_url = f"{self._base}/api/v1/generate"
        self._record_info_url = f"{self._base}/api/v1/generate/record-info"
        self._default_callback_url = default_callback_url
        self._default_negative_tags = default_negative_tags
        self._default_vocal_gender = default_vocal_gender
        self._default_style_weight = default_style_weight
        self._default_weirdness_constraint = default_weirdness_constraint
        self._default_audio_weight = default_audio_weight
        self._default_persona_id = default_persona_id
        self._default_persona_model = default_persona_model

    async def fetch_task_record(self, task_id: str) -> dict[str, Any]:
        """GET ``/api/v1/generate/record-info?taskId=`` — status i URL-e audio."""
        tid = (task_id or "").strip()
        if not tid:
            return {"code": 422, "msg": "empty taskId", "data": None}
        headers = {"Authorization": f"Bearer {self._api_key}"}
        async with httpx.AsyncClient(timeout=45.0) as client:
            r = await client.get(self._record_info_url, params={"taskId": tid}, headers=headers)
        text = r.text or ""
        try:
            parsed = r.json()
            payload = parsed if isinstance(parsed, dict) else {"_data": parsed}
        except json.JSONDecodeError:
            payload = {"code": r.status_code, "msg": text[:800], "data": None}
        if r.is_error:
            payload["_http_error"] = r.status_code
            payload["_body"] = text[:1200]
        return payload

    async def submit(self, request: MusicSubmitRequest) -> MusicSubmitResult:
        req = replace(
            request,
            call_back_url=request.call_back_url or self._default_callback_url,
            negative_tags=request.negative_tags or self._default_negative_tags,
            vocal_gender=request.vocal_gender or self._default_vocal_gender,
            style_weight=request.style_weight if request.style_weight is not None else self._default_style_weight,
            weirdness_constraint=(
                request.weirdness_constraint
                if request.weirdness_constraint is not None
                else self._default_weirdness_constraint
            ),
            audio_weight=request.audio_weight if request.audio_weight is not None else self._default_audio_weight,
            persona_id=request.persona_id or self._default_persona_id,
            persona_model=request.persona_model or self._default_persona_model,
        )
        cb = (req.call_back_url or "").strip()
        if not cb:
            return MusicSubmitResult(
                ok=False,
                http_status=400,
                payload={},
                error_detail=(
                    "KIE Suno API wymaga **callBackUrl** (zmienna ``KIE_MUSIC_CALLBACK_URL``). "
                    "Bez publicznego URL webhooka żądanie nie przejdzie walidacji — zob. "
                    "https://docs.kie.ai/suno-api/generate-music"
                ),
                task_id=None,
            )
        try:
            body = build_kie_generate_body(req)
        except ValueError as exc:
            code = str(exc)
            msg = {
                "missing_call_back_url": "Brak callBackUrl.",
                "empty_prompt_non_custom": "Tryb ``customMode: false`` wymaga niepustego promptu (max 500 znaków).",
            }.get(code, f"Błąd parametrów KIE: {code}")
            return MusicSubmitResult(
                ok=False, http_status=400, payload={}, error_detail=msg, task_id=None,
            )

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        logger.debug(
            "KIE.ai POST generate model=%s customMode=%s instrumental=%s title=%r",
            body.get("model"), body.get("customMode"), body.get("instrumental"), body.get("title"),
        )
        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await client.post(self._generate_url, json=body, headers=headers)
        text = r.text or ""
        payload: dict[str, Any]
        try:
            parsed = r.json()
            payload = parsed if isinstance(parsed, dict) else {"_data": parsed}
        except json.JSONDecodeError:
            payload = {"_raw": text[:4000]}

        ok_envelope, env_err = _kie_envelope_ok(payload)

        if r.is_error:
            detail = env_err or (text[:1200] if text else r.reason_phrase)
            logger.error("KIE.ai HTTP %s: %s", r.status_code, detail[:500])
            return MusicSubmitResult(
                ok=False,
                http_status=r.status_code,
                payload=payload,
                error_detail=detail,
                task_id=None,
            )

        if not ok_envelope:
            err = env_err or "KIE zwrócił code != 200"
            logger.error("KIE.ai logic error: %s", err[:500])
            return MusicSubmitResult(
                ok=False,
                http_status=r.status_code,
                payload=payload,
                error_detail=err,
                task_id=None,
            )

        task_id = _extract_kie_task_id(payload)
        return MusicSubmitResult(
            ok=True,
            http_status=r.status_code,
            payload=payload,
            error_detail=None,
            task_id=task_id,
        )
