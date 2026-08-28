# ADR: rate limit w Postgresie zamiast Redisa

**Data:** 2026-08-28  
**Status:** zaakceptowany

## Kontekst

Rate limiting opierał się na Redisie z cichym fallbackiem, gdy Redis był niedostępny.

## Decyzja

Licznik okna czasowego (żądania/min na użytkownika) przechowujemy w **Postgresie**. Redis i zależność `redis` wypadają z projektu.

## Uzasadnienie

- Render Free nie ma darmowego Redis — osobna instancja to dodatkowy koszt i wiring.
- Przy niskim ruchu Postgres wystarczy do liczników okien czasowych.
- Spójność ze standardem: jedna baza danych, zero dodatkowych serwisów.

## Konsekwencje

- Usuwamy: `REDIS_URL`, pakiet `redis`.
- Przy bardzo wysokim ruchu może być potrzebna optymalizacja (indeks, cleanup starych okien).
