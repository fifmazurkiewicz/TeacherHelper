"""Aplikacja FastAPI (obiekt ``app`` dla uvicorn).

Uruchamianie z katalogu ``backend``:

- ``python run_dev.py`` — najprościej (także pod debuggerem).
- ``poetry run uvicorn teacher_helper.main:app --host 127.0.0.1 --port 8080`` — z hot-reload.
"""

import logging
import os

logging.basicConfig(
    level=logging.DEBUG if os.environ.get("DEBUG", "").lower() in ("1", "true", "yes") else logging.INFO,
    format="%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)

from teacher_helper.adapters.http import create_app
from teacher_helper.monitoring import capture_error, init_sentry
from teacher_helper.use_cases.error_reporting import set_error_reporter

init_sentry("teacherhelper-api", api=True)
set_error_reporter(capture_error)
app = create_app()


def main() -> None:
    import uvicorn

    host = os.environ.get("UVICORN_HOST", "0.0.0.0")
    port = int(os.environ.get("UVICORN_PORT", "8080"))
    reload = os.environ.get("UVICORN_RELOAD", "1").lower() not in ("0", "false", "no")
    # String import — wymagany przy reload=True
    uvicorn.run("teacher_helper.main:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    main()
