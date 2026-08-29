from teacher_helper.config import Settings, normalize_postgres_url


def test_normalize_postgres_url_bare_to_psycopg() -> None:
    url = "postgresql://user:pass@pooler.supabase.com:6543/postgres"
    assert normalize_postgres_url(url, "psycopg") == (
        "postgresql+psycopg://user:pass@pooler.supabase.com:6543/postgres"
    )


def test_normalize_postgres_url_bare_to_asyncpg() -> None:
    url = "postgresql://user:pass@pooler.supabase.com:6543/postgres"
    assert normalize_postgres_url(url, "asyncpg") == (
        "postgresql+asyncpg://user:pass@pooler.supabase.com:6543/postgres"
    )


def test_normalize_postgres_url_heroku_style() -> None:
    url = "postgres://user:pass@host:5432/db"
    assert normalize_postgres_url(url, "psycopg") == "postgresql+psycopg://user:pass@host:5432/db"


def test_normalize_postgres_url_psycopg2_to_psycopg() -> None:
    url = "postgresql+psycopg2://user:pass@host:5432/db"
    assert normalize_postgres_url(url, "psycopg") == "postgresql+psycopg://user:pass@host:5432/db"


def test_settings_normalize_supabase_sync_url(monkeypatch) -> None:
    monkeypatch.setenv(
        "DATABASE_URL_SYNC",
        "postgresql://user:pass@aws-0-eu-central-1.pooler.supabase.com:6543/postgres",
    )
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://user:pass@aws-0-eu-central-1.pooler.supabase.com:6543/postgres",
    )
    settings = Settings()
    assert settings.database_url_sync.startswith("postgresql+psycopg://")
    assert settings.database_url.startswith("postgresql+asyncpg://")
