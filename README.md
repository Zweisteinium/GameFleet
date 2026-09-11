# GameFleet

A small, self-hosted dashboard for your game servers. It shows which servers are up, who is playing, and whatever else each game is willing to tell you: map, version, mods, in-game day, MOTD and more.

![GameFleet dashboard](docs/dashboard-dark.png)

<details>
<summary>More screenshots</summary>

![Light theme](docs/dashboard-light.png)
![Server detail](docs/server-detail.png)

</details>

## Features

- One dashboard for all your servers, with search, per-game filters, status filter, sorting and grid/list views
- Live status, player counts and player names (where the game publishes them), refreshed every 30 seconds
- Per-game details: Minecraft MOTD and server icon, ARK day/cluster/mods, Factorio evolution and tags, raw A2S rules for Steam games
- Real game artwork, downloaded once and cached locally by the backend
- Light and dark theme
- FastAPI backend with OpenAPI docs, SvelteKit frontend, PostgreSQL storage
- Ships as two Docker images

## Supported games

| Game | How it is queried | Notes |
|------|-------------------|-------|
| Minecraft (Java) | Server list ping | MOTD, icon, version, players, Forge mods |
| Minecraft (Bedrock) | Raknet ping | MOTD, version, players, game mode, map |
| Factorio | RCON | Factorio has no public query protocol. Start the server with `--rcon-port` and `--rcon-password` and enter them when adding the server. |
| Satisfactory | Dedicated server HTTPS API | Session, tech tier, game phase, tick rate |
| ARK: Survival Evolved | Steam A2S (query port, default 27015) | Day, mods, PvE/PvP, cluster, BattlEye |
| ARK: Survival Ascended | Epic Online Services | Official and Nitrado/public servers are found automatically via ARK's server lists. Private servers need RCON (`ListPlayers`). |
| Valheim, Rust, 7 Days to Die, Palworld, Project Zomboid, Enshrouded, V Rising, Conan Exiles, DayZ, Counter-Strike, Team Fortress 2, Garry's Mod, Unturned | Steam A2S | Default query ports are prefilled per game; override the query port if your server uses a different one. |
| Any other Steam game | Steam A2S | Pick "Steam game (A2S)" and enter the query port. |

The **port** of a server is always the port players connect to. The query port and RCON port only need to be set when they differ from the game's defaults, which the add-server form shows.

## Quick start (Docker)

You need Docker and a PostgreSQL database. The compose file runs the backend with host networking, so any Postgres reachable from the host works. To run one alongside:

```bash
docker run -d --name gamefleet-postgres --restart unless-stopped \
  -e POSTGRES_USER=gamefleet_user -e POSTGRES_PASSWORD=changeme -e POSTGRES_DB=gamefleet_db \
  -p 5432:5432 -v gamefleet-postgres:/var/lib/postgresql/data postgres:16
```

Then:

```bash
git clone https://github.com/H3xaChad/GameFleet.git
cd GameFleet
cp .env.example .env      # set DB_PASSWORD (and anything else you want to change)
make up                   # builds and starts backend + frontend in the background
```

- Dashboard: http://localhost:3000
- API docs: http://localhost:8000/swagger

The database schema is created and upgraded automatically when the backend starts. Game artwork is cached in the `gamefleet-assets` volume.

Prebuilt images are published as `h3xachad/gamefleet-backend` and `h3xachad/gamefleet-frontend`; see `docker-compose-example.yml` for using them.

## Configuration

`.env` in the repository root (used by `docker-compose.yml`):

| Variable | Default | Purpose |
|----------|---------|---------|
| `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` | `localhost`, `5432`, `gamefleet_db`, `gamefleet_user`, – | PostgreSQL connection |
| `BACKEND_PORT` | `8000` | Backend port (host network) |
| `FRONTEND_PORT` | `3000` | Published frontend port |
| `FRONTEND_TARGET` | `node-server` | `node-server` or `nginx-server` image variant |
| `ASSET_CACHE_DIR` | `data/assets` | Where the backend stores downloaded game artwork |
| `UV_LINK_MODE` | – | Set to `copy` if your uv cache and project live on different filesystems |

`backend/.env` (used when running the backend natively): `DATABASE_URL` (asyncpg URL) and `DATABASE_URL_SYNC` (psycopg2 URL, only for Alembic).

## Development

Prerequisites: [uv](https://docs.astral.sh/uv/), [pnpm](https://pnpm.io/), Docker (for Postgres), Python 3.13, Node 22.

```bash
# database (or use any Postgres; adjust backend/.env)
docker run -d --name gamefleet-postgres -e POSTGRES_USER=gamefleet_user -e POSTGRES_PASSWORD=gamefleet_pass \
  -e POSTGRES_DB=gamefleet_db -p 5432:5432 -v gamefleet-postgres:/var/lib/postgresql/data postgres:16

# backend on http://localhost:8000
cd backend
uv sync
make dev            # = uv run uvicorn gamefleet_backend.main:app --reload

# frontend on http://localhost:3000
cd frontend
pnpm install
pnpm dev
```

Useful frontend scripts: `pnpm check` (svelte-check), `pnpm build`, `pnpm lint`, and `pnpm swagger` to regenerate `src/lib/api/Api.ts` from the running backend's OpenAPI schema. Run it whenever you change API models.

Append `?theme=light` or `?theme=dark` to any URL to force a theme (useful for sharing links).

### Adding a game

1. Add a value to `GameServerType` and a `GameSpec` (protocol, default port, query-port rule) to `GAME_CATALOG` in `backend/src/gamefleet_backend/models/game_server_type.py`.
2. Steam games only need their app id in `STEAM_APP_IDS` (`services/game_asset_service.py`) for artwork; other games can list explicit image URLs there.
3. Add the display label in `frontend/src/lib/games.ts` and run `pnpm swagger`.

Games that speak A2S need no query code. Anything else gets a module in `backend/src/gamefleet_backend/lib/query/` returning one of the `*ServerInfo` models.

### Project layout

```
backend/   FastAPI + SQLModel. api/ (routes), services/ (live info, docker, assets),
           lib/query/ (one module per protocol), models/ (API models + game catalog), db/
frontend/  SvelteKit (static adapter) + Tailwind v4. lib/components/, routes/main, routes/server/[id]
docs/      screenshots
```

## Make targets

Root `Makefile` (Docker): `make dev` (foreground with build), `make up`, `make down`, `make restart`, `make logs`, `make build`, `make release` (build, tag and push images), `make clean`.

`backend/Makefile` (native): `make dev`, `make start`, `make migrate`, `make createmigration`.

## License

See [LICENSE](LICENSE).
