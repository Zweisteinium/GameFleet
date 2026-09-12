/** Tiny localStorage helper for per-browser UI preferences (filters, sort, view). */
export function loadPref<T>(key: string, fallback: T): T {
	try {
		const raw = localStorage.getItem(`gamefleet:${key}`);
		return raw ? { ...fallback, ...JSON.parse(raw) } : fallback;
	} catch {
		return fallback;
	}
}

export function savePref<T>(key: string, value: T): void {
	try {
		localStorage.setItem(`gamefleet:${key}`, JSON.stringify(value));
	} catch {
		// Storage can be unavailable (private mode, quota); the value is only a convenience.
	}
}
