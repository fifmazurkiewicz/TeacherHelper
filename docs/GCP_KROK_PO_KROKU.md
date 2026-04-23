# TeacherHelper na Google Cloud — Ścieżka A (Cloud SQL + Docker na VM)

Ten plik opisuje **domyślne wdrożenie**: **zarządzany PostgreSQL (Cloud SQL)** + **jedna maszyna (Compute Engine)** z **Docker Compose** (`redis`, `backend`, `frontend`). **Qdrant** jest **poza GCP** — darmowy klaster w [Qdrant Cloud](https://cloud.qdrant.io) (`QDRANT_URL`, `QDRANT_API_KEY` w `.env`).

**Pliki:** katalog **`deploy/gcp/`** — **`docker-compose.yml`**, **`.env`** (wzór **`.env.example`**), **`Caddyfile.host.example`** (proxy na hoście). Pliku **`.env` nie commituj**.

### Bezpieczeństwo: sekrety, repozytorium, migracje

- **Nie commituj** plików z prawdziwymi wartościami: `deploy/gcp/.env`, `backend/.env`, `frontend/.env.local`. W repozytorium są wyłącznie **placeholdery** (`sk-or-v1-...`, `TWOJE_HASLO`, itd.) — przed `git push` warto uruchomić wyszukiwanie po własnym fragmencie klucza, jeśli kiedykolwiek wklejałeś go do pliku śledzonego przez Git.
- **Pierwszy start backendu w Dockerze** uruchamia `alembic upgrade head` (patrz `backend/entrypoint.sh`). Migracja **`007`** może utworzyć konto administratora z **`ADMIN_SEED_EMAIL`** / **`ADMIN_SEED_PASSWORD`** ze środowiska kontenera (czyli z `deploy/gcp/.env` przekazanego jako `env_file`). **Ustaw silne hasło zanim** wykonasz pierwszy `docker compose ... up -d`. Gdy zmiennych brakuje, w kodzie migracji jest **wyłącznie deweloperski** fallback hasła — nie używaj tego na produkcji; alternatywnie **`SKIP_ADMIN_SEED=1`** (wartości `1` / `true` / `yes`) pomija wstawienie rekordu.
- W migracjach **nie ma** zahardkodowanych haseł do bazy ani kluczy API — poza **`007`** jedynie **hash** hasła seed admina, wyliczany z env w czasie migracji.

### Redis — czy coś klikać w GCP?

**Nie.** W Ścieżce A Redis jest **kontenerem Dockera** z pliku **`deploy/gcp/docker-compose.yml`** (obraz `redis:7-alpine`). Uruchamia się **razem** z backendem i frontendem po:

`docker compose --env-file .env up -d`

W **`.env`** ustaw **`REDIS_URL=redis://redis:6379/0`** — `redis` to **nazwa serwisu** w Compose (wewnętrzna sieć Docker), nie adres VM.

**Firewall:** **nie** otwieraj portu **6379** na świat — Redis ma być widoczny tylko dla kontenera backendu. Z internetu i tak nie łączysz się z Redisem.

**Alternatywa (rzadko na start):** zarządzany **Memorystore for Redis** w GCP — osobna usługa, płatność i konfiguracja VPC; obecny przewodnik i Compose **tego nie używają**.

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

**Dlaczego „nie widać” `.env.example`:** pliki z nazwą zaczynającą się od **kropki** są **ukryte**. Polecenie `ls` ich nie wypisuje — użyj:

```bash
ls -la ~/TeacherHelper/deploy/gcp
```

Powinieneś zobaczyć m.in. **`.env.example`**. To **nie** jest to samo co `.env` (ten drugi plik tworzysz sam i **nie** jest w repozytorium — trzyma sekrety).

**Skopiuj szablon na właściwy plik** (będąc w `deploy/gcp`):

```bash
cd ~/TeacherHelper/deploy/gcp
cp -n .env.example .env
```

(`cp -n` nie nadpisze `.env`, jeśli już istnieje; wtedy edytuj ręcznie `vim .env` lub `nano .env`.)

**Edytor vim na Ubuntu** (opcjonalnie — wygodne do dłuższych plików):

```bash
sudo apt-get update
sudo apt-get install -y vim
vim .env
```

Jeśli wolisz coś prostszego, często jest już **`nano`** (`nano .env`, zapis: Ctrl+O, wyjście: Ctrl+X).

3. Uzupełnij w `.env` m.in.:
   - `DATABASE_URL`, `DATABASE_URL_SYNC` (ETAP 3),
   - `REDIS_URL=redis://redis:6379/0`,
   - `QDRANT_URL`, `QDRANT_API_KEY` (ETAP 1),
   - `JWT_SECRET`, `OPENROUTER_API_KEY`, `OPENAPI_DOCS=false`,
   - **`CORS_ORIGINS`** — zgodnie z sekcją na początku dokumentu,
   - `STORAGE_ROOT=/app/data/storage`,
   - **`ADMIN_SEED_EMAIL`**, **`ADMIN_SEED_PASSWORD`** — **przed pierwszym** `up -d`, bo start kontenera backendu odpala migracje (w tym seed admina z migracji `007`); patrz sekcja *Bezpieczeństwo* powyżej,
   - opcjonalnie wg potrzeb: `OPENAI_API_KEY` / `EMBEDDINGS_BACKEND`, **KIE** / **Replicate** (SFX), **Langfuse** (`LANGFUSE_*`) — pełna lista komentarzy w `deploy/gcp/.env.example`.
4. `chmod 600 .env`
5. Uruchomienie:

```bash
docker compose --env-file .env build
docker compose --env-file .env up -d
```

6. `docker compose ps` — kontenery **redis**, **backend**, **frontend** (kontenera **qdrant** nie ma — wektory idą do Qdrant Cloud).
7. Frontend nasłuchuje **`127.0.0.1:8080`** na hoście — ruch z internetu podajesz dopiero przez proxy (ETAP 5).

**Porty:** nie musisz otwierać **6333** (Qdrant jest poza GCP). Nie wystawiaj publicznie portu aplikacji poza 80/443 na proxy.

---

## ETAP 5 — Reverse proxy na VM (Caddy)

Ruch: **internet → :80 / :443 na VM → Caddy → `http://127.0.0.1:8080`** (frontend z Docker Compose nasłuchuje tylko na localhost).

Upewnij się, że w **GCP** reguły firewall przepuszczają **TCP 80** (i **443**, jeśli używasz HTTPS z domeną). **Compose** musi już działać (`docker compose ps`).

### 5.1 Instalacja Caddy na Ubuntu (oficjalny pakiet apt)

Na VM (SSH). Instrukcja zgodna z [dokumentacją Caddy (Debian/Ubuntu)](https://caddyserver.com/docs/install):

```bash
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo chmod o+r /usr/share/keyrings/caddy-stable-archive-keyring.gpg
sudo chmod o+r /etc/apt/sources.list.d/caddy-stable.list
sudo apt update
sudo apt install -y caddy
```

Po instalacji usługa **`caddy`** jest pod **systemd** (często już włączona). Sprawdzenie:

```bash
sudo systemctl status caddy
caddy version
```

### 5.2 Konfiguracja (`Caddyfile`)

Domyślna ścieżka pakietu: **`/etc/caddy/Caddyfile`**. Zrób kopię zapasową i edytuj:

```bash
sudo cp /etc/caddy/Caddyfile /etc/caddy/Caddyfile.bak
```

**Edycja w vimie** (jeśli brak: `sudo apt install -y vim`):

```bash
sudo vim /etc/caddy/Caddyfile
```

Krótki **vim**:

- **Usuń stary blok** — np. `ggdG` (od pierwszej do ostatniej linii; uważaj, nieodwracalne w tej sesji) albo ręcznie usuń zawartość.
- **Wklejasz z komputera:** **Esc**, wpisz **`:set paste`**, **Enter**, **`i`**, wklej w terminalu, **Esc**, **`:set nopaste`**, **Enter** (opcjonalnie).
- **Zapis i wyjście:** **Esc**, **`:wq`**, **Enter**; wyjście bez zapisu: **`:q!`**

W repozytorium TeacherHelper masz szkic: **`deploy/gcp/Caddyfile.host.example`** (możesz otworzyć drugą sesję SSH: `vim ~/TeacherHelper/deploy/gcp/Caddyfile.host.example` i przepisać blok ręcznie).

- **Tylko HTTP (np. wejście po `http://EXTERNAL_IP`):** odkomentuj wariant z **`:80`** i **`reverse_proxy 127.0.0.1:8080`**. W Caddy **wcięcia** w bloku muszą być **tabulatorami** (nie spacjami), np.:

```caddy
:80 {
	reverse_proxy 127.0.0.1:8080
}
```

- **HTTPS (Let's Encrypt):** w pliku wpisz **jedną linię z domeną** (DNS **A** musi wskazywać **External IP** VM **zanim** pierwszy raz wystartuje ACME), np.:

```caddy
twoja.domena.pl {
	reverse_proxy 127.0.0.1:8080
}
```

Usuń lub nie zostawiaj **konfliktujących** bloków (np. dwa serwisy na `:80`).

Walidacja i restart:

```bash
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

Przy pierwszej konfiguracji, jeśli `reload` zawiedzie, spróbuj:

```bash
sudo systemctl restart caddy
sudo journalctl -u caddy -e --no-pager
```

### 5.3 `CORS_ORIGINS`

W **`deploy/gcp/.env`** ustaw **`CORS_ORIGINS`** tak samo jak adres w przeglądarce (`http://IP` vs `https://domena`).

### 5.4 Zamiast Caddy — nginx

Możesz użyć **nginx** jako reverse proxy na `:80` / `:443`; ten przewodnik nie rozpisuje kroków pod nginx. Idea ta sama: `proxy_pass http://127.0.0.1:8080;` i certyfikat (np. certbot) przy HTTPS.

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

## Wdrożenie zmian z brancha (szybki pull na VM)

Użyj tego, gdy **zmieniasz kod na innym branchu** (lub po `merge` na `main`) i chcesz **szybko wgrać** nową wersję na tę samą VM **bez** ponownego klikania w GCP.

**Założenia:** masz już działające środowisko (ETAPY 0–5), plik **`deploy/gcp/.env`** leży na serwerze i **nie** jest nadpisywany przez `git pull` (nie trzymaj sekretów w repo).

Na VM po SSH:

```bash
cd ~/TeacherHelper
git fetch origin
git checkout main
git pull origin main
```

Zamiast `main` podstaw **nazwę brancha**, np. `git checkout feature/nazwa && git pull origin feature/nazwa`.

Potem przebuduj i podnieś kontenery (z katalogu compose):

```bash
cd ~/TeacherHelper/deploy/gcp
docker compose --env-file .env build
docker compose --env-file .env up -d
```

**Migracje bazy:** przy starcie kontenera **backend** uruchamiany jest `alembic upgrade head` (patrz `backend/entrypoint.sh`) — nowe migracje zwykle zastosują się same po `up -d`.

**Kiedy wymusić pełną przebudowę obrazów** (rzadziej, np. podejrzenie cache Dockera):

```bash
docker compose --env-file .env build --no-cache
docker compose --env-file .env up -d
```

**Logi po wdrożeniu:** `docker compose logs -f backend` (lub `frontend`).

**Caddy** na hoście **nie** wymaga restartu po typowej zmianie tylko w aplikacji — tylko gdy zmieniasz port frontendu w Compose albo ścieżkę proxy.

---

## ETAP 7 — Backup i utrzymanie

| Zasób | Działanie |
|-------|-----------|
| **Cloud SQL** | W karcie instancji: **Backups**; ewentualnie eksport; przechowuj hasła. |
| **Pliki użytkowników** | Wolumen Docker **`backend_storage`** — snapshot dysku VM lub kopia przy zatrzymanym kontenerze. |
| **Wektory** | **Qdrant Cloud** — wg polityki usługi w panelu. |
| **Kod / wdrożenie** | Sekcja **„Wdrożenie zmian z brancha”** powyżej; okresowo `sudo apt upgrade` na VM. |

---

## Skrót menu w konsoli GCP

| Cel | Ścieżka w menu |
|-----|----------------|
| Projekt, billing | Góra → project picker; ☰ → **Billing** |
| Cloud SQL | ☰ → **SQL** |
| VM | ☰ → **Compute Engine** → **VM instances** |
| Firewall | ☰ → **VPC network** → **Firewall** |

Pełniejszy opis zmiennych backendu: `backend/teacher_helper/config.py` oraz `deploy/gcp/.env.example`.
