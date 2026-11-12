import adapter from '@sveltejs/adapter-node';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

/** @type {import('@sveltejs/kit').Config} */
const config = {
	preprocess: vitePreprocess(),

	kit: {
		// Node server that serves the client-only app (ssr is off in the root layout) and forwards
		// backend requests to BACKEND_URL (src/hooks.server.ts), so the browser only talks to one origin.
		adapter: adapter({ out: 'build' }),
		// Content-Security-Policy, sent with every page. SvelteKit adds hashes for its own inline bootstrap
		// script, so injected scripts do not run: a cross-site scripting bug cannot read the session token.
		// Styles stay 'unsafe-inline' for style attributes (MOTD colours, bars); they cannot run code.
		csp: {
			mode: 'hash',
			directives: {
				'default-src': ['self'],
				'script-src': ['self'],
				'style-src': ['self', 'unsafe-inline', 'https://fonts.googleapis.com'],
				'font-src': ['self', 'https://fonts.gstatic.com'],
				// Modpack icons and game art come from other hosts (Modrinth, Steam); server favicons are data: URLs.
				'img-src': ['self', 'data:', 'https:'],
				'connect-src': ['self'],
				'object-src': ['none'],
				'base-uri': ['self'],
				'form-action': ['self'],
				'frame-ancestors': ['none']
			}
		}
	}
};

export default config;
