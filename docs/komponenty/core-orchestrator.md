# core/orchestrator — analiza intencji i plan (tool calling)

## Odpowiedzialność

- Rozpoznanie intencji z wypowiedzi użytkownika (nowe zadanie vs. pytanie o istniejący plik).
- Delegowanie akcji przez **tool calling** (LLM decyduje które narzędzia wywołać).
- Koordynacja wykonania modułów generowania, obsługa postępu i błędów.

## Zaimplementowane

- Orchestrator oparty na **tool calling** (OpenAI-compatible function calling).
- Zdefiniowane narzędzia: `ask_clarification`, `reply_to_user`, `generate_scenario`, `generate_graphics`, `generate_video`, `generate_music`, `generate_poetry`, `generate_presentation`.
- LLM sam decyduje czy dopytać (ask_clarification) czy generować materiał.
- Obsługa wielu tool calls w jednej odpowiedzi (np. scenariusz + piosenka jednocześnie).
- Historia konwersacji przekazywana do LLM jako messages API.
- Kontekst plików (Qdrant search + załączniki) dołączany do wiadomości.

## Zależności zewnętrzne

- **OpenRouter** — LLM z obsługą tool calling (kompatybilny z OpenAI Chat Completions).
- **Qdrant** — wyszukiwanie semantyczne kontekstu plików.

## Porty (interfejsy wyjściowe)

- `LlmClientPort.complete_with_tools()` — wywołanie LLM z definicjami narzędzi.
- `LlmClientPort.complete()` — standardowe wywołanie dla modułów generowania.

## Zasady

- Orkiestrator nie zawiera szczegółów promptów konkretnych modułów — tylko delegacja.
- LLM decyduje o przepływie przez tool calling, nie przez hardcoded pipeline.
- Użytkownik widzi plan przed kosztownym generowaniem (ask_clarification).
