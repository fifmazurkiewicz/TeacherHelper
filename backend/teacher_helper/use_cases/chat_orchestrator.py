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
from teacher_helper.infrastructure.lyria_openrouter import OpenRouterLyriaMusicGenerator
from teacher_helper.infrastructure.web_search import format_hits_for_llm, run_web_search
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

- **ask_clarification** — gdy brakuje informacji; przy **ogólnej** prośbie o materiał **najpierw** doprecyzuj (patrz „Doprecyzowanie…” i „Przedstawienia…”).
- **prepare_create_teacher_project** — przygotuj utworzenie folderu projektu (nazwa + opis). **Nie tworzy** projektu — użytkownik musi potwierdzić w aplikacji. Użyj, gdy użytkownik chce „zapisać paczkę”, folder z materiałami itd.
- **prepare_delete_teacher_project** — przygotuj usunięcie projektu (**project_id** UUID albo **project_name**). **Nie usuwa** — wymaga potwierdzenia użytkownika.
- **search_library_fragments** — wyszukaj w zindeksowanej bibliotece plików użytkownika (semantycznie). W bloku **„Katalogi użytkownika”** masz UUID i nazwy folderów — gdy rozmowa dotyczy tematu zgodnego z nazwą lub opisem katalogu, ogranicz wyszukiwanie przez **project_id** (preferowane) lub **project_name**. Gdy potrzebujesz przeszukać wszystko naraz — **entire_library: true**. Użyj, gdy pytanie dotyczy treści z materiałów w „Moje materiały”, albo gdy użytkownik wspomina temat powiązany z istniejącym folderem.
- **search_web** — wyszukaj **w internecie** (Tavily). Użyj przy **opracowaniu / pogłębianiu wiedzy**, faktach aktualnych, definicjach, gdy biblioteka nie wystarcza. W jednej turze wywołaj **przed** ``generate_study``. Gdy API nie jest skonfigurowane, krótko poinformuj użytkownika i nie podawaj szczegółowych faktów z pamięci jako rzekomych wyników wyszukiwania.
- **generate_study** — przygotuj **opracowanie edukacyjne** (markdown) na podany temat i **zapisz** je jako plik w bibliotece. Opieraj treść na bloku wyników ``search_web`` w kontekście; zamieść linki do stron z tych wyników (sekcja na końcu dokumentu). Gdy użytkownik chce materiały w **osobnym folderze**, w tej samej turze użyj **prepare_create_teacher_project** (nazwa np. „Opracowanie: …”) — po **potwierdzeniu** utworzenia folderu w UI pliki z kolejnych generacji trafią tam, jeśli rozmowa ma ustawiony aktywny katalog.
- **export_library_file** — zapisz kopię istniejącego pliku z biblioteki jako PDF/DOCX/TXT/PPTX (podaj file_id UUID lub pomiń, by użyć pliku utworzonego w tej samej turze).
- **generate_scenario** — scenariusz przedstawienia.
- **generate_graphics** — grafika (plakat, ilustracja, scenografia) **wyłącznie przez OpenRouter** — domyślnie **Nano Banana 2**; język napisów na obrazie jak użytkownika (pole ``prompt_image`` w module). W ``.env``: ``OPENROUTER_IMAGE_MODEL``.
- **generate_video** — storyboard/prompt wideo.
- **generate_music** — **KIE** (Suno) + opcjonalnie **OpenRouter Lyria**: ten sam tekst idzie do obu; przy skonfigurowanych kluczach powstają **po dwa utwory** od każdego dostawcy (warianty aranżu). KIE: ``callBackUrl`` + ewentualnie **.mp3** z pollingu; Lyria: **.wav** z ``chat/completions`` (SSE).
- **generate_poetry** — wiersz do recytacji.
- **generate_presentation** — plan prezentacji (slajdy).
- **reply_to_user** — odpowiedź tekstowa bez generowania materiałów.

## Miejsce zapisu plików (katalog w rozmowie)

W kontekście wiadomości użytkownika masz **„Katalog aktywny w tej rozmowie”** oraz blok **„Katalogi użytkownika”** (UUID + nazwy).

**Gdzie trafia zapis:** ``generate_*`` i ``export_library_file`` zapisują plik do: (a) **project_id** podanego opcjonalnie w argumentach narzędzia (UUID z listy — katalog użytkownika), albo (b) do **katalogu aktywnego w tej rozmowie**; gdy aktywnego brak i nie podano **project_id** — do **„Innych plików”**. Sam tekst odpowiedzi **nie** zmienia folderu. **search_library_fragments** z innym ``project_id`` dotyczy tylko wyszukiwania — aby zapisać materiał w tym samym folderze, podaj ten sam **project_id** w ``generate_*`` / ``export_library_file`` albo ustaw aktywny katalog w UI.

1. Gdy **katalog aktywny: brak** i użytkownik prosi o **materiał do zapisania** (dowolne ``generate_*`` tworzące plik w bibliotece, w tym ``generate_study``) — **nie wywołuj** od razu narzędzi generujących. **Najpierw ask_clarification**: zapytaj, czy **utworzyć nowy folder** na podstawie tematu (zaproponuj nazwę), czy **dodać do istniejącego** — wymień **2–5** sensownych katalogów z listy (nazwa i UUID w apostrofach/backtickach), czy zostawić w **„Innych plikach”**. Gdy użytkownik wybierze istniejący folder, w wywołaniu ``generate_*`` **podaj jego project_id** (albo upewnij się, że rozmowa ma już ten katalog aktywny w UI). Wyjątek: użytkownik **jednoznacznie** pisze, że chce tylko „Inne pliki” / bez folderu — wtedy możesz od razu użyć ``generate_*`` bez **project_id**.
2. Po wyborze **nowego folderu** — **prepare_create_teacher_project**; po potwierdzeniu w UI aplikacja ustawi aktywny katalog rozmowy i kolejne pliki tam trafią (chyba że w danym wywołaniu podasz inny **project_id**).
3. Gdy **katalog aktywny jest ustawiony**, a nowa prośba **wyraźnie dotyczy innej tematyki** niż nazwa tego folderu — **ask_clarification**: czy zapisać w bieżącym folderze, czy w innym (kandydaci z listy + UUID); po wyborze użyj odpowiedniego **project_id** w narzędziu zapisu.
4. Przy **wielu** pasujących folderach — zawsze **ask_clarification** z listą do wyboru; nie zgaduj ``project_id`` w ciemno.

## Doprecyzowanie przed generowaniem (wszystkie tematy)

**Nie zgaduj w ciemno.** Gdy wiadomość jest **krótka, ogólna albo wieloznaczna**, a od tego zależy sensowny wynik — **najpierw ask_clarification**: krótki wstęp + **lista punktów** z pytaniami **dopasowanymi do typu prośby** (nie kopiuj ślepo listy z przedstawień, jeśli chodzi o coś innego).

Wskazówki wg kontekstu (wybierz tylko pasujące):

- **Prezentacja / plan lekcji** — klasa/przedmiot, czas, cel (wprowadzenie, powtórzenie), poziom szczegółowości, orientacyjna liczba slajdów lub „sam szkielet vs pełne notatki”.
- **Grafika** — przeznaczenie (plakat, ilustracja, okładka), styl, grupa wiekowa, orientacja, czego unikać.
- **Muzyka / piosenka** — wiek, nastrój, czy refren vs pełny tekst, ewentualnie tempo/gatunek.
- **Wideo / storyboard** — długość lub format (np. krótki spot), odbiorca, klimat.
- **Wiersz** — forma, długość, dokładniejsza tematyka niż jedno hasło.
- **Ogólne „zrób materiały / zadania / kartkówkę”** — doprecyzuj **co konkretnie** ma powstać w ramach dostępnych narzędzi (scenariusz, prezentacja, grafika, muzyka, wiersz, wideo) albo wyjaśnij krótko ograniczenia, potem dopytaj.
- **Opracowanie tematu / pogłębienie wiedzy / notatki do lekcji na dany temat** — jeśli prośba jest **jasna** (konkretne hasło lub temat), wywołaj **search_web** (dopasuj zapytanie: PL, kontekst szkolny) oraz **generate_study** z sensownym **material_title**. Gdy brakuje poziomu (klasa, przedmiot, czas), użyj **ask_clarification**.

Możesz zaproponować **domyślne wartości w nawiasach**. Jeśli użytkownik pisze wprost: „zrób domyślnie / przyjmij standard / sama wybierz” — wtedy **możesz** od razu użyć ``generate_*`` z rozsądnymi założeniami i **krótko je wymień** w odpowiedzi.

## Przedstawienia, jasełka, scenariusze

Gdy użytkownik prosi o **przedstawienie / scenariusz / jasełka / widowisko / spektakl szkolny** i podaje tylko **temat lub hasło** (np. „zrób przedstawienie o Aladynie”), **nie wywołuj** od razu ``generate_scenario``, ``generate_music``, ``generate_graphics`` ani innych ``generate_*``. Najpierw **ask_clarification**: krótki, przyjazny wstęp i **czytelna lista punktów** z pytaniami doprecyzowującymi, m.in.:

- **dla jakiej grupy** — klasa / przedszkole / wiek (np. klasa 3 SP, 10–12 lat);
- **czas trwania** — orientacyjnie (np. 15, 30, 45 minut);
- **obsada** — ilu uczniów / aktorów lub ile ról (szacunek);
- **muzyka** — czy mają być piosenki w przedstawieniu; jeśli tak, **ile** (np. jedna refrenowa, dwie);
- **materiały dodatkowe** — czy wygenerować też **grafikę** (plakat, ilustracja), **wideo**/storyboard, **wiersz**;
- ewentualnie: **ton** (lżejszy / bardziej pouczający), ograniczenia (bez przemocy), **język** (tylko PL / wstawki obcojęzyczne).

Możesz zaproponować **domyślne wartości w nawiasach** („jeśli nie odpiszesz, przyjmę 30 min i klasę 1–3”). Dopiero po odpowiedzi użytkownika (albo gdy **jednoznacznie** poda wszystko w jednej wiadomości) — użyj narzędzi generujących z **material_title**.

## Zapis w „Moje materiały” (nie myl z czatem)

- **Sam tekst** w ``reply_to_user`` **nie tworzy pliku** — użytkownik **nie zobaczy** go w „Materiały”, dopóki nie wywołasz narzędzia **zapisującego** (``generate_*`` lub ``export_library_file``) w tej turze.
- **Nigdy** nie pisz, że plik „został zapisany w bibliotece / folderze / moich materiałach”, jeśli **nie** wywołałeś takiego narzędzia. W przeciwnym razie użytkownik straci dostęp do treści.
- Gdy użytkownik prosi o **nowy plik**, **plik do pobrania**, **zapis w materiałach**, **„gdzie jest plik”** (bo oczekuje pliku), **nową wersję** scenariusza z rozszerzeniem (np. z piosenką) — **musisz** użyć właściwego ``generate_*`` z **nowym** ``material_title`` (dla scenariusza z tekstem piosenki nadal **generate_scenario** — cała treść w jednym pliku .txt).

## Kontynuacja rozmowy (stan materiałów — krytyczne)

W historii wiadomości asystenta mogą być **automatycznie doklejone** bloki w nawiasach kwadratowych, np.:
``[W tej odpowiedzi wygenerowano moduły: …]`` oraz ``[Pliki zapisane w bibliotece: …]``.
Traktuj je jako **fakt**: te pliki **już istnieją** w bibliotece użytkownika.

- **Nie generuj ponownie** scenariusza, grafiki, muzyki, wideo itd., jeśli użytkownik **nie prosi wyraźnie** o nową wersję, poprawkę, przeróbkę lub „od zera”.
- **Wyjątek:** słowa w stylu **„nowy plik”**, **„zapisz / wrzuć do materiałów”**, **„przygotuj plik”**, **„nowa wersja scenariusza”** oznaczają **konieczny** ponowny ``generate_*`` z nowym ``material_title`` — zasada „nie powtarzaj” **nie** dotyczy takiej prośby.
- Gdy użytkownik pisze w stylu **„dodatkowo / jeszcze / kolejną / następną / tylko …”** i prosi np. **wyłącznie o piosenkę** — wywołaj **tylko** ``generate_music`` (z nowym ``material_title``). **Nie** wołaj ponownie ``generate_scenario``, ``generate_graphics`` ani innych ``generate_*``, chyba że w tej samej wiadomości wyraźnie je ponowi.
- Jeśli potrzebujesz treści istniejącego scenariusza do spójnej piosenki, użyj **search_library_fragments** (zapytanie po temacie / fragmencie tytułu pliku z listy), zamiast pisać scenariusz od nowa.

## Zasady

1. Gdy wiadomość jest **ogólna** albo **niedookreślona** — użyj **ask_clarification** (wg sekcji „Doprecyzowanie…”; dla przedstawień dodatkowo „Przedstawienia…”). Nie zgaduj za użytkownika parametrów, które zmieniają mocno wynik (czas, odbiorca, zakres, liczba elementów), chyba że prosi o domyślne założenia.
2. Gdy użytkownik chce zestaw materiałów „do zapisania” → **prepare_create_teacher_project**, potem (po potwierdzeniu przez użytkownika) narzędzia generujące; pliki trafiają do folderu powiązanego z rozmową w UI. Jeśli w tej turze musisz zapisać **przed** potwierdzeniem utworzenia folderu, nie da się trafić do jeszcze nieistniejącego UUID — kolejna wiadomość po potwierdzeniu albo jawny **project_id** istniejącego katalogu.
3. Przy **każdym** narzędziu ``generate_*`` ZAWSZE podaj pole **material_title**: krótki, opisowy tytuł pliku po polsku (2–12 słów), widoczny w bibliotece — bez znaku ``/``, bez rozszerzenia (np. „Scenariusz jasełka klasa 4”, „Piosenka o zimie SP”).
4. Gdy masz wystarczające informacje → użyj odpowiedniego narzędzia generowania (z **material_title**).
5. Możesz wywołać WIELE narzędzi jednocześnie (np. prepare_create_teacher_project + generate_music + generate_graphics). **generate_scenario** wywołaj **co najwyżej raz** w jednej turze (jedna odpowiedź) — nie zduplikuj scenariusza; inne ``generate_*`` mogą być wielokrotnie wg potrzeb.
6. Eksport do PDF/DOCX: export_library_file (file_id z wcześniejszej wiadomości lub pominięty po wygenerowaniu pliku w tej samej odpowiedzi).
7. Gdy w tej samej turze szukasz w bibliotece i generujesz materiał — najpierw **search_library_fragments**, potem narzędzie generujące, żeby moduł dostał znalezione fragmenty w kontekście. To samo dla **search_web** przed **generate_study**.
8. Nie łącz **search_library_fragments** ani **search_web** z **reply_to_user** w jednej turze — odpowiedź tekstowa byłaby ustalana bez wglądu w wyniki. Szukaj osobno albo użyj samego **reply_to_user**, gdy wyszukiwanie nie jest potrzebne.
9. **Katalogi (foldery):** Na początku wiadomości użytkownika masz listę jego katalogów. Gdy temat rozmowy pasuje do któregoś z nich — zawołaj **search_library_fragments** z odpowiednim **project_id** (albo doprecyzuj przez **ask_clarification**, jeśli pasuje kilka folderów albo niepewność). **Zapis** w tym samym folderze wymaga tego samego **project_id** w ``generate_*`` / ``export_library_file`` albo aktywnego katalogu rozmowy zgodnego z tym folderem.
10. Przy **pierwszej** pełnej prośbie o przedstawienie / zestaw materiałów możesz AKTYWNIE zasugerować powiązane materiały (scenariusz → piosenka, plakat). Przy **kolejnych** wiadomościach dodawaj **tylko** to, o co użytkownik prosi w bieżącej wiadomości (patrz „Kontynuacja rozmowy”) — nie powtarzaj całego pakietu.
11. Odpowiadaj po polsku, przyjaźnie, zwięźle.
12. **Język materiałów** musi odpowiadać językowi użytkownika (zwykle polski): scenariusze, teksty, a także **napisy i etykiety na grafikach** (plakaty, slajdy-wizualizacje) — w tym samym języku co prośba; przy ``generate_graphics`` moduł przekazuje do Nano Banana pole ``prompt_image`` w tym języku (dokładne brzmienie tekstu na obrazie)."""

# Opcjonalny katalog zapisu — wspólny opis we wszystkich ``generate_*`` i ``export_library_file``.
_SAVE_PROJECT_ID_PROPERTY: dict[str, Any] = {
    "project_id": {
        "type": "string",
        "description": (
            "Opcjonalnie: UUID katalogu z bloku „Katalogi użytkownika”, do którego zapisać plik. "
            "Gdy pominiesz — katalog aktywny w tej rozmowie (UI); gdy i ten brak — „Inne pliki”."
        ),
    },
}

TOOL_DEFINITIONS: list[ToolDefinition] = [
    {"type": "function", "function": {
        "name": "ask_clarification",
        "description": (
            "Gdy prośba jest ogólna lub wieloznaczna — zanim wywołasz generate_*: jedno pole question z krótkim wstępem i listą punktów "
            "dopasowaną do tematu (prezentacja: klasa, czas, cel; grafika: styl, przeznaczenie; muzyka: wiek, nastrój; przedstawienie: obsada, czas, piosenki itd.)."
        ),
        "parameters": {"type": "object", "properties": {
            "question": {"type": "string", "description": "Tekst do nauczyciela: wstęp + pytania (np. lista punktowana)"},
            "suggestions": {"type": "array", "items": {"type": "string"},
                            "description": "Sugestie dodatkowych materiałów"},
        }, "required": ["question"]},
    }},
    {"type": "function", "function": {
        "name": "reply_to_user",
        "description": (
            "Odpowiedz nauczycielowi tekstem (bez generowania materiałów). "
            "**Nie zapisuje plików** — do pliku w „Moje materiały” potrzebne jest ``generate_*`` lub ``export_library_file``."
        ),
        "parameters": {"type": "object", "properties": {
            "message": {"type": "string", "description": "Treść odpowiedzi"},
        }, "required": ["message"]},
    }},
    {"type": "function", "function": {
        "name": "search_library_fragments",
        "description": (
            "Semantyczne wyszukiwanie po treści plików użytkownika w bibliotece (nie dotyczy plików przypiętych do wiadomości — te są już w kontekście). "
            "Opcjonalnie ogranicz do jednego katalogu (**project_id** z bloku „Katalogi użytkownika” albo **project_name**). "
            "**entire_library: true** — przeszukaj całą bibliotekę (wszystkie katalogi + „Inne pliki”), ignorując katalog aktywny w rozmowie. "
            "Bez tych pól zakres domyślny to katalog aktywny w rozmowie (jeśli jest), inaczej cała biblioteka."
        ),
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "Zapytanie wyszukiwawcze po sensie (np. temat lekcji, pojęcie z notatek)"},
            "project_id": {"type": "string", "description": "Opcjonalnie: UUID katalogu z listy w kontekście"},
            "project_name": {"type": "string", "description": "Opcjonalnie: nazwa katalogu (dokładna lub częściowa), gdy brak UUID"},
            "entire_library": {
                "type": "boolean",
                "description": "true = szukaj w całej bibliotece, pomiń domyślne ograniczenie do aktywnego katalogu",
            },
        }, "required": ["query"]},
    }},
    {"type": "function", "function": {
        "name": "search_web",
        "description": (
            "Wyszukiwanie w internecie (Tavily). Użyj przed generate_study lub gdy potrzebujesz aktualnych faktów spoza biblioteki użytkownika. "
            "Sformułuj zapytanie po polsku z kontekstem edukacyjnym."
        ),
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "Zapytanie do wyszukiwarki (np. fotosynteza lekcja biologia szkoła podstawowa)"},
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
            "Po potwierdzeniu usuwany jest folder oraz wszystkie przypisane do niego pliki (biblioteka + indeks). "
            "Podaj project_id (UUID) albo dokładną project_name (jak na liście projektów)."
        ),
        "parameters": {"type": "object", "properties": {
            "project_id": {"type": "string", "description": "UUID projektu do usunięcia"},
            "project_name": {"type": "string", "description": "Dokładna nazwa projektu (gdy brak UUID)"},
        }, "required": []},
    }},
    {"type": "function", "function": {
        "name": "export_library_file",
        "description": (
            "Wyeksportuj plik z biblioteki użytkownika do PDF, DOCX, TXT lub PPTX i zapisz jako nowy plik. "
            "Opcjonalnie **project_id** — folder docelowy eksportu (jak przy ``generate_*``)."
        ),
        "parameters": {"type": "object", "properties": {
            "file_id": {"type": "string", "description": "UUID pliku źródłowego (opcjonalnie — domyślnie ostatnio utworzony w tej turze)"},
            "format": {"type": "string", "enum": ["pdf", "docx", "txt", "pptx"], "description": "Format wyjściowy"},
            **_SAVE_PROJECT_ID_PROPERTY,
        }, "required": ["format"]},
    }},
    {"type": "function", "function": {
        "name": "generate_scenario",
        "description": (
            "Wygeneruj scenariusz przedstawienia szkolnego i **zapisz jako plik .txt w bibliotece** („Moje materiały”). "
            "Bez tego wywołania scenariusz **nie pojawi się** w materiałach. Maks. jedno wywołanie na turę (kolejne zignoruje backend)."
        ),
        "parameters": {"type": "object", "properties": {
            "topic": {"type": "string", "description": "Temat przedstawienia"},
            "material_title": {
                "type": "string",
                "description": "Tytuł pliku w bibliotece (po polsku, 2–12 słów, bez / i bez .txt), np. Scenariusz jasełka klasa 4",
            },
            "age_group": {"type": "string", "description": "Grupa wiekowa / klasa"},
            "duration_minutes": {"type": "integer", "description": "Czas trwania w minutach"},
            "style": {"type": "string", "description": "Styl (komedia, musical, dramat)"},
            **_SAVE_PROJECT_ID_PROPERTY,
        }, "required": ["topic", "material_title"]},
    }},
    {"type": "function", "function": {
        "name": "generate_graphics",
        "description": (
            "Wygeneruj grafikę edukacyjną (plakat, ilustrację, scenografię). "
            "Język napisów na obrazie i opisu — taki jak użytkownika (zwykle polski)."
        ),
        "parameters": {"type": "object", "properties": {
            "description": {"type": "string", "description": "Szczegółowy opis grafiki w języku użytkownika (zwykle po polsku)"},
            "material_title": {
                "type": "string",
                "description": "Krótki tytuł pliku w bibliotece, np. Plakat bezpieczeństwo w szkole",
            },
            "style": {"type": "string",
                       "description": "Styl: cartoon, realistic, watercolor, flat, 3d, pastel, comic"},
            "size": {"type": "string", "enum": ["1024x1024", "1792x1024", "1024x1792"],
                     "description": "Rozdzielczość: kwadrat, poziom, pion"},
            **_SAVE_PROJECT_ID_PROPERTY,
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
            **_SAVE_PROJECT_ID_PROPERTY,
        }, "required": ["description", "material_title"]},
    }},
    {"type": "function", "function": {
        "name": "generate_music",
        "description": (
            "Wygeneruj prompt muzyczny i tekst piosenki; zapis w bibliotece jako .txt z metadanymi. "
            "Przy skonfigurowanym KIE i OpenRouter: ten sam materiał trafia do obu — po kilka wariantów "
            "audio na dostawcę (MP3 z KIE, WAV z Lyrii; liczba: MUSIC_VARIANTS_PER_PROVIDER w .env)."
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
            **_SAVE_PROJECT_ID_PROPERTY,
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
            **_SAVE_PROJECT_ID_PROPERTY,
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
            **_SAVE_PROJECT_ID_PROPERTY,
        }, "required": ["topic", "material_title"]},
    }},
    {"type": "function", "function": {
        "name": "generate_study",
        "description": (
            "Opracowanie edukacyjne (markdown) na podany temat — zapis w bibliotece jako plik tekstowy. "
            "W tej samej turze wywołaj wcześniej search_web, by w kontekście znalazły się materiały z sieci."
        ),
        "parameters": {"type": "object", "properties": {
            "topic": {"type": "string", "description": "Temat opracowania"},
            "material_title": {
                "type": "string",
                "description": "Tytuł pliku w bibliotece, np. Opracowanie fotosynteza klasa 7",
            },
            "audience": {"type": "string", "description": "Odbiorcy: klasa, przedmiot, poziom"},
            "depth": {
                "type": "string",
                "enum": ["zwięzły", "standard", "rozszerzony"],
                "description": "Zakres materiału (domyślnie wybierz sensownie wg prośby)",
            },
            **_SAVE_PROJECT_ID_PROPERTY,
        }, "required": ["topic", "material_title"]},
    }},
]

MODULE_SYSTEM_PROMPTS: dict[str, str] = {
    "scenario": (
        "Jesteś dramaturgiem dla dzieci i młodzieży. Napisz kompletny scenariusz "
        "przedstawienia: postacie, dialogi, didaskalia, podział na sceny. "
        "Język całego scenariusza = język prośby użytkownika (zwykle polski). "
        "Tytuł pliku w bibliotece został już podany w argumencie narzędzia ``material_title`` — treść scenariusza ma z nim być spójna tematycznie."
    ),
    "graphics": (
        "Jesteś ekspertem od generowania obrazów AI (OpenRouter: Google Nano Banana / Gemini Image). "
        "Język napisów na obrazie i opisu sceny = język prośby użytkownika (zwykle polski). Na podstawie opisu wygeneruj WYŁĄCZNIE JSON "
        '(bez markdown, bez ```): {"prompt_image": "<jeden spójny prompt pod model obrazu w TYM SAMYM języku co prośba '
        '(po polsku jeśli nauczyciel pisze po polsku); szczegóły: kompozycja, kolory, oświetlenie, styl; '
        'jeśli na grafice ma być tekst — wpisz go dokładnie po polsku lub w języku prośby>", '
        '"style_notes": "<notatki o stylu w języku prośby>", '
        '"description_pl": "<krótki opis — po polsku gdy prośba po polsku>"}\n'
        "Dzieci i młodzież: jasne kolory, przyjazne postacie, bez przemocy. "
        'Opcjonalnie dodaj "prompt_en" — do generowania używane jest wyłącznie "prompt_image".'
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
    "presentation": (
        "Napisz plan prezentacji (nagłówki slajdów + punktory) w języku prośby użytkownika (zwykle polski). Markdown."
    ),
    "study": (
        "Tworzysz **opracowanie edukacyjne** (markdown) dla nauczyciela. Język = język prośby (zwykle polski). "
        "Struktura: krótki wstęp; **kluczowe pojęcia**; rozwinięcie merytoryczne z nagłówkami; "
        "**ćwiczenia lub pytania sprawdzające** (opcjonalnie); **słowniczek** lub **ciekawostki** (krótko, jeśli pasuje). "
        "Fragmenty z biblioteki i wyniki web w kontekście traktuj jako **surowiec** — syntetyzuj, nie wklejaj ich ponownie "
        "jako cytatów z nagłówkami plików; unikaj powtarzania tych samych sekcji. "
        "Jeśli w kontekście jest blok „Wyniki wyszukiwania w internecie”, **oprzyj się na nim** — nie kopiuj bezkrytycznie; "
        "uogólnij i dopasuj do poziomu z parametrów. Na końcu sekcja **Źródła (web)** z listą linków (tytuł + URL) "
        "wyłącznie z tego bloku. Gdy bloku wyszukiwania nie ma, napisz krótką notkę, że treść opiera się na ogólnej wiedzy modelu, "
        "i unikaj podawania dat lub statystyk bez pewności."
    ),
}

TOOL_TO_MODULE: dict[str, str] = {
    "generate_scenario": "scenario",
    "generate_graphics": "graphics",
    "generate_video": "video",
    "generate_music": "music",
    "generate_poetry": "poetry",
    "generate_presentation": "presentation",
    "generate_study": "study",
}

# Moduły zapisujące długi tekst .txt — długi reply_to_user w tej samej turze zwykle duplikuje plik w czacie.
_TEXT_FILE_MODULES = frozenset({"study", "scenario", "presentation", "poetry"})
_REPLY_TO_USER_MAX_AFTER_TEXT_MODULE = 2800

# Gdy brak wierszy w DB po zapisie (rzadkie) — bez żargonu konfiguracyjnego.
_MODULE_REPLY_FALLBACK: dict[str, str] = {
    "music": "Zapisano materiały w bibliotece. Otwórz „Moje materiały”, aby zobaczyć plik .txt oraz pliki audio (KIE: .mp3, Lyria: .wav).",
    "graphics": "Zapisano plik w „Moje materiały”.",
    "video": "Zapisano materiał wideo w „Moje materiały”.",
    "scenario": "Zapisano scenariusz w „Moje materiały”.",
    "poetry": "Zapisano wiersz w „Moje materiały”.",
    "presentation": "Zapisano plan prezentacji w „Moje materiały”.",
    "study": "Zapisano opracowanie tematu w „Moje materiały”.",
}

_INTENT_MODULE_TO_GENERATE_TOOL: dict[str, str] = {
    "scenario": "generate_scenario",
    "music": "generate_music",
    "graphics": "generate_graphics",
    "video": "generate_video",
    "poetry": "generate_poetry",
    "presentation": "generate_presentation",
    "study": "generate_study",
}

_PERSIST_FILE_TOOL_NAMES = frozenset(TOOL_TO_MODULE.keys()) | frozenset({"export_library_file"})

_NON_FILE_OR_SETUP_TOOLS = frozenset({
    "ask_clarification",
    "reply_to_user",
    "search_library_fragments",
    "search_web",
    "prepare_create_teacher_project",
    "prepare_delete_teacher_project",
})


def _user_requires_library_persist(user_message: str) -> bool:
    """Czy wiadomość wyraźnie wymaga zapisu pliku w bibliotece (nie tylko tekstu w czacie)."""
    t = (user_message or "").lower()
    if re.search(r"\bnowy plik\b|\bnowego pliku\b|\bnowym pliku\b", t):
        return True
    if any(
        p in t
        for p in (
            "przygotuj plik",
            "przygotuj nowy",
            "zrób plik",
            "zrob plik",
            "plik ze scenariusz",
            "scenariusz z piosenk",
            "w moje materiały",
            "w moje materialy",
        )
    ):
        return True
    if "do pobrania" in t or "pobierz plik" in t:
        return True
    if re.search(r"\bgdzie\b.{0,120}\bplik", t):
        return True
    if "zapisz" in t and any(x in t for x in ("materiał", "material", "bibliotek", "scenariusz")):
        return True
    if "nowa wersja" in t and "scenariusz" in t:
        return True
    return False


def _should_retry_llm_for_library_persist(completion: Any, user_message: str) -> bool:
    """Gdy user chce plik w „Moje materiały”, a model zwrócił tylko tekst / szukanie — ponów LLM.

    **Nie** ponawiaj, gdy jest ``prepare_create_teacher_project`` / ``prepare_delete_teacher_project`` —
    wtedy UI pokazuje własny przycisk potwierdzenia; druga tura LLM zastąpiłaby odpowiedź i **usunęłaby token** z JSON.
    """
    if not _user_requires_library_persist(user_message):
        return False
    if not completion.tool_calls:
        return True
    names = {tc.name or "" for tc in completion.tool_calls}
    if names <= {"ask_clarification"}:
        return False
    if "prepare_create_teacher_project" in names or "prepare_delete_teacher_project" in names:
        return False
    for n in names:
        if n in _PERSIST_FILE_TOOL_NAMES:
            return False
        if n not in _NON_FILE_OR_SETUP_TOOLS:
            return False
    return True


def _message_suggests_followup_addition(user_message: str) -> bool:
    t = (user_message or "").lower()
    markers = (
        "dodatk",
        "jeszcze",
        "kolejn",
        "następn",
        "ekstra",
        " drug",
        "trzeci",
        "another",
        "one more",
        "poza tym",
        "oprócz",
        "oprocz",
    )
    if "tylko " in t or t.strip().startswith("tylko"):
        return True
    return any(m in t for m in markers)


def _narrow_incremental_generate_intent(user_message: str) -> str | None:
    """Jednoznaczny jeden typ materiału w prośbie — inaczej None (bez agresywnego filtra)."""
    t = (user_message or "").lower()
    mentions: dict[str, bool] = {
        "scenario": any(
            k in t
            for k in ("scenariusz", "przedstaw", "jaseł", "jasel", "dialog", "widowisk", "dramat", "sceny")
        ),
        "music": any(
            k in t
            for k in (
                "piosenk",
                "muzyk",
                "nut",
                "refren",
                "śpiew",
                "spiew",
                "utwór",
                "utwor",
                "suno",
                "chór",
            )
        ),
        "graphics": any(k in t for k in ("grafik", "plakat", "obraz", "ilustrac", "poster", "okład", "oklad")),
        "video": any(k in t for k in ("wideo", "film", "storyboard", "kadr")),
        "poetry": any(k in t for k in ("wiersz", "poezj", "haiku")),
        "presentation": any(k in t for k in ("prezentac", "slajd", "powerpoint")),
        "study": any(k in t for k in ("opracow", "pogłęb", "pogleb", "notatki do lekcji")),
    }
    true_keys = [k for k, v in mentions.items() if v]
    if len(true_keys) != 1:
        return None
    return true_keys[0]


def _history_shows_prior_generated_artifacts(history: list[tuple[str, str]]) -> bool:
    """Czy w historii są znaczniki z backendu o już zapisanych materiałach."""
    for role, content in history:
        if role != "assistant":
            continue
        c = content or ""
        if "[W tej odpowiedzi wygenerowano moduły:" in c or "[Pliki zapisane w bibliotece:" in c:
            return True
    return False


def _filter_incremental_redundant_tool_calls(
    user_message: str,
    history: list[tuple[str, str]],
    tool_calls: list[Any],
) -> list[Any]:
    """Gdy użytkownik dopisuje jeden typ materiału, usuń inne wywołania generate_* (oszczędność tokenów i plików)."""
    if not tool_calls:
        return tool_calls
    intent_mod = _narrow_incremental_generate_intent(user_message)
    if intent_mod is None:
        return tool_calls
    if not (
        _message_suggests_followup_addition(user_message)
        or _history_shows_prior_generated_artifacts(history)
    ):
        return tool_calls
    keep_name = _INTENT_MODULE_TO_GENERATE_TOOL.get(intent_mod)
    if not keep_name or keep_name not in TOOL_TO_MODULE:
        return tool_calls
    filtered: list[Any] = []
    removed = False
    for tc in tool_calls:
        name = tc.name or ""
        if name in TOOL_TO_MODULE and name != keep_name:
            removed = True
            logger.info(
                "Pominięto %s — wąska prośba kontynuacyjna (zostaje %s).",
                name,
                keep_name,
            )
            continue
        filtered.append(tc)
    if not removed:
        return tool_calls
    if not any((tc.name or "") == keep_name for tc in filtered):
        logger.info("Filtr kontynuacji cofnięty — brak wywołania %s w odpowiedzi modelu.", keep_name)
        return tool_calls
    return filtered


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
    has_saved_audio: bool,
    result: Any,
    *,
    poll_enabled: bool,
    music_providers_configured: bool,
) -> str | None:
    """Komunikat przy braku zapisanego audio — KIE i/lub Lyria."""
    if has_saved_audio:
        return None
    if not music_providers_configured:
        return (
            "Generacja audio nie jest skonfigurowana (ustaw **KIE_API_KEY** i/lub **OPENROUTER_API_KEY** "
            "oraz włączoną Lyrię) — zapisano tylko materiał tekstowy."
        )
    parts: list[str] = []
    if extra.get("kie_error"):
        parts.append(f"KIE — problem przy uruchomieniu generacji:\n{str(extra['kie_error'])[:900]}")
    if extra.get("kie_download_error"):
        parts.append(f"KIE — nie udało się pobrać pliku audio:\n{str(extra['kie_download_error'])[:700]}")
    if extra.get("kie_download_errors"):
        kde = extra["kie_download_errors"]
        if isinstance(kde, list) and kde:
            parts.append("KIE — błędy pobierania wariantów:\n" + "\n".join(str(x)[:350] for x in kde[:5]))
    if extra.get("kie_poll_error"):
        parts.append(
            "KIE — zadanie nie zakończyło się powodzeniem albo zwrócono błąd:\n"
            f"{str(extra['kie_poll_error'])[:900]}"
        )
    if (
        result
        and getattr(result, "ok", False)
        and getattr(result, "task_id", None)
        and extra.get("kie_submitted")
        and not parts
    ):
        if not poll_enabled:
            parts.append(
                "Automatyczne oczekiwanie na MP3 jest wyłączone (KIE_MUSIC_POLL_TIMEOUT_SECONDS = 0). "
                "Gdy utwór będzie gotów, użyj taskId z pliku .txt w „Moje materiały” (import z KIE)."
            )
        else:
            st = extra.get("kie_poll_status")
            if st == "SUCCESS" and not extra.get("kie_audio_urls"):
                parts.append(
                    "KIE zgłosił zakończenie zadania, ale w odpowiedzi nie było jeszcze adresu audio. "
                    "Możesz ponowić import MP3 po taskId w „Moje materiały”."
                )
            else:
                parts.append(
                    "W ustawionym czasie nie pojawiło się gotowe audio od KIE — sprawdź saldo KIE i taskId w pliku .txt; "
                    "możesz ponowić import w „Moje materiały”."
                )
    ly_errs = extra.get("lyria_errors")
    if isinstance(ly_errs, list) and ly_errs:
        parts.append("OpenRouter Lyria:\n" + "\n".join(str(x)[:450] for x in ly_errs[:6]))
    if parts:
        return "\n\n".join(parts)[:2200]
    return None


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


async def _resolve_search_project_scope(
    session: AsyncSession,
    user_id: UUID,
    tool_args: dict[str, Any],
    active_project_id: UUID | None,
) -> tuple[UUID | None, str | None]:
    """Zakres ``project_id`` dla ``semantic_search_chunks`` oraz ewentualna notka do odpowiedzi."""
    if tool_args.get("entire_library") is True:
        return None, None
    pid_raw = tool_args.get("project_id")
    if pid_raw not in (None, ""):
        try:
            uid = UUID(str(pid_raw).strip())
        except (ValueError, TypeError):
            return active_project_id, "Nieprawidłowy **project_id** w wyszukiwaniu — użyto domyślnego zakresu (aktywny katalog lub cała biblioteka)."
        row = await session.get(ProjectORM, uid)
        if row is None or row.user_id != user_id:
            return active_project_id, "Wskazany katalog nie istnieje lub nie należy do użytkownika — użyto domyślnego zakresu."
        return uid, None
    pname_raw = tool_args.get("project_name")
    if pname_raw is not None and str(pname_raw).strip():
        q = str(pname_raw).strip()
        stmt_exact = (
            select(ProjectORM)
            .where(ProjectORM.user_id == user_id)
            .where(func.lower(ProjectORM.name) == q.lower())
        )
        rows = list((await session.scalars(stmt_exact)).all())
        if len(rows) == 1:
            return rows[0].id, None
        stmt_like = (
            select(ProjectORM)
            .where(ProjectORM.user_id == user_id)
            .where(ProjectORM.name.ilike(f"%{q}%"))
        )
        rows = list((await session.scalars(stmt_like)).all())
        if len(rows) == 1:
            return rows[0].id, None
        if len(rows) == 0:
            return None, (
                f"Nie znaleziono katalogu pasującego do „{q}” — przeszukuję całą bibliotekę (bez „Omówienia tematu”)."
            )
        sample = ", ".join(f"„{r.name}”" for r in rows[:5])
        suffix = f" (+{len(rows) - 5} więcej)" if len(rows) > 5 else ""
        return None, (
            f"Wiele katalogów pasuje do „{q}”: {sample}{suffix}. Podaj dokładną nazwę lub UUID z listy — przeszukuję całą bibliotekę."
        )
    return active_project_id, None


async def _resolve_write_project_id(
    session: AsyncSession,
    user_id: UUID,
    tool_args: dict[str, Any],
    active_project_id: UUID | None,
) -> tuple[UUID | None, str | None]:
    """Katalog zapisu pliku: opcjonalny ``project_id`` z narzędzia lub katalog aktywny rozmowy."""
    pid_raw = tool_args.get("project_id")
    if pid_raw in (None, ""):
        return active_project_id, None
    try:
        uid = UUID(str(pid_raw).strip())
    except (ValueError, TypeError):
        return active_project_id, (
            "Nieprawidłowy **project_id** przy zapisie — użyto katalogu aktywnego w rozmowie "
            "(lub „Inne pliki”, gdy brak aktywnego)."
        )
    row = await session.get(ProjectORM, uid)
    if row is None or row.user_id != user_id:
        return active_project_id, (
            "Podany katalog zapisu nie istnieje lub nie należy do użytkownika — użyto katalogu aktywnego w rozmowie."
        )
    return uid, None


async def _build_projects_catalog_block(
    session: AsyncSession, user_id: UUID, active_project_id: UUID | None,
) -> str:
    """Lista katalogów użytkownika z liczbą plików — dla LLM (dopasowanie tematu do folderu)."""
    proj_stmt = (
        select(ProjectORM)
        .where(ProjectORM.user_id == user_id)
        .order_by(ProjectORM.created_at.desc())
    )
    projects = list((await session.scalars(proj_stmt)).all())
    cnt_rows = (
        await session.execute(
            select(FileAssetORM.project_id, func.count(FileAssetORM.id))
            .where(FileAssetORM.user_id == user_id)
            .group_by(FileAssetORM.project_id)
        )
    ).all()
    counts: dict[Any, int] = {pid: int(n) for pid, n in cnt_rows}
    loose = int(counts.get(None, 0))
    lines: list[str] = []
    if projects:
        lines.append("=== Katalogi użytkownika (foldery w „Moje materiały”) ===")
        for p in projects:
            desc = (p.description or "").replace("\n", " ").strip()
            if len(desc) > 220:
                desc = desc[:217].rstrip() + "…"
            n_files = int(counts.get(p.id, 0))
            tail = f" — {desc}" if desc else ""
            lines.append(f"- **id=`{p.id}`** | **{p.name}**{tail} | plików: {n_files}")
    lines.append(f'Pliki poza katalogami („Inne pliki”): {loose}.')
    if active_project_id:
        ap = next((x for x in projects if x.id == active_project_id), None)
        if ap:
            lines.append(
                f'**Katalog aktywny w tej rozmowie (UI):** „{ap.name}” (`{active_project_id}`). '
                "Domyślnie nowe pliki trafiają tutaj; możesz też podać inny **project_id** z listy powyżej "
                "w argumentach ``generate_*`` lub ``export_library_file`` — wtedy zapis do wskazanego katalogu."
            )
        else:
            lines.append(
                f"**Katalog aktywny w UI:** `{active_project_id}` (brak na liście — sprawdź w aplikacji)."
            )
    else:
        lines.append(
            "**Katalog aktywny w tej rozmowie:** brak — nowe pliki trafią do „Inne pliki”, "
            "chyba że w wywołaniu ``generate_*`` / ``export_library_file`` podasz **project_id** z listy albo użytkownik powiąże rozmowę z folderem w UI."
        )
    lines.append(
        "Gdy temat rozmowy pasuje do nazwy/opisu katalogu, wywołaj **search_library_fragments** z **project_id** "
        "(lub **project_name**). Przy niepewności — **ask_clarification** z propozycjami z listy."
    )
    return "\n".join(lines)


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
    if module == "study":
        return _sanitize_filename_stem(str(ta.get("topic") or "opracowanie")) or "opracowanie"
    return _sanitize_filename_stem(module) or module


def _tool_call_sort_key(tc: Any) -> tuple[int, str]:
    name = tc.name or ""
    if name in ("prepare_create_teacher_project", "prepare_delete_teacher_project"):
        return (0, tc.id or "")
    if name == "search_library_fragments":
        return (1, tc.id or "")
    if name == "search_web":
        return (2, tc.id or "")
    if name in TOOL_TO_MODULE:
        return (3, tc.id or "")
    if name == "export_library_file":
        return (4, tc.id or "")
    if name in ("reply_to_user", "ask_clarification"):
        return (5, tc.id or "")
    return (3, tc.id or "")


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
        lyria_music: OpenRouterLyriaMusicGenerator | None = None,
    ) -> None:
        self._llm = llm
        self._llm_modules = llm_modules or llm
        self._storage = storage
        self._image_gen = image_gen
        self._video_gen = video_gen
        self._music_gen = music_gen
        self._lyria_music = lyria_music

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

        hist_cap = get_settings().chat_orchestrator_max_messages
        hist_slice = history[-hist_cap:] if hist_cap > 0 else history
        api_messages: list[dict[str, Any]] = [
            {"role": role, "content": content} for role, content in hist_slice
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

        if not dry_run and _should_retry_llm_for_library_persist(completion, message):
            logger.info(
                "Orchestrator: ponawiam wywołanie LLM — prośba o zapis w bibliotece bez generate_*/export_library_file.",
            )
            correction = (
                "【Wymóg systemu】 Poprzednia odpowiedź nie wywołała narzędzia zapisującego plik w „Moje materiały”. "
                "Użytkownik oczekuje pliku w bibliotece. Wywołaj teraz **generate_scenario** (scenariusz, także ze "
                "wkomponowaną piosenką — całość w jednym pliku) lub inne właściwe **generate_*** z **nowym** "
                "**material_title**. **reply_to_user** samo w sobie **nie tworzy pliku** — nie pisz, że plik został "
                "zapisany, dopóki nie użyjesz narzędzia."
            )
            api_retry = [*api_messages, {"role": "user", "content": correction}]
            completion = await self._llm.complete_with_tools(
                ORCHESTRATOR_SYSTEM, api_retry, TOOL_DEFINITIONS,
            )
            logger.debug(
                "LLM retry (persist): tool_calls=%d text_len=%d",
                len(completion.tool_calls), len(completion.text or ""),
            )
            await record_llm_usage_event(
                session,
                user_id=user_id,
                call_kind="orchestrator_retry",
                module_name=None,
                completion=completion,
                system_text=ORCHESTRATOR_SYSTEM,
                user_text=f"{user_content}\n\n[retry_persist]\n{correction}",
                dry_run=dry_run,
            )

        return await self._process_tool_calls(
            session, user_id, project_id, message, context_block, completion, dry_run, history,
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
        parts.append(await _build_projects_catalog_block(session, user_id, project_id))
        return "\n".join(parts)

    # --- Przetwarzanie tool calls ---

    async def _process_tool_calls(
        self, session: AsyncSession, user_id: UUID, project_id: UUID | None,
        user_message: str, context: str, completion: Any, dry_run: bool,
        history: list[tuple[str, str]],
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
        scenario_used_this_turn = False

        tool_calls_in = list(completion.tool_calls)
        tool_calls_eff = _filter_incremental_redundant_tool_calls(user_message, history, tool_calls_in)
        sorted_calls = sorted(tool_calls_eff, key=_tool_call_sort_key)
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
                raw_msg = (tc.arguments.get("message") or "").strip()
                if (
                    len(raw_msg) > _REPLY_TO_USER_MAX_AFTER_TEXT_MODULE
                    and _TEXT_FILE_MODULES.intersection(run_modules)
                ):
                    logger.info(
                        "Pominięto długi reply_to_user — pełna treść jest w zapisanym pliku modułu (%s).",
                        ", ".join(sorted(_TEXT_FILE_MODULES.intersection(run_modules))),
                    )
                else:
                    reply_parts.append(raw_msg)

            elif tc.name == "search_library_fragments":
                q = (tc.arguments.get("query") or "").strip() or user_message.strip()
                if dry_run:
                    side_effects_skipped = True
                    reply_parts.append("[Dry-run] Wyszukiwanie w bibliotece zostało pominięte.")
                    continue
                search_scope_id, scope_note = await _resolve_search_project_scope(
                    session, user_id, tc.arguments, active_project_id,
                )
                if scope_note:
                    reply_parts.append(scope_note)
                try:
                    search_hits = await semantic_search_chunks(
                        session, user_id, q, top_k=8, project_id=search_scope_id,
                    )
                except Exception as exc:
                    logger.exception("search_library_fragments failed")
                    reply_parts.append(f"Nie udało się przeszukać biblioteki: {exc}")
                    continue
                scope_hint = (
                    f" (katalog: {search_scope_id})"
                    if search_scope_id is not None
                    else " (cała biblioteka)"
                )
                ctx_search = "\n\n".join(
                    f"[{c.file_asset.name}]: {c.text}"
                    for c, _ in search_hits if c.file_asset is not None
                )
                if ctx_search:
                    block = f"=== Fragmenty z biblioteki (zapytanie: {q}{scope_hint}) ===\n{ctx_search}"
                    n_fr = len(search_hits)
                    reply_parts.append(
                        f"Przeszukałem Twoją bibliotekę ({n_fr} fragmentów) — użyłem ich przy generowaniu; "
                        "nie powielam surowej treści tutaj, żeby czat pozostał czytelny."
                    )
                    dynamic_context = f"{dynamic_context}\n{block}" if dynamic_context else block
                else:
                    reply_parts.append(
                        "(Brak trafnych fragmentów w zindeksowanej bibliotece — upewnij się, że pliki są przesłane i zindeksowane.)"
                    )

            elif tc.name == "search_web":
                q = (tc.arguments.get("query") or "").strip() or user_message.strip()
                if dry_run:
                    side_effects_skipped = True
                    reply_parts.append("[Dry-run] Wyszukiwanie w internecie zostało pominięte.")
                    continue
                hits, err = await run_web_search(q)
                if err:
                    reply_parts.append(err)
                if hits:
                    block = format_hits_for_llm(q, hits)
                    reply_parts.append(
                        f"Wyszukałem w internecie ({len(hits)} wyników) — przekazałem je do opracowania; "
                        "Pełna lista źródeł będzie w zapisanym pliku (ostatnia sekcja dokumentu)."
                    )
                    dynamic_context = f"{dynamic_context}\n{block}" if dynamic_context else block
                elif not err:
                    reply_parts.append("(Brak wyników wyszukiwania w internecie dla tego zapytania.)")

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
                n_files = await session.scalar(
                    select(func.count())
                    .select_from(FileAssetORM)
                    .where(FileAssetORM.project_id == proj_row.id)
                )
                nf = int(n_files or 0)
                s = get_settings()
                del_tok = create_resource_confirmation_token(
                    user_id=user_id,
                    action=ACTION_DELETE_PROJECT,
                    resource_type=RESOURCE_PROJECT,
                    resource_id=proj_row.id,
                )
                files_summary = (
                    f" Powiązane pliki ({nf}) zostaną trwale usunięte z biblioteki i indeksu."
                    if nf
                    else " W folderze nie ma plików — usunięty zostanie tylko projekt."
                )
                pending_project_deletion = {
                    "confirmation_token": del_tok,
                    "expires_in_seconds": s.confirmation_token_expire_minutes * 60,
                    "summary": f"Czy na pewno usunąć projekt „{proj_row.name}”?{files_summary}",
                    "project_id": str(proj_row.id),
                    "project_name": proj_row.name,
                }
                reply_parts.append(
                    f"Przygotowałem usunięcie projektu **„{proj_row.name}”**.{files_summary}"
                    "\n\nPotwierdź przyciskiem pod odpowiedzią lub w „Moje materiały” — bez potwierdzenia projekt **nie** "
                    "zostanie usunięty."
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
                        write_pid, write_note = await _resolve_write_project_id(
                            session, user_id, tc.arguments, active_project_id,
                        )
                        if write_note:
                            reply_parts.append(write_note)
                        new_fid = await persist_export_as_new_file(
                            session, user_id, fid, write_pid, fmt, self._storage,
                        )
                        created.append(new_fid)
                        last_created_file_id = new_fid
                        reply_parts.append(f"Zapisano eksport ({fmt}) w bibliotece.")
                    except ValueError as exc:
                        reply_parts.append(str(exc))

            elif tc.name in TOOL_TO_MODULE:
                module = TOOL_TO_MODULE[tc.name]
                if tc.name == "generate_scenario":
                    if scenario_used_this_turn:
                        logger.info("Pominięto zduplikowane generate_scenario w tej samej turze czatu")
                        reply_parts.append(
                            "Pominięto dodatkowe wywołanie **generate_scenario** — w jednej odpowiedzi "
                            "backend zapisuje co najwyżej **jeden** scenariusz."
                        )
                        continue
                    scenario_used_this_turn = True
                run_modules.append(module)
                if dry_run:
                    side_effects_skipped = True
                    reply_parts.append(
                        f"[Symulacja] Moduł **{module}** zostałby uruchomiony — pliki oraz wywołania KIE/Lyria **nie** są wykonywane."
                    )
                else:
                    write_pid, write_note = await _resolve_write_project_id(
                        session, user_id, tc.arguments, active_project_id,
                    )
                    if write_note:
                        reply_parts.append(write_note)
                    mod_fids, mod_note = await self._run_module(
                        session, user_id, write_pid, module, user_message, dynamic_context, tc.arguments,
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
                    "\nDołączono pliki audio (KIE: .mp3, Lyria: .wav) — pobierzesz je przyciskami pod wiadomością albo z „Moje materiały”."
                )
            else:
                lines.append(
                    "\nW pliku .txt jest m.in. tekst piosenki, styl oraz (jeśli KIE przyjęło zadanie) identyfikator taskId "
                    "i odpowiedź API; przy Lyrii — komunikaty z OpenRouter. Sprawdź też ewentualne błędy pobierania audio."
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

        args_for_prompt = dict(tool_args) if tool_args else {}
        args_for_prompt.pop("project_id", None)
        args_str = json.dumps(args_for_prompt, ensure_ascii=False) if args_for_prompt else ""
        user_part = f"Kontekst:\n{context}\n\nParametry:\n{args_str}\n\nProśba:\n{user_message}"
        logger.debug("Running module %r via %s", mod, type(self._llm_modules).__name__)
        mod_completion = await self._llm_modules.complete(sys_prompt, user_part)
        logger.debug(
            "Module %r result: provider=%s model=%s text_len=%d tokens=%s finish=%s",
            mod, mod_completion.provider, mod_completion.model,
            len(mod_completion.text or ""), mod_completion.resolved_total_tokens(),
            mod_completion.finish_reason,
        )
        await record_llm_usage_event(
            session, user_id=user_id, call_kind="module", module_name=mod,
            completion=mod_completion, system_text=sys_prompt, user_text=user_part,
        )
        content = mod_completion.text if mod_completion.text is not None else ""
        trunc_note: str | None = None
        if (mod_completion.finish_reason or "").lower() == "length":
            trunc_note = (
                "**Uwaga:** odpowiedź modelu mogła zostać ucięta na limicie długości — koniec pliku może być niepełny. "
                "Spróbuj krótszego zakresu (np. „tylko biografia + dwa wiersze”) albo zwiększ "
                "**OPENROUTER_MODULE_MAX_COMPLETION_TOKENS** w konfiguracji serwera."
            )

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
        return [fid], trunc_note

    # --- Grafika ---

    async def _handle_graphics(
        self, session: AsyncSession, user_id: UUID, project_id: UUID | None,
        llm_content: str, tool_args: dict[str, Any],
    ) -> UUID:
        prompt_data = _parse_media_json(llm_content)
        desc_fallback = str(tool_args.get("description", "") or "")
        prompt_main = (
            str(prompt_data.get("prompt_image") or "").strip()
            or str(prompt_data.get("prompt_en") or "").strip()
            or desc_fallback
        )
        prompt_en_legacy = str(prompt_data.get("prompt_en") or "").strip()
        extra: dict[str, Any] = {
            "module": "graphics",
            "tool_args": tool_args,
            "prompt_image": prompt_data.get("prompt_image"),
            "prompt_en": prompt_en_legacy or None,
            "style_notes": prompt_data.get("style_notes", ""),
            "description_pl": prompt_data.get("description_pl", desc_fallback),
        }

        if self._image_gen:
            try:
                result = await self._image_gen.generate(
                    prompt=prompt_main, style=tool_args.get("style"), size=tool_args.get("size", "1024x1024"),
                )
                extra["revised_prompt"] = result.revised_prompt
                extra["generator_model"] = result.model
                index_text = (
                    f"{extra['description_pl']}\n{prompt_main}\n{result.revised_prompt or ''}".strip()
                )
                mime = result.mime_type or "image/png"
                ext = "png"
                if "jpeg" in mime or "jpg" in mime:
                    ext = "jpg"
                elif "webp" in mime:
                    ext = "webp"
                return await self._persist_file(
                    session, user_id, project_id, "graphics",
                    data=result.image_data, mime=mime, ext=ext, extra=extra,
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

    # --- Muzyka (LLM + KIE + opcjonalnie OpenRouter Lyria) ---

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
        style_full = (style_en or style or "Educational pop for children, cheerful, classroom-friendly")
        n_variants = min(max(1, int(s.music_variants_per_provider)), 5)
        extra: dict[str, Any] = {
            "module": "music",
            "tool_args": tool_args,
            "kie_submitted": False,
            "music_variants_per_provider": n_variants,
            "openrouter_music_model": s.openrouter_music_model,
        }
        result = None
        kie_saved = 0
        lyria_saved = 0
        kie_saved_files: list[tuple[int, bytes, str]] = []
        lyria_wav_files: list[tuple[int, bytes]] = []

        if self._music_gen:
            req = MusicSubmitRequest(
                prompt=api_prompt,
                title=title,
                style=style_full,
                instrumental=False,
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
                    if urls and st in KIE_STATUSES_WITH_POSSIBLE_AUDIO:
                        extra["kie_audio_urls"] = urls
                        dl_errors: list[str] = []
                        for idx, url in enumerate(urls[:n_variants], start=1):
                            try:
                                mp3_b = await download_audio_url(url)
                                extra[f"kie_audio_downloaded_from_{idx}"] = url
                                kie_saved_files.append((idx, mp3_b, url))
                                kie_saved += 1
                            except Exception as dl_exc:
                                logger.warning("KIE audio download failed #%s: %s", idx, dl_exc)
                                dl_errors.append(f"#{idx}: {dl_exc!s:.350}")
                        if dl_errors:
                            extra["kie_download_errors"] = dl_errors
                        if kie_saved == 0 and dl_errors:
                            extra["kie_download_error"] = "; ".join(dl_errors)[:800]
                        if urls:
                            extra["kie_audio_downloaded_from"] = urls[0]
                        break
                    if st == "SUCCESS" and not urls:
                        pass
                    elif st in KIE_TERMINAL_FAIL_STATUSES:
                        break
                    await asyncio.sleep(interval)

        lyria_errors: list[str] = []
        lyria_traces: list[Any] = []
        if (
            self._lyria_music
            and s.openrouter_music_enabled
            and (s.openrouter_api_key or "").strip()
        ):
            extra["lyria_submitted"] = True

            async def _one_lyria(
                variant_index: int,
            ) -> tuple[int, bytes | None, str | None, list[dict[str, Any]], str | None]:
                suffix = (
                    f"Produce a distinct full song — arrangement variant {variant_index} of {n_variants} "
                    "(different melody, rhythm or energy while preserving the same lyrics and title theme)."
                )
                audio_b, cdn_url, trace, err = await self._lyria_music.generate(
                    title=title,
                    style=style_full,
                    lyrics=api_prompt,
                    instrumental=False,
                    variation_suffix=suffix,
                )
                return variant_index, audio_b, cdn_url, trace, err

            raw_results = await asyncio.gather(
                *(_one_lyria(i) for i in range(1, n_variants + 1)),
                return_exceptions=True,
            )
            for item in raw_results:
                if isinstance(item, BaseException):
                    lyria_errors.append(f"Lyria: {item!s:.500}")
                    continue
                variant_index, audio_b, _cdn, trace, err = item
                if trace:
                    lyria_traces.append({"variant": variant_index, "trace": trace[:12]})
                if err:
                    lyria_errors.append(f"Lyria #{variant_index}: {err[:600]}")
                elif audio_b:
                    extra[f"lyria_audio_variant_{variant_index}_bytes"] = len(audio_b)
                    lyria_wav_files.append((variant_index, audio_b))
                    lyria_saved += 1
            if lyria_traces:
                extra["lyria_traces_compact"] = lyria_traces
            if lyria_errors:
                extra["lyria_errors"] = lyria_errors

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
            elif kie_saved:
                parts.append(
                    f"\n\n**Pobrano {kie_saved} plik(ów) audio z KIE** i zapisano jako `.mp3` w bibliotece."
                )
        if extra.get("lyria_submitted"):
            parts.append("\n\n## OpenRouter Lyria\n\n")
            parts.append(f"Model: `{extra.get('openrouter_music_model')}`\n")
            if lyria_errors:
                parts.append("\n**Komunikaty:**\n" + "\n".join(str(x) for x in lyria_errors[:10]))
            if lyria_saved:
                parts.append(f"\n\nZapisano **{lyria_saved}** plik(ów) `.wav` w bibliotece.")
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
        for idx, mp3_b, url in kie_saved_files:
            mp3_extra: dict[str, Any] = {
                "module": "music",
                "tool_args": tool_args,
                "kie_task_id": extra.get("kie_task_id"),
                "kie_audio_url": url,
                "file_stem_suffix": f"kie_{idx}",
                "related_txt_context": "Powiązany raport KIE w pliku .txt z tej samej generacji.",
            }
            idx_text = f"{title}\n{url}\n{api_prompt[:4000]}".strip()
            mp3_id = await self._persist_file(
                session, user_id, project_id, "music",
                data=mp3_b, mime="audio/mpeg", ext="mp3",
                extra=mp3_extra,
                index_override=idx_text,
            )
            out.append(mp3_id)
        for variant_index, wav_b in lyria_wav_files:
            wav_extra: dict[str, Any] = {
                "module": "music",
                "tool_args": tool_args,
                "openrouter_music_model": extra.get("openrouter_music_model"),
                "lyria_variant": variant_index,
                "file_stem_suffix": f"lyria_{variant_index}",
                "related_txt_context": "Powiązany raport w pliku .txt z tej samej generacji.",
            }
            widx = f"{title}\nLyria wariant {variant_index}\n{api_prompt[:4000]}".strip()
            wav_id = await self._persist_file(
                session, user_id, project_id, "music",
                data=wav_b, mime="audio/wav", ext="wav",
                extra=wav_extra,
                index_override=widx,
            )
            out.append(wav_id)
        poll_enabled = bool(
            self._music_gen
            and result
            and result.ok
            and result.task_id
            and s.kie_music_poll_timeout_seconds > 0,
        )
        music_providers_configured = bool(self._music_gen) or bool(
            self._lyria_music
            and s.openrouter_music_enabled
            and (s.openrouter_api_key or "").strip()
        )
        has_saved_audio = kie_saved + lyria_saved > 0
        note = _music_kie_status_note(
            extra,
            has_saved_audio,
            result,
            poll_enabled=poll_enabled,
            music_providers_configured=music_providers_configured,
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
        suf = extra.get("file_stem_suffix")
        if isinstance(suf, str) and suf.strip():
            stem = f"{stem}_{suf.strip().replace(' ', '_')[:48]}"
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
