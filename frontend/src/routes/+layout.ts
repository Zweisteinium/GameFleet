import { checkSession } from '$lib/auth.svelte';

// Static SPA: everything renders in the browser, and no page renders before the session is known.
export const ssr = false;
export const prerender = false;

export const load = async () => {
	await checkSession();
};
