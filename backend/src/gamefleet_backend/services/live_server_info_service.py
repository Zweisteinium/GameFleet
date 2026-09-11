import asyncio

from gamefleet_backend.db.models.game_server import GameServer
from gamefleet_backend.models.server_info import BaseServerInfo, ServerStatus
from gamefleet_backend.models.game_server_type import GAME_CATALOG, GameServerType, QueryProtocol
from gamefleet_backend.lib.query.minecraft import get_minecraft_server_info, get_minecraft_bedrock_server_info
from gamefleet_backend.lib.query.factorio import get_factorio_server_info
from gamefleet_backend.lib.query.satisfactory import get_satisfactory_server_info
from gamefleet_backend.lib.query.ark_ase import get_ark_ase_server_info
from gamefleet_backend.lib.query.ark_asa import get_ark_asa_server_info
from gamefleet_backend.lib.query.steam import get_steam_server_info

# Hard upper bound per server so one dead host can never stall a dashboard refresh.
QUERY_DEADLINE = 20.0
MAX_CONCURRENT_QUERIES = 16


class LiveServerInfoService:
    """Service for fetching live server information from game servers."""

    @staticmethod
    async def get_server_info(server: GameServer) -> BaseServerInfo:
        spec = GAME_CATALOG.get(server.game)
        if spec is None:
            return BaseServerInfo(status=ServerStatus.UNKNOWN, error_message=f"Unsupported server type: {server.game}")

        address, port = server.address, server.port
        rcon_port = server.rcon_port or spec.default_rcon_port
        try:
            match spec.protocol:
                case QueryProtocol.minecraft_java:
                    coro = get_minecraft_server_info(address, port)
                case QueryProtocol.minecraft_bedrock:
                    coro = get_minecraft_bedrock_server_info(address, port)
                case QueryProtocol.factorio_rcon:
                    coro = get_factorio_server_info(address, port, rcon_port, server.rcon_password)
                case QueryProtocol.satisfactory_api:
                    coro = get_satisfactory_server_info(address, port)
                case QueryProtocol.ark_eos:
                    coro = get_ark_asa_server_info(address, port, rcon_port, server.rcon_password)
                case QueryProtocol.a2s if server.game == GameServerType.ark_ase:
                    coro = get_ark_ase_server_info(address, spec.resolve_query_port(port, server.query_port))
                case QueryProtocol.a2s:
                    coro = get_steam_server_info(address, spec.resolve_query_port(port, server.query_port))
            return await asyncio.wait_for(coro, QUERY_DEADLINE)
        except asyncio.TimeoutError:
            return BaseServerInfo(status=ServerStatus.OFFLINE, error_message="Query timed out")
        except Exception as exc:  # defensive: query modules already map their own errors
            return BaseServerInfo(status=ServerStatus.UNKNOWN, error_message=f"{type(exc).__name__}: {exc}")

    @staticmethod
    async def get_all_server_info(servers: list[GameServer]) -> dict[str, BaseServerInfo]:
        """Query many servers concurrently; returns a map of server id -> live info."""
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_QUERIES)

        async def query(server: GameServer) -> BaseServerInfo:
            async with semaphore:
                return await LiveServerInfoService.get_server_info(server)

        results = await asyncio.gather(*(query(server) for server in servers))
        return {server.id: info for server, info in zip(servers, results)}
