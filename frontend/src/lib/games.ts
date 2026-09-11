import { GameServerType } from '$lib/api/Api'

export const GAME_META: Record<GameServerType, { label: string; emoji: string }> = {
    [GameServerType.Minecraft]: { label: 'Minecraft (Java)', emoji: '⛏️' },
    [GameServerType.MinecraftBedrock]: { label: 'Minecraft (Bedrock)', emoji: '🧱' },
    [GameServerType.Factorio]: { label: 'Factorio', emoji: '⚙️' },
    [GameServerType.Satisfactory]: { label: 'Satisfactory', emoji: '🏭' },
    [GameServerType.ArkAse]: { label: 'ARK: Survival Evolved', emoji: '🦖' },
    [GameServerType.ArkAsa]: { label: 'ARK: Survival Ascended', emoji: '🦕' },
    [GameServerType.Valheim]: { label: 'Valheim', emoji: '🪓' },
    [GameServerType.Rust]: { label: 'Rust', emoji: '🔩' },
    [GameServerType.SevenDaysToDie]: { label: '7 Days to Die', emoji: '🧟' },
    [GameServerType.Palworld]: { label: 'Palworld', emoji: '🐾' },
    [GameServerType.ProjectZomboid]: { label: 'Project Zomboid', emoji: '🏚️' },
    [GameServerType.Enshrouded]: { label: 'Enshrouded', emoji: '🌫️' },
    [GameServerType.VRising]: { label: 'V Rising', emoji: '🧛' },
    [GameServerType.ConanExiles]: { label: 'Conan Exiles', emoji: '⚔️' },
    [GameServerType.Dayz]: { label: 'DayZ', emoji: '🩸' },
    [GameServerType.CounterStrike]: { label: 'Counter-Strike', emoji: '🔫' },
    [GameServerType.TeamFortress2]: { label: 'Team Fortress 2', emoji: '🎩' },
    [GameServerType.GarrysMod]: { label: "Garry's Mod", emoji: '🔧' },
    [GameServerType.Unturned]: { label: 'Unturned', emoji: '🟩' },
    [GameServerType.Steam]: { label: 'Steam game (A2S)', emoji: '♨️' }
}

export function gameLabel(game: GameServerType): string {
    return GAME_META[game]?.label ?? game.replace(/_/g, ' ')
}

export function gameEmoji(game: GameServerType): string {
    return GAME_META[game]?.emoji ?? '🎮'
}

export function isMinecraft(game: GameServerType): boolean {
    return game === GameServerType.Minecraft || game === GameServerType.MinecraftBedrock
}
