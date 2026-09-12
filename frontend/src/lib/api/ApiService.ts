import { Api } from './Api';
import { session, clearSession } from '$lib/auth.svelte';

class ApiService {
	public static GAMEFLEET_API_URL = import.meta.env.GAMEFLEET_API_URL || 'http://localhost:8000';

	private static instance: Api<unknown>;

	private constructor() {}

	public static getInstance(): Api<unknown> {
		if (!ApiService.instance) {
			ApiService.instance = new Api<unknown>({
				baseUrl: this.GAMEFLEET_API_URL,
				customFetch: async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
					const headers = new Headers(init?.headers);
					if (session.token) headers.set('Authorization', `Bearer ${session.token}`);
					const response = await fetch(input, { ...init, headers });
					// An expired or revoked token: drop it so the layout guard sends the user to the login page.
					if (response.status === 401 && session.token) clearSession();
					return response;
				}
			});
		}
		return ApiService.instance;
	}
}

export const api = ApiService.getInstance();
export const API_BASE_URL = ApiService.GAMEFLEET_API_URL;
