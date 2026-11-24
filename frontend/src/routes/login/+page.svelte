<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { resolve } from '$app/paths';
	import type { LoginResult } from '$lib/api/Api';
	import { login, loggedIn, secondFactor, signIn } from '$lib/auth.svelte';
	import AuthenticatorSetup from '$lib/components/AuthenticatorSetup.svelte';
	import AuthHeader from '$lib/components/AuthHeader.svelte';
	import CodeInput from '$lib/components/CodeInput.svelte';
	import Icon from '$lib/components/Icon.svelte';
	import KnownUser from '$lib/components/KnownUser.svelte';
	import RecoveryStep from '$lib/components/RecoveryStep.svelte';

	/** password → code (authenticator set up) or enroll (set one up) → recovery (after enrolling). */
	type Step = 'password' | 'code' | 'enroll' | 'recovery';

	let step = $state<Step>('password');
	let username = $state('');
	let password = $state('');
	let code = $state('');
	let useRecovery = $state(false);
	let challenge = $state<LoginResult | null>(null);
	let done = $state<LoginResult | null>(null);
	let error = $state<string | null>(null);
	let busy = $state(false);

	$effect(() => {
		if (loggedIn()) goto(resolve('/main'), { replaceState: true });
	});

	function problem(err: unknown, wrong: string): string {
		const status = (err as { status?: number })?.status;
		const detail = (err as { error?: { detail?: unknown } })?.error?.detail;
		if (status === 401 || status === 400) return typeof detail === 'string' ? detail : wrong;
		if ((status === 429 || status === 409) && typeof detail === 'string') return detail;
		return 'Could not reach the backend. Check that it is running.';
	}

	function finish(result: LoginResult) {
		signIn(result);
		const next = page.url.searchParams.get('next');
		// `next` is a same-origin path the layout put there; anything else falls back to the dashboard.
		const target = next && next.startsWith('/') && !next.startsWith('//') ? next : resolve('/main');
		// eslint-disable-next-line svelte/no-navigation-without-resolve -- already a resolved in-app path
		goto(target, { replaceState: true });
	}

	function restart(message: string) {
		step = 'password';
		challenge = null;
		code = '';
		useRecovery = false;
		password = '';
		error = message;
	}

	async function submitPassword(event: SubmitEvent) {
		event.preventDefault();
		busy = true;
		error = null;
		try {
			const result = await login(username.trim(), password);
			challenge = result;
			code = '';
			step = result.status === 'enroll' ? 'enroll' : 'code';
		} catch (err) {
			error = problem(err, 'Wrong username or password.');
		} finally {
			busy = false;
		}
	}

	async function submitCode(event: SubmitEvent) {
		event.preventDefault();
		// The code field submits by itself once complete; a request already under way wins.
		if (!challenge?.challenge || busy) return;
		busy = true;
		error = null;
		try {
			const result = await secondFactor(challenge.challenge, code.trim());
			if (step === 'enroll' && result.recovery_codes?.length) {
				// Show the recovery codes once before the session starts (the layout leaves this page then).
				done = result;
				step = 'recovery';
			} else finish(result);
		} catch (err) {
			const status = (err as { status?: number })?.status;
			const message = problem(err, 'Wrong code.');
			code = '';
			// An expired challenge, or an authenticator set up meanwhile, needs the password again.
			if (status === 409 || (status === 401 && message.includes('expired'))) restart(message);
			else error = message;
		} finally {
			busy = false;
		}
	}

	function toggleRecovery() {
		useRecovery = !useRecovery;
		code = '';
		error = null;
	}
</script>

<svelte:head>
	<title>Sign in · GameFleet</title>
</svelte:head>

{#snippet failure()}
	{#if error}
		<p class="notice tone-bad mt-4">
			<Icon name="alert" size={16} class="mt-0.5 shrink-0" />{error}
		</p>
	{/if}
{/snippet}

<div class="grid min-h-[70vh] place-items-center py-10">
	{#if step === 'password'}
		<form class="card rise w-full max-w-sm p-6" onsubmit={submitPassword}>
			<AuthHeader title="Sign in" subtitle="to manage your servers" />
			<div class="space-y-4">
				<div>
					<label class="label" for="login-user">Username</label>
					<input
						id="login-user"
						name="username"
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
						name="password"
						class="input"
						type="password"
						bind:value={password}
						required
						autocomplete="current-password"
					/>
				</div>
			</div>
			{@render failure()}
			<button type="submit" class="btn-primary mt-6 w-full" disabled={busy}>
				{busy ? 'Checking…' : 'Continue'}
			</button>
		</form>
	{:else if step === 'code' && challenge}
		<form class="card rise w-full max-w-sm p-6" onsubmit={submitCode}>
			<KnownUser username={challenge.username} />
			<AuthHeader title="Two-factor sign-in" subtitle={`Signing in as ${challenge.username}`} />
			{#if useRecovery}
				<label class="label" for="recovery-code">Recovery code</label>
				<input
					id="recovery-code"
					class="input font-mono tracking-wider"
					type="text"
					autocomplete="off"
					autocapitalize="off"
					spellcheck="false"
					data-bwignore
					placeholder="xxxxx-xxxxx"
					maxlength="20"
					bind:value={code}
					required
					{@attach (input) => input.focus()}
				/>
				<p class="hint mt-1.5">Each recovery code works once.</p>
			{:else}
				<p class="label mb-3 text-center">Code from your authenticator app</p>
				<div class="flex justify-center">
					<CodeInput bind:value={code} disabled={busy} autofocus />
				</div>
			{/if}
			{@render failure()}
			<button
				type="submit"
				class="btn-primary mt-6 w-full"
				disabled={busy || (useRecovery ? !code.trim() : code.length < 6)}
			>
				{busy ? 'Signing in…' : 'Sign in'}
			</button>
			<div class="mt-3 flex items-center justify-between">
				<button type="button" class="btn-ghost btn-sm" onclick={() => restart('')} disabled={busy}
					>Back</button
				>
				<button type="button" class="btn-ghost btn-sm" onclick={toggleRecovery} disabled={busy}>
					{useRecovery ? 'Use the authenticator app' : 'Use a recovery code'}
				</button>
			</div>
		</form>
	{:else if step === 'enroll' && challenge}
		<form class="card rise w-full max-w-md p-6" onsubmit={submitCode}>
			<KnownUser username={challenge.username} />
			<AuthHeader
				title="Set up two-factor sign-in"
				subtitle={`Required for ${challenge.username}`}
			/>
			<AuthenticatorSetup {challenge} bind:code disabled={busy} />
			{@render failure()}
			<button type="submit" class="btn-primary mt-6 w-full" disabled={busy || code.length < 6}>
				{busy ? 'Checking…' : 'Confirm and sign in'}
			</button>
		</form>
	{:else if step === 'recovery' && done}
		<div class="card rise w-full max-w-md p-6">
			<AuthHeader title="Save your recovery codes" subtitle="Shown only this once" />
			<RecoveryStep
				codes={done.recovery_codes ?? []}
				username={done.username}
				onfinish={() => done && finish(done)}
			/>
		</div>
	{/if}
</div>
