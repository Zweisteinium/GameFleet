import type { Handle, RequestEvent } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';
import { BlockList, isIP } from 'node:net';

// Paths served by the backend; the frontend proxies them so the browser needs no backend address.
export const BACKEND_PATHS = ['/api/', '/swagger', '/openapi.json'];

const BACKEND_URL = (env.BACKEND_URL || 'http://localhost:8000').replace(/\/$/, '');

// Sent with every page and proxied response: no framing, no MIME sniffing, no referrer leakage.
const SECURITY_HEADERS: Record<string, string> = {
	'X-Content-Type-Options': 'nosniff',
	'X-Frame-Options': 'DENY',
	'Referrer-Policy': 'same-origin',
	'Permissions-Policy': 'camera=(), microphone=(), geolocation=()'
};

// Reverse proxies in front of this server (TRUSTED_PROXIES: addresses or CIDR ranges, comma-separated).
// Their X-Forwarded-For names the browser; from anyone else the header is ignored and the connection counts.
const TRUSTED = new BlockList();
for (const entry of (env.TRUSTED_PROXIES ?? '').split(',')) {
	const [address, bits] = entry.trim().split('/');
	const type = isIP(address) === 6 ? 'ipv6' : isIP(address) === 4 ? 'ipv4' : null;
	if (!type) continue;
	if (bits === undefined) TRUSTED.addAddress(address, type);
	else TRUSTED.addSubnet(address, Number(bits), type);
}

const plain = (ip: string) => ip.trim().replace(/^::ffff:(?=\d+\.\d+\.\d+\.\d+$)/i, '');
const trusted = (ip: string) =>
	isIP(ip) === 4 ? TRUSTED.check(ip, 'ipv4') : isIP(ip) === 6 ? TRUSTED.check(ip, 'ipv6') : false;

/** The browser's address: the connection's, or through trusted proxies the last hop they did not add. */
function clientAddress(event: RequestEvent): string {
	let peer: string;
	try {
		peer = plain(event.getClientAddress());
	} catch {
		return '';
	}
	if (!trusted(peer)) return peer;
	const hops = (event.request.headers.get('x-forwarded-for') ?? '').split(',').map(plain);
	for (let i = hops.length - 1; i >= 0; i--) {
		if (!isIP(hops[i])) break;
		if (!trusted(hops[i])) return hops[i];
	}
	return peer;
}

function secured(response: Response): Response {
	for (const [name, value] of Object.entries(SECURITY_HEADERS)) response.headers.set(name, value);
	return response;
}

export const handle: Handle = async ({ event, resolve }) => {
	const { pathname, search } = event.url;
	if (!BACKEND_PATHS.some((p) => pathname === p || pathname.startsWith(p)))
		return secured(await resolve(event));

	const headers = new Headers(event.request.headers);
	// Hop-by-hop headers belong to the incoming connection; Node's fetch refuses some of them
	// (curl sends "Expect: 100-continue" with large uploads).
	for (const name of ['host', 'expect', 'connection', 'keep-alive', 'transfer-encoding', 'upgrade'])
		headers.delete(name);
	// The backend limits sign-in attempts per browser address and believes this header only from here.
	headers.delete('x-gamefleet-client');
	const client = clientAddress(event);
	if (client) headers.set('x-gamefleet-client', client);
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
		console.error(
			`Proxy ${event.request.method} ${pathname} failed:`,
			(error as Error).cause ?? error
		);
		return new Response(JSON.stringify({ detail: 'The backend could not be reached.' }), {
			status: 502,
			headers: { 'content-type': 'application/json' }
		});
	}
	// fetch already decoded the body, so the encoding headers no longer match it.
	const out = new Headers(response.headers);
	out.delete('content-encoding');
	out.delete('content-length');
	return secured(new Response(response.body, { status: response.status, headers: out }));
};
