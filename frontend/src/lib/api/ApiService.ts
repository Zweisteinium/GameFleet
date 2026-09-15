import { Api } from './Api';
import { session, clearSession } from '$lib/auth.svelte';

class ApiService {
	private static instance: Api<unknown>;

	private constructor() {}

	public static getInstance(): Api<unknown> {
		if (!ApiService.instance) {
			ApiService.instance = new Api<unknown>({
				// Same origin: the Node server and the Vite dev server proxy /api to the backend.
				baseUrl: '',
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
