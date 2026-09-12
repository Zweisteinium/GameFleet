import tailwindcss from '@tailwindcss/vite';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	plugins: [tailwindcss(), sveltekit()],
	// Expose GAMEFLEET_API_URL to the client bundle (Vite only exposes VITE_* by default).
	envPrefix: ['VITE_', 'GAMEFLEET_']
});
