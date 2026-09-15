import adapter from '@sveltejs/adapter-node';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

/** @type {import('@sveltejs/kit').Config} */
const config = {
	preprocess: vitePreprocess(),

	kit: {
		// Node server that serves the client-only app (ssr is off in the root layout) and forwards
		// backend requests to BACKEND_URL (src/hooks.server.ts), so the browser only talks to one origin.
		adapter: adapter({ out: 'build' })
	}
};

export default config;
