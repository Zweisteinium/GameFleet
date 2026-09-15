import tailwindcss from '@tailwindcss/vite';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

// The dev server forwards backend paths like the Node server does (src/hooks.server.ts).
const backend = process.env.BACKEND_URL || 'http://localhost:8000';

export default defineConfig({
	plugins: [tailwindcss(), sveltekit()],
	server: {
		proxy: { '/api': backend, '/swagger': backend, '/openapi.json': backend }
	}
});
