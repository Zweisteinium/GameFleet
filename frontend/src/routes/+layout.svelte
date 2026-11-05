<script lang="ts">
	import '../app.css';
	import { page } from '$app/state';
	import { resolve } from '$app/paths';
	import ThemeToggle from '$lib/components/ThemeToggle.svelte';
	import Icon from '$lib/components/Icon.svelte';
	import Logo from '$lib/components/Logo.svelte';
	import ConfirmDialog from '$lib/components/ConfirmDialog.svelte';
	import { session, loggedIn, logout } from '$lib/auth.svelte';

	let { children } = $props();

	const onLoginPage = $derived(page.url.pathname.startsWith('/login'));

	// No route guard: visitors without a login get the public view of every page.
	const loginHref = $derived(
		`${resolve('/login')}?next=${encodeURIComponent(page.url.pathname + page.url.search)}`
	);

	function signOut() {
		logout();
		// A full reload drops everything the admin view had loaded.
		window.location.assign(resolve('/main'));
	}
</script>

<div class="min-h-screen">
	<header class="border-line bg-surface-1 border-b">
		<div class="mx-auto flex h-14 max-w-[90rem] items-center justify-between px-4 sm:px-6">
			<a href={resolve('/main')} class="flex items-center gap-2.5" aria-label="GameFleet home">
				<Logo size={22} class="text-accent" />
				<span class="text-[15px] font-semibold tracking-tight">GameFleet</span>
			</a>

			<nav class="flex items-center gap-1">
				<a
					href={resolve('/main')}
					class="btn-ghost h-8 px-2.5 text-sm"
					aria-current={page.url.pathname.startsWith('/main') ? 'page' : undefined}
				>
					Servers
				</a>
				{#if session.dev && loggedIn()}
					<a
						href="/swagger"
						target="_blank"
						rel="external noreferrer"
						class="btn-ghost hidden h-8 px-2.5 text-sm sm:inline-flex"
					>
						API
					</a>
				{/if}
				<ThemeToggle />
				{#if session.authEnabled && session.token}
					<button class="btn-ghost h-8 px-2.5 text-sm" onclick={signOut} title="Sign out">
						<span class="hidden sm:inline">{session.username}</span>
						<Icon name="log-out" size={15} />
					</button>
				{:else if session.checked && session.authEnabled && !onLoginPage}
					<!-- eslint-disable-next-line svelte/no-navigation-without-resolve -- resolve() cannot carry a query string -->
					<a href={loginHref} class="btn-outline h-8 px-3 text-sm">Sign in</a>
				{/if}
			</nav>
		</div>
	</header>

	<main class="mx-auto max-w-[90rem] px-4 pb-16 sm:px-6">
		{#if session.checked && session.dev}
			<p class="notice tone-accent mt-4 text-xs">
				<Icon name="info" size={14} class="mt-0.5 shrink-0" />
				<span>
					Development mode: API docs are exposed and logging is verbose. Not intended for
					production; set <code class="font-mono">GAMEFLEET_DEV=false</code>.
				</span>
			</p>
		{/if}
		{#if session.checked && !session.authEnabled && !onLoginPage}
			<p class="notice tone-warn mt-4 text-xs">
				<Icon name="alert" size={14} class="mt-0.5 shrink-0" />
				<span>
					{#if session.admin}
						Login is disabled and everyone can manage this dashboard: set
						<code class="font-mono">GAMEFLEET_USERS</code> on the backend.
					{:else}
						No users are configured, so this dashboard is read-only: set
						<code class="font-mono">GAMEFLEET_USERS</code> on the backend to sign in and manage
						servers.
					{/if}
				</span>
			</p>
		{/if}
		{#if session.checked}
			{@render children?.()}
		{/if}
	</main>
</div>

<ConfirmDialog />
