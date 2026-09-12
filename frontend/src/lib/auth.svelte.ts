import { api } from '$lib/api/ApiService';

const TOKEN_KEY = 'gamefleet:token';

/**
 * Login state. The bearer token lives in localStorage (the SPA and the API are separate origins, so a
 * cookie session would need cross-site cookies); `authEnabled` mirrors the backend's configuration.
 */
export const session = $state<{
	token: string | null;
	username: string | null;
	authEnabled: boolean;
	/** Set once /api/auth/me has answered; the layout waits for it before rendering pages. */
	checked: boolean;
}>({
	token: null,
	username: null,
	authEnabled: true,
	checked: false
});

export const loggedIn = () => !session.authEnabled || session.token !== null;

function loadToken(): string | null {
	try {
		return localStorage.getItem(TOKEN_KEY);
	} catch {
		return null;
	}
}

export function clearSession() {
	session.token = null;
	session.username = null;
	try {
		localStorage.removeItem(TOKEN_KEY);
	} catch {
		// Storage can be unavailable (private mode); the token is only remembered as a convenience.
	}
}

/** Validate the stored token (or learn that auth is off). Safe to call repeatedly. */
export async function checkSession(): Promise<void> {
	session.token = loadToken();
	try {
		const info = (await api.me.getSession()).data;
		session.authEnabled = info.auth_enabled;
		session.username = info.username ?? null;
	} catch {
		// 401: the token was rejected and already cleared by ApiService. Anything else (backend down)
		// keeps the token so a reload after the backend returns does not log the user out.
	} finally {
		session.checked = true;
	}
}

export async function login(username: string, password: string): Promise<void> {
	const result = (await api.login.login({ username, password })).data;
	session.token = result.token;
	session.username = result.username;
	try {
		localStorage.setItem(TOKEN_KEY, result.token);
	} catch {
		// See clearSession.
	}
}

export function logout() {
	clearSession();
}
