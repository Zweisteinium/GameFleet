<script lang="ts">
	import { api } from '$lib/api/ApiService';
	import type { ConfigInfo, GameServerPublic, SettingValue } from '$lib/api/Api';
	import { confirmDialog } from '$lib/confirm.svelte';
	import Icon from './Icon.svelte';
	import SettingField from './SettingField.svelte';
	import Skeleton from './Skeleton.svelte';

	interface Props {
		server: GameServerPublic;
		running: boolean;
		/** Restart the container after a change; the page owns the power buttons. */
		onRestart: () => Promise<void>;
		/** The compose file owns the main settings: this is the file view, collapsed, for keys compose leaves alone. */
		advanced?: boolean;
	}

	let { server, running, onRestart, advanced = false }: Props = $props();
	let open = $state(false);

	let info = $state<ConfigInfo | null>(null);
	let loadError = $state<string | null>(null);
	let error = $state<string | null>(null);
	// Edited values by key; only keys in here are sent.
	let edits = $state<Record<string, string | number | boolean>>({});
	let saving = $state(false);
	let restartNeeded = $state(false);
	let restarting = $state(false);

	const settings = $derived(info?.settings ?? []);
	const dirty = $derived(Object.keys(edits).length > 0);
	const groups = $derived.by(() => {
		const byGroup: Record<string, SettingValue[]> = {};
		for (const s of settings) (byGroup[s.group ?? 'General'] ??= []).push(s);
		return Object.entries(byGroup);
	});

	function detail(err: unknown, fallback: string): string {
		const d = (err as { error?: { detail?: unknown } })?.error?.detail;
		return typeof d === 'string' ? d : fallback;
	}

	async function load() {
		try {
			info = (await api.serverId.getConfig(server.id)).data;
			loadError = null;
		} catch (err) {
			loadError = detail(err, 'Could not read the configuration of this server.');
		}
	}

	function current(s: SettingValue): string | number | boolean | null {
		return s.key in edits ? edits[s.key] : (s.value ?? null);
	}

	function set(s: SettingValue, value: string | number | boolean) {
		if (value === (s.value ?? (s.type === 'bool' ? false : ''))) delete edits[s.key];
		else edits[s.key] = value;
	}

	async function save() {
		saving = true;
		error = null;
		try {
			const result = (await api.serverId.updateSettings(server.id, { values: edits })).data;
			info = result;
			edits = {};
			restartNeeded = true;
		} catch (err) {
			error = detail(err, 'Could not save the settings.');
		} finally {
			saving = false;
		}
	}

	async function restart() {
		const go = await confirmDialog({
			title: 'Restart server',
			message: `Restart "${server.name}" to apply the new settings?`,
			note: 'Players will be disconnected.',
			confirmLabel: 'Restart',
			tone: 'danger'
		});
		if (!go) return;
		restarting = true;
		try {
			await onRestart();
			restartNeeded = false;
		} finally {
			restarting = false;
		}
	}

	$effect(() => {
		load();
	});
</script>

<section class="card p-5">
	<div class="flex flex-wrap items-center justify-between gap-3 {advanced && !open ? '' : 'mb-4'}">
		{#if advanced}
			<button
				class="section-title cursor-pointer"
				onclick={() => (open = !open)}
				aria-expanded={open}
			>
				<Icon
					name={open ? 'chevron-down' : 'chevron-right'}
					size={16}
					class="text-ink-3"
				/>Advanced:
				<span class="font-mono font-normal"
					>{info?.settings_file?.split('/').pop() ?? 'settings file'}</span
				>
			</button>
		{:else}
			<h2 class="section-title">
				<Icon name="sliders" size={16} class="text-ink-3" />Settings
				{#if info?.settings_file}
					<span class="font-mono text-xs font-normal text-ink-3">{info.settings_file}</span>
				{/if}
			</h2>
		{/if}
		{#if info?.supported && dirty && (open || !advanced)}
			<div class="flex items-center gap-2">
				<button class="btn-ghost btn-sm" onclick={() => (edits = {})} disabled={saving}
					>Discard</button
				>
				<button class="btn-primary btn-sm" onclick={save} disabled={saving}>
					<Icon name="save" size={14} />{saving ? 'Saving…' : `Save ${Object.keys(edits).length}`}
				</button>
			</div>
		{/if}
	</div>
	{#if advanced && !open}
		<p class="hint mt-1 pl-6">
			Edits the file directly. Keys set in the compose file are rewritten by the image on every
			start, so only the others stick here.
		</p>
	{/if}

	{#if !advanced || open}
		{#if advanced}
			<p class="notice tone-warn mb-4 text-xs">
				<Icon name="alert" size={14} class="mt-0.5 shrink-0" />The image writes the keys that are
				set in the compose file on every start; they are locked here. Change those under Server
				settings.
			</p>
		{/if}
		{#if error || loadError}
			<p class="notice tone-bad mb-4">
				<Icon name="alert" size={16} class="mt-0.5 shrink-0" />{error ?? loadError}
			</p>
		{/if}

		{#if restartNeeded}
			<div class="notice tone-warn mb-4 items-center">
				<Icon name="info" size={16} class="shrink-0" />
				<span class="flex-1">
					{running
						? 'Saved. The server reads its settings on start, so restart it to apply them.'
						: 'Saved. The new settings apply when the server starts.'}
				</span>
				{#if running}
					<button class="btn-outline btn-sm" onclick={restart} disabled={restarting}>
						<Icon name="rotate-cw" size={14} class={restarting ? 'animate-spin' : ''} />Restart now
					</button>
				{/if}
			</div>
		{/if}

		{#if !info}
			{#if !loadError}<Skeleton class="h-5 w-64" />{/if}
		{:else if !info.supported}
			<p class="text-sm text-ink-2">{info.reason}</p>
		{:else if settings.length === 0}
			<p class="hint">This game keeps its settings in files only; edit them in Files.</p>
		{:else}
			<div class="space-y-5">
				{#each groups as [group, items] (group)}
					<div>
						{#if groups.length > 1}<p class="caption mb-2">{group}</p>{/if}
						<div class="grid gap-x-6 gap-y-3 sm:grid-cols-2">
							{#each items as s (s.key)}
								<SettingField
									id="cfg-{s.key}"
									label={s.label}
									type={s.type}
									value={current(s)}
									options={s.options ?? []}
									description={s.description ?? ''}
									edited={s.key in edits}
									disabled={s.locked != null || s.env_override != null}
									note={s.env_override
										? `Set by ${s.env_override} in the container; change it under Server settings.`
										: (s.locked ?? null)}
									placeholder={current(s) == null ? 'game default' : ''}
									multiline={s.key === 'motd'}
									motd={s.key === 'motd' && server.game === 'minecraft'}
									onchange={(v) => set(s, v)}
								/>
							{/each}
						</div>
					</div>
				{/each}
			</div>
		{/if}
	{/if}
</section>
