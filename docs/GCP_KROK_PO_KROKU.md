# TeacherHelper na Google Cloud — Ścieżka A (Cloud SQL + Docker na VM)

Ten plik opisuje **domyślne wdrożenie**: **zarządzany PostgreSQL (Cloud SQL)** + **jedna maszyna (Compute Engine)** z **Docker Compose** (`redis`, `backend`, `frontend`). **Qdrant** jest **poza GCP** — darmowy klaster w [Qdrant Cloud](https://cloud.qdrant.io) (`QDRANT_URL`, `QDRANT_API_KEY` w `.env`).

**Pliki:** katalog **`deploy/gcp/`** — używasz **`docker-compose.yml`** i **`.env`** (wzór **`.env.example`**). Plików `.env` **nie commituj**.

**Czego nie uruchamiasz przy Ścieżce A:** `docker-compose.all.yml` (tam Postgres jest w kontenerze — to **Ścieżka B**, skrót na końcu dokumentu).

---

## Szybki plan (kolejność)

| Krok | ETAP | Co robisz |
|------|------|-----------|
| 1 | **0** | Projekt GCP, rozliczenia, wybór **regionu** (np. `europe-west1`) |
| 2 | **1** | Qdrant Cloud — klaster, URL, API Key |
| 3 | **2** | VM + firewall + SSH |
| 4 | **3** | Cloud SQL — instancja, baza, użytkownik, **Public IP**, **Authorized networks** (IP VM `/32`) |
| 5 | **4** | Docker na VM, `.env`, `docker compose --env-file .env up -d` |
| 6 | **5** | Caddy lub nginx na hoście → `http://127.0.0.1:8080` |
| 7 | **6** | Testy w przeglądarce |
| 8 | **7** | Backup, aktualizacje |

---

## Zanim zaczniesz — adres w przeglądarce a `CORS_ORIGINS`

Backend sprawdza **origin** żądań z frontendu. W `.env` ustaw **`CORS_ORIGINS`** dokładnie tak, jak użytkownik wpisuje stronę w pasku adresu (scheme + host, **bez** końcowego `/`):

- Tylko IP: `CORS_ORIGINS=http://203.0.113.10`
- Domena z HTTPS: `CORS_ORIGINS=https://twoja.duckdns.org`

**Let’s Encrypt** (automatyczny certyfikat w Caddy) wymaga **nazwy DNS** wskazującej na VM — nie „gołego” IP. Na szybki test wystarczy **HTTP pod IP** (bez certyfikatu).

---

## ETAP 0 — Projekt i rozliczenia

1. Wejdź na [Google Cloud Console](https://console.cloud.google.com/).
2. **Project picker** (selector u góry) → **New project** → nazwa np. `teacherhelper` → **Create**.
3. Menu ☰ → **Billing** — podłącz rozliczenia do projektu (bez tego Cloud SQL się nie utworzy).
4. Wybierz **jeden region** i trzymaj go dla VM i Cloud SQL (np. **europe-west1** — Belgia; **europe-central2** to m.in. Warszawa — sprawdź dostępność przy tworzeniu zasobów).

---

## ETAP 1 — Qdrant Cloud

1. Otwórz [cloud.qdrant.io](https://cloud.qdrant.io) i zaloguj się.
2. **Clusters** → **Create** / utwórz klaster (plan **Free**, jeśli dostępny).
3. Wejdź w klaster i skopiuj **Cluster URL** (np. `https://….cloud.qdrant.io:6333`) oraz **API Key** (często generujesz w panelu — zapisz od razu).
4. Wkleisz to do **`QDRANT_URL`** i **`QDRANT_API_KEY`** w `deploy/gcp/.env`.

---

## ETAP 2 — Compute Engine: VM i dostęp

### 2.1 Firewall (porty)

1. ☰ → **VPC network** → **Firewall**.
2. Dla serwera WWW potrzebujesz ruchu **TCP 22** (SSH), **80** i **443** (proxy). Przy tworzeniu VM możesz zaznaczyć **Allow HTTP traffic** / **Allow HTTPS traffic** — GCP często dołącza reguły dla tagów `http-server` / `https-server`.
3. Jeśli reguł brakuje: **Create firewall rule** — **Targets** (np. wszystkie instancje albo wybrane tagi), **Source** `0.0.0.0/0` tylko jeśli świadomie wystawiasz usługę do internetu, **Ports** `tcp:22`, oraz osobno reguły dla `tcp:80` i `tcp:443` według potrzeb.

### 2.2 Utworzenie instancji

1. ☰ → **Compute Engine** → **VM instances** → **Create instance**.
2. **Name:** np. `teacherhelper-app`.
3. **Region / zone:** **Ten sam region**, który wybierzesz dla Cloud SQL (np. `europe-west1`).
4. **Machine type:** dostosuj do budżetu (Ścieżka A bez Postgresa na VM jest lżejsza niż pełny stos z kontenerem bazy).
5. **Boot disk:** wybierz **Ubuntu** (nie „Accelerator Optimized” ani **Ubuntu Pro**, chyba że świadomie potrzebujesz GPU lub płatnego wsparcia Canonical). W nazwie obrazu szukaj **22.04** (`jammy`) lub **24.04** (`noble`) — to wydania **LTS**; w kreatorze GCP często nie ma słowa „LTS”, tylko numer wersji.
6. Sekcja **Firewall:** zaznacz **Allow HTTP traffic** i **Allow HTTPS traffic**, jeśli planujesz proxy na 80/443.
7. **Create** — poczekaj, aż VM będzie **Running**.
8. Z listy instancji skopiuj **External IP** (będzie potrzebny w Cloud SQL i w `CORS_ORIGINS`, jeśli wchodzisz po IP).

### 2.3 SSH

1. W wierszu VM kliknij **SSH** (terminal w przeglądarce) albo połącz się z własnego komputera (`gcloud compute ssh`, jeśli masz skonfigurowane).
2. Dalsze kroki (Docker, `git clone`) wykonujesz w tej sesji.

---

## ETAP 3 — Cloud SQL (PostgreSQL)

### 3.1 Nowa instancja

1. ☰ → **SQL** → **Create instance** → **PostgreSQL**.
2. **Instance ID:** np. `teacherhelper-pg`.
3. **Password** użytkownika domyślnego (`postgres`) — **zapisz** (na start możesz go zostawić; aplikacji i tak zwykle dajesz osobnego użytkownika).
4. **Region:** **identyczny** jak VM (np. `europe-west1`).
5. **Database version:** **PostgreSQL 16** (zgodnie ze stackiem w repozytorium).
6. **Machine type / storage:** najmniejsza sensowna konfiguracja na start; zwiększysz później.
7. **Create instance** — status **Running**.

### 3.2 Baza i użytkownik aplikacji

1. Kliknij nazwę instancji na liście.
2. **Databases** → **Create database** → nazwa **`teacherhelper`**.
3. **Users** → **Add user account** — login np. **`teacherhelper`**, silne hasło. **Zapisz login i hasło** do `DATABASE_URL`.

### 3.3 Publiczny IP i dostęp z VM

1. Zakładka **Connections**.
2. Włącz **Public IP** i zanotuj **Public IP address** instancji (np. `34.x.x.x`) — trafi do `DATABASE_URL`.
3. **Authorized networks** → **Add network**:
   - **Name:** np. `teacherhelper-vm`,
   - **Network:** **External IP Twojej VM** z ETAPU 2 w formacie **`x.x.x.x/32`**.
4. **Save**. Bez tego backend na VM nie połączy się z Cloud SQL.

**Bezpieczeństwo:** to uproszczony model (publiczny endpoint bazy + lista IP). Na produkcji często stosuje się **prywatny IP** i tę samą VPC co VM — więcej pracy w sieci, mniejsza powierzchnia ataku.

### 3.4 `DATABASE_URL` w `.env`

W `deploy/gcp/.env` (po `cp .env.example .env`):

```text
DATABASE_URL=postgresql+asyncpg://teacherhelper:HASLO@PUBLICZNY_IP_CLOUD_SQL:5432/teacherhelper
DATABASE_URL_SYNC=postgresql+psycopg://teacherhelper:HASLO@PUBLICZNY_IP_CLOUD_SQL:5432/teacherhelper
```

**Hasło** w URL musi być [zakodowane procentami](https://en.wikipedia.org/wiki/Percent-encoding), jeśli zawiera znaki specjalne (`@`, `#`, `%` itd.). Najprościej: hasło alfanumeryczne na czas konfiguracji.

Szablon z komentarzami: **`deploy/gcp/.env.example`**.

---

## ETAP 4 — Docker i Compose na VM

Wykonuj na VM po połączeniu **SSH** (np. przycisk **SSH** przy instancji w Compute Engine). Zakładamy **Ubuntu** z repozytoriów Dockera (oficjalna metoda; pełna dokumentacja: [Install Docker Engine on Ubuntu](https://docs.docker.com/engine/install/ubuntu/)).

### 4.1 Zależności i repozytorium Dockera

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "${VERSION_CODENAME:-$VERSION_ID}") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
```

Gdy polecenie z `VERSION_CODENAME` zwróci błąd, zastąp fragment w cudzysłowie nazwą kodową dystrybucji: **`jammy`** (22.04) lub **`noble`** (24.04), np. `... ubuntu jammy stable`.

### 4.2 Instalacja Docker Engine i pluginu Compose

```bash
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
```

Sprawdzenie:

```bash
sudo docker run --rm hello-world
sudo docker compose version
```

(`docker compose` z podkreślnikiem — plugin v2. Po dodaniu się do grupy `docker` (krok 4.3) możesz pisać `docker compose` bez `sudo`.)

### 4.3 Docker bez `sudo` (zalecane)

```bash
sudo usermod -aG docker "$USER"
```

**Wyloguj się z SSH i zaloguj ponownie** (albo zamknij sesję „SSH w przeglądarce” i otwórz nową). Dopiero wtedy `docker ps` bez `sudo` zwykle działa.

### 4.4 Klonowanie repozytorium TeacherHelper

**Wariant A — HTTPS** (GitHub poprosi o logowanie; na serwerze wygodnie: [Personal Access Token](https://github.com/settings/tokens) zamiast hasła):

```bash
cd ~
git clone https://github.com/TWOJA_ORGANIZACJA/TeacherHelper.git
```

**Wariant B — SSH** (najpierw wygeneruj klucz na VM: `ssh-keygen`, dodaj **publiczny** klucz w GitHub → Settings → SSH keys):

```bash
cd ~
git clone git@github.com:TWOJA_ORGANIZACJA/TeacherHelper.git
```

Podstaw właściwą ścieżkę URL swojego repo (fork lub prywatne).

### 4.5 Plik `.env` i uruchomienie Compose

1. `cd ~/TeacherHelper/deploy/gcp` (albo `cd ścieżka/do/TeacherHelper/deploy/gcp`, jeśli klonowałeś gdzie indziej).
2. `cp .env.example .env` — uzupełnij:
   - `DATABASE_URL`, `DATABASE_URL_SYNC` (ETAP 3),
   - `REDIS_URL=redis://redis:6379/0`,
   - `QDRANT_URL`, `QDRANT_API_KEY` (ETAP 1),
   - `JWT_SECRET`, `OPENROUTER_API_KEY`, `OPENAPI_DOCS=false`,
   - **`CORS_ORIGINS`** — zgodnie z sekcją na początku dokumentu,
   - `STORAGE_ROOT=/app/data/storage`,
   - `ADMIN_SEED_EMAIL`, `ADMIN_SEED_PASSWORD`.
3. `chmod 600 .env`
4. Uruchomienie:

```bash
docker compose --env-file .env build
docker compose --env-file .env up -d
```

5. `docker compose ps` — kontenery **redis**, **backend**, **frontend** (kontenera **qdrant** nie ma — wektory idą do Qdrant Cloud).
6. Frontend nasłuchuje **`127.0.0.1:8080`** na hoście — ruch z internetu podajesz dopiero przez proxy (ETAP 5).

**Porty:** nie musisz otwierać **6333** (Qdrant jest poza GCP). Nie wystawiaj publicznie portu aplikacji poza 80/443 na proxy.

---

## ETAP 5 — Reverse proxy na VM (Caddy lub nginx)

Ruch: **internet → :80 / :443 na VM → proxy → `http://127.0.0.1:8080`**.

1. Zainstaluj **Caddy** albo **nginx** na Ubuntu (poza Dockerem).
2. W repozytorium: **`deploy/gcp/Caddyfile.host.example`** — wariant **HTTP** (`:80` + `reverse_proxy 127.0.0.1:8080`) albo blok z **nazwą domeny** po skonfigurowaniu DNS na **External IP** VM.
3. Wgraj konfigurację na serwer (np. `/etc/caddy/Caddyfile`), przeładuj usługę (`systemctl restart caddy` lub odpowiednik dla nginx).
4. Sprawdź ponownie **`CORS_ORIGINS`** w `.env` vs adres w przeglądarce.

---

## ETAP 6 — Testy

1. Z sieci zewnętrznej otwórz stronę (`http://IP` lub `https://domena`).
2. Health API przez frontend (nginx w obrazie): **`https://twoja-domena/th-api/health`** lub **`http://IP/th-api/health`** — odpowiedź JSON z backendu.
3. Logowanie: `ADMIN_SEED_EMAIL` / `ADMIN_SEED_PASSWORD`.
4. Krótki test czatu i wgrywania pliku — w logach backendu widać ewentualne błędy **Qdrant Cloud**.

**Diagnoza**

- `docker compose logs backend` — PostgreSQL, Qdrant, brak klucza OpenRouter.
- **CORS** — `CORS_ORIGINS` musi być identyczny z originem przeglądarki.
- **502** — proxy nie widzi `127.0.0.1:8080` (Compose nie działa lub zły port).

---

## ETAP 7 — Backup i utrzymanie

| Zasób | Działanie |
|-------|-----------|
| **Cloud SQL** | W karcie instancji: **Backups**; ewentualnie eksport; przechowuj hasła. |
| **Pliki użytkowników** | Wolumen Docker **`backend_storage`** — snapshot dysku VM lub kopia przy zatrzymanym kontenerze. |
| **Wektory** | **Qdrant Cloud** — wg polityki usługi w panelu. |
| **Kod** | `git pull`, potem `docker compose --env-file .env build` i `up -d` po zmianach wymagających przebudowy obrazów. |

---

## Skrót menu w konsoli GCP

| Cel | Ścieżka w menu |
|-----|----------------|
| Projekt, billing | Góra → project picker; ☰ → **Billing** |
| Cloud SQL | ☰ → **SQL** |
| VM | ☰ → **Compute Engine** → **VM instances** |
| Firewall | ☰ → **VPC network** → **Firewall** |

---

## Dodatek — Ścieżka B (Postgres w Dockerze)

Jeśli **nie** używasz Cloud SQL, możesz uruchomić Postgresa w kontenerze razem z resztą:

- Pliki: **`deploy/gcp/docker-compose.all.yml`**, **`deploy/gcp/.env.all.example`** → `.env.all`.
- W Compose jest też **Caddy** (porty 80/443); w `.env.all` ustaw **`CADDY_DOMAIN`** i spójny **`CORS_ORIGINS`**.
- **Nie łącz** tego równolegle z tą samą bazą Cloud SQL w jednym środowisku bez świadomej migracji — wybierasz jeden model bazy.

Pełniejszy opis zmiennych: `backend/teacher_helper/config.py`.
