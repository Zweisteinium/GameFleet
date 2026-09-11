import { Api } from './Api';

class ApiService {
	public static GAMEFLEET_API_URL = import.meta.env.GAMEFLEET_API_URL || 'http://localhost:8000';
	// public static LOGIN_URL = this.GAMEFLEET_API_URL + '/api/auth/login'

	private static instance: Api<unknown>;

	private constructor() {}

	public static getInstance(): Api<unknown> {
		if (!ApiService.instance) {
			const API_BASE_URL = this.GAMEFLEET_API_URL;
			ApiService.instance = new Api<unknown>({
				baseUrl: API_BASE_URL,
				customFetch: (input: RequestInfo | URL, init?: RequestInit): Promise<Response> =>
					fetch(input, {
						...init
						// credentials: 'include'
					})
			});
		}
		return ApiService.instance;
	}
}

export const api = ApiService.getInstance();
export const API_BASE_URL = ApiService.GAMEFLEET_API_URL;
// export const apiLoginUrl = ApiService.LOGIN_URL
