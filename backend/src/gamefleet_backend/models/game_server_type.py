from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional


class GameServerType(str, Enum):
    minecraft = "minecraft"
    minecraft_bedrock = "minecraft_bedrock"
    factorio = "factorio"
    satisfactory = "satisfactory"
    ark_ase = "ark_ase"
    ark_asa = "ark_asa"
    valheim = "valheim"
    rust = "rust"
    seven_days_to_die = "seven_days_to_die"
    palworld = "palworld"
    project_zomboid = "project_zomboid"
    enshrouded = "enshrouded"
    v_rising = "v_rising"
    conan_exiles = "conan_exiles"
    dayz = "dayz"
    counter_strike = "counter_strike"
    team_fortress_2 = "team_fortress_2"
    garrys_mod = "garrys_mod"
    unturned = "unturned"
    left_4_dead_2 = "left_4_dead_2"
    squad = "squad"
    insurgency_sandstorm = "insurgency_sandstorm"
    mordhau = "mordhau"
    arma_reforger = "arma_reforger"
    soulmask = "soulmask"
    abiotic_factor = "abiotic_factor"
    space_engineers = "space_engineers"
    the_forest = "the_forest"
    sons_of_the_forest = "sons_of_the_forest"
    steam = "steam"


class QueryProtocol(str, Enum):
    minecraft_java = "minecraft_java"
    minecraft_bedrock = "minecraft_bedrock"
    a2s = "a2s"
    factorio_rcon = "factorio_rcon"
    satisfactory_api = "satisfactory_api"
    ark_eos = "ark_eos"


@dataclass(frozen=True)
class GameSpec:
    """Static knowledge about a game: how to display it and how to reach its query endpoint."""
    label: str
    protocol: QueryProtocol
    default_port: int
    # How the query port derives from the game port when the user has not set one explicitly.
    # None means "same as the game port".
    query_port: Optional[int | Callable[[int], int]] = None
    default_rcon_port: Optional[int] = None

    def resolve_query_port(self, port: int, override: Optional[int]) -> int:
        if override:
            return override
        if self.query_port is None:
            return port
        if callable(self.query_port):
            return self.query_port(port)
        return self.query_port


GAME_CATALOG: dict[GameServerType, GameSpec] = {
    GameServerType.minecraft: GameSpec("Minecraft (Java)", QueryProtocol.minecraft_java, 25565),
    GameServerType.minecraft_bedrock: GameSpec("Minecraft (Bedrock)", QueryProtocol.minecraft_bedrock, 19132),
    GameServerType.factorio: GameSpec("Factorio", QueryProtocol.factorio_rcon, 34197, default_rcon_port=27015),
    GameServerType.satisfactory: GameSpec("Satisfactory", QueryProtocol.satisfactory_api, 7777),
    GameServerType.ark_ase: GameSpec("ARK: Survival Evolved", QueryProtocol.a2s, 7777, query_port=27015),
    GameServerType.ark_asa: GameSpec("ARK: Survival Ascended", QueryProtocol.ark_eos, 7777, default_rcon_port=27020),
    GameServerType.valheim: GameSpec("Valheim", QueryProtocol.a2s, 2456, query_port=lambda p: p + 1),
    GameServerType.rust: GameSpec("Rust", QueryProtocol.a2s, 28015),
    GameServerType.seven_days_to_die: GameSpec("7 Days to Die", QueryProtocol.a2s, 26900),
    GameServerType.palworld: GameSpec("Palworld", QueryProtocol.a2s, 8211, query_port=27015),
    GameServerType.project_zomboid: GameSpec("Project Zomboid", QueryProtocol.a2s, 16261),
    GameServerType.enshrouded: GameSpec("Enshrouded", QueryProtocol.a2s, 15636, query_port=lambda p: p + 1),
    GameServerType.v_rising: GameSpec("V Rising", QueryProtocol.a2s, 9876, query_port=lambda p: p + 1),
    GameServerType.conan_exiles: GameSpec("Conan Exiles", QueryProtocol.a2s, 7777, query_port=27015),
    GameServerType.dayz: GameSpec("DayZ", QueryProtocol.a2s, 2302, query_port=27016),
    GameServerType.counter_strike: GameSpec("Counter-Strike", QueryProtocol.a2s, 27015),
    GameServerType.team_fortress_2: GameSpec("Team Fortress 2", QueryProtocol.a2s, 27015),
    GameServerType.garrys_mod: GameSpec("Garry's Mod", QueryProtocol.a2s, 27015),
    GameServerType.unturned: GameSpec("Unturned", QueryProtocol.a2s, 27015, query_port=lambda p: p + 1),
    GameServerType.left_4_dead_2: GameSpec("Left 4 Dead 2", QueryProtocol.a2s, 27015),
    GameServerType.squad: GameSpec("Squad", QueryProtocol.a2s, 7787, query_port=27165),
    GameServerType.insurgency_sandstorm: GameSpec("Insurgency: Sandstorm", QueryProtocol.a2s, 27102, query_port=27131),
    GameServerType.mordhau: GameSpec("Mordhau", QueryProtocol.a2s, 7777, query_port=27015),
    GameServerType.arma_reforger: GameSpec("Arma Reforger", QueryProtocol.a2s, 2001, query_port=17777),
    GameServerType.soulmask: GameSpec("Soulmask", QueryProtocol.a2s, 8777, query_port=27015),
    GameServerType.abiotic_factor: GameSpec("Abiotic Factor", QueryProtocol.a2s, 7777, query_port=27015),
    GameServerType.space_engineers: GameSpec("Space Engineers", QueryProtocol.a2s, 27016),
    GameServerType.the_forest: GameSpec("The Forest", QueryProtocol.a2s, 27015, query_port=27016),
    GameServerType.sons_of_the_forest: GameSpec("Sons of the Forest", QueryProtocol.a2s, 8766, query_port=27016),
    GameServerType.steam: GameSpec("Other Steam game (A2S)", QueryProtocol.a2s, 27015),
}
