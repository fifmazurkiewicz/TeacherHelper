# modules/music — prompty muzyczne

## Odpowiedzialność

Generowanie precyzyjnych promptów pod narzędzia zewnętrzne (Suno, MusicGen, Udio): styl, nastrój, tempo, instrumentacja, tekst piosenki.

## Formaty wyjściowe

TXT (prompty), DOCX/PDF z tekstem i opcjonalnie akordami.

## Adaptery

**OpenRouter** do treści promptów; integracja z Suno (lub innym) jako osobny adapter jeśli API dostępne. Uruchamiany przez tool call `generate_music`.
