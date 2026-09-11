import { GameServerType } from '$lib/api/Api';
import { API_BASE_URL } from '$lib/api/ApiService';

export const GAME_LABELS: Record<GameServerType, string> = {
	[GameServerType.Minecraft]: 'Minecraft (Java)',
	[GameServerType.MinecraftBedrock]: 'Minecraft (Bedrock)',
	[GameServerType.Factorio]: 'Factorio',
	[GameServerType.Satisfactory]: 'Satisfactory',
	[GameServerType.ArkAse]: 'ARK: Survival Evolved',
	[GameServerType.ArkAsa]: 'ARK: Survival Ascended',
	[GameServerType.Valheim]: 'Valheim',
	[GameServerType.Rust]: 'Rust',
	[GameServerType.SevenDaysToDie]: '7 Days to Die',
	[GameServerType.Palworld]: 'Palworld',
	[GameServerType.ProjectZomboid]: 'Project Zomboid',
	[GameServerType.Enshrouded]: 'Enshrouded',
	[GameServerType.VRising]: 'V Rising',
	[GameServerType.ConanExiles]: 'Conan Exiles',
	[GameServerType.Dayz]: 'DayZ',
	[GameServerType.CounterStrike]: 'Counter-Strike',
	[GameServerType.TeamFortress2]: 'Team Fortress 2',
	[GameServerType.GarrysMod]: "Garry's Mod",
	[GameServerType.Unturned]: 'Unturned',
	[GameServerType.Steam]: 'Steam game (A2S)'
};

export function gameLabel(game: GameServerType): string {
	return GAME_LABELS[game] ?? game.replace(/_/g, ' ');
}

/** Artwork is downloaded once by the backend and served from its disk cache. */
export function gameArtUrl(game: GameServerType, kind: 'poster' | 'hero'): string {
	return `${API_BASE_URL}/api/games/${game}/${kind}`;
}

/** Games whose default artwork is an icon rather than a poster; shown framed like a server icon. */
export function hasIconArt(game: GameServerType): boolean {
	return isMinecraft(game);
}

export function isMinecraft(game: GameServerType): boolean {
	return game === GameServerType.Minecraft || game === GameServerType.MinecraftBedrock;
}
