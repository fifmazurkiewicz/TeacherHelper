from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from teacher_helper.config import async_database_url, asyncpg_connect_args, get_settings

_settings = get_settings()
engine = create_async_engine(
    async_database_url(_settings.database_url),
    echo=_settings.debug,
    connect_args=asyncpg_connect_args(_settings.database_url),
)
async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session
