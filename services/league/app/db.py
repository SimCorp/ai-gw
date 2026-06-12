import ssl as _ssl
from typing import AsyncGenerator

from sqlalchemy.engine.url import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


def _engine_url_and_args(raw_url: str):
    """Translate a libpq ``sslmode`` query arg into asyncpg's ``ssl`` connect arg.

    The deployed DATABASE_URL carries ``?sslmode=require`` (libpq syntax) so the
    psycopg / raw-asyncpg-DSN consumers work. The SQLAlchemy *asyncpg dialect*,
    however, forwards unknown query args straight to ``asyncpg.connect()``, which
    has no ``sslmode`` kwarg — so it raises ``TypeError`` and the service never
    starts. Strip ``sslmode`` and pass an equivalent SSL context instead;
    ``require`` means encrypt-without-verification (matches the DSN consumers).
    """
    url = make_url(raw_url)
    connect_args: dict = {}
    sslmode = url.query.get("sslmode")
    if sslmode:
        url = url.set(query={k: v for k, v in url.query.items() if k != "sslmode"})
        if sslmode in ("require", "prefer", "allow"):
            ctx = _ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = _ssl.CERT_NONE
            connect_args["ssl"] = ctx
        elif sslmode in ("verify-ca", "verify-full"):
            connect_args["ssl"] = _ssl.create_default_context()
    return url, connect_args


_url, _connect_args = _engine_url_and_args(settings.database_url)
engine = create_async_engine(_url, echo=False, connect_args=_connect_args)
async_session_maker = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        yield session
