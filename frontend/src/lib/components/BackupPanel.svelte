<script lang="ts">
	import { onDestroy } from 'svelte';
	import { api } from '$lib/api/ApiService';
	import { session } from '$lib/auth.svelte';
	import type { Backup, BackupInfo, BackupJob, GameServerPublic } from '$lib/api/Api';
	import { formatBytes } from '$lib/gameinfo';
	import Icon from './Icon.svelte';
	import Modal from './Modal.svelte';
	import Skeleton from './Skeleton.svelte';

	interface Props {
		server: GameServerPublic;
		/** Container state from the host panel; decides what a restore has to do first. */
		running: boolean;
		/** Called when a restore finished so the page can re-query the server. */
		onChanged: () => void;
	}

	let { server, running, onChanged }: Props = $props();

	const POLL_MS = 2000;
	const PHASES: Record<BackupJob['phase'], string> = {
		preparing: 'Copying and checking the backup…',
		stopping: 'Stopping the server…',
		snapshot: 'Keeping a copy of the current world…',
		applying: 'Applying the backup…',
		starting: 'Starting the server…',
		done: 'Done',
		failed: 'Failed'
	};

	let info = $state<BackupInfo | null>(null);
	let loadError = $state<string | null>(null);
	let error = $state<string | null>(null);
	let fileInput = $state<HTMLInputElement>();
	// A restore waiting for confirmation: an uploaded file or one of the listed backups.
	let pending = $state<{ file?: File; backup?: Backup } | null>(null);
	let keepCopy = $state(true);
	let matchConfirmed = $state(false);
	let uploadProgress = $state<number | null>(null);
	let poll: ReturnType<typeof setTimeout> | undefined;

	const job = $derived(info?.job ?? null);
	const backups = $derived(info?.backups ?? []);
	/** Backups grouped by the folder they live in, GameFleet's own copies last. */
	const groups = $derived.by(() => {
		const byFolder: Record<string, Backup[]> = {};
		for (const b of backups) {
			const key = b.gamefleet ? 'Copies kept before a restore' : b.folder;
			(byFolder[key] ??= []).push(b);
		}
		return Object.entries(byFolder).sort(
			([a], [b]) => Number(a.startsWith('Copies')) - Number(b.startsWith('Copies'))
		);
	});
	// Hundreds of backups bury the page: only the newest few are shown until asked for all.
	const NEWEST = 3;
	let showAll = $state(false);
	const newest = $derived(
		[...backups].sort((a, b) => (a.created < b.created ? 1 : a.created > b.created ? -1 : 0)).slice(0, NEWEST)
	);
	const busy = $derived((job != null && job.finished_at == null) || uploadProgress != null);
	const modpack = $derived(
		server.modpack_name
			? `${server.modpack_name}${server.modpack_version ? ` ${server.modpack_version}` : ''}`
			: null
	);

	function detail(err: unknown, fallback: string): string {
		const d = (err as { error?: { detail?: unknown } })?.error?.detail;
		return typeof d === 'string' ? d : fallback;
	}

	async function load() {
		try {
			info = (await api.serverId.getBackups(server.id)).data;
			loadError = null;
		} catch (err) {
			loadError = detail(err, 'Could not read the backups of this server.');
		}
		if (info?.job && info.job.finished_at == null) schedulePoll();
	}

	function schedulePoll() {
		clearTimeout(poll);
		poll = setTimeout(pollJob, POLL_MS);
	}

	async function pollJob() {
		try {
			const current = (await api.serverId.getBackupJob(server.id)).data;
			if (info) info.job = current;
			if (current && current.finished_at == null) return schedulePoll();
		} catch {
			return schedulePoll();
		}
		// Finished: a copy may have been added, and the container state changed.
		await load();
		onChanged();
	}

	function track(started: BackupJob) {
		if (info) info.job = started;
		schedulePoll();
	}

	function open(source: { file?: File; backup?: Backup }) {
		error = null;
		keepCopy = true;
		matchConfirmed = false;
		pending = source;
	}

	function onFilePicked(event: Event) {
		const input = event.currentTarget as HTMLInputElement;
		const file = input.files?.[0];
		input.value = '';
		if (file) open({ file });
	}

	function uploadRestore(file: File): Promise<BackupJob> {
		const params = new URLSearchParams({ filename: file.name, keep_copy: String(keepCopy) });
		const url = `/api/servers/${encodeURIComponent(server.id)}/backups/upload?${params}`;
		// fetch() cannot report upload progress, so this one call goes through XHR.
		return new Promise((resolve, reject) => {
			const xhr = new XMLHttpRequest();
			xhr.open('POST', url);
			// Never a form content type, which SvelteKit's CSRF check would refuse.
			xhr.setRequestHeader('Content-Type', 'application/octet-stream');
			if (session.token) xhr.setRequestHeader('Authorization', `Bearer ${session.token}`);
			xhr.upload.onprogress = (e) => {
				if (e.lengthComputable) uploadProgress = e.loaded / e.total;
			};
			xhr.onload = () => {
				let body: { detail?: unknown } = {};
				try {
					body = JSON.parse(xhr.responseText);
				} catch {
					// not JSON: the proxy or a body-size limit answered
				}
				if (xhr.status >= 200 && xhr.status < 300) resolve(body as BackupJob);
				else
					reject(
						new Error(
							typeof body.detail === 'string'
								? body.detail
								: xhr.status === 413
									? 'The file is larger than the frontend accepts (BODY_SIZE_LIMIT).'
									: `Upload failed (${xhr.status}).`
						)
					);
			};
			xhr.onerror = () => reject(new Error('Upload failed: connection lost.'));
			xhr.send(file);
		});
	}

	async function confirmRestore() {
		if (!pending) return;
		const source = pending;
		error = null;
		try {
			let started: BackupJob;
			if (source.file) {
				uploadProgress = 0;
				started = await uploadRestore(source.file);
			} else {
				started = (
					await api.serverId.restoreBackup(server.id, {
						path: source.backup!.path,
						keep_copy: keepCopy
					})
				).data;
			}
			pending = null;
			track(started);
		} catch (err) {
			error = err instanceof Error ? err.message : detail(err, 'Could not start the restore.');
		} finally {
			uploadProgress = null;
		}
	}

	/** Downloads go through a short-lived link token, so the session token never appears in a URL. */
	async function download(backup: Backup) {
		error = null;
		try {
			const { token } = (await api.serverId.createDownloadToken(server.id, { path: backup.path })).data;
			const params = new URLSearchParams({ path: backup.path, dl: token });
			const link = document.createElement('a');
			link.href = `/api/servers/${encodeURIComponent(server.id)}/backups/download?${params}`;
			link.download = backup.file;
			link.rel = 'external';
			document.body.appendChild(link);
			link.click();
			link.remove();
		} catch (err) {
			error = detail(err, 'Could not prepare the download.');
		}
	}

	const when = (unix: number) =>
		new Date(unix * 1000).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });

	$effect(() => {
		load();
	});
	onDestroy(() => clearTimeout(poll));
</script>

<section class="card p-5">
	<div class="mb-4 flex flex-wrap items-center justify-between gap-3">
		<h3 class="section-title">
			<Icon name="archive" size={16} class="text-ink-3" />Backups
			{#if info?.supported}
				<span class="text-ink-3 text-sm font-normal">({backups.length})</span>
			{/if}
		</h3>
		{#if info?.supported}
			<button class="btn-outline btn-sm" onclick={() => fileInput?.click()} disabled={busy}>
				<Icon name="upload" size={14} />Restore from file
			</button>
			<input
				type="file"
				class="hidden"
				accept={info.accept ?? undefined}
				bind:this={fileInput}
				onchange={onFilePicked}
			/>
		{/if}
	</div>

	{#if loadError}
		<p class="notice tone-bad mb-4"><Icon name="alert" size={16} class="mt-0.5 shrink-0" />{loadError}</p>
	{/if}

	{#if !info}
		{#if !loadError}
			<Skeleton class="h-5 w-64" />
		{/if}
	{:else if !info.supported}
		<p class="text-ink-2 text-sm">{info.reason}</p>
	{:else}
		{#if job}
			<div
				class="notice mb-4 {job.phase === 'failed'
					? 'tone-bad'
					: job.phase === 'done'
						? 'tone-ok'
						: 'tone-accent'}"
			>
				{#if job.finished_at == null}
					<Icon name="refresh" size={16} class="mt-0.5 animate-spin" />
				{:else}
					<Icon name={job.phase === 'failed' ? 'alert' : 'check'} size={16} class="mt-0.5" />
				{/if}
				<div class="min-w-0">
					<p class="font-medium">
						Restore of <span class="font-mono">{job.source}</span>: {PHASES[job.phase]}
					</p>
					{#if job.error}<p class="text-xs">{job.error}</p>{/if}
					{#if job.phase === 'done'}
						<p class="text-xs">
							{job.restarted ? 'The server was started again.' : 'The server stays stopped.'}
							{#if job.snapshot}The previous world was kept as {job.snapshot}.{/if}
						</p>
					{:else if job.phase === 'failed' && !job.restarted}
						<p class="text-xs">If the world was already being replaced, the server was left stopped.</p>
					{/if}
					{#if job.warning}<p class="text-xs">{job.warning}</p>{/if}
					{#if job.finished_at == null}
						<p class="text-xs opacity-80">Large worlds take a few minutes.</p>
					{/if}
				</div>
			</div>
		{/if}

		{#if backups.length === 0}
			<p class="hint py-4 text-center">
				No backups found. The server's own backups are listed here once it has written some.
			</p>
		{:else}
			{#if !showAll}
				<p class="caption mb-1.5">Newest</p>
				<ul class="divide-line border-line divide-y rounded-[var(--radius-control)] border">
					{#each newest as backup (backup.path)}
						{@render row(backup, true)}
					{/each}
				</ul>
			{:else}
				<div class="space-y-4">
					{#each groups as [folder, items] (folder)}
						<div>
							<p class="caption mb-1.5 flex items-center gap-1.5">
								<Icon name="folder" size={12} />
								{#if folder.startsWith('Copies')}{folder}{:else}<span class="font-mono normal-case"
										>{folder}</span
									>{/if}
								<span class="text-ink-3 font-normal">({items.length})</span>
							</p>
							<ul class="divide-line border-line divide-y rounded-[var(--radius-control)] border">
								{#each items as backup (backup.path)}
									{@render row(backup, false)}
								{/each}
							</ul>
						</div>
					{/each}
				</div>
			{/if}
			{#if backups.length > NEWEST}
				<button class="btn-ghost btn-sm mt-2 -ml-2" onclick={() => (showAll = !showAll)}>
					<Icon name={showAll ? 'chevron-up' : 'chevron-down'} size={14} />
					{showAll ? 'Show only the newest' : `Show all (${backups.length})`}
				</button>
			{/if}
		{/if}
		{#if info.locations?.length}
			<p class="hint mt-3">
				Searched <span class="font-mono">{info.locations.join(', ')}</span> in the container.
			</p>
		{/if}
	{/if}
</section>

{#snippet row(backup: Backup, withFolder: boolean)}
	<li class="flex items-center gap-3 px-3 py-2">
		<div class="min-w-0 flex-1">
			<p class="truncate font-mono text-sm" title={backup.path}>{backup.file}</p>
			<p class="hint">
				{when(backup.created)} · {formatBytes(backup.size)}{#if withFolder}
					· <span class="font-mono"
						>{backup.gamefleet ? 'copy kept before a restore' : backup.folder}</span
					>{/if}
			</p>
		</div>
		<button
			class="btn-outline btn-sm"
			title="Restore this backup"
			disabled={busy}
			onclick={() => open({ backup })}
		>
			<Icon name="history" size={14} />Restore
		</button>
		<button
			class="btn-ghost btn-icon h-8 w-8"
			title="Download"
			aria-label="Download {backup.file}"
			onclick={() => download(backup)}><Icon name="download" size={15} /></button
		>
	</li>
{/snippet}

{#if pending && info}
	<Modal title="Restore backup" onClose={() => uploadProgress == null && (pending = null)}>
		<div class="space-y-4 text-sm">
			<div class="tile flex items-center gap-3 py-2.5">
				<Icon name={pending.file ? 'upload' : 'history'} size={18} class="text-ink-3 shrink-0" />
				<div class="min-w-0">
					<p class="truncate font-mono">{pending.file?.name ?? pending.backup?.file}</p>
					<p class="text-ink-3 text-xs">
						{#if pending.file}
							{formatBytes(pending.file.size)} from this computer
						{:else if pending.backup}
							{when(pending.backup.created)} · {formatBytes(pending.backup.size)}
						{/if}
						→ <span class="font-mono">{info.target}</span>
					</p>
				</div>
			</div>

			{#if pending.file}
				<div class="notice tone-warn block py-2.5">
					<p class="flex items-center gap-2 font-medium">
						<Icon name="alert" size={16} />Make sure this backup fits the server
					</p>
					<p class="mt-1 text-xs">
						It must come from the same game version{modpack
							? ` and modpack (${modpack})`
							: ' and the same mods'} as "{server.name}". A world from another version or modpack can
						fail to load, or be damaged for good when the server opens it.
					</p>
				</div>
				<p class="hint">{info.hint}</p>
			{:else}
				<p class="hint">
					A backup made before a game or modpack update may not load on the version the server runs
					now.
				</p>
			{/if}

			<p>
				{#if running}
					<span class="font-medium">"{server.name}" is running.</span> It will be stopped, the backup
					applied and the server started again. Players will be disconnected.
				{:else}
					The backup replaces the current world; the server stays stopped.
				{/if}
			</p>
			<label class="flex cursor-pointer items-start gap-3">
				<input
					type="checkbox"
					class="accent-accent mt-0.5 h-4 w-4"
					bind:checked={keepCopy}
					disabled={uploadProgress != null}
				/>
				<span>
					Keep a copy of the current world first
					<span class="text-ink-3 block text-xs"
						>Saved as a tar.gz in <span class="font-mono">{server.data_path}/gamefleet-backups</span>
						and listed here, so this restore can be undone.</span
					>
				</span>
			</label>
			{#if pending.file}
				<label class="flex cursor-pointer items-start gap-3">
					<input
						type="checkbox"
						class="accent-accent mt-0.5 h-4 w-4"
						bind:checked={matchConfirmed}
						disabled={uploadProgress != null}
					/>
					<span
						>I checked that this file matches the server's game version{modpack
							? ' and modpack'
							: ''}.</span
					>
				</label>
			{/if}
			{#if uploadProgress != null}
				<div>
					<p class="text-ink-2 mb-1 text-xs">Uploading… {Math.round(uploadProgress * 100)}%</p>
					<div class="track">
						<div class="h-full rounded-full bg-accent transition-all" style="width: {uploadProgress * 100}%"></div>
					</div>
				</div>
			{/if}
			{#if error}
				<p class="notice tone-bad"><Icon name="alert" size={16} class="mt-0.5 shrink-0" />{error}</p>
			{/if}
			<div class="flex justify-end gap-2 pt-1">
				<button
					class="btn-ghost h-9"
					onclick={() => (pending = null)}
					disabled={uploadProgress != null}
				>
					Cancel
				</button>
				<button
					class="btn-danger h-9"
					onclick={confirmRestore}
					disabled={uploadProgress != null || (pending.file != null && !matchConfirmed)}
				>
					<Icon name="history" size={15} />{uploadProgress != null ? 'Uploading…' : 'Restore'}
				</button>
			</div>
		</div>
	</Modal>
{/if}
