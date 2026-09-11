import os
from dotenv import load_dotenv
from typing import AsyncGenerator
from sqlalchemy import text
from sqlmodel import SQLModel
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession


load_dotenv()

# Build DATABASE_URL from individual environment variables
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "gamefleet")
DB_USER = os.getenv("DB_USER", "gamefleet")
DB_PASSWORD = os.getenv("DB_PASSWORD", "gamefleet")

DATABASE_URL = f"postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# Fallback to legacy DATABASE_URL if provided
if legacy_url := os.getenv("DATABASE_URL"):
    DATABASE_URL = legacy_url

engine = create_async_engine(DATABASE_URL)

async_session = async_sessionmaker(
    bind=engine, expire_on_commit=False
)

# Idempotent upgrades for databases created by older versions (create_all never alters existing tables).
LEGACY_SCHEMA_UPGRADES = [
    "ALTER TABLE gameserver ADD COLUMN IF NOT EXISTS query_port INTEGER",
    "ALTER TABLE gameserver ADD COLUMN IF NOT EXISTS rcon_port INTEGER",
    "ALTER TABLE gameserver ADD COLUMN IF NOT EXISTS rcon_password VARCHAR(200)",
    # 'game' used to be a Postgres enum, which had to be altered for every new game type.
    "ALTER TABLE gameserver ALTER COLUMN game TYPE VARCHAR(50) USING game::text",
    "DROP TYPE IF EXISTS gameservertype",
]


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        yield session


async def init_db():
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
        for statement in LEGACY_SCHEMA_UPGRADES:
            await connection.execute(text(statement))
