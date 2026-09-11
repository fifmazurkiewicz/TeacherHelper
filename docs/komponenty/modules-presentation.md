# modules/presentation — generator prezentacji

## Odpowiedzialność

Automatyczne slajdy PowerPoint w trybach:

- **Z tematu** — struktura i treść od zera.
- **Z obszaru** — zgodność z podstawą programową (np. przyroda).
- **Ze scenariusza** — konwersja istniejącego scenariusza na slajdy.

## Zaimplementowane

- Generowanie strukturalnego planu JSON przez tool calling (`generate_presentation`).
- Eksport do PPTX (`python-pptx`) z układami: tekst, grafika po prawej, pełna grafika,
  porównanie, ćwiczenie i podsumowanie.
- Notatki dla nauczyciela zapisywane jako speaker notes, poza treścią wyświetlaną uczniom.
- Główny osadzony obraz slajdu jest dopasowywany bez rozciągania i zachowywany przy
  edycji pliku PPTX, gdy kolejność slajdów pozostaje jednoznaczna.
- Eksport tekstowego planu do PDF.

## Formaty

PPTX oraz PDF planu.

## Adaptery / narzędzia

**OpenRouter** (treść, struktura) + **python-pptx** (Python) — generowanie pliku PPTX.

## Powiązanie z file-context

Tryb „ze scenariusza" wymaga odczytu pliku przez **ReadFileContext** / bezpośredni odczyt z **core/files**.
