# GameFleet

GameFleet is a self-hosted dashboard for game servers. It started because I run a handful of Minecraft, Factorio and Valheim servers at home and wanted one page that tells me which of them are up, who is playing and what they are running. It works just as well for public servers you only play on.

Today it shows live status for more than 20 games, finds game servers that run in Docker on the same machine, starts and stops them and restores their backups. The long-term plan is a complete management panel for your own hardware, similar to what hosts like Nitrado offer: set up new servers in a few clicks, change their settings and keep them updated. Without renting anything :)

![GameFleet dashboard](docs/dashboard-dark.png)

<details>
<summary>More screenshots</summary>

![Light theme](docs/dashboard-light.png)
![Server detail](docs/server-detail.png)

</details>

## Quick start

Save this as `docker-compose.yml`, change the `change-me` values and run `docker compose up -d`:

```yaml
services:
  backend:
    image: lordlayer/gamefleet_backend:latest
    restart: unless-stopped
    environment:
      DB_HOST: postgres
      DB_PASSWORD: change-me
      GAMEFLEET_USERS: admin:change-me # name:password, comma separated for more
      GAMEFLEET_SECRET: change-me # any long random string, e.g. from: openssl rand -hex 32
      DOCKER_SERVER_ADDRESS: host.docker.internal
    extra_hosts:
      - "host.docker.internal:host-gateway"
    volumes:
      - gamefleet-assets:/app/data/assets
      # Lets GameFleet find and control game servers in Docker on this host. Remove it to only monitor.
      - /var/run/docker.sock:/var/run/docker.sock
    depends_on:
      - postgres

  frontend:
    image: lordlayer/gamefleet_frontend:latest
    restart: unless-stopped
    environment:
      BACKEND_URL: http://backend:8000
    ports:
      - "3000:3000"

  postgres:
    image: postgres:16
    restart: unless-stopped
    environment:
      POSTGRES_DB: gamefleet
      POSTGRES_USER: gamefleet
      POSTGRES_PASSWORD: change-me # same as DB_PASSWORD
    volumes:
      - gamefleet-postgres:/var/lib/postgresql/data

volumes:
  gamefleet-assets:
  gamefleet-postgres:
```

Then open http://localhost:3000. Visitors see the servers you mark as public, and signing in lets you add, edit and control servers. The database is set up on the first start.

**From source:** clone the repository, `cp .env.example .env`, adjust it, then `make db` (optional Postgres container) and `make up`.

## Features

- Live status, players, version, map, MOTD, mods and game-specific details for 30 games, refreshed every 30 seconds
- Search, filters, sorting, grid and list view, light and dark theme, real game artwork
- Public by default: visitors see the servers you mark as public, signing in unlocks the rest
- Game servers in Docker on the same host are recognised automatically: start, stop, restart, CPU, memory and disk usage
- Deploy new servers from a template: Minecraft Java and Bedrock, Factorio, Valheim and Satisfactory
- Edit server settings in a form (`server.properties`, Factorio's server settings) or any config file in a raw editor
- Modpack detection for Minecraft (Modrinth, CurseForge, FTB, GTNH)
- Restore from the backups your servers already make, or from an uploaded file

## Supported games

GameFleet asks every server directly with the game's own protocol, so there is no plugin or mod to install on the server.

| Game | How it is queried | Notes |
|------|-------------------|-------|
| Minecraft Java | Server list ping over TCP, the same request the multiplayer menu sends | MOTD with colors, server icon, version, player count and sample, Forge and NeoForge mods when the server lists them |
| Minecraft Bedrock | RakNet ping over UDP, as used by the Bedrock server list | MOTD, version, players, game mode, world name |
| Factorio | RCON, because Factorio has no public query protocol | Start the server with `--rcon-port` and `--rcon-password`. For Docker servers the password is read from the container. Shows players, version, game time, evolution, tags and seed |
| Satisfactory | HTTPS API of the dedicated server, with a passwordless client login | Session, tech tier, game phase, tick rate and players. Servers with a join password cannot be read yet |
| ARK: Survival Evolved | Steam A2S on the query port (default 27015) | In-game day, mods, PvE or PvP, cluster, BattlEye |
| ARK: Survival Ascended | Epic Online Services, found through ARK's official server lists | Official and public servers are found by name. Private servers need RCON (`ListPlayers`) |
| Valheim, Rust, 7 Days to Die, Palworld, Project Zomboid, Enshrouded, V Rising, Conan Exiles, DayZ, Counter-Strike, Team Fortress 2, Garry's Mod, Unturned, Left 4 Dead 2, Squad, Insurgency: Sandstorm, Mordhau, Arma Reforger, Soulmask, Abiotic Factor, Space Engineers, The Forest, Sons of the Forest | Steam A2S over UDP: server info, player list and rules | The default query port of each game is prefilled. Player names appear where the game reports them, and the raw rules are shown on the server page |
| Any other Steam game | Steam A2S | Pick "Steam game (A2S)" and enter the query port |

The port of a server is always the one players connect to. Query and RCON ports only need to be set when they differ from the game's defaults, and the add-server form shows those.

## Servers in Docker

With the Docker socket mounted, GameFleet looks at every container on the host and recognises game servers by their image (`itzg/minecraft-server`, `factoriotools/factorio`, `wolveix/satisfactory-server`, `lloesche/valheim-server` and many more). Container names and ports are used as a hint when the image is unknown. There is nothing to label or configure, because data paths, ports and RCON passwords are read from the container itself.

**Import from Docker** on the dashboard adds all running game servers at once. Single containers, stopped ones included, can be imported from the host panel. Several instances of one game on the same port are fine too: starting one whose port is taken offers to stop the other first.

## Deploying servers

**Add server → Deploy a new server** creates a game server in Docker on the GameFleet host. Pick a game, give it a name, fill in the few settings that matter (version, memory, passwords, max players) and the host ports, and GameFleet pulls the image, creates the container and adds it to the dashboard. Templates exist for Minecraft Java (`itzg/minecraft-server`, with Paper, Fabric, Forge, NeoForge and modpacks from Modrinth or CurseForge), Minecraft Bedrock, Factorio, Valheim and Satisfactory.

Each server lives in `SERVERS_ROOT/<game>/<name>` on the host (default `/opt/gamefleet/servers`), with its data folder and a `docker-compose.yml` that describes the container, so you can keep managing it by hand with `docker compose` whenever you like. Ports are checked against the other containers before anything is created.

## Settings

Servers in Docker get a **Settings** panel with the important options as a form: for Minecraft the `server.properties` keys such as MOTD, difficulty, game mode, PvP, whitelist and view distance, for Factorio the `server-settings.json` values. Anything else is reachable through **Edit file**, a raw editor for the known config files of each game (ops and whitelist, Paper and Spigot configs, Factorio map settings, Valheim admin lists, Satisfactory ini files). Changes are written to the container and apply on the next start; the panel offers the restart.

Settings that the container sets from its environment (itzg's `MOTD`, `MAX_PLAYERS` and the like) are shown but locked, because the image rewrites them on every start. Change those in the compose file.

## Backups

GameFleet restores from the backups your servers already write and lists them on each server's page:

| Game | Backups found in |
|------|------------------|
| Minecraft Java | `backups/` (ServerUtilities, FTB Backups), `simplebackups/`, `backup/` (Textile Backup) |
| Minecraft Bedrock | `backups/` (`.mcworld` or archives) |
| Factorio | the autosaves in `saves/` |
| Satisfactory | `/config/backups` and the server's save folder |
| Valheim | `/config/backups` (lloesche) or `/home/steam/backups` (mbround18) |
| ARK | timestamped `.ark` copies in `SavedArks` |

Other folders with "backup" in their name next to the server's data are searched too. A running server is stopped for the restore and started again afterwards. You can keep a copy of the current world first, so a restore can always be undone. You can also upload a backup from your computer. It is checked before anything is touched, but make sure it matches the server's game version and modpack.

## Configuration

Set these in `.env` when running from source, or in the compose file:

| Variable | Default | Purpose |
|----------|---------|---------|
| `GAMEFLEET_USERS` | – | Logins as `name:password,name2:password2`. `make hash` turns a password into a hash (write `$` as `$$` in `.env`) |
| `GAMEFLEET_SECRET` | random | Signs login tokens. Without it every restart logs everyone out. Generate one with `openssl rand -hex 32` |
| `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` | this host, `5432`, `gamefleet`, `gamefleet`, – | PostgreSQL connection |
| `DATABASE_URL` | – | Full connection URL that replaces the `DB_*` values, e.g. `postgresql+asyncpg://gamefleet:secret@db.example.com:5432/gamefleet` |
| `FRONTEND_PORT`, `BACKEND_PORT` | `3000`, `8000` | Published ports when running from source. Browsers only need the frontend |
| `DOCKER_SERVER_ADDRESS` | `host.docker.internal` | Address GameFleet uses to reach game servers in Docker |
| `SERVERS_ROOT` | `/opt/gamefleet/servers` | Host folder where deployed servers get their data and compose file |
| `GAMEFLEET_DEV` | `false` | Development mode with API docs at `/swagger` and verbose logs. Not meant for production |

## Development

You need [uv](https://docs.astral.sh/uv/), [pnpm](https://pnpm.io/) and Docker. Run `make install` and `make db`, then `make backend` and `make frontend` in two terminals (API on port 8000, dashboard on 3000, both reload on changes). `make check` type-checks and lints, `make test` runs the backend tests, and `make swagger` regenerates the API client after model changes.

## License

See [LICENSE](LICENSE).
