<script lang="ts">
	import '../app.css';
	import favicon from '$lib/assets/favicon.svg';
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import ThemeToggle from '$lib/components/ThemeToggle.svelte';
	import Icon from '$lib/components/Icon.svelte';
		import { session, loggedIn, logout } from '$lib/auth.svelte';

	let { children } = $props();

	const onLoginPage = $derived(page.url.pathname.startsWith('/login'));

	// Route guard: every page except /login needs a session (or auth switched off on the backend).
	$effect(() => {
		if (session.checked && !loggedIn() && !onLoginPage) {
			const next = page.url.pathname + page.url.search;
			// eslint-disable-next-line svelte/no-navigation-without-resolve -- resolve() cannot carry a query string
			goto(`${resolve('/login')}?next=${encodeURIComponent(next)}`, { replaceState: true });
		}
	});

	function signOut() {
		logout();
		goto(resolve('/login'));
	}
</script>

<svelte:head>
	<link rel="icon" href={favicon} />
</svelte:head>

<div class="relative min-h-screen">
	<div class="page-tint pointer-events-none absolute inset-x-0 top-0 h-80"></div>

	<header class="relative z-10">
		<div class="mx-auto flex h-16 max-w-[90rem] items-center justify-between px-4 sm:px-6">
			<a href={resolve('/main')} class="flex items-center gap-2.5" aria-label="GameFleet home">
				<span
					class="grid h-9 w-9 place-items-center rounded-xl text-white shadow-card"
					style="background: linear-gradient(135deg, var(--accent), var(--accent-2))"
				>
					<Icon name="rocket" size={18} />
				</span>
				<span class="font-display text-lg font-semibold tracking-tight">GameFleet</span>
			</a>

			<nav class="flex items-center gap-1">
				{#if loggedIn()}
					<a
						href={resolve('/main')}
						class="btn-ghost h-9 px-3 text-sm"
						aria-current={page.url.pathname.startsWith('/main') ? 'page' : undefined}
					>
						Servers
					</a>
					<a
						href="/swagger"
						target="_blank"
						rel="external noreferrer"
						class="btn-ghost hidden h-9 px-3 text-sm sm:inline-flex"
					>
						API
					</a>
				{/if}
				<ThemeToggle />
				{#if session.authEnabled && session.token}
					<button class="btn-ghost h-9 px-3 text-sm" onclick={signOut} title="Sign out">
						<Icon name="user" size={15} class="text-ink-3" />
						<span class="hidden sm:inline">{session.username}</span>
						<Icon name="log-out" size={15} />
					</button>
				{/if}
			</nav>
		</div>
	</header>

	<main class="relative z-10 mx-auto max-w-[90rem] px-4 pb-16 sm:px-6">
		{#if session.checked && !session.authEnabled && !onLoginPage}
			<p
				class="mt-2 flex items-center gap-2 rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-2 text-xs text-amber-800 dark:text-amber-300"
			>
				<Icon name="alert" size={14} />
				Login is disabled: set <code class="font-mono">GAMEFLEET_USERS</code> on the backend to protect
				this dashboard.
			</p>
		{/if}
		{#if session.checked && (loggedIn() || onLoginPage)}
			{@render children?.()}
		{/if}
	</main>
</div>
