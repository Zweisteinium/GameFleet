<script lang="ts">
	import { onMount } from 'svelte';
	import { goto, replaceState } from '$app/navigation';
	import { resolve } from '$app/paths';
	import type { InviteInfo, LoginResult } from '$lib/api/Api';
	import { acceptInvite, getInvite, secondFactor, signIn } from '$lib/auth.svelte';
	import AuthenticatorSetup from '$lib/components/AuthenticatorSetup.svelte';
	import AuthHeader from '$lib/components/AuthHeader.svelte';
	import Icon from '$lib/components/Icon.svelte';
	import KnownUser from '$lib/components/KnownUser.svelte';
	import RecoveryStep from '$lib/components/RecoveryStep.svelte';

	/** checking → password → enroll → recovery; gone for a link that cannot be used. */
	type Step = 'checking' | 'gone' | 'password' | 'enroll' | 'recovery';

	let step = $state<Step>('checking');
	let token = '';
	let invite = $state<InviteInfo | null>(null);
	let password = $state('');
	let repeat = $state('');
	let code = $state('');
	let challenge = $state<LoginResult | null>(null);
	let done = $state<LoginResult | null>(null);
	let error = $state<string | null>(null);
	let busy = $state(false);

	const status = (err: unknown) => (err as { status?: number })?.status;

	function problem(err: unknown, fallback: string): string {
		const detail = (err as { error?: { detail?: unknown } })?.error?.detail;
		const code = status(err);
		if (code && code < 500 && typeof detail === 'string') return detail;
		return code ? fallback : 'Could not reach GameFleet. Try again in a moment.';
	}

	onMount(async () => {
		// The token travels after '#', so browsers never send it to a server. Once read, it leaves the
		// address bar and the history; the link itself stays valid until the account is set up.
		token = decodeURIComponent(window.location.hash.slice(1));
		if (!token) {
			step = 'gone';
			return;
		}
		try {
			invite = await getInvite(token);
			step = 'password';
		} catch (err) {
			error = problem(err, 'This invite link cannot be used.');
			step = 'gone';
		}
		// Only now: the router refuses replaceState while the page is still being set up.
		try {
			replaceState(resolve('/invite'), {});
		} catch {
			// The address keeps the token; harmless, it only works until the account is set up.
		}
	});

	const tooShort = $derived(invite !== null && password.length < invite.password_min_length);
	const mismatch = $derived(repeat.length > 0 && repeat !== password);

	async function submitPassword(event: SubmitEvent) {
		event.preventDefault();
		if (busy || tooShort || password !== repeat) return;
		busy = true;
		error = null;
		try {
			challenge = await acceptInvite(token, password);
			code = '';
			step = 'enroll';
		} catch (err) {
			error = problem(err, 'Could not save the password.');
			if (status(err) === 410) step = 'gone';
		} finally {
			busy = false;
		}
	}

	async function submitCode(event: SubmitEvent) {
		event.preventDefault();
		if (!challenge?.challenge || busy) return;
		busy = true;
		error = null;
		try {
			done = await secondFactor(challenge.challenge, code.trim());
			step = 'recovery';
		} catch (err) {
			code = '';
			const message = problem(err, 'Wrong code.');
			if (status(err) === 410) {
				error = message;
				step = 'gone';
			} else if (status(err) === 401 && message.includes('expired')) {
				// The QR code is valid for ten minutes; choosing the password again makes a new one.
				error = 'That took too long. Choose your password again to get a new QR code.';
				step = 'password';
			} else error = message;
		} finally {
			busy = false;
		}
	}

	function finish() {
		if (!done) return;
		signIn(done);
		goto(resolve('/main'), { replaceState: true });
	}

	const until = $derived(
		invite
			? new Date(invite.expires_at * 1000).toLocaleString(undefined, {
					dateStyle: 'medium',
					timeStyle: 'short'
				})
			: ''
	);
</script>

<svelte:head>
	<title>Invite · GameFleet</title>
</svelte:head>

{#snippet failure()}
	{#if error}
		<p class="notice tone-bad mt-4">
			<Icon name="alert" size={16} class="mt-0.5 shrink-0" />{error}
		</p>
	{/if}
{/snippet}

<div class="grid min-h-[70vh] place-items-center py-10">
	{#if step === 'checking'}
		<p class="text-sm text-ink-2">Checking the invite…</p>
	{:else if step === 'gone'}
		<div class="card rise w-full max-w-sm p-6">
			<AuthHeader title="Invite not valid" subtitle="GameFleet" />
			<p class="text-sm text-ink-2">
				{error ?? 'This page needs the whole invite link, including the part after #.'} Ask whoever invited
				you for a new link.
			</p>
		</div>
	{:else if step === 'password' && invite}
		<form class="card rise w-full max-w-sm p-6" onsubmit={submitPassword}>
			<AuthHeader title="Welcome to GameFleet" subtitle="Set up your account" />
			<div class="space-y-4">
				<div>
					<label class="label" for="invite-user">Username</label>
					<input
						id="invite-user"
						name="username"
						class="input bg-surface-2 text-ink-2"
						type="text"
						value={invite.username}
						readonly
						autocomplete="username"
					/>
				</div>
				<div>
					<label class="label" for="invite-pass">Password</label>
					<input
						id="invite-pass"
						name="new-password"
						class="input"
						type="password"
						bind:value={password}
						required
						minlength={invite.password_min_length}
						autocomplete="new-password"
						{@attach (input) => input.focus()}
					/>
					<p class="hint mt-1.5">At least {invite.password_min_length} characters.</p>
				</div>
				<div>
					<label class="label" for="invite-repeat">Repeat the password</label>
					<input
						id="invite-repeat"
						name="repeat-password"
						class="input"
						type="password"
						bind:value={repeat}
						required
						autocomplete="new-password"
					/>
					{#if mismatch}<p class="mt-1.5 text-xs text-bad">The passwords differ.</p>{/if}
				</div>
			</div>
			{@render failure()}
			<button
				type="submit"
				class="btn-primary mt-6 w-full"
				disabled={busy || tooShort || password !== repeat}
			>
				{busy ? 'Saving…' : 'Continue'}
			</button>
			<p class="hint mt-4 text-center">This link works until {until}.</p>
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
				{busy ? 'Checking…' : 'Confirm'}
			</button>
		</form>
	{:else if step === 'recovery' && done}
		<div class="card rise w-full max-w-md p-6">
			<AuthHeader title="Save your recovery codes" subtitle="Shown only this once" />
			<RecoveryStep codes={done.recovery_codes ?? []} username={done.username} onfinish={finish} />
		</div>
	{/if}
</div>
