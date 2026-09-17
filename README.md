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
- Game servers running in Docker on the same host are found automatically, can be started, stopped and restarted from the dashboard, and show CPU, memory, data and world size
- Public by default: visitors see the servers you mark as public; signing in (users from an environment variable) unlocks the rest, including adding, editing and controlling servers
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

## Servers in Docker on the same host

With the Docker socket mounted into the backend (the compose files do this), GameFleet looks at every container on the host and recognises game servers from what they already are, most reliable first (there are no GameFleet labels to add or maintain):

1. **Known images** (`itzg/minecraft-server`, `factoriotools/factorio`, `lloesche/valheim-server`, `thijsvanloef/palworld-server-docker`, `wolveix/satisfactory-server`, `cm2network/*` and more, see `models/container_catalog.py`) are recognised with certainty. The catalog also knows where each image keeps its data and how it is given its RCON password, so a Factorio or Minecraft container needs no configuration at all.
2. **Names and ports** only produce a suggestion: a container called `my-valheim` or one that exposes 34197/udp shows up in the "Containers on this host" panel with a game dropdown and an Import button.

Nothing is imported on its own. **Import from Docker** on the dashboard (signed in) takes every running container with a known image at once; the panel imports single containers, including stopped ones and guesses. Stopped containers are left out of the bulk import because several of them may claim the same host port, and a linked server whose container is not running is shown as offline instead of being queried.

Hosts with many instances of one game are the normal case: a compose directory per server, most of them stopped, all on the game's default port. Stopped containers are read through their configured port bindings, an image whose tag moved on to a newer pull is resolved to its name, and the panels show each container's compose directory. Starting a server whose host port is held by another running server asks whether to stop that one first; a port held by a container that is not in the fleet, or by a process on the host, is reported and nothing is stopped. GameFleet only sees containers that exist: a compose project that was taken `down` has none until it is created again with `docker compose up --no-start` or `up -d`.

**Modpacks** of Minecraft servers are read from the container as well: the `itzg/minecraft-server` variables name the pack (`MODRINTH_MODPACK`, `CF_SLUG` or `CF_PAGE_URL`, `FTB_MODPACK_ID`, `TYPE=GTNH`, or the file name of a `GENERIC_PACK` or `CF_MODPACK_ZIP` archive). A Modrinth project, or a pack whose exact name exists on Modrinth, gets its title, icon and link from the Modrinth API; CurseForge, FTB and GTNH link to their own sites. Servers with hand-installed mods name no pack anywhere, and remote servers have no container to read: both can be given a name and link in the server form, which detection then leaves alone.

Ports are translated to what is reachable from the host (published port, or the container's own address when nothing is published), the container name is the link, so `docker compose up` recreating a container keeps it attached, and a changed address or port mapping is picked up on the next discovery run. Imported servers get a **Host container** panel with start/stop/restart, CPU and memory (one Docker stats sample per refresh, cached for 10 s), and the size of the data and world directories (`du` inside the container, cached for 5 min). Removing an imported server hides the container from discovery; it can be shown again from the panel.

Backups and rollback are planned on top of this: every imported server already records its persistent paths and volumes, and stop/start are the primitives a restore needs.

## Quick start (Docker)

You need Docker and a PostgreSQL database; `make db` starts one from the same compose file if you have none.

```bash
git clone https://github.com/H3xaChad/GameFleet.git
cd GameFleet
cp .env.example .env      # set DB_PASSWORD and GAMEFLEET_USERS (and anything else you want to change)
make db                   # optional: PostgreSQL 16 container using the DB_* values from .env
make up                   # builds and starts backend + frontend in the background
```

- Dashboard: http://localhost:3000 (public view; sign in with a user from `GAMEFLEET_USERS` to manage servers)
- API docs: http://localhost:8000/swagger, only with `GAMEFLEET_DEV=true` (also proxied at http://localhost:3000/swagger)

`FRONTEND_PORT` and `BACKEND_PORT` in `.env` are the only ports to set. The frontend forwards `/api` to the backend
inside the compose network, so browsers on the LAN need nothing but the frontend port.

The database schema is created and upgraded automatically when the backend starts. Game artwork is cached in the `gamefleet-assets` volume.

Prebuilt images are published as `lordlayer/gamefleet_backend` and `lordlayer/gamefleet_frontend`: `docker compose pull && docker compose up -d` runs them without building.

## Configuration

One `.env` in the repository root configures everything: `docker-compose.yml` reads it, and the backend loads it when run natively. Real environment variables take precedence.

| Variable | Default | Purpose |
|----------|---------|---------|
| `GAMEFLEET_DEV` | `false` | `true` serves the API docs (`/swagger`, `/redoc`, `/openapi.json`), logs verbosely, opens a dashboard without users to everyone and shows a development banner. `make backend` always runs in dev mode |
| `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` | Postgres on this host, `5432`, `gamefleet`, `gamefleet`, – | PostgreSQL connection; `make db` creates its database from the same values. Empty `DB_HOST` means `localhost` natively and `host.docker.internal` in Docker |
| `DATABASE_URL` | – | Full SQLAlchemy URL (`postgresql+asyncpg://...`) that overrides the `DB_*` values |
| `BACKEND_PORT` | `8000` | Published backend port (API, plus the Swagger UI in dev mode) |
| `FRONTEND_PORT` | `3000` | Published frontend port; the frontend proxies `/api` to the backend |
| `ASSET_CACHE_DIR` | `data/assets` | Where the backend stores downloaded game artwork |
| `GAMEFLEET_USERS` | – | Login users, `name:password,name2:password2`. Passwords in plain text or scrypt hashes from `make hash` (`$` becomes `$$` in `.env`). Without a login, visitors only see servers marked public. Empty means nobody can sign in: read-only in prod, open to everyone in dev. |
| `GAMEFLEET_SECRET` | random per start | Signs login tokens (30 days, `GAMEFLEET_SESSION_HOURS`); set it so logins survive restarts |
| `DOCKER_SERVER_ADDRESS` | `host.docker.internal` in Docker, `127.0.0.1` natively | Address imported containers are queried at |
| `DOCKER_DISCOVERY_INTERVAL` | `60` | Seconds between background discovery runs, `0` disables |
| `UV_LINK_MODE` | – | Set to `copy` if your uv cache and project live on different filesystems |

## Development

Prerequisites: [uv](https://docs.astral.sh/uv/), [pnpm](https://pnpm.io/), Docker (for Postgres), Python 3.14, Node 24. uv downloads Python 3.14 automatically if it is missing; the pnpm version is pinned in `package.json` (corepack).

```bash
make install        # uv sync + pnpm install
make db             # PostgreSQL 16 container with the DB_* values from .env (or point .env at any Postgres)
make backend        # API with auto-reload on http://localhost:8000
make frontend       # SvelteKit dev server on http://localhost:3000
```

`make check` runs svelte-check and ESLint on the frontend and import-checks the backend. `make swagger` regenerates `frontend/src/lib/api/Api.ts` from the OpenAPI schema of the running dev backend (`make backend`; the schema is not served in prod); run it whenever you change API models. The frontend proxies `/api`, `/swagger` and `/openapi.json` to `BACKEND_URL` (default `http://localhost:8000`), both in `pnpm dev` and in the Node server that the Docker image runs; `BACKEND_URL=http://localhost:8010 pnpm dev` targets a spare backend.

Append `?theme=light` or `?theme=dark` to any URL to force a theme (useful for sharing links).

### Adding a game

1. Add a value to `GameServerType` and a `GameSpec` (protocol, default port, query-port rule) to `GAME_CATALOG` in `backend/src/gamefleet_backend/models/game_server_type.py`.
2. Steam games only need their app id in `STEAM_APP_IDS` (`services/game_asset_service.py`) for artwork; other games can list explicit image URLs there.
3. Add the display label in `frontend/src/lib/games.ts` and run `pnpm swagger`.

Games that speak A2S need no query code. Anything else gets a module in `backend/src/gamefleet_backend/lib/query/` returning one of the `*ServerInfo` models.

### Project layout

```
backend/   FastAPI + SQLModel. api/ (routes), auth.py (users, tokens), services/ (live info, docker,
           discovery, assets), lib/query/ (one module per protocol), models/ (API models, game and
           container catalogs), db/
frontend/  SvelteKit (adapter-node, client-only, proxies /api) + Tailwind v4. lib/components/, routes/main, routes/server/[id]
docs/      screenshots
```

## Make targets

`make help` lists everything. Native development: `install`, `db`, `backend`, `frontend`, `check`, `swagger`, `hash` (password hash for `GAMEFLEET_USERS`). Docker: `up`, `down`, `restart`, `logs` (`S=backend` for one service), `ps`, `shell`, `build`, `release` (build, tag and push both images to `DOCKER_REPO`, default `h3xachad`), `clean` (also deletes the artwork cache; the database volume is kept).

Images are tagged with the project version from `backend/pyproject.toml`; override with `make release VERSION=x.y.z`.

## License

See [LICENSE](LICENSE).
