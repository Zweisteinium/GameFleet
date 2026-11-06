import { getContext, setContext } from 'svelte';
import type { GameServerPublic, HostStats } from '$lib/api/Api';
import type { LiveServerInfo } from '$lib/api/types';

/** What the server layout shares with its tabs: the server, its live data and the power actions. */
export interface ServerPage {
	readonly server: GameServerPublic;
	readonly liveInfo: LiveServerInfo | null;
	readonly hostStats: HostStats | undefined;
	readonly isLocal: boolean;
	readonly running: boolean;
	readonly refreshing: boolean;
	power(action: 'start' | 'stop' | 'restart'): Promise<void>;
	/** `docker compose up -d` for the server: applies a changed compose file. */
	recreate(): Promise<void>;
	refresh(): Promise<void>;
	/** Re-query a few times after the container changed. */
	settle(): void;
}

const KEY = Symbol('server-page');

export function setServerPage(page: ServerPage) {
	setContext(KEY, page);
}

export function serverPage(): ServerPage {
	return getContext<ServerPage>(KEY);
}
