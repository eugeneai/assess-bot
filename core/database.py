from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase

from core.config import settings


engine = create_async_engine(settings.database_url, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with async_session() as session:
        yield session


async def get_session() -> AsyncSession:
    return async_session()


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_migrate_v1_review)


def _migrate_v1_review(conn):
    from sqlalchemy import inspect, text
    inspector = inspect(conn)
    columns = [c["name"] for c in inspector.get_columns("submissions")]
    if "review" not in columns:
        conn.execute(text("ALTER TABLE submissions ADD COLUMN review TEXT DEFAULT ''"))
        import logging
        logging.getLogger(__name__).info("Added 'review' column to submissions table")
