# modules/scenario — projektant scenariuszy

## Odpowiedzialność

Generowanie scenariuszy przedstawień: postacie, dialogi, didaskalia, wskazówki reżyserskie, podział na sceny.

## Parametry wejściowe

Temat, wiek/klasa, liczba uczniów, czas trwania, styl (np. komedia, musical). Przekazywane jako argumenty tool call `generate_scenario`.

## Wyjście

Tekst strukturalny + eksport DOCX/PDF/PPTX zgodnie z **modules/export**.

## Adapter AI

**OpenRouter** (przez port LLM). Tool calling decyduje o uruchomieniu tego modułu.

## Use case

`GenerateScenario` — pojedyncza odpowiedzialność, bez mieszania z grafiką czy wideo.
