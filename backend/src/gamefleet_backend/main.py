from contextlib import asynccontextmanager
from importlib.metadata import version as package_version
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import servers, docker, games
from .db.session import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="Game Server Dashboard API",
    description="API for managing and monitoring game servers",
    version=package_version("gamefleet-backend"),  # single source of truth: pyproject.toml
    docs_url="/swagger",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(servers.router, prefix="/api/servers", tags=["servers"])
app.include_router(docker.router, prefix="/api/docker", tags=["docker"])
app.include_router(games.router, prefix="/api/games", tags=["games"])

@app.get("/")
def root():
    return {"status": "ok", "message": "Backend running"}