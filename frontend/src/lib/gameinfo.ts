/**
 * Turns the per-game live-info union into uniform building blocks for the UI, so every game is shown
 * with the same structure (overview tiles, property chips, capabilities) even though each publishes
 * different fields.
 */
import { GameServerType, type HostStats } from '$lib/api/Api';
import type { LiveServerInfo } from '$lib/api/types';

export type Tone = 'neutral' | 'accent' | 'success' | 'danger' | 'warning';

export interface Property {
	key: string;
	icon: string;
	label: string;
	tone: Tone;
	/** Longer explanation shown as a tooltip. */
	title?: string;
}

export interface Tile {
	key: string;
	icon: string;
	title: string;
	/** null renders as a dash, keeping the grid stable while a value is missing. */
	value: string | null;
	subtitle?: string;
	tone?: Tone;
}

/** What a query protocol can report at all; drives placeholders and empty-state messages. */
export interface Capabilities {
	latency: boolean;
	playerNames: boolean;
	map: boolean;
	mods: boolean;
	description: boolean;
}

const CAPABILITIES: Record<LiveServerInfo['kind'], Capabilities> = {
	base: { latency: true, playerNames: false, map: false, mods: false, description: false },
	steam: { latency: true, playerNames: true, map: true, mods: false, description: false },
	minecraft: { latency: true, playerNames: true, map: false, mods: true, description: true },
	factorio: { latency: false, playerNames: true, map: false, mods: false, description: true },
	satisfactory: { latency: false, playerNames: false, map: false, mods: false, description: false },
	ark: { latency: true, playerNames: true, map: true, mods: true, description: false }
};

export function capabilities(info: LiveServerInfo): Capabilities {
	return CAPABILITIES[info.kind] ?? CAPABILITIES.base;
}

/** Message for an empty player list that does not blame the server for something it cannot do. */
export function playersEmptyMessage(info: LiveServerInfo): string {
	if (info.players_online) {
		return capabilities(info).playerNames
			? 'This server does not publish player names.'
			: 'This game does not publish player names.';
	}
	return 'Nobody is online right now.';
}

function bool(value: boolean | null | undefined): value is boolean {
	return value === true || value === false;
}

/** Access, security and rule flags, in a fixed order, for any game. */
export function serverProperties(info: LiveServerInfo): Property[] {
	const items: Property[] = [];
	if (bool(info.password_protected)) {
		items.push(
			info.password_protected
				? { key: 'password', icon: 'lock', label: 'Password', tone: 'warning', title: 'Players need a password to join' }
				: { key: 'password', icon: 'lock-open', label: 'Open', tone: 'neutral', title: 'Anyone can join' }
		);
	}
	if (bool(info.anti_cheat_enabled)) {
		const name = info.kind === 'ark' ? 'BattlEye' : info.kind === 'steam' ? 'VAC' : 'Anti-cheat';
		items.push(
			info.anti_cheat_enabled
				? { key: 'anticheat', icon: 'shield', label: name, tone: 'success', title: `${name} is enabled` }
				: { key: 'anticheat', icon: 'shield-off', label: `No ${name}`, tone: 'neutral', title: `${name} is disabled` }
		);
	}
	switch (info.kind) {
		case 'minecraft':
			if (bool(info.enforces_secure_chat))
				items.push({
					key: 'securechat',
					icon: 'message-square',
					label: info.enforces_secure_chat ? 'Secure chat' : 'Unsigned chat',
					tone: info.enforces_secure_chat ? 'success' : 'neutral',
					title: 'Whether chat messages must be cryptographically signed'
				});
			break;
		case 'factorio':
			if (bool(info.public))
				items.push({
					key: 'listing',
					icon: 'radio',
					label: info.public ? 'Public listing' : 'Unlisted',
					tone: 'neutral',
					title: 'Whether the server appears in the public server browser'
				});
			if (bool(info.require_user_verification))
				items.push({
					key: 'verified',
					icon: 'user-check',
					label: info.require_user_verification ? 'Verified accounts' : 'Any account',
					tone: info.require_user_verification ? 'success' : 'neutral',
					title: 'Whether players must have a verified factorio.com account'
				});
			if (info.allow_commands)
				items.push({
					key: 'commands',
					icon: 'terminal',
					label: `Commands: ${info.allow_commands.replace(/-/g, ' ')}`,
					tone: 'neutral'
				});
			break;
		case 'ark':
			if (bool(info.pve))
				items.push(
					info.pve
						? { key: 'pve', icon: 'heart', label: 'PvE', tone: 'success' }
						: { key: 'pve', icon: 'swords', label: 'PvP', tone: 'danger' }
				);
			if (info.official) items.push({ key: 'official', icon: 'badge-check', label: 'Official', tone: 'accent' });
			if (info.platform_type)
				items.push({ key: 'platforms', icon: 'monitor', label: info.platform_type, tone: 'neutral', title: 'Platforms that can join' });
			break;
		case 'satisfactory':
			if (info.is_paused) items.push({ key: 'paused', icon: 'pause', label: 'Paused', tone: 'warning' });
			break;
		case 'steam':
			if (info.server_type && info.server_type !== 'd')
				items.push({
					key: 'servertype',
					icon: 'server',
					label: { l: 'Listen server', p: 'Proxy' }[info.server_type] ?? info.server_type,
					tone: 'neutral'
				});
			if (info.platform)
				items.push({
					key: 'platform',
					icon: 'monitor',
					label: { l: 'Linux', w: 'Windows', m: 'macOS' }[info.platform] ?? info.platform,
					tone: 'neutral',
					title: 'Operating system of the server'
				});
			break;
	}
	return items;
}

function latencyTile(info: LiveServerInfo): Tile {
	return {
		key: 'latency',
		icon: 'zap',
		title: 'Latency',
		value: info.latency != null ? `${Math.trunc(info.latency)} ms` : null,
		tone: 'warning'
	};
}

function versionTile(info: LiveServerInfo): Tile {
	return { key: 'version', icon: 'tag', title: 'Version', value: info.version ?? null };
}

function mapTile(info: LiveServerInfo): Tile {
	return {
		key: 'map',
		icon: 'map',
		title: 'Map',
		value: info.map_name ?? null,
		subtitle: info.game_mode ?? undefined,
		tone: 'success'
	};
}

/** "1 hour, 5 minutes and 41 seconds" (Factorio /time) -> "1h 5m 41s". */
function compactDuration(text: string | null | undefined): string | null {
	if (!text) return null;
	const parts = [...text.matchAll(/(\d+)\s*(day|hour|minute|second)/g)].map(
		([, n, unit]) => `${n}${unit[0]}`
	);
	return parts.length ? parts.join(' ') : text;
}

function hours(seconds: number | null | undefined): string | null {
	if (seconds == null) return null;
	const h = Math.floor(seconds / 3600);
	const m = Math.floor((seconds % 3600) / 60);
	return h ? `${h}h ${m}m` : `${m}m`;
}

/**
 * Three headline tiles next to the player count, chosen per game so the row is always full and
 * always shows what matters most for that game.
 */
export function overviewTiles(info: LiveServerInfo, game: GameServerType): Tile[] {
	switch (info.kind) {
		case 'factorio': {
			const evolution = Object.values(info.evolution ?? {});
			return [
				{ key: 'time', icon: 'hourglass', title: 'Game time', value: compactDuration(info.game_time), tone: 'warning' },
				versionTile(info),
				{
					key: 'evolution',
					icon: 'flask',
					title: 'Evolution',
					value: evolution.length ? `${(Math.max(...evolution) * 100).toFixed(1)}%` : null,
					tone: 'danger'
				}
			];
		}
		case 'satisfactory':
			return [
				{ key: 'tier', icon: 'layers', title: 'Tech tier', value: info.tech_tier != null ? String(info.tech_tier) : null, tone: 'accent' },
				{ key: 'phase', icon: 'flask', title: 'Game phase', value: info.game_phase ?? null, tone: 'success' },
				{ key: 'playtime', icon: 'hourglass', title: 'Play time', value: hours(info.total_game_duration), tone: 'warning' }
			];
		case 'ark':
			return [
				{ key: 'day', icon: 'calendar', title: 'In-game day', value: info.day_time ?? null, tone: 'warning' },
				mapTile(info),
				versionTile(info)
			];
		case 'minecraft':
			if (game === GameServerType.MinecraftBedrock || info.edition === 'bedrock')
				return [latencyTile(info), versionTile(info), mapTile(info)];
			return [
				latencyTile(info),
				versionTile(info),
				{
					key: 'mods',
					icon: 'puzzle',
					title: 'Mods',
					value: info.mods ? String(info.mods.length) : 'Vanilla',
					tone: info.mods?.length ? 'accent' : 'neutral'
				}
			];
		case 'steam':
		default:
			return [latencyTile(info), mapTile(info), versionTile(info)];
	}
}

// ---- Host stats formatting ----------------------------------------------------------------------

export function formatBytes(bytes: number | null | undefined): string | null {
	if (bytes == null) return null;
	const units = ['B', 'KB', 'MB', 'GB', 'TB'];
	let value = bytes;
	let unit = 0;
	while (value >= 1024 && unit < units.length - 1) {
		value /= 1024;
		unit++;
	}
	return `${value < 10 && unit > 0 ? value.toFixed(1) : Math.round(value)} ${units[unit]}`;
}

export function formatUptime(startedAt: string | null | undefined): string | null {
	if (!startedAt) return null;
	const seconds = Math.max(0, (Date.now() - new Date(startedAt).getTime()) / 1000);
	const d = Math.floor(seconds / 86400);
	const h = Math.floor((seconds % 86400) / 3600);
	const m = Math.floor((seconds % 3600) / 60);
	if (d) return `${d}d ${h}h`;
	if (h) return `${h}h ${m}m`;
	return `${m}m`;
}

export function hostTone(state: string | undefined): Tone {
	switch (state) {
		case 'running':
			return 'success';
		case 'restarting':
		case 'created':
		case 'paused':
			return 'warning';
		case 'exited':
		case 'dead':
		case 'missing':
			return 'danger';
		default:
			return 'neutral';
	}
}

export function hostStateLabel(stats: HostStats | undefined): string {
	if (!stats) return 'Unknown';
	switch (stats.state) {
		case 'running':
			return 'Running';
		case 'exited':
			return 'Stopped';
		case 'missing':
			return 'Container missing';
		default:
			return stats.state.charAt(0).toUpperCase() + stats.state.slice(1);
	}
}
