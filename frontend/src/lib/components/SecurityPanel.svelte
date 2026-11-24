<script lang="ts">
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { api } from '$lib/api/ApiService';
	import type { SecurityInfo } from '$lib/api/Api';
	import { logoutEverywhere, session } from '$lib/auth.svelte';
	import { confirmDialog } from '$lib/confirm.svelte';
	import CodeInput from './CodeInput.svelte';
	import Icon from './Icon.svelte';
	import KnownUser from './KnownUser.svelte';
	import RecoveryCodes from './RecoveryCodes.svelte';

	let info = $state<SecurityInfo | null>(null);
	let error = $state<string | null>(null);
	let renewing = $state(false);
	let code = $state('');
	let busy = $state(false);
	let codes = $state<string[] | null>(null);

	function detail(err: unknown, fallback: string): string {
		const d = (err as { error?: { detail?: unknown } })?.error?.detail;
		return typeof d === 'string' ? d : fallback;
	}

	async function load() {
		try {
			info = (await api.security.getSecurity()).data;
		} catch (err) {
			error = detail(err, 'Could not load the sign-in settings.');
		}
	}

	async function renew(event: SubmitEvent) {
		event.preventDefault();
		if (busy) return;
		busy = true;
		error = null;
		try {
			codes = (await api.recoveryCodes.renewRecoveryCodes({ code: code.trim() })).data
				.recovery_codes;
			renewing = false;
			code = '';
			await load();
		} catch (err) {
			code = '';
			error = detail(err, 'Could not create new recovery codes.');
		} finally {
			busy = false;
		}
	}

	async function signOutEverywhere() {
		const go = await confirmDialog({
			title: 'Sign out everywhere',
			message:
				'End every session of this account, on all devices and in this browser? Signing in again needs your password and a code.',
			confirmLabel: 'Sign out everywhere',
			tone: 'danger'
		});
		if (!go) return;
		try {
			await logoutEverywhere();
			goto(resolve('/login'), { replaceState: true });
		} catch (err) {
			error = detail(err, 'Could not end the sessions.');
		}
	}

	$effect(() => {
		load();
	});
</script>

<section class="card space-y-4 p-6">
	<h2 class="section-title"><Icon name="lock" size={16} />Sign-in</h2>

	{#if error}
		<p class="notice tone-bad"><Icon name="alert" size={16} class="mt-0.5 shrink-0" />{error}</p>
	{/if}

	{#if info}
		<dl class="grid grid-cols-[auto_1fr] gap-x-6 gap-y-2 text-sm">
			<dt class="text-ink-2">Two-factor</dt>
			<dd>
				{#if info.totp_enabled}
					<span class="inline-flex items-center gap-1.5 text-ok"
						><Icon name="check" size={14} />Authenticator app</span
					>
				{:else}
					<span class="text-warn">Not set up; the next sign-in sets it up</span>
				{/if}
			</dd>
			<dt class="text-ink-2">Recovery codes</dt>
			<dd class={info.recovery_codes_left < 3 ? 'text-warn' : ''}>
				{info.recovery_codes_left} unused
			</dd>
			<dt class="text-ink-2">Sessions</dt>
			<dd>End after {info.session_hours} hours</dd>
		</dl>

		{#if codes}
			<div class="space-y-2">
				<p class="text-sm">New recovery codes. The old ones no longer work. Save these now:</p>
				<RecoveryCodes {codes} username={session.username ?? 'user'} />
				<button type="button" class="btn-ghost btn-sm" onclick={() => (codes = null)}>Done</button>
			</div>
		{:else if renewing}
			<form class="space-y-3" onsubmit={renew}>
				<KnownUser username={session.username ?? ''} />
				<p class="label">Code from your authenticator app</p>
				<CodeInput bind:value={code} id="renew-code" disabled={busy} autofocus />
				<div class="flex gap-2">
					<button class="btn-primary btn-sm" type="submit" disabled={busy || code.length < 6}
						>{busy ? 'Creating…' : 'Create new codes'}</button
					>
					<button
						class="btn-ghost btn-sm"
						type="button"
						onclick={() => ((renewing = false), (code = ''))}>Cancel</button
					>
				</div>
			</form>
		{/if}

		<div class="flex flex-wrap gap-2 border-t border-line pt-4">
			{#if info.totp_enabled && !renewing && !codes}
				<button type="button" class="btn-outline btn-sm" onclick={() => (renewing = true)}>
					<Icon name="key" size={14} />New recovery codes
				</button>
			{/if}
			<button type="button" class="btn-outline btn-sm" onclick={signOutEverywhere}>
				<Icon name="x" size={14} />Sign out everywhere
			</button>
		</div>
		<p class="hint">
			Lost the authenticator and the recovery codes? On the host, <code class="font-mono"
				>make reset-2fa U={session.username}</code
			>
			removes it; the next sign-in sets up a new one. New users:
			<code class="font-mono">make invite U=name</code>.
		</p>
	{/if}
</section>
