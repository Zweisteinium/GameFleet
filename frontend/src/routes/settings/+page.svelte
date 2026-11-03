<script lang="ts">
	import { onMount } from 'svelte';
	import { api } from '$lib/api/ApiService';
	import type { SettingsView } from '$lib/api/Api';
	import { loggedIn } from '$lib/auth.svelte';
	import Icon from '$lib/components/Icon.svelte';
	import LoadingSpinner from '$lib/components/LoadingSpinner.svelte';

	let settings = $state<SettingsView | null>(null);
	let cpuLimit = $state<number | null>(null);
	let saving = $state(false);
	let saved = $state(false);
	let error = $state<string | null>(null);

	function detail(err: unknown, fallback: string): string {
		const d = (err as { error?: { detail?: unknown } })?.error?.detail;
		if (Array.isArray(d)) return d.map((item) => item?.msg ?? String(item)).join('; ');
		return typeof d === 'string' ? d : fallback;
	}

	onMount(async () => {
		if (!loggedIn()) return;
		try {
			settings = (await api.getSettings()).data;
			cpuLimit = settings.cpu_limit ?? null;
		} catch (err) {
			error = detail(err, 'Could not load the settings.');
		}
	});

	async function save(event: SubmitEvent) {
		event.preventDefault();
		if (!settings) return;
		saving = true;
		saved = false;
		error = null;
		try {
			const values = { ...settings };
			delete values.servers_dir_problem;
			settings = (
				await api.updateSettings({
					...values,
					servers_dir: values.servers_dir?.trim() || null,
					public_address: values.public_address?.trim() || null,
					cpu_limit: cpuLimit || null
				})
			).data;
			saved = true;
		} catch (err) {
			error = detail(err, 'Could not save the settings.');
		} finally {
			saving = false;
		}
	}
</script>

<svelte:head><title>Settings · GameFleet</title></svelte:head>

<div class="mx-auto max-w-2xl pt-6">
	<h1 class="mb-1 font-display text-2xl font-semibold tracking-tight">Settings</h1>
	<p class="mb-6 text-sm text-ink-2">Where new servers are created and what they start with.</p>

	{#if !loggedIn()}
		<p class="card p-6 text-sm text-ink-2">Sign in to change the settings.</p>
	{:else if !settings}
		{#if error}
			<p class="card p-6 text-sm text-rose-600 dark:text-rose-400">{error}</p>
		{:else}
			<div class="py-16"><LoadingSpinner message="Loading settings…" /></div>
		{/if}
	{:else}
		<form class="space-y-6" onsubmit={save}>
			<section class="card space-y-4 p-6">
				<h2 class="section-title"><Icon name="folder" size={16} />Servers folder</h2>
				<div>
					<label class="label" for="st-dir">Folder on the host</label>
					<input
						id="st-dir"
						class="input font-mono"
						bind:value={settings.servers_dir}
						placeholder="/srv/gameservers"
					/>
					<p class="meta mt-1.5">
						New servers go to <code class="font-mono">folder/game/name/</code>, e.g.
						<code class="font-mono"
							>{settings.servers_dir || '/srv/gameservers'}/minecraft/skyblock/</code
						>
					</p>
				</div>
				{#if settings.servers_dir_problem}
					<p
						class="flex gap-2 rounded-xl border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-800 dark:text-amber-300"
					>
						<Icon name="alert" size={14} class="mt-0.5 shrink-0" />{settings.servers_dir_problem}
					</p>
				{:else}
					<p class="meta text-emerald-600 dark:text-emerald-400">
						<Icon name="check" size={14} />GameFleet can create servers here.
					</p>
				{/if}
				<div class="grid grid-cols-2 gap-3">
					<div>
						<label class="label" for="st-uid">Owner UID</label>
						<input
							id="st-uid"
							class="input font-mono"
							type="number"
							min="0"
							max="65535"
							bind:value={settings.owner_uid}
						/>
					</div>
					<div>
						<label class="label" for="st-gid">Owner GID</label>
						<input
							id="st-gid"
							class="input font-mono"
							type="number"
							min="0"
							max="65535"
							bind:value={settings.owner_gid}
						/>
					</div>
				</div>
				<p class="meta">
					Owner of the folders GameFleet creates, and the user the game runs as where the image
					allows it.
				</p>
			</section>

			<section class="card space-y-4 p-6">
				<h2 class="section-title"><Icon name="globe" size={16} />Public address</h2>
				<div>
					<label class="label" for="st-address">Host name players connect to</label>
					<input
						id="st-address"
						class="input font-mono"
						bind:value={settings.public_address}
						placeholder="play.example.com"
					/>
				</div>
			</section>

			<section class="card space-y-4 p-6">
				<h2 class="section-title"><Icon name="server" size={16} />Defaults for new servers</h2>
				<div class="grid grid-cols-2 gap-3">
					<div>
						<label class="label" for="st-memory">Memory (GB)</label>
						<input
							id="st-memory"
							class="input"
							type="number"
							min="1"
							max="256"
							bind:value={settings.default_memory_gb}
						/>
					</div>
					<div>
						<label class="label" for="st-cpu">CPU limit (cores)</label>
						<input
							id="st-cpu"
							class="input"
							type="number"
							min="0"
							step="0.5"
							bind:value={cpuLimit}
							placeholder="no limit"
						/>
					</div>
					<div>
						<label class="label" for="st-restart">Restart policy</label>
						<select id="st-restart" class="input" bind:value={settings.restart_policy}>
							<option value="unless-stopped">unless-stopped</option>
							<option value="always">always</option>
							<option value="on-failure">on-failure</option>
							<option value="no">no</option>
						</select>
					</div>
					<div>
						<label class="label" for="st-grace">Stop grace period (s)</label>
						<input
							id="st-grace"
							class="input"
							type="number"
							min="10"
							max="3600"
							bind:value={settings.stop_grace_seconds}
						/>
					</div>
					<div class="col-span-2">
						<label class="label" for="st-tz">Time zone</label>
						<input
							id="st-tz"
							class="input font-mono"
							bind:value={settings.timezone}
							placeholder="Europe/Berlin"
						/>
					</div>
				</div>
				<p class="meta">
					The grace period is how long a server may take to save and stop before Docker kills it.
				</p>
			</section>

			<div class="flex items-center justify-end gap-3">
				{#if error}<span class="text-sm text-rose-600 dark:text-rose-400">{error}</span>{/if}
				{#if saved}<span class="meta"><Icon name="check" size={14} />Saved</span>{/if}
				<button class="btn-primary" type="submit" disabled={saving}
					>{saving ? 'Saving…' : 'Save'}</button
				>
			</div>
		</form>
	{/if}
</div>
