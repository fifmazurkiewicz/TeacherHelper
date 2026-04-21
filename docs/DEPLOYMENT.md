# Wdrożenie TeacherHelper

Instrukcja dwufazowa:
- **Faza 1 — GCP (teraz):** darmowe $300 kredytów na 90 dni → szybki start bez kosztów
- **Faza 2 — Migracja na Hetzner VPS:** po wyczerpaniu kredytów lub po 90 dniach → ~€8/mies.

Obie fazy używają **Coolify** — panel webowy zarządzający kontenerami, SSL i auto-deployem z GitHub. Konfiguracja serwisów jest identyczna w obu przypadkach; różni się tylko tworzenie serwera.

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

Wszystko na jednym serwerze. Coolify zarządza kontenerami, SSL i auto-deployem z GitHub.

---

# FAZA 1: Deploy na Google Cloud Platform

**Wymagania:** Konto Google, darmowy trial GCP ($300 na 90 dni)

Czas wykonania: ~45-60 minut

---

## Krok 1: Utwórz VM na GCP

1. Wejdź na [console.cloud.google.com](https://console.cloud.google.com)
2. Utwórz nowy projekt (np. `teacherhelper`)
3. **Compute Engine → VM Instances → Create Instance**

| Pole | Wartość |
|---|---|
| Name | `teacherhelper-vm` |
| Region | `europe-west3` (Frankfurt) lub `us-central1` |
| Machine type | `e2-standard-2` (2 vCPU, 8 GB RAM) |
| OS | Ubuntu 22.04 LTS |
| Boot disk | 50 GB SSD |
| Firewall | ✓ Allow HTTP traffic, ✓ Allow HTTPS traffic |

Kliknij **Create**.

---

## Krok 2: Zarezerwuj statyczne IP

Domyślne IP w GCP jest tymczasowe — zmienia się po restarcie VM.

**VPC Network → IP Addresses → Reserve Static Address:**
- Typ: `External`
- Przypisz do `teacherhelper-vm`

Zapisz IP — będzie potrzebne do DuckDNS i SSH.

---

## Krok 3: Otwórz port 8000 (panel Coolify)

**VPC Network → Firewall → Create Firewall Rule:**

| Pole | Wartość |
|---|---|
| Name | `allow-coolify-panel` |
| Direction | Ingress |
| Targets | All instances in the network |
| Source IP | `0.0.0.0/0` |
| Ports | TCP `8000` |

> Po skonfigurowaniu Coolify możesz usunąć tę regułę — panel będzie dostępny przez HTTPS.

---

## Krok 4: Dodaj klucz SSH

**Compute Engine → Metadata → SSH Keys → Add SSH Key:**

Wklej zawartość `~/.ssh/id_ed25519.pub` (lub wygeneruj: `ssh-keygen -t ed25519`).

Połącz się:
```bash
ssh TWOJ_USER@TWOJE_IP
```

> Alternatywnie: GCP Console → VM Instances → SSH (przeglądarka).

---

## Krok 5: Zainstaluj Coolify

```bash
# Na serwerze GCP
curl -fsSL https://cdn.coollabs.io/coolify/install.sh | bash
```

Po ~3 minutach otwórz `http://TWOJE_IP:8000` w przeglądarce.

- Utwórz konto admina Coolify (e-mail + hasło)
- Serwer `localhost` jest już automatycznie dodany

---

## Krok 6: Dodaj swap (ochrona przed OOM)

```bash
fallocate -l 2G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
```

---

## Krok 7: Zabezpiecz serwer

```bash
apt install fail2ban -y
```

> W GCP `PasswordAuthentication` jest domyślnie wyłączone — nie trzeba tego konfigurować ręcznie.

---

## Krok 8: Skonfiguruj darmową domenę DuckDNS

1. Wejdź na [duckdns.org](https://duckdns.org), zaloguj się przez Google
2. **Sub domain:** wpisz nazwę (np. `teacherhelper`) → **add domain**
3. **Current ip:** wpisz statyczne IP z Kroku 2 → **update ip**
4. Twoja domena: `https://teacherhelper.duckdns.org`

Propagacja jest natychmiastowa.

---

## Krok 9: Dodaj serwisy bazodanowe w Coolify

Panel Coolify → **Resources → New Resource**:

### PostgreSQL 16
- **Database → PostgreSQL 16** → Deploy
- Skopiuj **Connection String** (potrzebny w Kroku 11)

### Redis 7
- **Database → Redis** → Deploy
- Skopiuj **Connection String**

### Qdrant
- **Service → Qdrant** → Deploy, port `6333`
- Zapamiętaj nazwę serwisu (URL: `http://NAZWA:6333`)

---

## Krok 10: Podłącz GitHub

Panel Coolify → **Settings → Source → GitHub**:
1. **Register GitHub App**
2. Autoryzuj dostęp do repozytorium `TeacherHelper`

---

## Krok 11: Deploy backendu

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
# Skopiuj connection stringi z Coolify UI (Kroki 9)
DATABASE_URL=postgresql+asyncpg://USER:PASS@postgres-host:5432/DB_NAME
DATABASE_URL_SYNC=postgresql+psycopg://USER:PASS@postgres-host:5432/DB_NAME
QDRANT_URL=http://qdrant-NAZWA:6333
REDIS_URL=redis://redis-host:6379/0

# Generuj losowy sekret: openssl rand -hex 32
JWT_SECRET=WYGENERUJ_LOSOWY_STRING

# Wymagany do chatu
OPENROUTER_API_KEY=sk-or-...

# Konto admina (tworzone automatycznie przy pierwszym uruchomieniu)
ADMIN_SEED_EMAIL=admin@teacherhelper.duckdns.org
ADMIN_SEED_PASSWORD=SilneHasloAdmin123!

# Produkcja
OPENAPI_DOCS=false
CORS_ORIGINS=https://teacherhelper.duckdns.org
STORAGE_ROOT=/app/data/storage

# Opcjonalne — włączają dodatkowe funkcje
# OPENAI_API_KEY=sk-...
# XAI_API_KEY=...
# TAVILY_API_KEY=...
```

Kliknij **Deploy** — migracje Alembic uruchomią się automatycznie (widać w logach).

---

## Krok 12: Deploy frontendu

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

## Krok 13: Weryfikacja

```bash
curl https://teacherhelper.duckdns.org/th-api/health
# → {"status": "ok"}
```

Checklist:
- [ ] Otwórz `https://teacherhelper.duckdns.org` w przeglądarce
- [ ] Zaloguj się jako admin (`ADMIN_SEED_EMAIL` / `ADMIN_SEED_PASSWORD`)
- [ ] Utwórz projekt i przetestuj chat
- [ ] Wgraj plik i sprawdź wyszukiwanie semantyczne
- [ ] Sprawdź logi backendu w Coolify (brak `ERROR`)

---

## Krok 14: Monitoring (darmowy)

1. Zarejestruj się na [uptimerobot.com](https://uptimerobot.com)
2. **New Monitor → HTTP(s)**
   - URL: `https://teacherhelper.duckdns.org/th-api/health`
   - Interval: `5 minutes`
   - Alert e-mail: Twój adres

---

## Koszty Fazy 1

| Element | Koszt |
|---|---|
| GCP e2-standard-2 | ~$48/mies. → **pokryte z $300 kredytów (~6 mies.)** |
| DuckDNS | Darmowy |
| SSL (Let's Encrypt) | Darmowy |
| UptimeRobot | Darmowy |
| OpenRouter API | ~$1-5/mies. (poza kredytami GCP) |

---

---

# FAZA 2: Migracja na Hetzner VPS

Wykonaj gdy kredyty GCP zbliżają się do końca lub po 90 dniach.  
**Docelowy koszt: ~€8/mies.**

Migracja zajmuje ok. 30-60 minut. Przestój aplikacji: ~5-10 minut (tylko zmiana IP w DuckDNS).

---

## Krok M1: Utwórz backup na GCP

Wykonaj na serwerze GCP przez SSH:

```bash
mkdir -p ~/backups

# 1. Backup PostgreSQL
docker exec $(docker ps -q --filter "name=postgres") \
  pg_dump -U postgres postgres | gzip > ~/backups/postgres_$(date +%Y%m%d).sql.gz

# 2. Backup plików użytkowników (STORAGE_ROOT)
STORAGE_VOL=$(docker volume ls -q --filter "name=storage")
tar czf ~/backups/storage_$(date +%Y%m%d).tar.gz \
  -C /var/lib/docker/volumes/${STORAGE_VOL}/_data .

# 3. Backup danych Qdrant (wektory embeddings)
QDRANT_VOL=$(docker volume ls -q --filter "name=qdrant")
tar czf ~/backups/qdrant_$(date +%Y%m%d).tar.gz \
  -C /var/lib/docker/volumes/${QDRANT_VOL}/_data .

ls -lh ~/backups/
```

---

## Krok M2: Utwórz serwer na Hetzner

1. Zarejestruj się na [console.hetzner.com](https://console.hetzner.com)
2. **New Server:**
   - Lokalizacja: `Nuremberg` lub `Helsinki`
   - Image: `Ubuntu 22.04`
   - Type: **CX32** (4 vCPU, 8 GB RAM)
   - SSH Key: ten sam klucz co na GCP (`~/.ssh/id_ed25519.pub`)
3. Zapisz IP serwera Hetzner

**Firewall** (Hetzner → Firewalls → Create, przypisz do serwera):

| TCP | Port |
|---|---|
| SSH | 22 |
| HTTP | 80 |
| HTTPS | 443 |
| Coolify panel | 8000 |

---

## Krok M3: Zainstaluj Coolify na Hetzner

```bash
ssh root@HETZNER_IP

curl -fsSL https://cdn.coollabs.io/coolify/install.sh | bash
```

Otwórz `http://HETZNER_IP:8000` → utwórz konto admina Coolify.

Dodaj swap i fail2ban:
```bash
fallocate -l 2G /swapfile && chmod 600 /swapfile
mkswap /swapfile && swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
apt install fail2ban -y
sed -i 's/#PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config
systemctl restart sshd
```

---

## Krok M4: Skonfiguruj serwisy w Coolify (Hetzner)

Powtórz Kroki 9–10 z Fazy 1 na nowym serwerze:
- Deploy PostgreSQL 16, Redis 7, Qdrant
- Podłącz GitHub

**Nie deployuj jeszcze backendu ani frontendu** — najpierw przenieś dane.

---

## Krok M5: Prześlij backup na Hetzner

Z lokalnej maszyny (lub bezpośrednio między serwerami):

```bash
# Z lokalnej maszyny — pobierz z GCP, wyślij na Hetzner
scp TWOJ_USER@GCP_IP:~/backups/*.gz .
scp *.gz root@HETZNER_IP:~/backups/
```

Lub bezpośrednio między serwerami (szybciej):
```bash
# Na serwerze GCP:
scp ~/backups/*.gz root@HETZNER_IP:~/backups/
```

---

## Krok M6: Przywróć dane na Hetzner

Na serwerze Hetzner przez SSH:

```bash
# Znajdź nazwy wolumenów (po deployu serwisów w Kroku M4)
docker volume ls

# --- PostgreSQL ---
# Nazwa wolumenu Postgres (np. postgres_data lub podobna z Coolify)
PG_CONTAINER=$(docker ps -q --filter "name=postgres")

# Przywróć dump
gunzip -c ~/backups/postgres_*.sql.gz | \
  docker exec -i $PG_CONTAINER psql -U postgres postgres

# --- Pliki użytkowników ---
STORAGE_VOL=$(docker volume ls -q --filter "name=storage")
tar xzf ~/backups/storage_*.tar.gz \
  -C /var/lib/docker/volumes/${STORAGE_VOL}/_data

# --- Qdrant ---
QDRANT_VOL=$(docker volume ls -q --filter "name=qdrant")
# Zatrzymaj Qdrant przed przywróceniem
docker stop $(docker ps -q --filter "name=qdrant")
tar xzf ~/backups/qdrant_*.tar.gz \
  -C /var/lib/docker/volumes/${QDRANT_VOL}/_data
docker start $(docker ps -q --filter "name=qdrant")
```

---

## Krok M7: Deploy backendu i frontendu na Hetzner

Powtórz Kroki 11–12 z Fazy 1 na Coolify Hetzner.

**Zmienne środowiskowe** — identyczne jak na GCP, tylko zaktualizuj connection stringi (skopiuj z nowego Coolify UI).

`CORS_ORIGINS` i `ADMIN_SEED_EMAIL` pozostają z `teacherhelper.duckdns.org` — domena się nie zmienia.

---

## Krok M8: Aktualizuj DuckDNS (przestój ~1-2 min)

1. Wejdź na [duckdns.org](https://duckdns.org)
2. Zmień IP z `GCP_IP` na `HETZNER_IP` → **update ip**
3. Propagacja jest natychmiastowa

Sprawdź:
```bash
curl https://teacherhelper.duckdns.org/th-api/health
# → {"status": "ok"}
```

---

## Krok M9: Weryfikacja po migracji

- [ ] Aplikacja działa pod `https://teacherhelper.duckdns.org`
- [ ] Poprzednie dane widoczne (projekty, rozmowy, pliki)
- [ ] Chat działa
- [ ] Wyszukiwanie semantyczne plików działa (Qdrant)
- [ ] Logi backendu bez `ERROR`

---

## Krok M10: Wyłącz VM na GCP

Po udanej weryfikacji (daj sobie 24h bufor):

**GCP Console → Compute Engine → VM Instances → Stop** (zatrzymaj, nie usuwaj — dane zostają, koszty prawie zerowe).

Po kolejnych kilku dniach bez problemów → **Delete** VM.

> Zachowane kredyty GCP można wykorzystać na inne projekty.

---

## Koszty po migracji

| Element | Koszt |
|---|---|
| Hetzner CX32 | **€8.29/mies.** |
| DuckDNS | Darmowy |
| SSL (Let's Encrypt) | Darmowy |
| UptimeRobot | Darmowy |
| OpenRouter API | ~$1-5/mies. |
| **Łącznie** | **~€8-10/mies.** |

---

---

# Operacje bieżące (obie fazy)

## Aktualizacje kodu

```bash
git push origin main
```

Coolify automatycznie wykryje push i uruchomi zero-downtime deploy. Migracje Alembic uruchomią się automatycznie.

---

## Backup bazy (harmonogram)

Panel Coolify → **Resources → [PostgreSQL] → Backups → Schedule**:
- Harmonogram: codziennie 3:00
- Retencja: 14 kopii
- Destination: lokalnie lub S3-compatible (Hetzner Object Storage ~€0.022/GB)

---

## Rozwiązywanie problemów

```bash
# Logi backendu
docker logs -f $(docker ps -q --filter "name=backend")

# Ręczne migracje
docker exec -it $(docker ps -q --filter "name=backend") python -m alembic upgrade head

# Użycie pamięci
docker stats --no-stream

# Miejsce na dysku
df -h && docker system df
```

---

## Pliki konfiguracyjne w repozytorium

| Plik | Rola |
|---|---|
| `backend/Dockerfile` | Obraz backendu (Python 3.11-slim) |
| `backend/entrypoint.sh` | Migracje Alembic + start uvicorn |
| `frontend/Dockerfile` | Multi-stage: Node 20 build → Nginx serve |
| `nginx/nginx.conf` | Proxy `/th-api/` → backend, React SPA fallback |
