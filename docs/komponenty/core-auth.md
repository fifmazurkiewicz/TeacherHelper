# core/auth — uwierzytelnianie i role

## Odpowiedzialność

Rejestracja, logowanie, sesje, przypisanie ról. Dostarcza tożsamość użytkownika do wszystkich use case'ów i warstwy plików.

## Zaimplementowane

- Rejestracja (e-mail + hasło, bcrypt), logowanie, JWT Bearer.
- Endpoint `GET /v1/auth/me` (dane użytkownika, w tym `is_approved`).
- Brama akceptacji: nowi użytkownicy logują się, ale funkcje `/v1/*` (poza `/me`) zwracają 403 `account_pending_approval` do czasu Accept admina.
- Role: `teacher` (domyślna przy rejestracji), `admin` (nadawana w bazie / przez admina).
- `ADMIN_EMAILS` — auto-rola admin i auto-akceptacja **tylko przy pierwszym insercie profilu**.
- Admin guard (`require_admin`) + opcjonalny `X-Admin-Key`.
- Resetowanie hasła użytkownika z panelu admina (`POST /v1/admin/users/{id}/reset-password`).
- Security headers middleware (HSTS, X-Content-Type-Options, X-Frame-Options, Referrer-Policy).
- Swagger/ReDoc wyłączony w trybie produkcyjnym (`DEBUG=false`).

## Zależności zewnętrzne (adaptery)

- `python-jose` — JWT.
- `bcrypt` — hashowanie haseł.

## Powiązania

- **core/files** — każda operacja na pliku wymaga zweryfikowanego `user_id`.
- **core/file-context** — audyt odczytów AI musi zapisywać identyfikator użytkownika.

## Encje domenowe

`User`, `Role` (nauczyciel | administrator), flaga `is_approved`.

## Zasady

- Brak logiki biznesowej generowania treści w module auth.
- JWT przekazywany w nagłówku `Authorization: Bearer <token>`.
- Dostęp do narzędzia wyłącznie dla zaproszonych osób — admin zarządza kontami.
