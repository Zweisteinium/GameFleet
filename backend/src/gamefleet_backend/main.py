import asyncio
import logging
from contextlib import asynccontextmanager
from importlib.metadata import version as package_version

from fastapi import Depends, FastAPI

from .api import auth as auth_api, docker, games, servers
from .auth import current_user, log_startup_state
from .db.session import init_db
from .services.docker_discovery_service import DISCOVERY_INTERVAL, discovery_loop
from .settings import DEV

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
if DEV:
    logging.getLogger("gamefleet_backend").setLevel(logging.DEBUG)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if DEV:
        logging.getLogger(__name__).warning("Development mode (GAMEFLEET_ENV=dev): API docs are served; not for production")
    log_startup_state()
    await init_db()
    task = asyncio.create_task(discovery_loop()) if DISCOVERY_INTERVAL > 0 else None
    yield
    if task:
        task.cancel()


app = FastAPI(
    title="Game Server Dashboard API",
    description="API for managing and monitoring game servers",
    version=package_version("gamefleet-backend"),  # single source of truth: pyproject.toml
    # The interactive docs and the schema describe every endpoint; they are only served in development mode.
    docs_url="/swagger" if DEV else None,
    redoc_url="/redoc" if DEV else None,
    openapi_url="/openapi.json" if DEV else None,
    lifespan=lifespan
)

protected = [Depends(current_user)]
app.include_router(auth_api.router, prefix="/api/auth", tags=["auth"])
# Reading servers is open to visitors (limited to public servers); the router protects everything else itself.
app.include_router(servers.router, prefix="/api/servers", tags=["servers"])
app.include_router(docker.router, prefix="/api/docker", tags=["docker"], dependencies=protected)
# Artwork stays public: it is loaded through <img> tags, which cannot send a bearer token.
app.include_router(games.router, prefix="/api/games", tags=["games"])

@app.get("/")
def root():
    return {"status": "ok", "message": "Backend running"}
