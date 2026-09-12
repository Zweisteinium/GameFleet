import { api } from '$lib/api/ApiService';
import { ServerStatus, type HostStats } from '$lib/api/Api';
import type { LiveServerInfo } from '$lib/api/types';

const STORAGE_KEY = 'gamefleet:live';

/**
 * Shared live-info cache. Each server is queried on its own so fast servers fill in immediately
 * while slow ones are still loading; the last known result is kept across navigation and reloads.
 * Host stats (container state, CPU, memory, sizes) come from Docker for locally running servers.
 */
export const live = $state<{
	info: Record<string, LiveServerInfo>;
	pending: Record<string, boolean>;
	host: Record<string, HostStats>;
}>({
	info: {},
	pending: {},
	host: {}
});

let restored = false;

export function restoreLive() {
	if (restored) return;
	restored = true;
	try {
		live.info = JSON.parse(sessionStorage.getItem(STORAGE_KEY) ?? '{}');
	} catch {
		live.info = {};
	}
}

function persist() {
	try {
		sessionStorage.setItem(STORAGE_KEY, JSON.stringify(live.info));
	} catch {
		// Storage can be unavailable (private mode, quota); the value is only a convenience.
	}
}

export async function refreshServer(id: string): Promise<void> {
	if (live.pending[id]) return;
	live.pending[id] = true;
	try {
		live.info[id] = (await api.serverId.getServerLiveInfoById(id)).data;
	} catch (error) {
		console.error(`Failed to fetch live info for ${id}:`, error);
		live.info[id] = {
			kind: 'base',
			status: ServerStatus.Unknown,
			error_message: 'Failed to fetch live information'
		};
	} finally {
		delete live.pending[id];
		persist();
	}
}

export async function refreshServers(ids: string[]): Promise<void> {
	await Promise.all([...ids.map(refreshServer), refreshAllHostStats()]);
}

/** One request for every Docker-linked server; the backend caches samples so this is cheap. */
export async function refreshAllHostStats(): Promise<void> {
	try {
		live.host = (await api.hostStats.getAllHostStats()).data;
	} catch (error) {
		console.error('Failed to fetch host stats:', error);
	}
}

export async function refreshHostStats(id: string): Promise<void> {
	try {
		live.host[id] = (await api.serverId.getServerHostStats(id)).data;
	} catch (error) {
		console.error(`Failed to fetch host stats for ${id}:`, error);
	}
}

export function forgetServer(id: string) {
	delete live.info[id];
	delete live.host[id];
	persist();
}
