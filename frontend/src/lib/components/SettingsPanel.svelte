<script lang="ts">
	import { api } from '$lib/api/ApiService';
	import type { ConfigFile, ConfigInfo, GameServerPublic, SettingValue } from '$lib/api/Api';
	import { formatBytes } from '$lib/gameinfo';
	import { confirmDialog } from '$lib/confirm.svelte';
	import Icon from './Icon.svelte';
	import Modal from './Modal.svelte';
	import Skeleton from './Skeleton.svelte';

	interface Props {
		server: GameServerPublic;
		running: boolean;
		/** Restart the container after a change; the page owns the power buttons. */
		onRestart: () => Promise<void>;
	}

	let { server, running, onRestart }: Props = $props();

	let info = $state<ConfigInfo | null>(null);
	let loadError = $state<string | null>(null);
	let error = $state<string | null>(null);
	// Edited values by key; only keys in here are sent.
	let edits = $state<Record<string, string | number | boolean>>({});
	let saving = $state(false);
	let restartNeeded = $state(false);
	let restarting = $state(false);
	// Raw file editor
	let editing = $state<{ file: ConfigFile; content: string; original: string } | null>(null);
	let fileBusy = $state(false);

	const settings = $derived(info?.settings ?? []);
	const files = $derived(info?.files ?? []);
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

	async function openFile(file: ConfigFile) {
		error = null;
		fileBusy = true;
		try {
			const { content } = (await api.serverId.getConfigFile(server.id, { path: file.path })).data;
			editing = { file, content, original: content };
		} catch (err) {
			error = detail(err, `Could not read ${file.label}.`);
		} finally {
			fileBusy = false;
		}
	}

	async function saveFile() {
		if (!editing) return;
		fileBusy = true;
		error = null;
		try {
			await api.serverId.updateConfigFile(server.id, { path: editing.file.path, content: editing.content });
			editing = null;
			restartNeeded = true;
			await load();
		} catch (err) {
			error = detail(err, 'Could not save the file.');
		} finally {
			fileBusy = false;
		}
	}

	$effect(() => {
		load();
	});
</script>

<section class="card p-5">
	<div class="mb-4 flex flex-wrap items-center justify-between gap-3">
		<h3 class="section-title">
			<Icon name="sliders" size={16} class="text-ink-3" />Settings
			{#if info?.settings_file}
				<span class="text-ink-3 font-mono text-xs font-normal">{info.settings_file}</span>
			{/if}
		</h3>
		{#if info?.supported}
			<div class="flex items-center gap-2">
				{#if files.length}
					<label class="relative">
						<span class="sr-only">Edit a file</span>
						<select
							class="input btn-sm w-44 appearance-none pr-8"
							disabled={fileBusy}
							onchange={(e) => {
								const path = (e.currentTarget as HTMLSelectElement).value;
								const file = files.find((f) => f.path === path);
								(e.currentTarget as HTMLSelectElement).value = '';
								if (file) openFile(file);
							}}
						>
							<option value="">Edit file…</option>
							{#each files as file (file.path)}
								<option value={file.path}>{file.label}</option>
							{/each}
						</select>
						<Icon
							name="chevron-down"
							size={14}
							class="text-ink-3 pointer-events-none absolute top-1/2 right-2.5 -translate-y-1/2"
						/>
					</label>
				{/if}
				{#if dirty}
					<button class="btn-ghost btn-sm" onclick={() => (edits = {})} disabled={saving}>Discard</button>
					<button class="btn-primary btn-sm" onclick={save} disabled={saving}>
						<Icon name="save" size={14} />{saving ? 'Saving…' : `Save ${Object.keys(edits).length}`}
					</button>
				{/if}
			</div>
		{/if}
	</div>

	{#if error || loadError}
		<p class="notice tone-bad mb-4"><Icon name="alert" size={16} class="mt-0.5 shrink-0" />{error ?? loadError}</p>
	{/if}

	{#if restartNeeded}
		<div class="notice tone-warn mb-4 items-center">
			<Icon name="info" size={16} class="shrink-0" />
			<span class="flex-1">
				{running ? 'Saved. The server reads its settings on start, so restart it to apply them.' : 'Saved. The new settings apply when the server starts.'}
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
		<p class="text-ink-2 text-sm">{info.reason}</p>
	{:else if settings.length === 0}
		<p class="hint">This game keeps its settings in files only; pick one above to edit it.</p>
	{:else}
		<div class="space-y-5">
			{#each groups as [group, items] (group)}
				<div>
					{#if groups.length > 1}<p class="caption mb-2">{group}</p>{/if}
					<div class="grid gap-x-6 gap-y-3 sm:grid-cols-2">
						{#each items as s (s.key)}
							{@const locked = s.locked != null || s.env_override != null}
							{@const value = current(s)}
							<div class="min-w-0" title={s.description ?? ''}>
								{#if s.type === 'bool'}
									<label class="flex cursor-pointer items-start gap-3 py-1 text-sm {locked ? 'opacity-60' : ''}">
										<input
											type="checkbox"
											class="accent-accent mt-0.5 h-4 w-4"
											checked={Boolean(value)}
											disabled={locked}
											onchange={(e) => set(s, (e.currentTarget as HTMLInputElement).checked)}
										/>
										<span>
											{s.label}
											{#if s.description}<span class="hint block">{s.description}</span>{/if}
										</span>
									</label>
								{:else}
									<label class="label flex items-center gap-2" for="cfg-{s.key}">
										{s.label}
										{#if s.key in edits}<span class="h-1.5 w-1.5 rounded-full bg-accent"></span>{/if}
									</label>
									{#if s.type === 'enum'}
										<div class="relative">
											<select
												id="cfg-{s.key}"
												class="input appearance-none pr-8"
												disabled={locked}
												value={String(value ?? '')}
												onchange={(e) => set(s, (e.currentTarget as HTMLSelectElement).value)}
											>
												{#each s.options ?? [] as option (option)}
													<option value={option}>{option}</option>
												{/each}
											</select>
											<Icon
												name="chevron-down"
												size={14}
												class="text-ink-3 pointer-events-none absolute top-1/2 right-2.5 -translate-y-1/2"
											/>
										</div>
									{:else}
										<input
											id="cfg-{s.key}"
											class="input {s.type === 'int' ? 'font-mono' : ''}"
											type={s.type === 'int' ? 'number' : 'text'}
											disabled={locked}
											placeholder={value == null ? 'game default' : ''}
											value={value ?? ''}
											onchange={(e) => {
												const raw = (e.currentTarget as HTMLInputElement).value;
												set(s, s.type === 'int' ? Number(raw) : raw);
											}}
										/>
									{/if}
								{/if}
								{#if s.env_override}
									<p class="hint mt-1">
										Set by <span class="font-mono">{s.env_override}</span> in the container; change it in the compose file.
									</p>
								{:else if s.locked}
									<p class="hint mt-1">{s.locked}</p>
								{/if}
							</div>
						{/each}
					</div>
				</div>
			{/each}
		</div>
	{/if}
</section>

{#if editing}
	<Modal title={editing.file.label} size="lg" onClose={() => !fileBusy && (editing = null)}>
		<p class="hint mb-2 flex items-center justify-between">
			<span class="font-mono">{editing.file.path}</span>
			<span>{formatBytes(editing.content.length)}</span>
		</p>
		<textarea
			class="input h-[60vh] resize-y font-mono text-xs leading-5 whitespace-pre"
			spellcheck="false"
			bind:value={editing.content}
		></textarea>
		{#if error}
			<p class="notice tone-bad mt-3"><Icon name="alert" size={16} class="mt-0.5 shrink-0" />{error}</p>
		{/if}
		<div class="mt-4 flex items-center justify-between gap-2">
			<p class="hint">Saved files take effect when the server starts.</p>
			<div class="flex gap-2">
				<button class="btn-ghost" onclick={() => (editing = null)} disabled={fileBusy}>Cancel</button>
				<button
					class="btn-primary"
					onclick={saveFile}
					disabled={fileBusy || editing.content === editing.original}
				>
					<Icon name="save" size={15} />{fileBusy ? 'Saving…' : 'Save file'}
				</button>
			</div>
		</div>
	</Modal>
{/if}
