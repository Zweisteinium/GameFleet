import type { Handle } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';

// Paths served by the backend; the frontend proxies them so the browser needs no backend address.
export const BACKEND_PATHS = ['/api/', '/swagger', '/openapi.json'];

const BACKEND_URL = (env.BACKEND_URL || 'http://localhost:8000').replace(/\/$/, '');

export const handle: Handle = async ({ event, resolve }) => {
	const { pathname, search } = event.url;
	if (!BACKEND_PATHS.some((p) => pathname === p || pathname.startsWith(p))) return resolve(event);

	const headers = new Headers(event.request.headers);
	// Hop-by-hop headers belong to the incoming connection; Node's fetch refuses some of them
	// (curl sends "Expect: 100-continue" with large uploads).
	for (const name of ['host', 'expect', 'connection', 'keep-alive', 'transfer-encoding', 'upgrade'])
		headers.delete(name);
	let response: Response;
	try {
		response = await fetch(BACKEND_URL + pathname + search, {
			method: event.request.method,
			headers,
			body: event.request.body,
			// @ts-expect-error Node's fetch needs duplex for streamed request bodies.
			duplex: 'half',
			redirect: 'manual'
		});
	} catch (error) {
		console.error(`Proxy ${event.request.method} ${pathname} failed:`, (error as Error).cause ?? error);
		return new Response(JSON.stringify({ detail: 'The backend could not be reached.' }), {
			status: 502,
			headers: { 'content-type': 'application/json' }
		});
	}
	// fetch already decoded the body, so the encoding headers no longer match it.
	const out = new Headers(response.headers);
	out.delete('content-encoding');
	out.delete('content-length');
	return new Response(response.body, { status: response.status, headers: out });
};
