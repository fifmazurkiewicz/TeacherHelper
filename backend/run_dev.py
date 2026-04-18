"""Lokalny serwer API — uruchom z katalogu ``backend`` albo z debuggera (konfiguracja „Backend API”).

Przykład: ``.venv\\Scripts\\python.exe run_dev.py``  
``UVICORN_RELOAD=1`` włącza hot-reload (słabo w połączeniu z debuggerem).
"""

from __future__ import annotations

import os


def main() -> None:
    import uvicorn

    host = os.environ.get("UVICORN_HOST", "127.0.0.1")
    port = int(os.environ.get("UVICORN_PORT", "8080"))
    reload = os.environ.get("UVICORN_RELOAD", "0").lower() in ("1", "true", "yes")
    uvicorn.run("teacher_helper.main:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    main()
