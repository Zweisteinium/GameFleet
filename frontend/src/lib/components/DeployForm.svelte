<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { api } from '$lib/api/ApiService';
	import type { DeployCheckResult, DeployField, DeployJob, DeployTemplate, GameServerPublic, PortIssue } from '$lib/api/Api';
	import { gameLabel } from '$lib/games';
	import GameArt from './GameArt.svelte';
	import Icon from './Icon.svelte';

	interface Props {
		onDeployed: (server: GameServerPublic) => void;
		onCancel: () => void;
	}

	let { onDeployed, onCancel }: Props = $props();

	const POLL_MS = 1500;
	const PHASES: Record<string, string> = {
		queued: 'Starting…',
		pulling: 'Pulling the image…',
		creating: 'Creating the container…',
		starting: 'Starting the server…',
		importing: 'Adding it to GameFleet…',
		done: 'Done',
		failed: 'Failed'
	};

	let templates = $state<DeployTemplate[]>([]);
	let template = $state<DeployTemplate | null>(null);
	let name = $state('');
	let values = $state<Record<string, string | number | boolean>>({});
	// A port without a value stays unpublished (the template's default for RCON ports).
	let hostPorts = $state<Record<string, number | null>>({});
	const published = $derived(
		Object.fromEntries(Object.entries(hostPorts).filter(([, v]) => v != null)) as Record<string, number>
	);
	let isPublic = $state(false);
	let showAdvanced = $state(false);
	let check = $state<DeployCheckResult | null>(null);
	let checking = $state(false);
	let job = $state<DeployJob | null>(null);
	let error = $state<string | null>(null);
	let poll: ReturnType<typeof setTimeout> | undefined;
	let checkTimer: ReturnType<typeof setTimeout> | undefined;

	// 'Game' and 'Access' fields are the ones everyone fills in; the rest sits behind "More options".
	const isBasic = (f: DeployField) => f.group == null || f.group === 'Game' || f.group === 'Access';
	const basicFields = $derived(template?.fields.filter(isBasic) ?? []);
	const advancedFields = $derived(template?.fields.filter((f) => !isBasic(f)) ?? []);
	const conflicts = $derived(check?.conflicts ?? []);
	const warnings = $derived(check?.warnings ?? []);
	const issue = (p: PortIssue) => `${p.label} ${p.port}/${p.protocol} is used by ${p.container} (${p.state}).`;
	const busy = $derived(job != null && job.finished_at == null);
	const canDeploy = $derived(
		template != null &&
			name.trim().length > 0 &&
			!busy &&
			check?.name_free !== false &&
			conflicts.length === 0 &&
			basicFields.every((f) => !f.required || String(values[f.key] ?? '').trim() !== '')
	);

	function detail(err: unknown, fallback: string): string {
		const d = (err as { error?: { detail?: unknown } })?.error?.detail;
		return typeof d === 'string' ? d : fallback;
	}

	function pick(t: DeployTemplate) {
		template = t;
		values = Object.fromEntries(t.fields.filter((f) => f.default != null).map((f) => [f.key, f.default as string]));
		hostPorts = Object.fromEntries(t.ports.map((p) => [p.label, p.default_host_port ?? null]));
		check = null;
		scheduleCheck();
	}

	function scheduleCheck() {
		clearTimeout(checkTimer);
		checkTimer = setTimeout(runCheck, 400);
	}

	async function runCheck() {
		if (!template || !name.trim()) {
			check = null;
			return;
		}
		checking = true;
		try {
			check = (await api.check.checkDeploy({ template: template.id, name: name.trim(), host_ports: published })).data;
		} catch {
			check = null;
		} finally {
			checking = false;
		}
	}

	async function deploy() {
		if (!template) return;
		error = null;
		try {
			job = (
				await api.deployServer({
					template: template.id,
					name: name.trim(),
					host_ports: published,
					values,
					is_public: isPublic,
					start: true
				})
			).data;
			schedulePoll();
		} catch (err) {
			error = detail(err, 'Could not start the deployment.');
		}
	}

	function schedulePoll() {
		clearTimeout(poll);
		poll = setTimeout(pollJob, POLL_MS);
	}

	async function pollJob() {
		if (!job) return;
		try {
			job = (await api.jobs.getDeployJob(job.id)).data;
		} catch {
			return schedulePoll();
		}
		if (job.finished_at == null) return schedulePoll();
		if (job.phase === 'done' && job.server_id) {
			try {
				onDeployed((await api.serverId.getServerById(job.server_id)).data);
			} catch (err) {
				error = detail(err, 'The server was created but could not be loaded; refresh the page.');
			}
		}
	}

	function fieldValue(f: DeployField): string {
		const v = values[f.key];
		return v == null ? '' : String(v);
	}

	onMount(async () => {
		try {
			templates = (await api.templates.getDeployTemplates()).data;
		} catch (err) {
			error = detail(err, 'Could not load the deploy templates.');
		}
	});
	onDestroy(() => {
		clearTimeout(poll);
		clearTimeout(checkTimer);
	});
</script>

{#snippet field(f: DeployField)}
	<div class="min-w-0" title={f.description ?? ''}>
		{#if f.type === 'bool'}
			<label class="flex cursor-pointer items-start gap-3 py-1 text-sm">
				<input
					type="checkbox"
					class="accent-accent mt-0.5 h-4 w-4"
					checked={Boolean(values[f.key])}
					disabled={busy}
					onchange={(e) => (values[f.key] = (e.currentTarget as HTMLInputElement).checked)}
				/>
				<span>
					{f.label}
					{#if f.description}<span class="hint block">{f.description}</span>{/if}
				</span>
			</label>
		{:else}
			<label class="label" for="dep-{f.key}"
				>{f.label}{#if !f.required}<span class="text-ink-3"> · optional</span>{/if}</label
			>
			{#if f.type === 'enum'}
				<div class="relative">
					<select
						id="dep-{f.key}"
						class="input appearance-none pr-8"
						disabled={busy}
						value={fieldValue(f)}
						onchange={(e) => (values[f.key] = (e.currentTarget as HTMLSelectElement).value)}
					>
						{#each f.options ?? [] as option (option)}
							<option value={option}>{option}</option>
						{/each}
					</select>
					<Icon name="chevron-down" size={14} class="text-ink-3 pointer-events-none absolute top-1/2 right-2.5 -translate-y-1/2" />
				</div>
			{:else}
				<input
					id="dep-{f.key}"
					class="input {f.type === 'int' || f.type === 'secret' ? 'font-mono' : ''}"
					type={f.type === 'int' ? 'number' : f.type === 'secret' ? 'password' : 'text'}
					required={f.required}
					disabled={busy}
					autocomplete="off"
					value={fieldValue(f)}
					oninput={(e) => {
						const raw = (e.currentTarget as HTMLInputElement).value;
						values[f.key] = f.type === 'int' ? Number(raw) : raw;
					}}
				/>
			{/if}
			{#if f.description}<p class="hint mt-1">{f.description}</p>{/if}
		{/if}
	</div>
{/snippet}

{#if !template}
	<p class="text-ink-2 mb-4 text-sm">
		Pick a game. GameFleet pulls the image, creates the container with its data under the servers root and adds it here.
	</p>
	{#if error}<p class="notice tone-bad mb-4"><Icon name="alert" size={16} class="mt-0.5 shrink-0" />{error}</p>{/if}
	<div class="grid gap-2 sm:grid-cols-2">
		{#each templates as t (t.id)}
			<button
				class="card hover:border-line-2 flex items-center gap-3 p-3 text-left transition-colors"
				onclick={() => pick(t)}
			>
				<GameArt game={t.game} class="h-14 w-10 shrink-0 rounded-[5px]" />
				<span class="min-w-0">
					<span class="block truncate text-sm font-semibold">{gameLabel(t.game)}</span>
					<span class="hint block truncate font-mono">{t.image}</span>
					{#if t.description}<span class="hint mt-0.5 block line-clamp-2">{t.description}</span>{/if}
				</span>
			</button>
		{/each}
	</div>
	<div class="mt-4 flex justify-end">
		<button class="btn-ghost" onclick={onCancel}>Cancel</button>
	</div>
{:else}
	<form
		class="space-y-4"
		onsubmit={(e) => {
			e.preventDefault();
			deploy();
		}}
	>
		<div class="tile flex items-center gap-3 py-2.5">
			<GameArt game={template.game} class="h-12 w-9 shrink-0 rounded-[5px]" />
			<div class="min-w-0 flex-1">
				<p class="text-sm font-semibold">{gameLabel(template.game)}</p>
				<p class="hint truncate font-mono">{template.image}</p>
			</div>
			{#if !busy}
				<button type="button" class="btn-ghost btn-sm" onclick={() => (template = null)}>Change</button>
			{/if}
		</div>

		<div>
			<label class="label" for="dep-name">Server name</label>
			<input
				id="dep-name"
				class="input"
				type="text"
				bind:value={name}
				oninput={scheduleCheck}
				required
				maxlength="60"
				disabled={busy}
				placeholder="Weekend survival"
			/>
			<p class="hint mt-1">
				Container and folder are named after it:
				<span class="font-mono">{check?.slug ?? (name.trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || '…')}</span>
				{#if check && !check.name_free}<span class="text-bad"> · a container with this name exists</span>{/if}
			</p>
		</div>

		<div class="grid gap-x-4 gap-y-3 sm:grid-cols-2">
			{#each basicFields as f (f.key)}
				{@render field(f)}
			{/each}
		</div>

		<div>
			<p class="label">Ports on this host</p>
			<div class="flex flex-wrap gap-3">
				{#each template.ports as p (p.label)}
					<label class="flex items-center gap-2 text-sm">
						<span class="text-ink-2 w-20 truncate">{p.label}</span>
						<input
							class="input w-24 font-mono"
							type="number"
							min="1"
							max="65535"
							disabled={busy}
							placeholder="off"
							value={hostPorts[p.label] ?? ''}
							oninput={(e) => {
								const raw = (e.currentTarget as HTMLInputElement).value;
								hostPorts[p.label] = raw ? Number(raw) : null;
								scheduleCheck();
							}}
						/>
						<span class="hint">→ {p.container_port}/{p.protocol}</span>
					</label>
				{/each}
			</div>
			{#if conflicts.length}
				<p class="notice tone-bad mt-2 text-xs"><Icon name="alert" size={14} class="mt-0.5 shrink-0" />{conflicts.map(issue).join(' ')}</p>
			{:else if warnings.length}
				<p class="notice tone-warn mt-2 text-xs"><Icon name="info" size={14} class="mt-0.5 shrink-0" />{warnings.map(issue).join(' ')} Both cannot run at the same time.</p>
			{:else if checking}
				<p class="hint mt-2">Checking ports…</p>
			{/if}
		</div>

		{#if advancedFields.length}
			<button type="button" class="btn-ghost btn-sm -ml-2" onclick={() => (showAdvanced = !showAdvanced)}>
				<Icon name="chevron-down" size={14} class={showAdvanced ? 'rotate-180' : ''} />
				{showAdvanced ? 'Fewer options' : `More options (${advancedFields.length})`}
			</button>
			{#if showAdvanced}
				<div class="grid gap-x-4 gap-y-3 sm:grid-cols-2">
					{#each advancedFields as f (f.key)}
						{@render field(f)}
					{/each}
				</div>
			{/if}
		{/if}

		<label class="flex cursor-pointer items-start gap-3 text-sm">
			<input type="checkbox" class="accent-accent mt-0.5 h-4 w-4" bind:checked={isPublic} disabled={busy} />
			<span>Show on the public dashboard</span>
		</label>

		{#if job}
			<div
				class="notice {job.phase === 'failed' ? 'tone-bad' : job.phase === 'done' ? 'tone-ok' : 'tone-accent'}"
			>
				{#if job.finished_at == null}
					<Icon name="refresh" size={16} class="mt-0.5 shrink-0 animate-spin" />
				{:else}
					<Icon name={job.phase === 'failed' ? 'alert' : 'check'} size={16} class="mt-0.5 shrink-0" />
				{/if}
				<div class="min-w-0 flex-1">
					<p class="font-medium">{PHASES[job.phase ?? 'queued'] ?? job.phase}</p>
					{#if job.detail}<p class="text-xs">{job.detail}</p>{/if}
					{#if job.error}<p class="text-xs">{job.error}</p>{/if}
					{#if job.phase === 'pulling' && job.progress != null}
						<div class="track mt-2">
							<div class="h-full rounded-full bg-accent transition-all" style="width: {job.progress * 100}%"></div>
						</div>
					{/if}
				</div>
			</div>
		{/if}
		{#if error}<p class="notice tone-bad"><Icon name="alert" size={16} class="mt-0.5 shrink-0" />{error}</p>{/if}

		<div class="flex justify-end gap-2 pt-1">
			<button type="button" class="btn-ghost" onclick={onCancel} disabled={busy}>
				{job?.phase === 'failed' ? 'Close' : 'Cancel'}
			</button>
			<button type="submit" class="btn-primary" disabled={!canDeploy}>
				<Icon name="package" size={15} />{busy ? 'Deploying…' : 'Deploy'}
			</button>
		</div>
	</form>
{/if}
