<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { api } from '$lib/api/ApiService';
	import type {
		CreateJob,
		CreatePreview,
		CreateRequest,
		ModrinthPack,
		SettingsView,
		Template,
		TemplateVariable
	} from '$lib/api/Api';
	import { loggedIn } from '$lib/auth.svelte';
	import GameArt from '$lib/components/GameArt.svelte';
	import Icon from '$lib/components/Icon.svelte';
	import LoadingSpinner from '$lib/components/LoadingSpinner.svelte';

	const STEPS = ['Game', 'Essentials', 'Review'];
	const PHASES: [CreateJob['phase'], string][] = [
		['writing', 'Writing the compose file'],
		['pulling', 'Downloading the image'],
		['creating', 'Creating the container'],
		['starting', 'Starting'],
		['waiting', 'Waiting until it is ready']
	];

	let templates = $state<Template[]>([]);
	let settings = $state<SettingsView | null>(null);
	let loadError = $state<string | null>(null);

	let step = $state(0);
	let template = $state<Template | null>(null);
	let name = $state('');
	let slug = $state('');
	let slugEdited = $state(false);
	let values = $state<Record<string, string>>({});
	let tag = $state('');
	let tagChosen = $state(false);
	let port = $state<number | null>(null);
	let eula = $state(false);
	let isPublic = $state(false);
	let startNow = $state(true);
	let stopConflicting = $state(false);
	let showAdvanced = $state(false);

	let versions = $state<string[]>([]);
	let packQuery = $state('');
	let packs = $state<ModrinthPack[]>([]);
	let pack = $state<ModrinthPack | null>(null);
	let packTimer: ReturnType<typeof setTimeout> | undefined;

	let preview = $state<CreatePreview | null>(null);
	let previewing = $state(false);
	let error = $state<string | null>(null);
	let creating = $state(false);
	let job = $state<CreateJob | null>(null);
	let poll: ReturnType<typeof setInterval> | undefined;

	function detail(err: unknown, fallback: string): string {
		const d = (err as { error?: { detail?: unknown } })?.error?.detail;
		if (Array.isArray(d)) return d.map((item) => item?.msg ?? String(item)).join('; ');
		return typeof d === 'string' ? d : fallback;
	}

	onMount(async () => {
		if (!loggedIn()) return;
		try {
			[templates, settings] = await Promise.all([
				api.templates.getTemplates().then((r) => r.data),
				api.getSettings().then((r) => r.data)
			]);
		} catch (err) {
			loadError = detail(err, 'Could not load the templates from the backend.');
		}
	});

	onDestroy(() => {
		clearInterval(poll);
		clearTimeout(packTimer);
	});

	function defaultValue(variable: TemplateVariable): string {
		if (variable.type === 'memory' && !variable.default)
			return `${settings?.default_memory_gb ?? 4}G`;
		return variable.default ?? '';
	}

	function current(env: string): string {
		const variable = template?.variables?.find((v) => v.env === env);
		return values[env] ?? (variable ? defaultValue(variable) : '');
	}

	const active = $derived(
		(template?.variables ?? []).filter((v) =>
			Object.entries(v.show_if ?? {}).every(([env, allowed]) => allowed.includes(current(env)))
		)
	);
	const essentials = $derived(active.filter((v) => !v.advanced && v.type !== 'secret'));
	const advanced = $derived(active.filter((v) => v.advanced));
	const gamePort = $derived(template?.ports?.[0]?.port ?? 0);
	const missing = $derived(
		!name.trim() ||
			!slug ||
			(template?.eula != null && !eula) ||
			essentials.some((v) => v.required && !current(v.env).trim())
	);
	const runningHolders = $derived((preview?.holders ?? []).filter((h) => h.running));
	const foreignRunning = $derived(runningHolders.filter((h) => !h.server_id));

	function slugify(text: string): string {
		return text
			.toLowerCase()
			.normalize('NFKD')
			.replace(/[^a-z0-9]+/g, '-')
			.replace(/^-+|-+$/g, '')
			.slice(0, 32)
			.replace(/-+$/, '');
	}

	function pick(chosen: Template) {
		template = chosen;
		values = {};
		tag = chosen.tags[0]?.tag ?? '';
		tagChosen = false;
		port = chosen.ports[0]?.port ?? null;
		eula = false;
		pack = null;
		packQuery = '';
		packs = [];
		step = 1;
		if (chosen.variables?.some((v) => v.suggest === 'minecraft-versions') && !versions.length) {
			api.minecraftVersions
				.getMinecraftVersions()
				.then((r) => (versions = r.data))
				.catch(() => {});
		}
	}

	/** itzg image tag that fits a Minecraft version (1.20.5+ needs Java 21, 26.x Java 25). */
	function javaTagFor(version: string): string | null {
		const match = /^1\.(\d+)(?:\.(\d+))?/.exec(version);
		if (!match) return /^\d{2}\./.test(version) ? 'java25' : null;
		const minor = Number(match[1]);
		const patch = Number(match[2] ?? 0);
		if (minor > 20 || (minor === 20 && patch >= 5)) return 'java21';
		if (minor >= 18) return 'java17';
		return 'java8';
	}

	function suggestTag(version: string | undefined) {
		if (tagChosen || !version || !template?.tags?.length) return;
		const suggested = javaTagFor(version);
		if (suggested && template.tags.some((t) => t.tag === suggested)) tag = suggested;
	}

	function setValue(variable: TemplateVariable, value: string) {
		values[variable.env] = value;
		if (variable.suggest === 'minecraft-versions')
			suggestTag(value === 'LATEST' ? undefined : value);
	}

	function searchPacks(variable: TemplateVariable, query: string) {
		packQuery = query;
		pack = null;
		values[variable.env] = query.trim();
		clearTimeout(packTimer);
		if (query.trim().length < 2) {
			packs = [];
			return;
		}
		packTimer = setTimeout(async () => {
			try {
				packs = (await api.modrinthPacks.searchModrinthPacks({ q: query.trim() })).data;
			} catch {
				packs = [];
			}
		}, 300);
	}

	function choosePack(variable: TemplateVariable, chosen: ModrinthPack) {
		pack = chosen;
		packQuery = chosen.title;
		packs = [];
		values[variable.env] = chosen.slug;
		suggestTag(chosen.versions?.at(-1));
	}

	function memoryGb(variable: TemplateVariable): number {
		const match = /^(\d+)([MG])$/i.exec(current(variable.env));
		if (!match) return settings?.default_memory_gb ?? 4;
		return match[2].toUpperCase() === 'G'
			? Number(match[1])
			: Math.max(1, Math.round(Number(match[1]) / 1024));
	}

	function request(): CreateRequest {
		const sent: Record<string, string> = {};
		for (const variable of active) {
			if (variable.type !== 'secret' && values[variable.env] !== undefined)
				sent[variable.env] = values[variable.env];
		}
		return {
			template: template!.id,
			name: name.trim(),
			slug,
			values: sent,
			tag: tag || null,
			port: port && port !== gamePort ? port : null,
			eula,
			is_public: isPublic,
			start: startNow,
			stop_conflicting: stopConflicting
		};
	}

	async function review() {
		previewing = true;
		error = null;
		try {
			preview = (await api.preview.previewCreate(request())).data;
			stopConflicting = runningHolders.length > 0 && foreignRunning.length === 0;
			step = 2;
		} catch (err) {
			error = detail(err, 'Could not check the server.');
		} finally {
			previewing = false;
		}
	}

	async function create() {
		creating = true;
		error = null;
		try {
			job = (await api.createServer(request())).data;
			step = 3;
			poll = setInterval(async () => {
				try {
					job = (await api.jobs.getCreateJob(job!.id)).data;
					if (job.finished_at) clearInterval(poll);
				} catch (err) {
					clearInterval(poll);
					error = detail(err, 'Lost track of the creation.');
				}
			}, 1500);
		} catch (err) {
			error = detail(err, 'Could not create the server.');
		} finally {
			creating = false;
		}
	}

	function phaseState(
		phase: CreateJob['phase']
	): 'done' | 'active' | 'todo' | 'failed' | 'skipped' {
		if (!job) return 'todo';
		const order = PHASES.map(([p]) => p);
		const index = order.indexOf(phase);
		const reached =
			job.phase === 'done' || job.phase === 'failed' ? order.length : order.indexOf(job.phase);
		if (job.phase === 'failed') {
			const last = job.started
				? order.indexOf('waiting')
				: job.server_id
					? order.indexOf('starting')
					: -1;
			if (index <= last) return index === last ? 'failed' : 'done';
			return 'todo';
		}
		if (job.phase === 'done' && !job.started && index >= order.indexOf('starting'))
			return 'skipped';
		if (index < reached) return 'done';
		return index === reached ? 'active' : 'todo';
	}
</script>

<svelte:head><title>New server · GameFleet</title></svelte:head>

<div class="mx-auto max-w-3xl pt-6">
	<a href={resolve('/main')} class="meta mb-3 hover:text-ink"
		><Icon name="arrow-left" size={14} />Servers</a
	>
	<h1 class="mb-1 font-display text-2xl font-semibold tracking-tight">New server</h1>

	{#if !loggedIn()}
		<p class="card mt-6 p-6 text-sm text-ink-2">Sign in to create servers.</p>
	{:else if loadError}
		<p class="card mt-6 p-6 text-sm text-rose-600 dark:text-rose-400">{loadError}</p>
	{:else if !settings}
		<div class="py-16"><LoadingSpinner message="Loading templates…" /></div>
	{:else}
		{#if step < 3}
			<ol class="mt-3 mb-6 flex items-center gap-2 text-xs font-medium text-ink-3">
				{#each STEPS as label, index (label)}
					<li
						class="flex items-center gap-2 {index === step
							? 'text-accent'
							: index < step
								? 'text-ink-2'
								: ''}"
					>
						<span
							class="grid h-6 w-6 place-items-center rounded-full border {index === step
								? 'border-accent bg-accent-soft'
								: 'border-line-2'}">{index + 1}</span
						>{label}
					</li>
					{#if index < STEPS.length - 1}<li class="h-px w-8 bg-line-2"></li>{/if}
				{/each}
			</ol>
		{/if}

		{#if settings.servers_dir_problem}
			<p
				class="mb-4 flex gap-2 rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-800 dark:text-amber-300"
			>
				<Icon name="alert" size={16} class="mt-0.5 shrink-0" />
				<span
					>{settings.servers_dir_problem}
					<a class="underline" href={resolve('/settings')}>Settings</a></span
				>
			</p>
		{/if}

		{#if step === 0}
			<div class="grid grid-cols-2 gap-4 sm:grid-cols-3">
				{#each templates as item (item.id)}
					<button
						class="card group overflow-hidden text-left transition hover:-translate-y-0.5"
						onclick={() => pick(item)}
					>
						<GameArt game={item.game} class="aspect-[3/4] w-full" />
						<div class="p-4">
							<div class="font-display font-semibold">{item.label}</div>
							<p class="mt-1 text-xs text-ink-2">{item.description}</p>
						</div>
					</button>
				{/each}
			</div>
		{:else if step === 1 && template}
			<form
				class="card space-y-5 p-6"
				onsubmit={(event) => {
					event.preventDefault();
					review();
				}}
			>
				<div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
					<div>
						<label class="label" for="cr-name">Name</label>
						<input
							id="cr-name"
							class="input"
							bind:value={name}
							oninput={() => !slugEdited && (slug = slugify(name))}
							maxlength="100"
							placeholder="Skyblock with friends"
							required
						/>
					</div>
					<div>
						<label class="label" for="cr-slug">Folder</label>
						<input
							id="cr-slug"
							class="input font-mono"
							bind:value={slug}
							oninput={() => (slugEdited = true)}
							maxlength="32"
							placeholder="skyblock"
							required
						/>
						<p class="meta mt-1 font-mono">
							{settings.servers_dir ?? '…'}/{template.folder}/{slug || 'name'}/
						</p>
					</div>
				</div>

				{#snippet field(variable: TemplateVariable)}
					<div class={variable.type === 'modrinth-modpack' ? 'sm:col-span-2' : ''}>
						{#if variable.type === 'boolean'}
							<label class="flex h-10 items-center gap-2 text-sm">
								<input
									type="checkbox"
									checked={current(variable.env) === 'true'}
									onchange={(e) => setValue(variable, e.currentTarget.checked ? 'true' : 'false')}
								/>
								{variable.label}
							</label>
						{:else}
							<label class="label" for="cr-{variable.env}">{variable.label}</label>
							{#if variable.type === 'select'}
								<select
									id="cr-{variable.env}"
									class="input"
									value={current(variable.env)}
									onchange={(e) => setValue(variable, e.currentTarget.value)}
								>
									{#each variable.options ?? [] as option (option.value)}
										<option value={option.value}>{option.label ?? option.value}</option>
									{/each}
								</select>
							{:else if variable.type === 'memory'}
								<div class="flex items-center gap-2">
									<input
										id="cr-{variable.env}"
										class="input"
										type="number"
										min="1"
										max="256"
										value={memoryGb(variable)}
										oninput={(e) => setValue(variable, `${e.currentTarget.value || 1}G`)}
									/>
									<span class="text-sm text-ink-2">GB</span>
								</div>
							{:else if variable.type === 'modrinth-modpack'}
								<div class="relative">
									<input
										id="cr-{variable.env}"
										class="input"
										value={packQuery}
										oninput={(e) => searchPacks(variable, e.currentTarget.value)}
										placeholder="Search Modrinth: Cobblemon, Fabulously Optimized…"
										autocomplete="off"
									/>
									{#if packs.length}
										<ul
											class="card absolute inset-x-0 top-11 z-20 max-h-80 overflow-auto p-1 shadow-pop"
										>
											{#each packs as item (item.slug)}
												<li>
													<button
														type="button"
														class="flex w-full items-center gap-3 rounded-lg p-2 text-left hover:bg-surface-2"
														onclick={() => choosePack(variable, item)}
													>
														{#if item.icon_url}
															<img src={item.icon_url} alt="" class="h-9 w-9 rounded-lg" />
														{:else}
															<span class="h-9 w-9 rounded-lg bg-surface-2"></span>
														{/if}
														<span class="min-w-0">
															<span class="block truncate text-sm font-medium">{item.title}</span>
															<span class="block truncate text-xs text-ink-3"
																>{item.versions?.at(-1) ?? ''} · {(
																	item.downloads ?? 0
																).toLocaleString()} downloads</span
															>
														</span>
													</button>
												</li>
											{/each}
										</ul>
									{/if}
								</div>
								{#if pack}
									<p class="meta mt-1.5">
										<Icon name="check" size={14} />{pack.title} ({pack.slug}), Minecraft {pack.versions?.at(
											-1
										) ?? '?'}
									</p>
								{/if}
							{:else}
								<input
									id="cr-{variable.env}"
									class="input {variable.suggest ? 'font-mono' : ''}"
									type={variable.type === 'number' ? 'number' : 'text'}
									value={current(variable.env)}
									oninput={(e) => setValue(variable, e.currentTarget.value)}
									placeholder={variable.placeholder ?? ''}
									list={variable.suggest ? `cr-list-${variable.env}` : undefined}
								/>
								{#if variable.suggest === 'minecraft-versions'}
									<datalist id="cr-list-{variable.env}">
										<option value="LATEST"></option>
										{#each versions as version (version)}<option value={version}></option>{/each}
									</datalist>
								{/if}
							{/if}
						{/if}
						{#if variable.help}<p class="meta mt-1">{variable.help}</p>{/if}
					</div>
				{/snippet}

				<div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
					{#each essentials as variable (variable.env)}{@render field(variable)}{/each}
				</div>

				<div class="border-t border-line pt-4">
					<button
						type="button"
						class="meta hover:text-ink"
						onclick={() => (showAdvanced = !showAdvanced)}
					>
						<Icon name="chevron-down" size={14} class={showAdvanced ? 'rotate-180' : ''} />Advanced
					</button>
					{#if showAdvanced}
						<div class="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
							<div>
								<label class="label" for="cr-tag">Image</label>
								<select
									id="cr-tag"
									class="input"
									bind:value={tag}
									onchange={() => (tagChosen = true)}
								>
									{#each template.tags as item (item.tag)}
										<option value={item.tag}>{item.label} ({template.image}:{item.tag})</option>
									{/each}
								</select>
								<p class="meta mt-1">{template.tags.find((t) => t.tag === tag)?.hint ?? ''}</p>
							</div>
							<div>
								<label class="label" for="cr-port">Game port</label>
								<input
									id="cr-port"
									class="input font-mono"
									type="number"
									min="1"
									max="65535"
									bind:value={port}
								/>
								<p class="meta mt-1">
									Servers of one game share {gamePort} by default; only one of them runs at a time.
								</p>
							</div>
							{#each advanced as variable (variable.env)}{@render field(variable)}{/each}
						</div>
					{:else}
						<p class="meta mt-1">
							Image {template.image}:{tag}, port {port}{advanced.length
								? `, ${advanced.length} more settings`
								: ''}
						</p>
					{/if}
				</div>

				{#if template.eula}
					<label class="flex items-center gap-2 text-sm">
						<input type="checkbox" bind:checked={eula} />
						<span
							>{template.eula.label}
							(<a
								class="text-accent underline"
								href={template.eula.url}
								target="_blank"
								rel="external noreferrer">read it</a
							>)</span
						>
					</label>
				{/if}

				{#if error}<p class="text-sm text-rose-600 dark:text-rose-400">{error}</p>{/if}
				<div class="flex justify-between">
					<button type="button" class="btn-ghost" onclick={() => (step = 0)}>Back</button>
					<button class="btn-primary" type="submit" disabled={missing || previewing}>
						{previewing ? 'Checking…' : 'Review'}
					</button>
				</div>
			</form>
		{:else if step === 2 && template && preview}
			<div class="card space-y-5 p-6">
				<dl class="grid grid-cols-[8rem_1fr] gap-x-4 gap-y-2 text-sm">
					<dt class="text-ink-2">Game</dt>
					<dd>{template.label}</dd>
					<dt class="text-ink-2">Name</dt>
					<dd>{name}</dd>
					<dt class="text-ink-2">Folder</dt>
					<dd class="font-mono">{preview.folder}</dd>
					<dt class="text-ink-2">Container</dt>
					<dd class="font-mono">{preview.container_name}</dd>
					<dt class="text-ink-2">Players connect to</dt>
					<dd class="font-mono">
						{settings.public_address ?? 'this host'}{port && port !== gamePort ? `:${port}` : ''}
						<span class="text-ink-3">({preview.ports.join(', ')})</span>
					</dd>
					{#if preview.secrets.length}
						<dt class="text-ink-2">Secrets</dt>
						<dd>{preview.secrets.join(', ')} generated into .env</dd>
					{/if}
				</dl>

				{#each preview.holders as holder (holder.container_name)}
					<p class="flex gap-2 rounded-xl bg-surface-2 px-3 py-2 text-xs text-ink-2">
						<Icon name="info" size={14} class="mt-0.5 shrink-0" />
						<span>
							{holder.server_name ?? holder.container_name} also uses {holder.ports.join(', ')}
							({holder.running ? 'running' : 'stopped'}). Only one of them can run at a time.
						</span>
					</p>
				{/each}

				<div class="space-y-2">
					<label class="flex items-center gap-2 text-sm">
						<input type="checkbox" bind:checked={startNow} />Start it right away
					</label>
					{#if startNow && runningHolders.length}
						{#if foreignRunning.length}
							<p class="meta pl-6">
								{foreignRunning.map((h) => h.container_name).join(', ')} is not a GameFleet server, so
								the new server will be created stopped. Choose another port to run both.
							</p>
						{:else}
							<label class="flex items-center gap-2 pl-6 text-sm">
								<input type="checkbox" bind:checked={stopConflicting} />
								Stop {runningHolders.map((h) => h.server_name ?? h.container_name).join(', ')} first
							</label>
						{/if}
					{/if}
					<label class="flex items-center gap-2 text-sm">
						<input type="checkbox" bind:checked={isPublic} />Show it to visitors without a login
					</label>
				</div>

				<details class="text-sm">
					<summary class="cursor-pointer text-ink-2">docker-compose.yml</summary>
					<pre
						class="mt-2 overflow-auto rounded-xl bg-surface-2 p-4 font-mono text-xs">{preview.compose}</pre>
				</details>

				{#if preview.problems.length}
					<ul
						class="space-y-1 rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-700 dark:text-rose-300"
					>
						{#each preview.problems as problem (problem)}<li>{problem}</li>{/each}
					</ul>
				{/if}
				{#if error}<p class="text-sm text-rose-600 dark:text-rose-400">{error}</p>{/if}

				<div class="flex justify-between">
					<button class="btn-ghost" onclick={() => (step = 1)}>Back</button>
					<button
						class="btn-primary"
						onclick={create}
						disabled={creating || preview.problems.length > 0}
					>
						<Icon name="rocket" size={16} />{creating ? 'Creating…' : 'Create server'}
					</button>
				</div>
			</div>
		{:else if step === 3 && job}
			<div class="card mt-6 space-y-5 p-6">
				<div>
					<h2 class="font-display text-lg font-semibold">{job.name}</h2>
					<p class="meta font-mono">{job.folder}</p>
				</div>
				<ol class="space-y-2">
					{#each PHASES as [phase, label] (phase)}
						{@const state = phaseState(phase)}
						<li
							class="flex items-center gap-3 text-sm {state === 'todo' || state === 'skipped'
								? 'text-ink-3'
								: ''}"
						>
							<span class="grid h-5 w-5 place-items-center">
								{#if state === 'done'}<Icon name="check" size={16} class="text-emerald-500" />
								{:else if state === 'failed'}<Icon name="x" size={16} class="text-rose-500" />
								{:else if state === 'active'}<span
										class="h-2 w-2 animate-pulse rounded-full bg-accent"
									></span>
								{:else}<span class="h-1.5 w-1.5 rounded-full bg-line-2"></span>{/if}
							</span>
							{label}
							{#if state === 'active' && phase === 'pulling' && job.progress != null}
								<span class="h-1.5 w-40 overflow-hidden rounded-full bg-surface-2">
									<span
										class="block h-full bg-accent"
										style="width: {Math.round(job.progress * 100)}%"
									></span>
								</span>
								<span class="text-xs text-ink-3">{Math.round(job.progress * 100)} %</span>
							{/if}
							{#if state === 'active' && phase === 'waiting' && job.health}
								<span class="text-xs text-ink-3">health: {job.health}</span>
							{/if}
							{#if state === 'skipped'}<span class="text-xs">skipped</span>{/if}
						</li>
					{/each}
				</ol>

				{#if job.phase === 'waiting' && job.ready_hint}<p class="meta">{job.ready_hint}</p>{/if}
				{#if job.log?.length}
					<pre
						class="max-h-72 overflow-auto rounded-xl bg-surface-2 p-4 font-mono text-xs">{job.log.join(
							'\n'
						)}</pre>
				{/if}
				{#if job.warning}
					<p
						class="rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-800 dark:text-amber-300"
					>
						{job.warning}
					</p>
				{/if}
				{#if job.error}
					<p
						class="rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-700 dark:text-rose-300"
					>
						{job.error}
					</p>
				{/if}
				{#if error}<p class="text-sm text-rose-600 dark:text-rose-400">{error}</p>{/if}

				<div class="flex justify-end gap-2">
					<a href={resolve('/main')} class="btn-ghost">Back to servers</a>
					{#if job.server_id}
						<button
							class="btn-primary"
							onclick={() => goto(resolve('/server/[id]', { id: job!.server_id! }))}
						>
							{job.finished_at ? 'Open server' : 'Open server page'}
						</button>
					{/if}
				</div>
			</div>
		{/if}
	{/if}
</div>
