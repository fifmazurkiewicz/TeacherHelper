from __future__ import annotations

from teacher_helper.use_cases.ports import VideoResult


class StubVideoGenerator:
    """Placeholder — rzeczywiste adaptery wideo (Runway, Sora) do dodania w przyszłości."""

    async def generate(
        self,
        prompt: str,
        duration_seconds: int = 5,
        style: str | None = None,
    ) -> VideoResult:
        return VideoResult(
            video_data=None,
            mime_type="video/mp4",
            prompt_used=prompt,
            model="stub",
            status="pending",
            poll_url=None,
            message=(
                f"[STUB] Generowanie wideo nie jest jeszcze dostępne. "
                f"Zapisano storyboard. Prompt: {prompt[:200]}"
            ),
        )
