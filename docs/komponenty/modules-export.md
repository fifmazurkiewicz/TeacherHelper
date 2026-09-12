# modules/export — konwersja formatów

## Odpowiedzialność

Eksport treści plików do formatów docelowych na podstawie wyodrębnionego tekstu.

## Zaimplementowane

| Format | Narzędzie | Uwagi |
|--------|-----------|-------|
| TXT | encoding UTF-8 | Surowy tekst |
| PDF | `fpdf2` | Automatyczne wyszukiwanie systemowej czcionki Unicode (Arial/DejaVu Sans) dla polskich znaków |
| DOCX | `python-docx` | Domyślny format koncepcji i treści tekstowych; motyw TeacherHelper, marginesy, typografia, nagłówki, listy, numeracja, wyróżnienia i cytaty z wejścia markdown-like |
| PPTX | `python-pptx` | Parsowanie markdown-like tekstu na slajdy (nagłówki → tytuły, listy → punktory) |

**Endpoint:** `POST /v1/files/{file_id}/export?target_format=pdf`

Zwraca plik binarny z nagłówkiem `Content-Disposition: attachment`.

## Przepływ

1. Pobranie pliku ze storage.
2. Ekstrakcja tekstu (`text_extract.py`).
3. Konwersja tekstu do formatu docelowego (`export.py`).
4. Zwrócenie wyniku jako download.

Nowe materiały tekstowe (`study`, `scenario`, `poetry`) są zapisywane od razu jako DOCX, a ich czysta treść nadal trafia do indeksu wyszukiwania. Jawna prośba użytkownika o PDF, TXT lub PPTX ma pierwszeństwo i jest realizowana przez eksport.

## Do zrobienia

- Eksport ZIP całego projektu.
- Konwersja zachowująca formatowanie źródłowe (Pandoc, LibreOffice headless).
- Kolejka dla długotrwałych konwersji (Redis worker).
