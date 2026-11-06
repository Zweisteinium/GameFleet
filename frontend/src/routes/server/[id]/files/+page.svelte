<script lang="ts">
	import { page } from '$app/state';
	import { goto, beforeNavigate } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { api } from '$lib/api/ApiService';
	import { formatBytes } from '$lib/gameinfo';
	import { confirmDialog } from '$lib/confirm.svelte';
	import { serverPage } from '$lib/serverPage.svelte';
	import Icon from '$lib/components/Icon.svelte';
	import Skeleton from '$lib/components/Skeleton.svelte';

	const COMPOSE = 'compose';

	interface Entry {
		id: string; // the container path, or COMPOSE
		label: string;
		path: string; // shown
		size: number | null;
	}

	const ctx = serverPage();
	const server = $derived(ctx.server);

	let entries = $state<Entry[] | null>(null);
	let loadError = $state<string | null>(null);
	let open = $state<{ entry: Entry; content: string; original: string } | null>(null);
	let loading = $state(false);
	let saving = $state(false);
	let error = $state<string | null>(null);
	let saved = $state<string | null>(null);

	const selected = $derived(page.url.searchParams.get('file'));
	const dirty = $derived(open != null && open.content !== open.original);

	function detail(err: unknown, fallback: string): string {
		const d = (err as { error?: { detail?: unknown } })?.error?.detail;
		return typeof d === 'string' ? d : fallback;
	}

	async function loadList() {
		const list: Entry[] = [];
		const [compose, config] = await Promise.allSettled([
			api.serverId.getCompose(server.id),
			api.serverId.getConfig(server.id)
		]);
		if (compose.status === 'fulfilled' && compose.value.data.supported && compose.value.data.file)
			list.push({ id: COMPOSE, label: 'Compose file', path: compose.value.data.file, size: null });
		if (config.status === 'fulfilled')
			for (const f of config.value.data.files ?? [])
				list.push({ id: f.path, label: f.label, path: f.path, size: f.size });
		else loadError = detail(config.reason, 'Could not list the files of this server.');
		entries = list;
	}

	async function show(id: string | null) {
		error = null;
		saved = null;
		const entry = entries?.find((e) => e.id === id) ?? null;
		if (!entry) {
			open = null;
			return;
		}
		loading = true;
		try {
			const content =
				entry.id === COMPOSE
					? (await api.serverId.getComposeFile(server.id)).data.content
					: (await api.serverId.getConfigFile(server.id, { path: entry.id })).data.content;
			open = { entry, content, original: content };
		} catch (err) {
			open = null;
			error = detail(err, `Could not read ${entry.label}.`);
		} finally {
			loading = false;
		}
	}

	function pick(entry: Entry) {
		const path = resolve('/server/[id]/files', { id: server.id });
		// eslint-disable-next-line svelte/no-navigation-without-resolve -- resolved above, plus the query
		goto(`${path}?file=${encodeURIComponent(entry.id)}`, { keepFocus: true, noScroll: true });
	}

	async function save() {
		if (!open || !dirty || saving) return;
		saving = true;
		error = null;
		try {
			if (open.entry.id === COMPOSE) {
				const result = (await api.serverId.updateComposeFile(server.id, { content: open.content }))
					.data;
				open = { ...open, content: result.content, original: result.content };
				saved =
					'Saved. The old file is kept as .gamefleet-bak; the change applies when the container is recreated.';
			} else {
				await api.serverId.updateConfigFile(server.id, {
					path: open.entry.id,
					content: open.content
				});
				open = { ...open, original: open.content };
				saved = 'Saved. The server reads it on its next start.';
			}
		} catch (err) {
			error = detail(err, 'Could not save the file.');
		} finally {
			saving = false;
		}
	}

	async function recreate() {
		const go = await confirmDialog({
			title: 'Recreate server',
			message: `Recreate "${server.name}" from its compose file?`,
			note: ctx.running
				? 'The server stops, saves and starts again; players are disconnected.'
				: undefined,
			confirmLabel: 'Recreate',
			tone: 'danger'
		});
		if (!go) return;
		try {
			await ctx.recreate();
			saved = 'Recreated from the compose file.';
		} catch (err) {
			error = detail(err, 'Could not recreate the container.');
		}
	}

	function onKey(event: KeyboardEvent) {
		if ((event.ctrlKey || event.metaKey) && event.key === 's') {
			event.preventDefault();
			save();
		}
	}

	beforeNavigate(async (navigation) => {
		if (!dirty || navigation.type === 'leave') return;
		navigation.cancel();
		const discard = await confirmDialog({
			title: 'Unsaved changes',
			message: `Discard your changes to ${open?.entry.label}?`,
			confirmLabel: 'Discard',
			tone: 'danger'
		});
		if (discard && navigation.to) {
			open = open && { ...open, content: open.original };
			// eslint-disable-next-line svelte/no-navigation-without-resolve -- a URL SvelteKit already resolved
			goto(navigation.to.url);
		}
	});

	$effect(() => {
		loadList();
	});
	$effect(() => {
		if (entries) show(selected ?? entries[0]?.id ?? null);
	});
</script>

<svelte:head><title>Files · {server.name} · GameFleet</title></svelte:head>
<svelte:window onkeydown={onKey} onbeforeunload={(e) => dirty && e.preventDefault()} />

<div class="grid gap-5 lg:grid-cols-[15rem_1fr]">
	<nav class="card h-fit p-2 lg:sticky lg:top-4" aria-label="Files">
		{#if !entries}
			<div class="space-y-2 p-2"><Skeleton class="h-4 w-32" /><Skeleton class="h-4 w-28" /></div>
		{:else if entries.length === 0}
			<p class="hint p-2">{loadError ?? 'GameFleet knows no editable files for this game.'}</p>
		{:else}
			<ul class="space-y-0.5">
				{#each entries as entry (entry.id)}
					<li>
						<button
							class="flex w-full cursor-pointer items-center gap-2 rounded-[var(--radius-control)] px-2.5 py-1.5 text-left text-sm transition-colors {open
								?.entry.id === entry.id
								? 'bg-accent-soft text-accent'
								: 'text-ink-2 hover:bg-surface-2'}"
							onclick={() => pick(entry)}
						>
							<Icon name={entry.id === COMPOSE ? 'box' : 'file-text'} size={14} class="shrink-0" />
							<span class="min-w-0 flex-1 truncate">{entry.label}</span>
							{#if entry.size != null}<span class="text-[11px] text-ink-3"
									>{formatBytes(entry.size)}</span
								>{/if}
						</button>
					</li>
				{/each}
			</ul>
		{/if}
	</nav>

	<section class="card flex min-w-0 flex-col p-4">
		{#if error}
			<p class="notice tone-bad mb-3">
				<Icon name="alert" size={16} class="mt-0.5 shrink-0" />{error}
			</p>
		{/if}
		{#if loading && !open}
			<Skeleton class="h-[60vh] w-full" />
		{:else if open}
			<div class="mb-3 flex flex-wrap items-center justify-between gap-3">
				<div class="min-w-0">
					<h2 class="section-title">
						{open.entry.label}{#if dirty}<span class="h-1.5 w-1.5 rounded-full bg-accent"
							></span>{/if}
					</h2>
					<p class="hint truncate font-mono">{open.entry.path}</p>
				</div>
				<div class="flex items-center gap-2">
					{#if dirty}
						<button
							class="btn-ghost btn-sm"
							onclick={() => open && (open = { ...open, content: open.original })}
							disabled={saving}>Discard</button
						>
					{/if}
					<button
						class="btn-primary btn-sm"
						onclick={save}
						disabled={!dirty || saving}
						title="Ctrl+S"
					>
						<Icon name="save" size={14} />{saving ? 'Saving…' : 'Save'}
					</button>
				</div>
			</div>
			{#if saved}
				<div class="notice tone-ok mb-3 items-center">
					<Icon name="check" size={16} class="shrink-0" /><span class="flex-1">{saved}</span>
					{#if open.entry.id === COMPOSE}
						<button class="btn-outline btn-sm" onclick={recreate}>
							<Icon name="rotate-cw" size={14} />Recreate now
						</button>
					{/if}
				</div>
			{/if}
			{#if open.entry.id !== COMPOSE && open.entry.label === 'server.properties'}
				<p class="hint mb-2">
					Keys set in the compose file are rewritten by the image on every start; change those under
					Settings.
				</p>
			{/if}
			<textarea
				class="input h-[calc(100vh-16rem)] min-h-[24rem] resize-y py-2 font-mono text-xs leading-5 whitespace-pre"
				spellcheck="false"
				aria-label={open.entry.label}
				bind:value={open.content}></textarea>
		{:else if entries?.length}
			<p class="hint">Pick a file.</p>
		{/if}
	</section>
</div>
