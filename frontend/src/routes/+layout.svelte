<script lang="ts">
	import '../app.css';
	import favicon from '$lib/assets/favicon.svg';
	import { page } from '$app/state';
	import ThemeToggle from '$lib/components/ThemeToggle.svelte';
	import Icon from '$lib/components/Icon.svelte';
	import { API_BASE_URL } from '$lib/api/ApiService';

	let { children } = $props();
</script>

<svelte:head>
	<link rel="icon" href={favicon} />
</svelte:head>

<div class="relative min-h-screen">
	<div class="bg-grid pointer-events-none absolute inset-x-0 top-0 h-72"></div>

	<header class="relative z-10">
		<div class="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6">
			<a href="/main" class="flex items-center gap-2.5" aria-label="GameFleet home">
				<span
					class="grid h-9 w-9 place-items-center rounded-xl text-white shadow-card"
					style="background: linear-gradient(135deg, var(--accent), var(--accent-2))"
				>
					<Icon name="rocket" size={18} />
				</span>
				<span class="font-display text-lg font-semibold tracking-tight">GameFleet</span>
			</a>

			<nav class="flex items-center gap-1">
				<a
					href="/main"
					class="btn-ghost h-9 px-3 text-sm"
					aria-current={page.url.pathname.startsWith('/main') ? 'page' : undefined}
				>
					Servers
				</a>
				<a
					href="{API_BASE_URL}/swagger"
					target="_blank"
					rel="noreferrer"
					class="btn-ghost hidden h-9 px-3 text-sm sm:inline-flex"
				>
					API
				</a>
				<ThemeToggle />
			</nav>
		</div>
	</header>

	<main class="relative z-10 mx-auto max-w-7xl px-4 pb-16 sm:px-6">
		{@render children?.()}
	</main>
</div>
