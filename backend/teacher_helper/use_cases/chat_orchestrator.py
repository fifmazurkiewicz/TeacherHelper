from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from teacher_helper.infrastructure.db.file_ops import (
    category_for_module,
    index_file_content,
    load_attached_context,
    persist_export_as_new_file,
    semantic_search_chunks,
)
from teacher_helper.infrastructure.db.llm_usage import record_llm_usage_event
from teacher_helper.infrastructure.music_kie import (
    KIE_STATUSES_WITH_POSSIBLE_AUDIO,
    KIE_TERMINAL_FAIL_STATUSES,
    download_audio_url,
    parse_task_record,
)
from teacher_helper.infrastructure.db.models import FileAssetORM, FileStatus, ProjectORM
from teacher_helper.infrastructure.storage.local import LocalStorage
from teacher_helper.config import get_settings
from teacher_helper.use_cases.ports import (
    ImageGeneratorPort,
    LlmClientPort,
    MusicGeneratorPort,
    MusicSubmitRequest,
    ToolDefinition,
    VideoGeneratorPort,
)
from teacher_helper.security.resource_confirmation import (
    ACTION_DELETE_PROJECT,
    RESOURCE_PROJECT,
    create_project_creation_token,
    create_resource_confirmation_token,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt i definicje narzędzi
# ---------------------------------------------------------------------------

ORCHESTRATOR_SYSTEM = """\
Jesteś Asystentem Nauczyciela AI. Pomagasz polskim nauczycielom tworzyć materiały edukacyjne.

## Twoje narzędzia

Masz dostęp do narzędzi (tool calling). Używaj ich zamiast pisania JSON:

- **ask_clarification** — gdy potrzebujesz więcej informacji od nauczyciela.
- **prepare_create_teacher_project** — przygotuj utworzenie folderu projektu (nazwa + opis). **Nie tworzy** projektu — użytkownik musi potwierdzić w aplikacji. Użyj, gdy użytkownik chce „zapisać paczkę”, folder z materiałami itd.
- **prepare_delete_teacher_project** — przygotuj usunięcie projektu (**project_id** UUID albo **project_name**). **Nie usuwa** — wymaga potwierdzenia użytkownika.
- **search_library_fragments** — wyszukaj w zindeksowanej bibliotece plików użytkownika (semantycznie). Użyj TYLKO gdy pytanie dotyczy treści z przesłanych materiałów, podręcznika, własnych notatek w systemie albo „co mam w plikach”. Nie wywołuj przy zwykłej rozmowie bez potrzeby odwołania do biblioteki.
- **export_library_file** — zapisz kopię istniejącego pliku z biblioteki jako PDF/DOCX/TXT/PPTX (podaj file_id UUID lub pomiń, by użyć pliku utworzonego w tej samej turze).
- **generate_scenario** — scenariusz przedstawienia.
- **generate_graphics** — grafika (plakat, ilustracja, scenografia).
- **generate_video** — storyboard/prompt wideo.
- **generate_music** — KIE Suno API (``/api/v1/generate``): tekst/prompt, wymagany publiczny **callBackUrl**; w bibliotece najpierw **.txt** (taskId, JSON); przy włączonym pollingu backend może dociągnąć **.mp3** z „record-info”.
- **generate_poetry** — wiersz do recytacji.
- **generate_presentation** — plan prezentacji (slajdy).
- **reply_to_user** — odpowiedź tekstowa bez generowania materiałów.

## Zasady

1. Gdy wiadomość jest OGÓLNA → użyj ask_clarification.
2. Gdy użytkownik chce zestaw materiałów „do zapisania” → **prepare_create_teacher_project**, potem (po potwierdzeniu przez użytkownika) narzędzia generujące; w jednej turze możesz przygotować projekt i wygenerować pliki — pliki trafią do aktywnego projektu dopiero po jego utworzeniu przez użytkownika.
3. Przy **każdym** narzędziu ``generate_*`` ZAWSZE podaj pole **material_title**: krótki, opisowy tytuł pliku po polsku (2–12 słów), widoczny w bibliotece — bez znaku ``/``, bez rozszerzenia (np. „Scenariusz jasełka klasa 4”, „Piosenka o zimie SP”).
4. Gdy masz wystarczające informacje → użyj odpowiedniego narzędzia generowania (z **material_title**).
5. Możesz wywołać WIELE narzędzi jednocześnie (np. prepare_create_teacher_project + generate_scenario + generate_music).
6. Eksport do PDF/DOCX: export_library_file (file_id z wcześniejszej wiadomości lub pominięty po wygenerowaniu pliku w tej samej odpowiedzi).
7. Gdy w tej samej turze szukasz w bibliotece i generujesz materiał — najpierw **search_library_fragments**, potem narzędzie generujące, żeby moduł dostał znalezione fragmenty w kontekście.
8. Nie łącz **search_library_fragments** z **reply_to_user** w jednej turze — odpowiedź tekstowa byłaby ustalana bez wglądu w wyniki wyszukiwania. Szukaj w bibliotece osobno albo użyj samego **reply_to_user**, gdy biblioteka nie jest potrzebna.
9. AKTYWNIE sugeruj powiązane materiały (scenariusz → piosenka, plakat).
10. Odpowiadaj po polsku, przyjaźnie, zwięźle."""

TOOL_DEFINITIONS: list[ToolDefinition] = [
    {"type": "function", "function": {
        "name": "ask_clarification",
        "description": "Zadaj pytanie doprecyzowujące nauczycielowi, gdy brakuje informacji.",
        "parameters": {"type": "object", "properties": {
            "question": {"type": "string", "description": "Pytanie do nauczyciela"},
            "suggestions": {"type": "array", "items": {"type": "string"},
                            "description": "Sugestie dodatkowych materiałów"},
        }, "required": ["question"]},
    }},
    {"type": "function", "function": {
        "name": "reply_to_user",
        "description": "Odpowiedz nauczycielowi tekstem (bez generowania materiałów).",
        "parameters": {"type": "object", "properties": {
            "message": {"type": "string", "description": "Treść odpowiedzi"},
        }, "required": ["message"]},
    }},
    {"type": "function", "function": {
        "name": "search_library_fragments",
        "description": (
            "Semantyczne wyszukiwanie po treści plików użytkownika w bibliotece (nie dotyczy plików przypiętych do wiadomości — te są już w kontekście). "
            "Wywołuj tylko, gdy potrzebujesz fragmentów z zindeksowanych materiałów."
        ),
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "Zapytanie wyszukiwawcze po sensie (np. temat lekcji, pojęcie z notatek)"},
        }, "required": ["query"]},
    }},
    {"type": "function", "function": {
        "name": "prepare_create_teacher_project",
        "description": (
            "Przygotuj utworzenie projektu (folderu) na materiały — użytkownik musi potwierdzić w UI; dopiero potem projekt istnieje. "
            "Użyj przed zapisem wielu artefaktów do jednego miejsca."
        ),
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string", "description": "Krótka nazwa projektu"},
            "description": {"type": "string", "description": "Opcjonalny opis"},
        }, "required": ["name"]},
    }},
    {"type": "function", "function": {
        "name": "prepare_delete_teacher_project",
        "description": (
            "Przygotuj usunięcie projektu użytkownika — nie usuwa od razu; wymaga potwierdzenia. "
            "Podaj project_id (UUID) albo dokładną project_name (jak na liście projektów)."
        ),
        "parameters": {"type": "object", "properties": {
            "project_id": {"type": "string", "description": "UUID projektu do usunięcia"},
            "project_name": {"type": "string", "description": "Dokładna nazwa projektu (gdy brak UUID)"},
        }, "required": []},
    }},
    {"type": "function", "function": {
        "name": "export_library_file",
        "description": "Wyeksportuj plik z biblioteki użytkownika do PDF, DOCX, TXT lub PPTX i zapisz jako nowy plik.",
        "parameters": {"type": "object", "properties": {
            "file_id": {"type": "string", "description": "UUID pliku źródłowego (opcjonalnie — domyślnie ostatnio utworzony w tej turze)"},
            "format": {"type": "string", "enum": ["pdf", "docx", "txt", "pptx"], "description": "Format wyjściowy"},
        }, "required": ["format"]},
    }},
    {"type": "function", "function": {
        "name": "generate_scenario",
        "description": "Wygeneruj scenariusz przedstawienia szkolnego.",
        "parameters": {"type": "object", "properties": {
            "topic": {"type": "string", "description": "Temat przedstawienia"},
            "material_title": {
                "type": "string",
                "description": "Tytuł pliku w bibliotece (po polsku, 2–12 słów, bez / i bez .txt), np. Scenariusz jasełka klasa 4",
            },
            "age_group": {"type": "string", "description": "Grupa wiekowa / klasa"},
            "duration_minutes": {"type": "integer", "description": "Czas trwania w minutach"},
            "style": {"type": "string", "description": "Styl (komedia, musical, dramat)"},
        }, "required": ["topic", "material_title"]},
    }},
    {"type": "function", "function": {
        "name": "generate_graphics",
        "description": "Wygeneruj grafikę edukacyjną (plakat, ilustrację, scenografię).",
        "parameters": {"type": "object", "properties": {
            "description": {"type": "string", "description": "Szczegółowy opis grafiki po polsku"},
            "material_title": {
                "type": "string",
                "description": "Krótki tytuł pliku w bibliotece, np. Plakat bezpieczeństwo w szkole",
            },
            "style": {"type": "string",
                       "description": "Styl: cartoon, realistic, watercolor, flat, 3d, pastel, comic"},
            "size": {"type": "string", "enum": ["1024x1024", "1792x1024", "1024x1792"],
                     "description": "Rozdzielczość: kwadrat, poziom, pion"},
        }, "required": ["description", "material_title"]},
    }},
    {"type": "function", "function": {
        "name": "generate_video",
        "description": "Wygeneruj storyboard/prompt wideo edukacyjnego.",
        "parameters": {"type": "object", "properties": {
            "description": {"type": "string", "description": "Opis wideo (scena, akcja, nastrój)"},
            "material_title": {
                "type": "string",
                "description": "Tytuł pliku w bibliotece, np. Storyboard film o recyklingu",
            },
            "duration_seconds": {"type": "integer", "description": "Czas trwania (5-30s)"},
            "style": {"type": "string",
                       "description": "Styl: animation, realistic, cartoon, cinematic, whiteboard"},
        }, "required": ["description", "material_title"]},
    }},
    {"type": "function", "function": {
        "name": "generate_music",
        "description": (
            "Wygeneruj prompt muzyczny i tekst piosenki; zapis w bibliotece jako .txt z metadanymi. "
            "Przy KIE: wyślij zadanie generacji — MP3 nie wraca synchronicznie; w pliku będzie taskId / odpowiedź JSON."
        ),
        "parameters": {"type": "object", "properties": {
            "topic": {"type": "string", "description": "Temat piosenki"},
            "material_title": {
                "type": "string",
                "description": "Tytuł pliku w bibliotece, np. Piosenka o zimie klasa 2",
            },
            "style": {"type": "string", "description": "Styl muzyczny"},
            "age_group": {"type": "string", "description": "Grupa wiekowa"},
            "instrumental": {
                "type": "boolean",
                "description": "true = tylko instrumenty; false = z wokalem (gdy brak — heurystyka z treści)",
            },
        }, "required": ["topic", "material_title"]},
    }},
    {"type": "function", "function": {
        "name": "generate_poetry",
        "description": "Napisz wiersz do recytacji.",
        "parameters": {"type": "object", "properties": {
            "topic": {"type": "string", "description": "Temat wiersza"},
            "material_title": {
                "type": "string",
                "description": "Tytuł pliku w bibliotece, np. Wiersz o jesieni SP",
            },
            "form": {"type": "string", "description": "Forma (rymowany, biały, haiku)"},
            "length": {"type": "string", "description": "Długość (krótki, średni, długi)"},
        }, "required": ["topic", "material_title"]},
    }},
    {"type": "function", "function": {
        "name": "generate_presentation",
        "description": "Wygeneruj plan prezentacji (slajdy).",
        "parameters": {"type": "object", "properties": {
            "topic": {"type": "string", "description": "Temat prezentacji"},
            "material_title": {
                "type": "string",
                "description": "Tytuł pliku w bibliotece, np. Prezentacja ekologia klasa 5",
            },
            "slides_count": {"type": "integer", "description": "Liczba slajdów"},
            "audience": {"type": "string", "description": "Odbiorcy (klasa, wiek)"},
        }, "required": ["topic", "material_title"]},
    }},
]

MODULE_SYSTEM_PROMPTS: dict[str, str] = {
    "scenario": (
        "Jesteś dramaturgiem dla dzieci i młodzieży. Napisz kompletny scenariusz "
        "przedstawienia: postacie, dialogi, didaskalia, podział na sceny. Po polsku. "
        "Tytuł pliku w bibliotece został już podany w argumencie narzędzia ``material_title`` — treść scenariusza ma z nim być spójna tematycznie."
    ),
    "graphics": (
        "Jesteś ekspertem od generowania obrazów AI. Na podstawie opisu wygeneruj WYŁĄCZNIE JSON "
        '(bez markdown, bez ```): {"prompt_en": "<szczegółowy prompt po angielsku, '
        'zoptymalizowany pod DALL-E 3, 1-2 zdania, dużo detali wizualnych>", '
        '"style_notes": "<notatki o stylu po polsku>", '
        '"description_pl": "<krótki opis po polsku co przedstawia grafika>"}\n'
        "Prompt angielski: kolory, kompozycja, oświetlenie, perspektywa. "
        "Dla dzieci: jasne kolory, przyjazne postacie, brak przemocy."
    ),
    "video": (
        "Jesteś ekspertem od wideo AI. Na podstawie opisu wygeneruj WYŁĄCZNIE JSON "
        '(bez markdown, bez ```): {"prompt_en": "<prompt wideo po angielsku>", '
        '"storyboard": ["<scena 1>", "<scena 2>", ...], '
        '"style_notes": "<notatki>", "description_pl": "<opis po polsku>"}'
    ),
    "music": (
        "Tworzysz materiał muzyczny dla nauczyciela i **osobno** treść trafiającą do API Suno jako lyrics. "
        "Zwróć wyłącznie JSON (bez markdown, bez ```): "
        '{"style_en": "<jeden akapit po angielsku: styl, tempo, instrumentacja, wokal — pod pole style Suno>", '
        '"lyrics_pl": "<wyłącznie słowa piosenki po polsku ze znacznikami [Intro]/[Verse]/[Chorus]; '
        'bez nagłówków dokumentu, bez zdań typu «Oto gotowy prompt», bez opisu Suno/Udio>", '
        '"material_md": "<markdown dla nauczyciela: wstęp, informacje o utworze, wskazówki techniczne; '
        'możesz powtórzyć tekst piosenki dla czytelności>"}. '
        "Pole lyrics_pl nie może zawierać wstępów ani instrukcji — inaczej model „nuci” cały dokument. "
        "Dopasuj tematykę do ``material_title`` z narzędzia."
    ),
    "poetry": "Napisz wiersz do recytacji zgodnie z prośbą. Krótki wstęp i treść wiersza.",
    "presentation": "Napisz plan prezentacji (nagłówki slajdów + punktory). Markdown.",
}

TOOL_TO_MODULE: dict[str, str] = {
    "generate_scenario": "scenario",
    "generate_graphics": "graphics",
    "generate_video": "video",
    "generate_music": "music",
    "generate_poetry": "poetry",
    "generate_presentation": "presentation",
}

# Gdy brak wierszy w DB po zapisie (rzadkie) — bez żargonu konfiguracyjnego.
_MODULE_REPLY_FALLBACK: dict[str, str] = {
    "music": "Zapisano materiały w bibliotece. Otwórz „Moje materiały”, aby zobaczyć plik .txt i ewentualnie .mp3.",
    "graphics": "Zapisano plik w „Moje materiały”.",
    "video": "Zapisano materiał wideo w „Moje materiały”.",
    "scenario": "Zapisano scenariusz w „Moje materiały”.",
    "poetry": "Zapisano wiersz w „Moje materiały”.",
    "presentation": "Zapisano plan prezentacji w „Moje materiały”.",
}


def _brief_file_label(mime: str | None, name: str) -> str:
    m = (mime or "").lower()
    nl = name.lower()
    if m.startswith("audio/") or nl.endswith(".mp3") or nl.endswith(".wav") or nl.endswith(".ogg"):
        return "nagranie audio"
    if m.startswith("image/"):
        return "obraz"
    if m.startswith("video/") or nl.endswith(".mp4") or nl.endswith(".webm"):
        return "wideo"
    if nl.endswith(".txt"):
        return "tekst (raport, metadane)"
    if nl.endswith(".json"):
        return "plik JSON"
    return "plik"


def _music_kie_status_note(
    extra: dict[str, Any],
    mp3_bytes: bytes | None,
    result: Any,
    *,
    poll_enabled: bool,
    music_gen_enabled: bool,
) -> str | None:
    """Krótki komunikat dla czatu, gdy nie ma MP3 albo KIE zwróciło błąd (np. limity, timeout)."""
    if mp3_bytes:
        return None
    if not music_gen_enabled:
        return (
            "Generacja audio przez KIE nie jest skonfigurowana (brak klucza API) — zapisano tylko materiał tekstowy."
        )
    if extra.get("kie_error"):
        return f"KIE — problem przy uruchomieniu generacji:\n{str(extra['kie_error'])[:900]}"
    if extra.get("kie_download_error"):
        return f"KIE — nie udało się pobrać pliku audio:\n{str(extra['kie_download_error'])[:700]}"
    if extra.get("kie_poll_error"):
        return (
            "KIE — zadanie generacji audio nie zakończyło się powodzeniem albo zwrócono błąd "
            "(np. wyczerpane środki, odrzucona treść). Szczegóły:\n"
            f"{str(extra['kie_poll_error'])[:900]}"
        )
    if result and getattr(result, "ok", False) and getattr(result, "task_id", None):
        if not poll_enabled:
            return (
                "Automatyczne oczekiwanie na MP3 jest wyłączone (KIE_MUSIC_POLL_TIMEOUT_SECONDS = 0). "
                "Gdy utwór będzie gotów, użyj taskId z pliku .txt w „Moje materiały” (import z KIE)."
            )
        st = extra.get("kie_poll_status")
        if st == "SUCCESS" and not extra.get("kie_audio_urls"):
            return (
                "KIE zgłosił zakończenie zadania, ale w odpowiedzi nie było jeszcze adresu audio. "
                "Za chwilę spróbuj ponownie pobrać MP3 po taskId w „Moje materiały”."
            )
        return (
            "W ustawionym czasie nie pojawiło się jeszcze gotowe audio od KIE (generacja często trwa dłużej niż timeout). "
            "To nie musi być błąd konta — sprawdź saldo i limity w panelu KIE oraz pole taskId w pliku .txt; "
            "możesz ponowić import MP3 w „Moje materiały”."
        )
    return None


def _infer_instrumental_music(llm_text: str, tool_args: dict[str, Any], default_instrumental: bool) -> bool:
    v = tool_args.get("instrumental")
    if isinstance(v, bool):
        return v
    t = llm_text.lower()
    if any(k in t for k in ("zwrotka", "refren", "tekst piosenki", "słowa piosenki", "lyrics:", "verse")):
        return False
    return default_instrumental


def _sanitize_filename_stem(raw: str, max_len: int = 100) -> str:
    """Bezpieczna nazwa pliku (bez ścieżki, znaków zabronionych w Windows)."""
    s = (raw or "").strip()
    if not s:
        return ""
    s = re.sub(r'[\x00-\x1f<>:"/\\|?*]', "", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = s.rstrip(". ")
    if len(s) > max_len:
        s = s[:max_len].rstrip(". ")
    return s


async def _resolve_user_project_for_delete(
    session: AsyncSession, user_id: UUID, tool_args: dict[str, Any],
) -> tuple[ProjectORM | None, str | None]:
    """Dopasowanie projektu do usunięcia: ``project_id`` (UUID) albo dokładna ``project_name`` (bez wielkości liter)."""
    pid_raw = tool_args.get("project_id")
    if pid_raw not in (None, ""):
        try:
            uid = UUID(str(pid_raw).strip())
        except (ValueError, TypeError):
            return None, "Nieprawidłowy project_id — wymagany UUID."
        row = await session.get(ProjectORM, uid)
        if row is None or row.user_id != user_id:
            return None, "Projekt nie znaleziony lub nie należy do Ciebie."
        return row, None
    pname = tool_args.get("project_name")
    if pname is None or not str(pname).strip():
        return None, "Podaj **project_id** (UUID) albo **project_name** (dokładna nazwa z listy projektów)."
    q = str(pname).strip()
    stmt = (
        select(ProjectORM)
        .where(ProjectORM.user_id == user_id)
        .where(func.lower(ProjectORM.name) == q.lower())
    )
    rows = list((await session.scalars(stmt)).all())
    if len(rows) == 1:
        return rows[0], None
    if len(rows) == 0:
        return None, f"Nie znaleziono projektu o nazwie „{q}”."
    return None, f"Wiele projektów pasuje do „{q}” — podaj **project_id** (UUID)."


def _resolve_file_stem(module: str, tool_args: dict[str, Any] | None) -> str:
    """Tytuł pliku z argumentów narzędzia (LLM) lub sensowny fallback."""
    ta = tool_args or {}
    mt = ta.get("material_title")
    if isinstance(mt, str):
        stem = _sanitize_filename_stem(mt)
        if stem:
            return stem
    if module == "music":
        return _sanitize_filename_stem(str(ta.get("topic") or "muzyka")) or "muzyka"
    if module == "scenario":
        return _sanitize_filename_stem(str(ta.get("topic") or "scenariusz")) or "scenariusz"
    if module == "graphics":
        d = str(ta.get("description") or "grafika")[:140]
        return _sanitize_filename_stem(d) or "grafika"
    if module == "video":
        d = str(ta.get("description") or "wideo")[:140]
        return _sanitize_filename_stem(d) or "wideo"
    if module == "poetry":
        return _sanitize_filename_stem(str(ta.get("topic") or "wiersz")) or "wiersz"
    if module == "presentation":
        return _sanitize_filename_stem(str(ta.get("topic") or "prezentacja")) or "prezentacja"
    return _sanitize_filename_stem(module) or module


def _tool_call_sort_key(tc: Any) -> tuple[int, str]:
    name = tc.name or ""
    if name in ("prepare_create_teacher_project", "prepare_delete_teacher_project"):
        return (0, tc.id or "")
    if name == "search_library_fragments":
        return (1, tc.id or "")
    if name in TOOL_TO_MODULE:
        return (2, tc.id or "")
    if name == "export_library_file":
        return (3, tc.id or "")
    if name in ("reply_to_user", "ask_clarification"):
        return (4, tc.id or "")
    return (2, tc.id or "")


# ---------------------------------------------------------------------------
# Wynik czatu
# ---------------------------------------------------------------------------

@dataclass
class ChatResult:
    reply: str
    created_file_ids: list[UUID]
    run_modules: list[str]
    needs_clarification: bool
    clarification_question: str | None
    dry_run: bool = False
    side_effects_skipped: bool = False
    linked_project_id: UUID | None = None
    pending_project_creation: dict[str, Any] | None = None
    pending_project_deletion: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class ChatOrchestratorUseCase:
    def __init__(
        self,
        llm: LlmClientPort,
        storage: LocalStorage,
        image_gen: ImageGeneratorPort | None = None,
        video_gen: VideoGeneratorPort | None = None,
        music_gen: MusicGeneratorPort | None = None,
        llm_modules: LlmClientPort | None = None,
    ) -> None:
        self._llm = llm
        self._llm_modules = llm_modules or llm
        self._storage = storage
        self._image_gen = image_gen
        self._video_gen = video_gen
        self._music_gen = music_gen

    # --- Główny punkt wejścia ---

    async def execute(
        self,
        session: AsyncSession,
        user_id: UUID,
        message: str,
        project_id: UUID | None = None,
        attached_file_ids: list[UUID] | None = None,
        history: list[tuple[str, str]] | None = None,
        dry_run: bool = False,
    ) -> ChatResult:
        attached_file_ids = attached_file_ids or []
        history = history or []

        logger.debug("Orchestrator.execute: user=%s project=%s msg=%r", user_id, project_id, message[:120])
        context_block = await self._build_context(session, user_id, message, attached_file_ids, project_id)
        logger.debug("Context block length: %d chars", len(context_block))

        api_messages: list[dict[str, Any]] = [
            {"role": role, "content": content} for role, content in history[-20:]
        ]
        user_content = f"{context_block}\n{message.strip()}" if context_block else message.strip()
        api_messages.append({"role": "user", "content": user_content})

        logger.debug("Calling LLM (%s) with %d messages, %d tools", type(self._llm).__name__, len(api_messages), len(TOOL_DEFINITIONS))
        completion = await self._llm.complete_with_tools(ORCHESTRATOR_SYSTEM, api_messages, TOOL_DEFINITIONS)
        logger.debug(
            "LLM response: provider=%s model=%s finish=%s tool_calls=%d text_len=%d tokens=%s",
            completion.provider, completion.model, completion.finish_reason,
            len(completion.tool_calls), len(completion.text or ""),
            completion.resolved_total_tokens(),
        )
        await record_llm_usage_event(
            session, user_id=user_id, call_kind="orchestrator", module_name=None,
            completion=completion, system_text=ORCHESTRATOR_SYSTEM, user_text=user_content, dry_run=dry_run,
        )

        return await self._process_tool_calls(
            session, user_id, project_id, message, context_block, completion, dry_run,
        )

    # --- Budowanie kontekstu ---

    @staticmethod
    async def _build_context(
        session: AsyncSession, user_id: UUID, message: str,
        attached_file_ids: list[UUID], project_id: UUID | None,
    ) -> str:
        parts: list[str] = []
        ctx_attached = await load_attached_context(session, user_id, attached_file_ids, message)
        if ctx_attached:
            parts.append(f"=== Załączone pliki ===\n{ctx_attached}")
        return "\n".join(parts)

    # --- Przetwarzanie tool calls ---

    async def _process_tool_calls(
        self, session: AsyncSession, user_id: UUID, project_id: UUID | None,
        user_message: str, context: str, completion: Any, dry_run: bool,
    ) -> ChatResult:
        if not completion.tool_calls:
            return ChatResult(
                reply=completion.text or "Przepraszam, nie zrozumiałem. Możesz powtórzyć?",
                created_file_ids=[], run_modules=[],
                needs_clarification=False, clarification_question=None, dry_run=dry_run,
                linked_project_id=None,
                pending_project_creation=None,
                pending_project_deletion=None,
            )

        reply_parts: list[str] = []
        created: list[UUID] = []
        run_modules: list[str] = []
        needs_clarification = False
        clarification_question: str | None = None
        side_effects_skipped = False
        active_project_id: UUID | None = project_id
        linked_project_id: UUID | None = None
        last_created_file_id: UUID | None = None
        dynamic_context = context
        pending_project_creation: dict[str, Any] | None = None
        pending_project_deletion: dict[str, Any] | None = None

        sorted_calls = sorted(completion.tool_calls, key=_tool_call_sort_key)
        for tc in sorted_calls:
            logger.debug("Processing tool call: %s (id=%s) args_keys=%s", tc.name, tc.id, list(tc.arguments.keys()))
            if tc.name == "ask_clarification":
                needs_clarification = True
                q = tc.arguments.get("question", "")
                suggestions = tc.arguments.get("suggestions", [])
                clarification_question = q
                text = f"{q}\n\nMogę też przygotować: {', '.join(suggestions)}." if suggestions else q
                reply_parts.append(text)

            elif tc.name == "reply_to_user":
                reply_parts.append(tc.arguments.get("message", ""))

            elif tc.name == "search_library_fragments":
                q = (tc.arguments.get("query") or "").strip() or user_message.strip()
                if dry_run:
                    side_effects_skipped = True
                    reply_parts.append("[Dry-run] Wyszukiwanie w bibliotece zostało pominięte.")
                    continue
                try:
                    search_hits = await semantic_search_chunks(
                        session, user_id, q, top_k=6, project_id=active_project_id,
                    )
                except Exception as exc:
                    logger.exception("search_library_fragments failed")
                    reply_parts.append(f"Nie udało się przeszukać biblioteki: {exc}")
                    continue
                ctx_search = "\n\n".join(
                    f"[{c.file_asset.name}]: {c.text}"
                    for c, _ in search_hits if c.file_asset is not None
                )
                if ctx_search:
                    block = f"=== Fragmenty z biblioteki (zapytanie: {q}) ===\n{ctx_search}"
                    reply_parts.append(block)
                    dynamic_context = f"{dynamic_context}\n{block}" if dynamic_context else block
                else:
                    reply_parts.append(
                        "(Brak trafnych fragmentów w zindeksowanej bibliotece — upewnij się, że pliki są przesłane i zindeksowane.)"
                    )

            elif tc.name == "prepare_create_teacher_project":
                pname = (tc.arguments.get("name") or "").strip()
                if not pname:
                    reply_parts.append("Nie podano nazwy projektu.")
                    continue
                desc = tc.arguments.get("description")
                desc_str = str(desc).strip() if desc else None
                if dry_run:
                    side_effects_skipped = True
                    reply_parts.append(f"[Dry-run] Przygotowano by propozycję projektu „{pname}”.")
                    continue
                s = get_settings()
                token = create_project_creation_token(
                    user_id=user_id, name=pname, description=desc_str,
                )
                pending_project_creation = {
                    "confirmation_token": token,
                    "expires_in_seconds": s.confirmation_token_expire_minutes * 60,
                    "summary": f"Czy utworzyć projekt „{pname}”?",
                    "name": pname,
                    "description": desc_str or "",
                }
                reply_parts.append(
                    f"Przygotowałem propozycję projektu **„{pname}”**."
                    + (f" Opis: _{desc_str}_." if desc_str else "")
                    + "\n\nPotwierdź **utworzenie** przyciskiem pod tą odpowiedzią albo w zakładce „Moje materiały” "
                    "(bez potwierdzenia projekt **nie** powstanie). Dopiero po utworzeniu mogę zapisywać kolejne "
                    "pliki do tego folderu."
                )

            elif tc.name == "prepare_delete_teacher_project":
                if dry_run:
                    side_effects_skipped = True
                    reply_parts.append("[Dry-run] Usunięcie projektu byłoby tylko zaplanowane.")
                    continue
                proj_row, err = await _resolve_user_project_for_delete(session, user_id, tc.arguments)
                if err or proj_row is None:
                    reply_parts.append(err or "Nie udało się zidentyfikować projektu.")
                    continue
                s = get_settings()
                del_tok = create_resource_confirmation_token(
                    user_id=user_id,
                    action=ACTION_DELETE_PROJECT,
                    resource_type=RESOURCE_PROJECT,
                    resource_id=proj_row.id,
                )
                pending_project_deletion = {
                    "confirmation_token": del_tok,
                    "expires_in_seconds": s.confirmation_token_expire_minutes * 60,
                    "summary": f"Czy na pewno usunąć projekt „{proj_row.name}”? Pliki pozostaną w bibliotece bez tego folderu.",
                    "project_id": str(proj_row.id),
                    "project_name": proj_row.name,
                }
                reply_parts.append(
                    f"Przygotowałem usunięcie projektu **„{proj_row.name}”**. Potwierdź przyciskiem pod odpowiedzią "
                    "lub w „Moje materiały” — bez potwierdzenia projekt **nie** zostanie usunięty."
                )

            elif tc.name == "export_library_file":
                fmt = (tc.arguments.get("format") or "pdf").lower().strip()
                fid_raw = tc.arguments.get("file_id")
                fid: UUID | None = None
                if fid_raw:
                    try:
                        fid = UUID(str(fid_raw).strip())
                    except (ValueError, TypeError):
                        reply_parts.append("Nieprawidłowy file_id do eksportu.")
                        continue
                else:
                    fid = last_created_file_id
                if fid is None:
                    reply_parts.append(
                        "Brak pliku do eksportu — podaj file_id (UUID) lub najpierw wygeneruj plik w tej samej odpowiedzi."
                    )
                    continue
                if dry_run:
                    side_effects_skipped = True
                    reply_parts.append(f"[Dry-run] Eksport do {fmt} byłby wykonany.")
                else:
                    try:
                        new_fid = await persist_export_as_new_file(
                            session, user_id, fid, active_project_id, fmt, self._storage,
                        )
                        created.append(new_fid)
                        last_created_file_id = new_fid
                        reply_parts.append(f"Zapisano eksport ({fmt}) w bibliotece.")
                    except ValueError as exc:
                        reply_parts.append(str(exc))

            elif tc.name in TOOL_TO_MODULE:
                module = TOOL_TO_MODULE[tc.name]
                run_modules.append(module)
                if dry_run:
                    side_effects_skipped = True
                    reply_parts.append(
                        f"[Symulacja] Moduł **{module}** zostałby uruchomiony — pliki i wywołanie KIE **nie** są wykonywane."
                    )
                else:
                    mod_fids, mod_note = await self._run_module(
                        session, user_id, active_project_id, module, user_message, dynamic_context, tc.arguments,
                    )
                    if mod_fids:
                        for mod_fid in mod_fids:
                            created.append(mod_fid)
                            last_created_file_id = mod_fid
                        reply_body = await self._reply_for_saved_module(
                            session, module, tc.arguments, mod_fids,
                        )
                        if mod_note:
                            reply_body = f"{reply_body}\n\n{mod_note}"
                        reply_parts.append(reply_body)
                    else:
                        reply_parts.append(
                            f"Moduł **{module}** nie zapisał pliku (pominięto lub błąd konfiguracji). "
                            "Sprawdź klucze LLM modułów i logi serwera."
                        )

        if completion.text and not reply_parts:
            reply_parts.append(completion.text)
        if not reply_parts and run_modules:
            reply_parts.append(f"Przygotowuję: {', '.join(run_modules)}.")

        return ChatResult(
            reply="\n\n".join(reply_parts) or "Gotowe!",
            created_file_ids=created, run_modules=run_modules,
            needs_clarification=needs_clarification, clarification_question=clarification_question,
            dry_run=dry_run, side_effects_skipped=side_effects_skipped,
            linked_project_id=linked_project_id,
            pending_project_creation=pending_project_creation,
            pending_project_deletion=pending_project_deletion,
        )

    async def _reply_for_saved_module(
        self,
        session: AsyncSession,
        module: str,
        tool_args: dict[str, Any],
        file_ids: list[UUID],
    ) -> str:
        stmt = select(FileAssetORM).where(FileAssetORM.id.in_(file_ids))
        rows = list((await session.scalars(stmt)).all())
        by_id = {r.id: r for r in rows}
        ordered = [by_id[i] for i in file_ids if i in by_id]
        if not ordered:
            return _MODULE_REPLY_FALLBACK.get(
                module,
                f'Zapisano materiał w „Moje materiały” (moduł {module}).',
            )
        mt = (tool_args.get("material_title") or "").strip()
        topic = (tool_args.get("topic") or "").strip()
        if mt:
            head = f"Przygotowałem materiał: „{mt}”."
        elif topic:
            head = f"Przygotowałem materiał: „{topic}”."
        else:
            head = "Zapisałem pliki w bibliotece."
        lines: list[str] = [head, "", "Znajdziesz je w zakładce „Moje materiały”:"]
        for r in ordered:
            lines.append(f"• {r.name} — {_brief_file_label(r.mime_type, r.name)}")
        if module == "music":
            has_audio = any((r.mime_type or "").lower().startswith("audio/") for r in ordered)
            if has_audio:
                lines.append(
                    "\nDołączono plik audio (.mp3) — pobierzesz go przyciskiem pod wiadomością albo z „Moje materiały”."
                )
            else:
                lines.append(
                    "\nW pliku .txt jest m.in. tekst piosenki, styl oraz (jeśli KIE przyjęło zadanie) identyfikator taskId "
                    "i odpowiedź API — tam też ewentualny komunikat błędu od KIE."
                )
        elif module == "graphics":
            lines.append("\nMożesz pobrać obraz przyciskiem pod wiadomością.")
        elif module == "video":
            lines.append("\nJeśli to wideo MP4, pobierzesz je przyciskiem pod wiadomością.")
        else:
            lines.append("\nMożesz pobrać pliki przyciskami pod tą wiadomością.")
        return "\n".join(lines)

    # --- Uruchamianie modułu generowania ---

    async def _run_module(
        self, session: AsyncSession, user_id: UUID, project_id: UUID | None,
        module: str, user_message: str, context: str, tool_args: dict[str, Any],
    ) -> tuple[list[UUID], str | None]:
        mod = module.lower().strip()
        sys_prompt = MODULE_SYSTEM_PROMPTS.get(mod)
        if not sys_prompt:
            logger.warning("No system prompt for module %r — skipping", mod)
            return [], None

        args_str = json.dumps(tool_args, ensure_ascii=False) if tool_args else ""
        user_part = f"Kontekst:\n{context}\n\nParametry:\n{args_str}\n\nProśba:\n{user_message}"
        logger.debug("Running module %r via %s", mod, type(self._llm_modules).__name__)
        mod_completion = await self._llm_modules.complete(sys_prompt, user_part)
        logger.debug(
            "Module %r result: provider=%s model=%s text_len=%d tokens=%s",
            mod, mod_completion.provider, mod_completion.model,
            len(mod_completion.text or ""), mod_completion.resolved_total_tokens(),
        )
        await record_llm_usage_event(
            session, user_id=user_id, call_kind="module", module_name=mod,
            completion=mod_completion, system_text=sys_prompt, user_text=user_part,
        )
        content = mod_completion.text if mod_completion.text is not None else ""

        if mod == "graphics":
            return [await self._handle_graphics(session, user_id, project_id, content, tool_args)], None
        if mod == "video":
            return [await self._handle_video(session, user_id, project_id, content, tool_args)], None
        if mod == "music":
            return await self._handle_music(session, user_id, project_id, content, tool_args)
        body = content if isinstance(content, str) else ""
        fid = await self._persist_file(
            session, user_id, project_id, mod,
            data=body.encode("utf-8"), mime="text/plain; charset=utf-8", ext="txt",
            extra={"module": mod, "tool_args": tool_args},
        )
        return [fid], None

    # --- Grafika ---

    async def _handle_graphics(
        self, session: AsyncSession, user_id: UUID, project_id: UUID | None,
        llm_content: str, tool_args: dict[str, Any],
    ) -> UUID:
        prompt_data = _parse_media_json(llm_content)
        prompt_en = prompt_data.get("prompt_en", tool_args.get("description", ""))
        extra: dict[str, Any] = {
            "module": "graphics", "tool_args": tool_args, "prompt_en": prompt_en,
            "style_notes": prompt_data.get("style_notes", ""),
            "description_pl": prompt_data.get("description_pl", tool_args.get("description", "")),
        }

        if self._image_gen:
            try:
                result = await self._image_gen.generate(
                    prompt=prompt_en, style=tool_args.get("style"), size=tool_args.get("size", "1024x1024"),
                )
                extra["revised_prompt"] = result.revised_prompt
                extra["generator_model"] = result.model
                index_text = f"{extra['description_pl']}\n{prompt_en}\n{result.revised_prompt or ''}".strip()
                return await self._persist_file(
                    session, user_id, project_id, "graphics",
                    data=result.image_data, mime=result.mime_type, ext="png", extra=extra,
                    index_override=index_text,
                )
            except Exception as exc:
                logger.error("Image generation failed: %s", exc)
                extra["generation_error"] = str(exc)[:500]

        return await self._persist_file(
            session, user_id, project_id, "graphics",
            data=llm_content.encode("utf-8"), mime="application/json; charset=utf-8",
            ext="json", extra=extra,
        )

    # --- Wideo ---

    async def _handle_video(
        self, session: AsyncSession, user_id: UUID, project_id: UUID | None,
        llm_content: str, tool_args: dict[str, Any],
    ) -> UUID:
        prompt_data = _parse_media_json(llm_content)
        prompt_en = prompt_data.get("prompt_en", tool_args.get("description", ""))
        extra: dict[str, Any] = {
            "module": "video", "tool_args": tool_args, "prompt_en": prompt_en,
            "storyboard": prompt_data.get("storyboard", []),
            "description_pl": prompt_data.get("description_pl", tool_args.get("description", "")),
        }

        if self._video_gen:
            try:
                result = await self._video_gen.generate(
                    prompt=prompt_en, duration_seconds=tool_args.get("duration_seconds", 5),
                    style=tool_args.get("style"),
                )
                extra["generator_model"] = result.model
                extra["video_status"] = result.status
                if result.status == "completed" and result.video_data:
                    index_text = f"{extra['description_pl']}\n{prompt_en}".strip()
                    return await self._persist_file(
                        session, user_id, project_id, "video",
                        data=result.video_data, mime=result.mime_type, ext="mp4", extra=extra,
                        index_override=index_text,
                    )
                extra["poll_url"] = result.poll_url
                extra["message"] = result.message
            except Exception as exc:
                logger.error("Video generation failed: %s", exc)
                extra["generation_error"] = str(exc)[:500]

        return await self._persist_file(
            session, user_id, project_id, "video",
            data=llm_content.encode("utf-8"), mime="application/json; charset=utf-8",
            ext="json", extra=extra,
        )

    # --- Muzyka (LLM + opcjonalnie KIE.ai) ---

    async def _handle_music(
        self,
        session: AsyncSession,
        user_id: UUID,
        project_id: UUID | None,
        llm_content: str,
        tool_args: dict[str, Any],
    ) -> tuple[list[UUID], str | None]:
        s = get_settings()
        topic = (tool_args.get("topic") or "Utwór edukacyjny").strip()
        age = tool_args.get("age_group")
        style = (tool_args.get("style") or "").strip() or None
        music_data = _parse_music_json(llm_content or "")
        explicit_lyrics = (
            (music_data.get("lyrics_pl") or music_data.get("lyrics") or "").strip()
        )
        style_en = (music_data.get("style_en") or "").strip() or None
        material_md = (music_data.get("material_md") or music_data.get("document_pl") or "").strip()
        legacy_full = (llm_content or "").strip()
        if explicit_lyrics:
            lyrics_body = explicit_lyrics
            api_prompt = explicit_lyrics[:8000]
        else:
            lyrics_body = legacy_full
            lines = [f"Temat: {topic}"]
            if age:
                lines.append(f"Grupa wiekowa: {age}")
            if lyrics_body:
                lines.append(lyrics_body)
            api_prompt = "\n\n".join(lines)[:8000]
        title = (topic[:80] if topic else "TeacherHelper track")[:80]
        instrumental = _infer_instrumental_music(lyrics_body, tool_args, s.kie_music_instrumental_default)
        extra: dict[str, Any] = {
            "module": "music",
            "tool_args": tool_args,
            "kie_submitted": False,
        }
        result = None
        if self._music_gen:
            req = MusicSubmitRequest(
                prompt=api_prompt,
                title=title,
                style=(style_en or style or "Educational pop for children, cheerful, classroom-friendly"),
                instrumental=instrumental,
                model=s.kie_music_model,
                custom_mode=s.kie_music_custom_mode,
                call_back_url=s.kie_music_callback_url,
                negative_tags=s.kie_music_negative_tags,
                vocal_gender=s.kie_music_vocal_gender,
                style_weight=s.kie_music_style_weight,
                weirdness_constraint=s.kie_music_weirdness_constraint,
                audio_weight=s.kie_music_audio_weight,
                persona_id=s.kie_music_persona_id,
                persona_model=s.kie_music_persona_model,
            )
            try:
                result = await self._music_gen.submit(req)
                extra["kie_submitted"] = True
                extra["kie_http_status"] = result.http_status
                extra["kie_response"] = result.payload
                if result.ok and result.task_id:
                    extra["kie_task_id"] = result.task_id
                if not result.ok:
                    extra["kie_error"] = (result.error_detail or "")[:1200]
            except Exception as exc:
                logger.error("KIE music generation failed: %s", exc)
                extra["kie_error"] = str(exc)[:800]

        mp3_bytes: bytes | None = None
        if (
            self._music_gen
            and result
            and result.ok
            and result.task_id
            and s.kie_music_poll_timeout_seconds > 0
        ):
            fetch = getattr(self._music_gen, "fetch_task_record", None)
            if callable(fetch):
                deadline = time.monotonic() + float(s.kie_music_poll_timeout_seconds)
                interval = max(0.35, float(s.kie_music_poll_interval_seconds))
                while time.monotonic() < deadline:
                    rec = await fetch(result.task_id)
                    st, urls, perr = parse_task_record(rec)
                    extra["kie_poll_status"] = st
                    if perr:
                        extra["kie_poll_error"] = perr
                    logger.debug(
                        "KIE record-info: task=%s status=%s audio_urls=%d",
                        result.task_id, st, len(urls),
                    )
                    # FIRST_SUCCESS często zawiera pierwszy audioUrl zanim przyjdzie pełne SUCCESS.
                    if (
                        urls
                        and st in KIE_STATUSES_WITH_POSSIBLE_AUDIO
                    ):
                        extra["kie_audio_urls"] = urls
                        try:
                            mp3_bytes = await download_audio_url(urls[0])
                            extra["kie_audio_downloaded_from"] = urls[0]
                        except Exception as dl_exc:
                            logger.warning("KIE audio download failed: %s", dl_exc)
                            extra["kie_download_error"] = str(dl_exc)[:800]
                        break
                    if st == "SUCCESS" and not urls:
                        # Sukces wg KIE, ale jeszcze bez URL-i w odpowiedzi — dalej poll.
                        pass
                    elif st in KIE_TERMINAL_FAIL_STATUSES:
                        break
                    await asyncio.sleep(interval)

        if material_md:
            doc_body = material_md
        elif music_data:
            chunks: list[str] = []
            if style_en:
                chunks.append(f"### Styl (Suno, EN)\n\n{style_en}")
            if lyrics_body:
                chunks.append(f"### Tekst piosenki\n\n{lyrics_body}")
            doc_body = "\n\n".join(chunks) if chunks else legacy_full
        else:
            doc_body = legacy_full
        parts = ["# Muzyka — materiał asystenta\n\n", doc_body]
        if extra.get("kie_submitted"):
            parts.append("\n\n## Odpowiedź KIE.ai (API)\n")
            parts.append(json.dumps(extra.get("kie_response"), ensure_ascii=False, indent=2))
            tid = extra.get("kie_task_id")
            if tid:
                parts.append(
                    f"\n\nZadanie zarejestrowane asynchronicznie — **taskId:** `{tid}` "
                    "(wynik audio także przez callback skonfigurowany w KIE)."
                )
            if extra.get("kie_poll_status"):
                parts.append(f"\n\n**Status zadania (polling):** `{extra['kie_poll_status']}`")
            if extra.get("kie_download_error"):
                parts.append(f"\n\n**Błąd pobierania MP3:** {extra['kie_download_error']}")
            elif mp3_bytes:
                parts.append("\n\n**Pobrano plik audio z KIE** i zapisano jako osobny plik `.mp3` w bibliotece.")
        if extra.get("kie_error"):
            parts.append("\n\n## Błąd KIE.ai\n")
            parts.append(str(extra["kie_error"]))
        combined = "\n".join(parts)
        txt_id = await self._persist_file(
            session, user_id, project_id, "music",
            data=combined.encode("utf-8"), mime="text/plain; charset=utf-8",
            ext="txt", extra=extra,
            index_override=api_prompt[:12000],
        )
        out: list[UUID] = [txt_id]
        if mp3_bytes:
            mp3_extra: dict[str, Any] = {
                "module": "music",
                "tool_args": tool_args,
                "kie_task_id": extra.get("kie_task_id"),
                "kie_audio_url": extra.get("kie_audio_downloaded_from"),
                "related_txt_context": "Powiązany raport KIE w pliku .txt z tej samej generacji.",
            }
            idx = f"{title}\n{extra.get('kie_audio_downloaded_from') or ''}\n{api_prompt[:4000]}".strip()
            mp3_id = await self._persist_file(
                session, user_id, project_id, "music",
                data=mp3_bytes, mime="audio/mpeg", ext="mp3",
                extra=mp3_extra,
                index_override=idx,
            )
            out.append(mp3_id)
        poll_enabled = bool(
            self._music_gen
            and result
            and result.ok
            and result.task_id
            and s.kie_music_poll_timeout_seconds > 0,
        )
        note = _music_kie_status_note(
            extra,
            mp3_bytes,
            result,
            poll_enabled=poll_enabled,
            music_gen_enabled=bool(self._music_gen),
        )
        return out, note

    # --- Wspólny zapis pliku (jedna metoda zamiast czterech) ---

    async def _persist_file(
        self, session: AsyncSession, user_id: UUID, project_id: UUID | None,
        mod: str, *, data: bytes, mime: str, ext: str,
        extra: dict[str, Any], index_override: str | None = None,
    ) -> UUID:
        ta = extra.get("tool_args") if isinstance(extra.get("tool_args"), dict) else {}
        stem = _resolve_file_stem(mod, ta)
        name = f"{stem}_{uuid.uuid4().hex[:8]}.{ext}"
        key = await self._storage.put(data, prefix=f"u/{user_id}")
        row = FileAssetORM(
            id=uuid.uuid4(), user_id=user_id, project_id=project_id,
            name=name, category=category_for_module(mod), mime_type=mime,
            storage_key=key, version=1, size_bytes=len(data),
            status=FileStatus.draft, extra=extra,
        )
        session.add(row)
        await session.flush()

        if index_override is not None:
            await index_file_content(session, row, index_override.encode("utf-8"), f"{name}.txt")
        else:
            await index_file_content(session, row, data, name)
        return row.id


# ---------------------------------------------------------------------------
# Helpery
# ---------------------------------------------------------------------------

def _parse_music_json(raw: str) -> dict[str, Any]:
    """Odpowiedź modułu muzyka: JSON ze stylami, samymi słowami piosenki i materiałem dla nauczyciela."""
    try:
        t = raw.strip()
        if t.startswith("```"):
            t = t.split("\n", 1)[-1]
            if "```" in t:
                t = t.rsplit("```", 1)[0]
        data = json.loads(t)
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, TypeError):
        pass
    return {}


def _parse_media_json(raw: str) -> dict[str, Any]:
    try:
        t = raw.strip()
        if t.startswith("```"):
            t = t.split("\n", 1)[-1]
            if "```" in t:
                t = t.rsplit("```", 1)[0]
        return json.loads(t)
    except (json.JSONDecodeError, TypeError):
        return {"prompt_en": raw[:500]}


def parse_orchestration_json(raw: str) -> dict:
    """Fallback parser dla legacy JSON (używany w /v1/intent/analyze)."""
    try:
        t = raw.strip()
        if t.startswith("```"):
            t = t.split("\n", 1)[-1]
            if "```" in t:
                t = t.rsplit("```", 1)[0]
        data = json.loads(t)
        return {
            "assistant_reply": str(data.get("assistant_reply", "")),
            "run_modules": list(data.get("run_modules") or []),
            "needs_clarification": bool(data.get("needs_clarification", False)),
            "clarification_question": data.get("clarification_question"),
        }
    except (json.JSONDecodeError, TypeError):
        return {
            "assistant_reply": raw[:4000] if raw else "Nie udało się zinterpretować odpowiedzi modelu.",
            "run_modules": [], "needs_clarification": False, "clarification_question": None,
        }
