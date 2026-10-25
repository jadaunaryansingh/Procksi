from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool
from typing import AsyncGenerator
from app.core.config import settings


class Base(DeclarativeBase):
    pass


import uuid
import ssl
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

database_url = f"{settings.DATABASE_URL.split('?')[0]}?prepared_statement_cache_size=0"

engine = create_async_engine(
    database_url,
    echo=False,
    pool_size=10,
    max_overflow=20,
    pool_recycle=1800,
    connect_args={
        "ssl": ctx,
        # Both sides of this merge independently added a connect timeout, which
        # is the agreement worth keeping; only the numbers differed. Upstream's
        # 10.0 is retained for the connect phase.
        "timeout": 10.0,
        # command_timeout was 60s, which meant a blocked Postgres port (some
        # networks allow HTTPS but not 5432/6543) stalled every request for a
        # full minute before the caller's `except` swallowed it — the request
        # still "succeeded", just a minute late and with empty data. Measured:
        # the mentor chat endpoints took 60.3s and returned empty lists. 8s is
        # well beyond a healthy round trip to the pooler and short enough that a
        # failure reads as a failure.
        "command_timeout": 8,
        # Required when using Supabase PgBouncer in transaction/statement pool mode.
        "statement_cache_size": 0,
        "prepared_statement_cache_size": 0,
        "prepared_statement_name_func": lambda: f"__asyncpg_{uuid.uuid4().hex}__"
    }
)


async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()
