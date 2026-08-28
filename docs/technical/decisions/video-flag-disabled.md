# ADR: generowanie wideo wyłączone flagą

**Data:** 2026-08-28  
**Status:** zaakceptowany

## Kontekst

Integracja Veo (generowanie wideo) jest kosztowna i produkuje duże pliki.

## Decyzja

`VIDEO_GENERATION_ENABLED` (domyślnie `false`): narzędzie `generate_video` nie trafia do listy orchestratora. Próba użycia kończy się komunikatem o chwilowej niedostępności. **Kod adaptera Veo pozostaje nietknięty.**

## Uzasadnienie

- Kontrola kosztów API i miejsca w Storage.
- Możliwość włączenia później bez przepisywania kodu.
- Użytkownik dostaje jasny komunikat zamiast błędu.

## Konsekwencje

- Wymaganie W8 ze specyfikacji designu.
- Włączenie wideo = osobna decyzja produktowa + aktualizacja ADR.
