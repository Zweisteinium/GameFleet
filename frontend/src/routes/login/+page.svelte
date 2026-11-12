<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { resolve } from '$app/paths';
	import type { LoginResult } from '$lib/api/Api';
	import { login, loggedIn, secondFactor, signIn } from '$lib/auth.svelte';
	import Icon from '$lib/components/Icon.svelte';
	import Logo from '$lib/components/Logo.svelte';
	import QrCode from '$lib/components/QrCode.svelte';
	import RecoveryCodes from '$lib/components/RecoveryCodes.svelte';

	/** password → code (authenticator set up) or enroll (set one up) → recovery (after enrolling). */
	type Step = 'password' | 'code' | 'enroll' | 'recovery';

	let step = $state<Step>('password');
	let username = $state('');
	let password = $state('');
	let code = $state('');
	let challenge = $state<LoginResult | null>(null);
	let done = $state<LoginResult | null>(null);
	let saved = $state(false);
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
		if (!challenge?.challenge) return;
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

	/** The base32 key in groups of four, easier to type into an app by hand. */
	const groupedSecret = $derived((challenge?.totp_secret ?? '').replace(/(.{4})/g, '$1 ').trim());
</script>

<svelte:head>
	<title>Sign in · GameFleet</title>
</svelte:head>

{#snippet header(title: string, subtitle: string)}
	<div class="mb-6 flex items-center gap-3">
		<Logo size={26} class="text-accent" />
		<div>
			<h1 class="text-lg font-semibold">{title}</h1>
			<p class="text-sm text-ink-2">{subtitle}</p>
		</div>
	</div>
{/snippet}

{#snippet codeField(label: string, hint: string)}
	<div>
		<label class="label" for="login-code">{label}</label>
		<input
			id="login-code"
			class="input text-center font-mono text-lg tracking-[0.3em]"
			type="text"
			inputmode={step === 'enroll' ? 'numeric' : 'text'}
			autocomplete="one-time-code"
			maxlength="20"
			bind:value={code}
			required
			{@attach (input) => input.focus()}
		/>
		<p class="hint mt-1.5">{hint}</p>
	</div>
{/snippet}

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
			{@render header('Sign in', 'to manage your servers')}
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
			{@render failure()}
			<button type="submit" class="btn-primary mt-6 w-full" disabled={busy}>
				{busy ? 'Checking…' : 'Continue'}
			</button>
			<p class="hint mt-4 text-center">
				Users are configured with <code class="font-mono">GAMEFLEET_USERS</code> on the backend.
			</p>
		</form>
	{:else if step === 'code'}
		<form class="card rise w-full max-w-sm p-6" onsubmit={submitCode}>
			{@render header('Two-factor sign-in', `Signing in as ${challenge?.username}`)}
			{@render codeField(
				'Code from your authenticator app',
				'Lost the app? Enter one of your recovery codes instead.'
			)}
			{@render failure()}
			<button type="submit" class="btn-primary mt-6 w-full" disabled={busy || !code.trim()}>
				{busy ? 'Signing in…' : 'Sign in'}
			</button>
			<button
				type="button"
				class="btn-ghost mt-2 w-full"
				onclick={() => restart('')}
				disabled={busy}
			>
				Back
			</button>
		</form>
	{:else if step === 'enroll'}
		<form class="card rise w-full max-w-md p-6" onsubmit={submitCode}>
			{@render header('Set up two-factor sign-in', `Required for ${challenge?.username}`)}
			<ol class="space-y-4 text-sm">
				<li>
					<p class="mb-3">
						1. Scan this code with an authenticator app (Aegis, Google Authenticator, 1Password,
						Bitwarden …).
					</p>
					<div class="flex flex-col items-center gap-3">
						{#if challenge?.totp_uri}<QrCode
								value={challenge.totp_uri}
								label="QR code for the authenticator app"
							/>{/if}
						<details class="w-full text-center">
							<summary class="hint">Can't scan it? Enter the key by hand</summary>
							<p class="mt-2 font-mono text-sm break-all select-all">{groupedSecret}</p>
							<p class="hint mt-1">Time-based, 6 digits, 30 seconds.</p>
						</details>
					</div>
				</li>
				<li>
					<p class="mb-3">2. Enter the 6-digit code the app shows to confirm it works.</p>
					{@render codeField('Code', 'This code finishes the setup and signs you in.')}
				</li>
			</ol>
			{@render failure()}
			<button type="submit" class="btn-primary mt-6 w-full" disabled={busy || !code.trim()}>
				{busy ? 'Checking…' : 'Confirm and sign in'}
			</button>
		</form>
	{:else if step === 'recovery' && done}
		<div class="card rise w-full max-w-md p-6">
			{@render header('Save your recovery codes', 'Shown only this once')}
			<p class="mb-4 text-sm text-ink-2">
				If you lose your phone, each of these codes signs you in once instead of the app. Keep them
				somewhere safe, apart from your password.
			</p>
			<RecoveryCodes codes={done.recovery_codes ?? []} username={done.username} />
			<label class="mt-5 flex items-center gap-2.5 text-sm">
				<input type="checkbox" class="h-4 w-4 accent-accent" bind:checked={saved} />
				I have saved these codes
			</label>
			<button
				type="button"
				class="btn-primary mt-5 w-full"
				disabled={!saved}
				onclick={() => done && finish(done)}
			>
				Continue to GameFleet
			</button>
		</div>
	{/if}
</div>
