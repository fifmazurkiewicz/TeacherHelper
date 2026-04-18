# modules/presentation — generator prezentacji

## Odpowiedzialność

Automatyczne slajdy PowerPoint w trybach:

- **Z tematu** — struktura i treść od zera.
- **Z obszaru** — zgodność z podstawą programową (np. przyroda).
- **Ze scenariusza** — konwersja istniejącego scenariusza na slajdy.

## Zaimplementowane

- Generowanie planu prezentacji (markdown) przez tool calling (`generate_presentation`).
- Eksport do PPTX (`python-pptx`) — automatyczne parsowanie markdown na slajdy.
- Eksport do PDF.

## Formaty

PPTX, PDF, PNG (slajdy).

## Adaptery / narzędzia

**OpenRouter** (treść, struktura) + **python-pptx** (Python) — generowanie pliku PPTX.

## Powiązanie z file-context

Tryb „ze scenariusza" wymaga odczytu pliku przez **ReadFileContext** / bezpośredni odczyt z **core/files**.
