from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ToolCall:
    """Pojedyncze wywołanie narzędzia zwrócone przez model."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True, slots=True)
class LlmCompletion:
    """Wynik pojedynczego wywołania LLM (tekst + metadane zużycia + opcjonalne tool calls)."""

    text: str
    provider: str
    model: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str | None = None

    def resolved_total_tokens(self) -> int | None:
        if self.total_tokens is not None:
            return self.total_tokens
        if self.prompt_tokens is not None and self.completion_tokens is not None:
            return self.prompt_tokens + self.completion_tokens
        return None


ToolDefinition = dict[str, Any]


@runtime_checkable
class LlmClientPort(Protocol):
    """Port do wywołań modelu językowego (implementacja w infrastructure)."""

    async def complete(self, system: str, user: str) -> LlmCompletion:
        """Zwraca treść odpowiedzi oraz opcjonalne liczniki tokenów."""
        ...

    async def complete_with_tools(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[ToolDefinition],
    ) -> LlmCompletion:
        """Wywołanie z definicjami narzędzi (OpenAI function calling format)."""
        ...


# ---------------------------------------------------------------------------
# Porty generowania mediów (grafika / wideo)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ImageResult:
    """Wynik generowania obrazu przez zewnętrzne API."""

    image_data: bytes
    mime_type: str
    prompt_used: str
    model: str
    revised_prompt: str | None = None


@dataclass(frozen=True, slots=True)
class VideoResult:
    """Wynik generowania wideo (lub status asynchronicznego zadania)."""

    video_data: bytes | None
    mime_type: str
    prompt_used: str
    model: str
    status: str  # "completed" | "pending" | "failed"
    poll_url: str | None = None
    message: str | None = None


@runtime_checkable
class ImageGeneratorPort(Protocol):
    """Port generowania obrazów — produkcyjnie OpenRouter (modele z wyjściem image)."""

    async def generate(
        self,
        prompt: str,
        style: str | None = None,
        size: str = "1024x1024",
        user_id: UUID | None = None,
    ) -> ImageResult: ...


@runtime_checkable
class VideoGeneratorPort(Protocol):
    """Port generowania wideo — wymienne adaptery (Runway, Pika, Sora)."""

    async def generate(
        self,
        prompt: str,
        duration_seconds: int = 5,
        style: str | None = None,
    ) -> VideoResult: ...


# ---------------------------------------------------------------------------
# Muzyka (KIE.ai / Suno‑like API)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MusicSubmitRequest:
    """Żądanie POST ``/api/v1/generate`` (kie.ai) — pola zgodne z dokumentacją API."""

    prompt: str
    title: str
    style: str | None = None
    instrumental: bool = True
    model: str = "V4_5ALL"
    custom_mode: bool = True
    call_back_url: str | None = None
    negative_tags: str | None = None
    vocal_gender: str | None = None
    style_weight: float | None = None
    weirdness_constraint: float | None = None
    audio_weight: float | None = None
    persona_id: str | None = None
    persona_model: str | None = None


@dataclass(frozen=True, slots=True)
class MusicSubmitResult:
    """Odpowiedź HTTP z KIE (sukces lub błąd — ``payload`` to sparsowany JSON albo ``{"_raw": "..."}``).

    API KIE zwykle zwraca kopertę ``{ "code": 200, "msg": "success", "data": { "taskId": "..." } }`` —
    pole ``task_id`` wypełniamy z ``data.taskId`` przy sukcesie.
    """

    ok: bool
    http_status: int
    payload: dict[str, Any]
    error_detail: str | None = None
    task_id: str | None = None


@runtime_checkable
class MusicGeneratorPort(Protocol):
    """Port zgłoszenia generacji utworu do zewnętrznego API (np. KIE.ai)."""

    async def submit(self, request: MusicSubmitRequest) -> MusicSubmitResult: ...


# ---------------------------------------------------------------------------
# Dźwięki / efekty audio (np. ElevenLabs Text to Sound)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SoundResult:
    """Wynik generowania krótkiego efektu dźwiękowego."""

    audio_data: bytes
    mime_type: str
    prompt_used: str
    model: str
    duration_seconds: int


@runtime_checkable
class SoundGeneratorPort(Protocol):
    """Port generowania krótkich efektów dźwiękowych (np. trzask ognia, deszcz)."""

    async def generate(
        self,
        prompt: str,
        duration_seconds: int = 10,
        *,
        mode: str = "sfx",
    ) -> SoundResult: ...
