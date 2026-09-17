import os
from typing import AsyncGenerator
from sqlalchemy import text
from sqlmodel import SQLModel
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from urllib.parse import quote_plus


def database_url() -> str:
    """Connection URL from the DB_* variables; a full DATABASE_URL overrides them. Variables that are set
    but empty (as DB_HOST is in .env.example) count as unset."""
    if url := os.getenv("DATABASE_URL"):
        return url
    user = quote_plus(os.getenv("DB_USER") or "gamefleet")
    password = quote_plus(os.getenv("DB_PASSWORD") or "")
    host = os.getenv("DB_HOST") or "localhost"
    port = os.getenv("DB_PORT") or "5432"
    name = os.getenv("DB_NAME") or "gamefleet"
    return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{name}"


engine = create_async_engine(database_url())

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
    # 0.6: servers can be linked to local Docker containers.
    "ALTER TABLE gameserver ADD COLUMN IF NOT EXISTS source VARCHAR(20) NOT NULL DEFAULT 'manual'",
    "ALTER TABLE gameserver ADD COLUMN IF NOT EXISTS container_name VARCHAR(200)",
    "ALTER TABLE gameserver ADD COLUMN IF NOT EXISTS data_path VARCHAR(300)",
    "ALTER TABLE gameserver ADD COLUMN IF NOT EXISTS world_path VARCHAR(300)",
    "CREATE UNIQUE INDEX IF NOT EXISTS ix_gameserver_container_name ON gameserver (container_name)",
    # 0.8: visitors without a login only see servers flagged public.
    "ALTER TABLE gameserver ADD COLUMN IF NOT EXISTS is_public BOOLEAN NOT NULL DEFAULT FALSE",
    # 0.10: modpack of a Minecraft server.
    "ALTER TABLE gameserver ADD COLUMN IF NOT EXISTS modpack_name VARCHAR(200)",
    "ALTER TABLE gameserver ADD COLUMN IF NOT EXISTS modpack_version VARCHAR(100)",
    "ALTER TABLE gameserver ADD COLUMN IF NOT EXISTS modpack_url VARCHAR(500)",
    "ALTER TABLE gameserver ADD COLUMN IF NOT EXISTS modpack_icon VARCHAR(500)",
    "ALTER TABLE gameserver ADD COLUMN IF NOT EXISTS modpack_source VARCHAR(20)",
]


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        yield session


async def init_db():
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
        for statement in LEGACY_SCHEMA_UPGRADES:
            await connection.execute(text(statement))
