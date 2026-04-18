# Opis komponentów systemu

Poniższe pliki rozwijają sekcje analizy v4.0 (architektura modularnego monolitu). Każdy komponent powinien mieć własne `domain` / `use_cases` / `adapters` przy współdzieleniu infrastruktury.

## Rdzeń (core)

| Komponent | Dokument |
|-----------|----------|
| Uwierzytelnianie i role | [core-auth.md](core-auth.md) |
| Orkiestracja intencji (tool calling) | [core-orchestrator.md](core-orchestrator.md) |
| Baza plików (metadane, wersje) | [core-files.md](core-files.md) |
| Kontekst plików dla LLM (Qdrant) | [core-file-context.md](core-file-context.md) |
| Omówienie tematu (zapis plików, podsumowanie + punkty LLM, opcjonalnie Qdrant, czat) | [core-topic-studio.md](core-topic-studio.md) |

## Moduły generowania

| Komponent | Dokument |
|-----------|----------|
| Scenariusze | [modules-scenario.md](modules-scenario.md) |
| Grafiki | [modules-graphics.md](modules-graphics.md) |
| Wideo | [modules-video.md](modules-video.md) |
| Muzyka (prompty) | [modules-music.md](modules-music.md) |
| Wiersze | [modules-poetry.md](modules-poetry.md) |
| Prezentacje PPTX | [modules-presentation.md](modules-presentation.md) |
| Eksport / konwersja formatów | [modules-export.md](modules-export.md) |

## Pozostałe

| Komponent | Dokument |
|-----------|----------|
| Frontend (React + Vite) | [frontend.md](frontend.md) |
| Panel administracyjny | [admin-panel.md](admin-panel.md) |
