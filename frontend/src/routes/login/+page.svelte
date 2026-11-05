<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { resolve } from '$app/paths';
	import { login, loggedIn } from '$lib/auth.svelte';
	import Icon from '$lib/components/Icon.svelte';
	import Logo from '$lib/components/Logo.svelte';

	let username = $state('');
	let password = $state('');
	let error = $state<string | null>(null);
	let busy = $state(false);

	$effect(() => {
		if (loggedIn()) goto(resolve('/main'), { replaceState: true });
	});

	async function submit(event: SubmitEvent) {
		event.preventDefault();
		busy = true;
		error = null;
		try {
			await login(username.trim(), password);
			const next = page.url.searchParams.get('next');
			// `next` is a same-origin path the layout put there; anything else falls back to the dashboard.
			const target = next && next.startsWith('/') && !next.startsWith('//') ? next : resolve('/main');
			// eslint-disable-next-line svelte/no-navigation-without-resolve -- already a resolved in-app path
			goto(target, { replaceState: true });
		} catch (err) {
			const status = (err as { status?: number })?.status;
			error =
				status === 401
					? 'Wrong username or password.'
					: status === 429
						? 'Too many attempts. Wait a few minutes and try again.'
						: 'Could not reach the backend. Check that it is running.';
		} finally {
			busy = false;
		}
	}
</script>

<svelte:head>
	<title>Sign in · GameFleet</title>
</svelte:head>

<div class="grid min-h-[70vh] place-items-center py-10">
	<form class="card rise w-full max-w-sm p-6" onsubmit={submit}>
		<div class="mb-6 flex items-center gap-3">
			<Logo size={26} class="text-accent" />
			<div>
				<h1 class="text-lg font-semibold">Sign in</h1>
				<p class="text-ink-2 text-sm">to manage your servers</p>
			</div>
		</div>

		<div class="space-y-4">
			<div>
				<label class="label" for="login-user">Username</label>
				<input
					id="login-user"
					class="input"
					type="text"
					bind:value={username}
					required
					autocomplete="username"
				/>
			</div>
			<div>
				<label class="label" for="login-pass">Password</label>
				<input
					id="login-pass"
					class="input"
					type="password"
					bind:value={password}
					required
					autocomplete="current-password"
				/>
			</div>
		</div>

		{#if error}
			<p class="notice tone-bad mt-4">
				<Icon name="alert" size={16} class="mt-0.5 shrink-0" />{error}
			</p>
		{/if}

		<button type="submit" class="btn-primary mt-6 w-full" disabled={busy}>
			{busy ? 'Signing in…' : 'Sign in'}
		</button>
		<p class="hint mt-4 text-center">
			Users are configured with <code class="font-mono">GAMEFLEET_USERS</code> on the backend.
		</p>
	</form>
</div>
