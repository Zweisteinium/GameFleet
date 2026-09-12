<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { resolve } from '$app/paths';
	import { login, loggedIn } from '$lib/auth.svelte';
	import Icon from '$lib/components/Icon.svelte';

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
			// `next` is a same-origin path the layout guard put there; anything else falls back to the dashboard.
			const target = next && next.startsWith('/') && !next.startsWith('//') ? next : resolve('/main');
			// eslint-disable-next-line svelte/no-navigation-without-resolve -- already a resolved in-app path
			goto(target, { replaceState: true });
		} catch (err) {
			const status = (err as { status?: number })?.status;
			error =
				status === 401
					? 'Wrong username or password.'
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
	<form class="card rise w-full max-w-sm p-7" onsubmit={submit}>
		<div class="mb-6 flex items-center gap-3">
			<span
				class="grid h-11 w-11 place-items-center rounded-2xl text-white shadow-card"
				style="background: linear-gradient(135deg, var(--accent), var(--accent-2))"
			>
				<Icon name="rocket" size={20} />
			</span>
			<div>
				<h1 class="font-display text-xl font-semibold tracking-tight">Sign in</h1>
				<p class="text-ink-2 text-sm">to your GameFleet dashboard</p>
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
			<p
				class="mt-4 flex items-center gap-2 rounded-xl bg-rose-500/10 px-3 py-2 text-sm text-rose-700 dark:text-rose-400"
			>
				<Icon name="alert" size={16} />{error}
			</p>
		{/if}

		<button type="submit" class="btn-primary mt-6 w-full" disabled={busy}>
			{busy ? 'Signing in…' : 'Sign in'}
		</button>
		<p class="text-ink-3 mt-4 text-center text-xs">
			Users are configured with <code class="font-mono">GAMEFLEET_USERS</code> on the backend.
		</p>
	</form>
</div>
