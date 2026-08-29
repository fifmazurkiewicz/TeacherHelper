from teacher_helper.config import (
    Settings,
    async_database_url,
    asyncpg_connect_args,
    normalize_postgres_url,
    uses_transaction_pooler,
)


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


def test_uses_transaction_pooler() -> None:
    assert uses_transaction_pooler("postgresql+asyncpg://user:pass@pooler.supabase.com:6543/postgres")
    assert uses_transaction_pooler("postgresql://user:pass@aws-0-eu.pooler.supabase.com:6543/postgres")
    assert not uses_transaction_pooler("postgresql+asyncpg://postgres:postgres@localhost:5432/teacher")


def test_asyncpg_connect_args_disables_statement_cache_for_pooler() -> None:
    pooler = "postgresql+asyncpg://user:pass@pooler.supabase.com:6543/postgres"
    assert asyncpg_connect_args(pooler) == {"statement_cache_size": 0}
    local = "postgresql+asyncpg://postgres:postgres@localhost:5432/teacher"
    assert asyncpg_connect_args(local) == {}


def test_async_database_url_disables_sqlalchemy_prepared_cache_for_pooler() -> None:
    pooler = "postgresql+asyncpg://user:pass@pooler.supabase.com:6543/postgres"
    assert async_database_url(pooler).endswith("prepared_statement_cache_size=0")
    local = "postgresql+asyncpg://postgres:postgres@localhost:5432/teacher"
    assert async_database_url(local) == local


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
