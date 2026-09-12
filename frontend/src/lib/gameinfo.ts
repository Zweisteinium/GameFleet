/** Formatting helpers for the Docker host stats shown on the cards and the server detail page. */
import type { HostStats } from '$lib/api/Api';

export type Tone = 'neutral' | 'accent' | 'success' | 'danger' | 'warning';

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
