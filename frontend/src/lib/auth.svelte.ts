import { api } from '$lib/api/ApiService';

const TOKEN_KEY = 'gamefleet:token';

/**
 * Login state. Without a token the dashboard runs in public mode: visitors see the servers flagged public
 * and none of the controls. The bearer token lives in localStorage; `authEnabled`, `admin` and `dev` mirror
 * what the backend reports (without configured users, only a development backend makes everyone an admin).
 */
export const session = $state<{
	token: string | null;
	username: string | null;
	authEnabled: boolean;
	/** May see and change everything: logged in, or a development backend without users. */
	admin: boolean;
	/** The backend runs with GAMEFLEET_ENV=dev. */
	dev: boolean;
	/** Set once /api/auth/me has answered; the layout waits for it before rendering pages. */
	checked: boolean;
}>({
	token: null,
	username: null,
	authEnabled: true,
	admin: false,
	dev: false,
	checked: false
});

/** Whether the viewer may see and change everything. */
export const loggedIn = () => session.admin;

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
	session.admin = false;
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
		session.admin = info.admin;
		session.dev = info.dev;
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
	session.admin = true;
	try {
		localStorage.setItem(TOKEN_KEY, result.token);
	} catch {
		// See clearSession.
	}
}

export function logout() {
	clearSession();
}
