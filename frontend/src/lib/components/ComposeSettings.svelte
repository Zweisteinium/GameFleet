<script lang="ts">
	import { api } from '$lib/api/ApiService';
	import type { ComposeInfo, ComposeSetting, GameServerPublic } from '$lib/api/Api';
	import { confirmDialog } from '$lib/confirm.svelte';
	import Icon from './Icon.svelte';
	import SettingField from './SettingField.svelte';
	import Skeleton from './Skeleton.svelte';

	type Value = string | number | boolean;

	interface Props {
		server: GameServerPublic;
		running: boolean;
		playersOnline: number | null;
		/** `docker compose up -d`; the layout handles port conflicts. */
		onRecreate: () => Promise<void>;
		/** Told whether the server has a compose file, so the page can arrange the other sections. */
		onLoaded?: (info: ComposeInfo) => void;
	}

	let { server, running, playersOnline, onRecreate, onLoaded }: Props = $props();

	let info = $state<ComposeInfo | null>(null);
	let loadError = $state<string | null>(null);
	let error = $state<string | null>(null);
	let edits = $state<Record<string, Value>>({});
	let saving = $state(false);
	let recreating = $state(false);

	const dirty = $derived(Object.keys(edits).length > 0);
	const groups = $derived.by(() => {
		const byGroup: Record<string, ComposeSetting[]> = {};
		for (const s of info?.settings ?? []) (byGroup[s.group || 'General'] ??= []).push(s);
		return Object.entries(byGroup);
	});
	const pendingLabels = $derived(
		(info?.pending ?? []).map((env) => info?.settings?.find((s) => s.env === env)?.label ?? env)
	);

	function detail(err: unknown, fallback: string): string {
		const d = (err as { error?: { detail?: unknown } })?.error?.detail;
		return typeof d === 'string' ? d : fallback;
	}

	async function load() {
		try {
			info = (await api.serverId.getCompose(server.id)).data;
			loadError = null;
			onLoaded?.(info);
		} catch (err) {
			loadError = detail(err, 'Could not read the compose file of this server.');
		}
	}

	/** What the field shows: the edit, the compose value, or for an unset checkbox what the game has now. */
	function baseline(s: ComposeSetting): Value | null {
		if (s.value != null) return s.value;
		if (s.type === 'bool') return typeof s.file_value === 'boolean' ? s.file_value : false;
		return null;
	}

	function current(s: ComposeSetting): Value | null {
		return s.env in edits ? edits[s.env] : baseline(s);
	}

	function set(s: ComposeSetting, value: Value) {
		if (value === (baseline(s) ?? '')) delete edits[s.env];
		else edits[s.env] = value;
	}

	function note(s: ComposeSetting): string | null {
		if (s.readonly) return s.readonly;
		if (s.value == null && s.file_value != null && s.file_value !== '')
			return `Not set in compose; server.properties has ${s.type === 'str' ? `"${s.file_value}"` : s.file_value}. Setting it here makes compose own it.`;
		return null;
	}

	async function save() {
		saving = true;
		error = null;
		try {
			info = (await api.serverId.updateComposeSettings(server.id, { values: edits })).data;
			edits = {};
		} catch (err) {
			error = detail(err, 'Could not save the compose file.');
		} finally {
			saving = false;
		}
	}

	async function recreate() {
		const online = playersOnline ?? 0;
		const go = await confirmDialog({
			title: running ? 'Recreate server' : 'Apply and start',
			message: running
				? `Recreate "${server.name}" with the new settings? It stops, saves and starts again.`
				: `Create the container of "${server.name}" with the new settings and start it?`,
			note:
				online > 0
					? `${online} player${online === 1 ? ' is' : 's are'} online and will be disconnected.`
					: undefined,
			confirmLabel: running ? 'Recreate' : 'Start',
			tone: running ? 'danger' : 'primary'
		});
		if (!go) return;
		recreating = true;
		error = null;
		try {
			await onRecreate();
			await load();
		} catch (err) {
			error = detail(err, 'Could not recreate the container.');
		} finally {
			recreating = false;
		}
	}

	$effect(() => {
		load();
	});
</script>

<section class="card p-5">
	<div class="mb-4 flex flex-wrap items-center justify-between gap-3">
		<div class="min-w-0">
			<h2 class="section-title">
				<Icon name="sliders" size={16} class="text-ink-3" />Server settings
			</h2>
			{#if info?.file}
				<p class="hint mt-1">
					From the environment of <span class="font-mono">{info.service}</span> in
					<span class="font-mono">{info.file}</span>
				</p>
			{/if}
		</div>
		{#if dirty}
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

	{#if error || loadError}
		<p class="notice tone-bad mb-4">
			<Icon name="alert" size={16} class="mt-0.5 shrink-0" />{error ?? loadError}
		</p>
	{/if}

	{#if info?.pending?.length}
		<div class="notice tone-warn mb-4 items-center">
			<Icon name="info" size={16} class="shrink-0" />
			<span class="flex-1">
				Not applied yet: {pendingLabels.join(', ')}. They take effect when the container is
				recreated (Restart does that too).
			</span>
			<button class="btn-outline btn-sm" onclick={recreate} disabled={recreating || dirty}>
				<Icon name="rotate-cw" size={14} class={recreating ? 'animate-spin' : ''} />{recreating
					? 'Recreating…'
					: running
						? 'Recreate now'
						: 'Apply and start'}
			</button>
		</div>
	{/if}

	{#if !info}
		{#if !loadError}<Skeleton class="h-5 w-64" />{/if}
	{:else if !info.supported}
		<p class="text-sm text-ink-2">{info.reason}</p>
	{:else if !info.settings?.length}
		<p class="hint">GameFleet knows no settings for this image; edit the compose file in Files.</p>
	{:else}
		<div class="space-y-5">
			{#each groups as [group, items] (group)}
				<div>
					{#if groups.length > 1}<p class="caption mb-2">{group}</p>{/if}
					<div class="grid gap-x-6 gap-y-3 sm:grid-cols-2">
						{#each items as s (s.env)}
							<SettingField
								id="env-{s.env}"
								label={s.label}
								type={s.type}
								value={current(s)}
								options={s.options ?? []}
								description={s.description ?? ''}
								edited={s.env in edits}
								disabled={s.readonly != null}
								note={note(s)}
								placeholder={s.value == null
									? s.file_value == null
										? 'image default'
										: String(s.file_value)
									: ''}
								multiline={s.multiline ?? false}
								motd={s.motd ?? false}
								onchange={(v) => set(s, v)}
							/>
						{/each}
					</div>
				</div>
			{/each}
		</div>
	{/if}
</section>
