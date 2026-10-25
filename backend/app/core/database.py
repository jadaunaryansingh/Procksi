from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from typing import AsyncGenerator
from app.core.config import settings


class Base(DeclarativeBase):
    pass


import uuid
import ssl
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

engine = create_async_engine(
    settings.DATABASE_URL.split("?")[0],
    echo=False,
    # Avoid handing out stale connections (common with VPN/WARP + Supabase pooler).
    pool_pre_ping=True,
    # Recycle periodically to reduce long-idle disconnects.
    pool_recycle=900,
    connect_args={
        "ssl": ctx,
        # Fail fast-ish when network/DB is flaky; long-running ops should be explicit.
        "command_timeout": 60,
        # Required when using Supabase pgbouncer in transaction/statement pool mode.
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
