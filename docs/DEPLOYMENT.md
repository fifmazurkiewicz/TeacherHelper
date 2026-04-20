# Wdrożenie TeacherHelper — Hetzner CX32 + Coolify

Instrukcja krok po kroku dla wdrożenia produkcyjnego. Czas wykonania: ~30-60 minut.

## Wymagania wstępne

- Konto na [hetzner.com](https://hetzner.com)
- Konto na GitHub z dostępem do tego repozytorium
- Klucz SSH wygenerowany lokalnie (`ssh-keygen -t ed25519`)
- Konto na [duckdns.org](https://duckdns.org) (darmowa subdomena)

---

## Architektura

```
Internet → Coolify (reverse proxy + SSL)
              ├── Frontend (Nginx + React SPA)
              │     └── /th-api/ → Backend (FastAPI)
              └── Serwisy wewnętrzne:
                    ├── PostgreSQL 16
                    ├── Qdrant (vector search)
                    └── Redis (cache)
```

Wszystko działa na jednym serwerze. Coolify zarządza kontenerami, SSL i auto-deployem z GitHub.

---

## Krok 1: Utwórz serwer na Hetzner

1. Zaloguj się na [console.hetzner.com](https://console.hetzner.com)
2. **New Server:**
   - Lokalizacja: `Nuremberg` lub `Helsinki`
   - Image: `Ubuntu 22.04`
   - Type: **CX32** (4 vCPU, 8 GB RAM — wymagane dla Coolify)
   - SSH Key: wklej zawartość `~/.ssh/id_ed25519.pub`
3. Kliknij **Create & Buy now**
4. Zapisz IP serwera

**Firewall** (Hetzner → Firewalls → Create Firewall, przypisz do serwera):

| Protokół | Port | Opis |
|---|---|---|
| TCP | 22 | SSH |
| TCP | 80 | HTTP |
| TCP | 443 | HTTPS |
| TCP | 8000 | Coolify panel (można zamknąć po konfiguracji) |

---

## Krok 2: Zainstaluj Coolify

```bash
ssh root@TWOJE_IP

# Instalacja jedną komendą
curl -fsSL https://cdn.coollabs.io/coolify/install.sh | bash
```

Po ~3 minutach otwórz `http://TWOJE_IP:8000` w przeglądarce.

- Utwórz konto admina (e-mail + hasło)
- Serwer `localhost` jest już dodany automatycznie

---

## Krok 3: Dodaj swap (ochrona przed OOM)

```bash
fallocate -l 2G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
```

---

## Krok 4: Zabezpiecz serwer

```bash
# Tylko klucze SSH (wyłącz hasła)
sed -i 's/#PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config
systemctl restart sshd

# Fail2ban — blokuje brute-force na SSH
apt install fail2ban -y
```

---

## Krok 5: Dodaj serwisy bazodanowe w Coolify

Panel Coolify → **Resources → New Resource**:

### PostgreSQL 16
- Wybierz: **Database → PostgreSQL**
- Wersja: `16`
- Kliknij **Deploy**
- Po deployu skopiuj **Connection String** (będzie potrzebny w Kroku 8)

### Redis 7
- Wybierz: **Database → Redis**
- Kliknij **Deploy**
- Skopiuj **Connection String**

### Qdrant
- Wybierz: **Service → Qdrant** (jest w katalogu one-click)
- Port: `6333`
- Kliknij **Deploy**
- Zapamiętaj nazwę serwisu — URL będzie: `http://NAZWA_SERWISU:6333`

---

## Krok 6: Podłącz GitHub

Panel Coolify → **Settings → Source → GitHub**:
1. Kliknij **Register GitHub App**
2. Postępuj zgodnie z instrukcją OAuth
3. Autoryzuj dostęp do repozytorium `TeacherHelper`

---

## Krok 7: Skonfiguruj darmową domenę DuckDNS

1. Wejdź na [duckdns.org](https://duckdns.org) i zaloguj się przez GitHub/Google
2. W polu **sub domain** wpisz wybraną nazwę (np. `teacherhelper`) → kliknij **add domain**
3. W polu **current ip** wpisz IP serwera Hetzner → kliknij **update ip**
4. Twoja domena to: `https://teacherhelper.duckdns.org`

Propagacja DuckDNS jest natychmiastowa — możesz od razu przejść do kolejnego kroku.

---

## Krok 8: Deploy backendu

Panel Coolify → **Resources → New Resource → Application → GitHub**:

| Pole | Wartość |
|---|---|
| Repository | `TeacherHelper` |
| Branch | `main` |
| Build Pack | `Dockerfile` |
| Dockerfile path | `backend/Dockerfile` |
| Build context | `/` |
| Port | `8080` |
| Domain | *(zostaw puste — backend wewnętrzny)* |

### Zmienne środowiskowe (zakładka Environment Variables)

```bash
# Baza danych — skopiuj z Coolify UI panelu PostgreSQL
DATABASE_URL=postgresql+asyncpg://USER:PASS@postgres-host:5432/DB_NAME
DATABASE_URL_SYNC=postgresql+psycopg://USER:PASS@postgres-host:5432/DB_NAME

# Qdrant — nazwa serwisu z Coolify
QDRANT_URL=http://qdrant-NAZWA:6333

# Redis — skopiuj z Coolify UI
REDIS_URL=redis://redis-host:6379/0

# Generuj: openssl rand -hex 32
JWT_SECRET=WYGENERUJ_LOSOWY_STRING

# Wymagany do działania chatu
OPENROUTER_API_KEY=sk-or-...

# Konto admina (tworzone automatycznie przy pierwszym uruchomieniu)
ADMIN_SEED_EMAIL=admin@teacherhelper.duckdns.org
ADMIN_SEED_PASSWORD=SilneHasloAdmin123!

# Produkcja
OPENAPI_DOCS=false
CORS_ORIGINS=https://teacherhelper.duckdns.org

# Przechowywanie plików
STORAGE_ROOT=/app/data/storage

# Opcjonalne — włączają dodatkowe funkcje
# OPENAI_API_KEY=sk-...
# XAI_API_KEY=...
# TAVILY_API_KEY=...
# LANGFUSE_PUBLIC_KEY=...
# LANGFUSE_SECRET_KEY=...
```

Kliknij **Deploy** i obserwuj logi — migracje Alembic (10 kroków) uruchomią się automatycznie.

---

## Krok 9: Deploy frontendu

Panel Coolify → **Resources → New Resource → Application → GitHub**:

| Pole | Wartość |
|---|---|
| Repository | `TeacherHelper` |
| Branch | `main` |
| Build Pack | `Dockerfile` |
| Dockerfile path | `frontend/Dockerfile` |
| Build context | `/` |
| Port | `80` |
| Domain | `https://teacherhelper.duckdns.org` |

- Zaznacz **Generate SSL Certificate** (Let's Encrypt — automatyczny)
- Kliknij **Deploy**

---

## Krok 10: Weryfikacja

```bash
# Health check
curl https://teacherhelper.duckdns.org/th-api/health
# Oczekiwane: {"status": "ok"}
```

Checklist:
- [ ] Otwórz `https://teacherhelper.duckdns.org` w przeglądarce
- [ ] Zaloguj się na konto admina (`ADMIN_SEED_EMAIL` / `ADMIN_SEED_PASSWORD`)
- [ ] Utwórz projekt i przetestuj chat
- [ ] Wgraj plik i sprawdź wyszukiwanie semantyczne
- [ ] Sprawdź logi backendu w Coolify (brak błędów `ERROR`)

---

## Krok 11: Monitoring (darmowy)

1. Zarejestruj się na [uptimerobot.com](https://uptimerobot.com)
2. **New Monitor → HTTP(s)**
   - URL: `https://teacherhelper.duckdns.org/th-api/health`
   - Monitoring Interval: `5 minutes`
   - Alert contacts: Twój e-mail
3. Dostaniesz alert e-mail jeśli aplikacja przestanie odpowiadać

---

## Aktualizacje

```bash
git push origin main
```

Coolify automatycznie wykryje push i uruchomi nowy deploy (zero-downtime rolling restart). Migracje Alembic uruchomią się przy każdym starcie kontenera — są idempotentne.

---

## Backup bazy danych

Panel Coolify → **Resources → [twoja baza PostgreSQL] → Backups**:
- Harmonogram: codziennie o 3:00
- Retencja: 14 dni
- Destination: S3-compatible storage lub lokalnie

---

## Health check i odporność na awarie

Coolify automatycznie:
- Restartuje kontenery po crash lub OOM kill (`restart: unless-stopped`)
- Konfiguruje health checki (zakładka Health Check w ustawieniach aplikacji)
- Restartuje wszystko po reboecie serwera

**Opcjonalne limity pamięci** (Coolify → aplikacja → Advanced):
- backend: `512m`
- qdrant: `512m`
- postgres: `256m`
- redis: `128m`

---

## Bezpieczeństwo sekretów

Coolify przechowuje zmienne środowiskowe zaszyfrowane. Klucze API wpisujesz przez HTTPS panel — nie trafiają do plików ani do git.

**Rotacja klucza po wycieku:**
1. Unieważnij klucz na stronie dostawcy (openrouter.ai, openai.com)
2. Wygeneruj nowy
3. Zaktualizuj w Coolify UI → Environment Variables
4. Coolify automatycznie restartuje kontener

---

## Szacowany koszt

| Element | Koszt |
|---|---|
| Hetzner CX32 | €8.29/mies. |
| Domena (DuckDNS) | **Darmowa** |
| SSL (Let's Encrypt) | Darmowy |
| UptimeRobot | Darmowy |
| OpenRouter API (5 users) | ~$1-5/mies. |
| **Łącznie** | **~€8-10/mies.** |

---

## Rozwiązywanie problemów

```bash
# Logi backendu w czasie rzeczywistym (przez Coolify UI lub SSH)
docker logs -f $(docker ps -q --filter "name=backend")

# Ręczne uruchomienie migracji
docker exec -it $(docker ps -q --filter "name=backend") python -m alembic upgrade head

# Restart serwisu
docker restart $(docker ps -q --filter "name=backend")

# Sprawdź użycie pamięci
docker stats --no-stream

# Sprawdź miejsce na dysku
df -h && docker system df
```

---

## Pliki konfiguracyjne w repozytorium

| Plik | Rola |
|---|---|
| `backend/Dockerfile` | Buduje obraz backendu (Python 3.11) |
| `backend/entrypoint.sh` | Uruchamia migracje Alembic + uvicorn |
| `frontend/Dockerfile` | Multi-stage: Node 20 build → Nginx serve |
| `nginx/nginx.conf` | Proxy `/th-api/` → backend, React SPA fallback |
