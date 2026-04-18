"""MiniMax Music przez WaveSpeedAI — submit + polling."""

from __future__ import annotations

import asyncio
import time as _t
from typing import Any, Literal

import httpx

WavespeedMinimaxVariant = Literal["music-02", "music-2.6"]


def wavespeed_submit_url(base: str, variant: WavespeedMinimaxVariant) -> str:
    b = base.rstrip("/")
    slug = "music-02" if variant == "music-02" else "music-2.6"
    return f"{b}/api/v3/minimax/{slug}"


def _result_url(base: str, prediction_id: str) -> str:
    return f"{base.rstrip('/')}/api/v3/predictions/{prediction_id}/result"


def build_minimax_payload(
    variant: WavespeedMinimaxVariant,
    *,
    style: str,
    title: str,
    lyrics: str,
    instrumental: bool,
    duration_minutes: float | None = None,
) -> dict[str, Any]:
    st = (style or "").strip()
    ti = (title or "").strip() or "Benchmark track"
    ly = (lyrics or "").strip()
    hint = ""
    if duration_minutes is not None:
        d = float(duration_minutes)
        if d >= 0.25:
            lab = f"{d:.2f}".rstrip("0").rstrip(".")
            hint = f" Target length approx. {lab} minutes."
    if variant == "music-02":
        prompt = f"{st}. Song title: {ti}. Educational, clear vocals.{hint}"[:2900]
        return {
            "prompt": prompt,
            "lyrics": ly[:3000],
            "bitrate": 256000,
            "sample_rate": 44100,
        }
    prompt = f"{st}. Title: {ti}. Classroom-friendly, intelligible vocals.{hint}"[:2000]
    return {
        "prompt": prompt,
        "lyrics": ly[:3000],
        "bitrate": 256000,
        "sample_rate": 44100,
        "is_instrumental": bool(instrumental),
    }


async def wavespeed_minimax_generate(
    api_key: str,
    *,
    base_url: str = "https://api.wavespeed.ai",
    variant: WavespeedMinimaxVariant = "music-2.6",
    style: str,
    title: str,
    lyrics: str,
    instrumental: bool,
    poll_interval: float = 1.25,
    poll_timeout: float = 240.0,
) -> tuple[bytes | None, list[dict[str, Any]], str | None]:
    trace: list[dict[str, Any]] = []
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = build_minimax_payload(
        variant, style=style, title=title, lyrics=lyrics, instrumental=instrumental,
    )
    url_submit = wavespeed_submit_url(base_url, variant)
    trace.append(
        {
            "step": len(trace) + 1,
            "action": "POST",
            "url": url_submit,
            "headers": {"Authorization": "Bearer ***", "Content-Type": "application/json"},
            "json_body": payload,
        },
    )
    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.post(url_submit, json=payload, headers=headers)
        try:
            data = r.json()
        except Exception:
            data = {"_raw": (r.text or "")[:2000]}
        trace.append(
            {
                "step": len(trace) + 1,
                "action": "response_submit",
                "http_status": r.status_code,
                "body": data if isinstance(data, dict) else str(data)[:2000],
            },
        )
        if r.is_error:
            return None, trace, f"WaveSpeed submit HTTP {r.status_code}"
        if isinstance(data, dict) and data.get("code") not in (None, 200, "200"):
            return None, trace, f"WaveSpeed submit logic code={data.get('code')!r} message={data.get('message')!r}"

        pred_id: str | None = None
        if isinstance(data, dict):
            inner = data.get("data")
            if isinstance(inner, dict):
                pred_id = inner.get("id") or inner.get("task_id")
            pred_id = pred_id or data.get("id")

        if not pred_id:
            return None, trace, "Brak prediction id w odpowiedzi WaveSpeed"

        result_url = _result_url(base_url, pred_id)
        trace.append(
            {
                "step": len(trace) + 1,
                "action": "poll_loop",
                "get_url_template": _result_url(base_url, "<prediction_id>"),
                "prediction_id": pred_id,
            },
        )

        deadline = _t.monotonic() + poll_timeout
        last_status: str | None = None
        outputs: list[str] | None = None

        while _t.monotonic() < deadline:
            gr = await client.get(result_url, headers={"Authorization": f"Bearer {api_key}"})
            try:
                gdata = gr.json()
            except Exception:
                gdata = {"_raw": (gr.text or "")[:1500]}
            if isinstance(gdata, dict):
                gd = gdata.get("data")
                if isinstance(gd, dict):
                    last_status = str(gd.get("status") or "")
                    outs = gd.get("outputs") or gd.get("output")
                    if isinstance(outs, list):
                        outputs = [str(u) for u in outs if u]
                    elif isinstance(outs, str) and outs:
                        outputs = [outs]
            if last_status == "completed" and outputs:
                break
            if last_status == "failed":
                err = ""
                if isinstance(gdata, dict):
                    gd = gdata.get("data")
                    if isinstance(gd, dict):
                        err = str(gd.get("error") or "")
                return None, trace, err or "WaveSpeed status=failed"
            await asyncio.sleep(poll_interval)

        if not outputs:
            return None, trace, f"Timeout / brak URL (ostatni status={last_status!r})"

        audio_url = outputs[0]
        trace.append({"step": len(trace) + 1, "action": "GET_audio", "url": audio_url})

        ar = await client.get(audio_url, follow_redirects=True, timeout=180.0)
        ar.raise_for_status()
        content = ar.content
        if len(content) > 40 * 1024 * 1024:
            return None, trace, "Plik audio zbyt duży"
        return content, trace, None


async def wavespeed_minimax_generate_from_payload(
    api_key: str,
    *,
    base_url: str = "https://api.wavespeed.ai",
    variant: WavespeedMinimaxVariant = "music-2.6",
    payload: dict[str, Any],
    poll_interval: float = 1.25,
    poll_timeout: float = 240.0,
) -> tuple[bytes | None, list[dict[str, Any]], str | None]:
    """To samo co ``wavespeed_minimax_generate``, ale JSON z zewnątrz (po edycji)."""
    trace: list[dict[str, Any]] = []
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    url_submit = wavespeed_submit_url(base_url, variant)
    trace.append(
        {
            "step": len(trace) + 1,
            "action": "POST",
            "url": url_submit,
            "headers": {"Authorization": "Bearer ***", "Content-Type": "application/json"},
            "json_body": payload,
        },
    )
    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.post(url_submit, json=payload, headers=headers)
        try:
            data = r.json()
        except Exception:
            data = {"_raw": (r.text or "")[:2000]}
        trace.append(
            {
                "step": len(trace) + 1,
                "action": "response_submit",
                "http_status": r.status_code,
                "body": data if isinstance(data, dict) else str(data)[:2000],
            },
        )
        if r.is_error:
            return None, trace, f"WaveSpeed submit HTTP {r.status_code}"
        if isinstance(data, dict) and data.get("code") not in (None, 200, "200"):
            return None, trace, f"WaveSpeed submit logic code={data.get('code')!r} message={data.get('message')!r}"

        pred_id: str | None = None
        if isinstance(data, dict):
            inner = data.get("data")
            if isinstance(inner, dict):
                pred_id = inner.get("id") or inner.get("task_id")
            pred_id = pred_id or data.get("id")

        if not pred_id:
            return None, trace, "Brak prediction id w odpowiedzi WaveSpeed"

        result_url = _result_url(base_url, pred_id)
        trace.append(
            {
                "step": len(trace) + 1,
                "action": "poll_loop",
                "get_url_template": _result_url(base_url, "<prediction_id>"),
                "prediction_id": pred_id,
            },
        )

        deadline = _t.monotonic() + poll_timeout
        last_status: str | None = None
        outputs: list[str] | None = None

        while _t.monotonic() < deadline:
            gr = await client.get(result_url, headers={"Authorization": f"Bearer {api_key}"})
            try:
                gdata = gr.json()
            except Exception:
                gdata = {"_raw": (gr.text or "")[:1500]}
            if isinstance(gdata, dict):
                gd = gdata.get("data")
                if isinstance(gd, dict):
                    last_status = str(gd.get("status") or "")
                    outs = gd.get("outputs") or gd.get("output")
                    if isinstance(outs, list):
                        outputs = [str(u) for u in outs if u]
                    elif isinstance(outs, str) and outs:
                        outputs = [outs]
            if last_status == "completed" and outputs:
                break
            if last_status == "failed":
                err = ""
                if isinstance(gdata, dict):
                    gd = gdata.get("data")
                    if isinstance(gd, dict):
                        err = str(gd.get("error") or "")
                return None, trace, err or "WaveSpeed status=failed"
            await asyncio.sleep(poll_interval)

        if not outputs:
            return None, trace, f"Timeout / brak URL (ostatni status={last_status!r})"

        audio_url = outputs[0]
        trace.append({"step": len(trace) + 1, "action": "GET_audio", "url": audio_url})

        ar = await client.get(audio_url, follow_redirects=True, timeout=180.0)
        ar.raise_for_status()
        content = ar.content
        if len(content) > 40 * 1024 * 1024:
            return None, trace, "Plik audio zbyt duży"
        return content, trace, None
