import { api } from '$lib/api/ApiService';
import type { InviteInfo, LoginResult } from '$lib/api/Api';

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
	/** The backend runs with GAMEFLEET_DEV=true. */
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

/**
 * First step of signing in: the password. The answer is never a session yet but a challenge, either for a
 * code from the authenticator (`totp`) or, without one, for setting one up (`enroll`, with the QR data).
 */
export async function login(username: string, password: string): Promise<LoginResult> {
	return (await api.login.login({ username, password })).data;
}

/** Second step: a code (or recovery code) for the challenge. On success the result carries the token. */
export async function secondFactor(challenge: string, code: string): Promise<LoginResult> {
	return (await api.login.loginSecondFactor({ challenge, code })).data;
}

/** Who an invite link (the token after '#') is for; fails with 410 for a used or expired one. */
export async function getInvite(token: string): Promise<InviteInfo> {
	return (await api.invite.getInvite({ token })).data;
}

/**
 * Choose the password of an invite. The answer is an `enroll` challenge: the password takes effect together
 * with the authenticator, once `secondFactor` accepts its first code.
 */
export async function acceptInvite(token: string, password: string): Promise<LoginResult> {
	return (await api.invite.acceptInvite({ token, password })).data;
}

/** Start the session from a successful second step. */
export function signIn(result: LoginResult) {
	if (result.status !== 'ok' || !result.token) return;
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

/** End every session of this user on the server, this one included. */
export async function logoutEverywhere(): Promise<void> {
	await api.logoutAll.logoutEverywhere();
	clearSession();
}
