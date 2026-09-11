from mcstatus import BedrockServer, JavaServer

from gamefleet_backend.models.server_info import MinecraftServerInfo, ServerStatus
from .common import QUERY_TIMEOUT, info_from_exception


async def get_minecraft_server_info(address: str, port: int = 25565) -> MinecraftServerInfo:
    try:
        server = await JavaServer.async_lookup(f"{address}:{port}", timeout=QUERY_TIMEOUT)
        status = await server.async_status()
    except Exception as exc:
        return info_from_exception(MinecraftServerInfo, exc)

    forge = status.forge_data
    mods = [{"name": mod.name, "version": mod.marker} for mod in forge.mods] if forge and forge.mods else None

    return MinecraftServerInfo(
        status=ServerStatus.ONLINE,
        latency=status.latency,
        version=status.version.name,
        description=status.motd.to_minecraft(),
        icon=status.icon,
        mods=mods,
        players_online=status.players.online,
        players_max=status.players.max,
        player_list=[player.name for player in status.players.sample] if status.players.sample else None,
        edition="java",
        protocol=status.version.protocol,
        enforces_secure_chat=status.enforces_secure_chat,
    )


async def get_minecraft_bedrock_server_info(address: str, port: int = 19132) -> MinecraftServerInfo:
    try:
        server = BedrockServer.lookup(f"{address}:{port}", timeout=QUERY_TIMEOUT)
        status = await server.async_status()
    except Exception as exc:
        return info_from_exception(MinecraftServerInfo, exc)

    return MinecraftServerInfo(
        status=ServerStatus.ONLINE,
        latency=status.latency,
        version=status.version.name,
        description=status.motd.to_minecraft(),
        game_mode=status.gamemode,
        map_name=status.map_name or None,
        players_online=status.players.online,
        players_max=status.players.max,
        edition="bedrock",
        protocol=status.version.protocol,
    )
