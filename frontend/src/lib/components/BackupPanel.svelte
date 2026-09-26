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
	const SHOWN = 8;
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
	let showAll = $state(false);
	let uploadProgress = $state<number | null>(null);
	let poll: ReturnType<typeof setTimeout> | undefined;

	const job = $derived(info?.job ?? null);
	const backups = $derived(info?.backups ?? []);
	const shown = $derived(showAll ? backups : backups.slice(0, SHOWN));
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

	function downloadUrl(backup: Backup): string {
		const params = new URLSearchParams(
			session.token ? { path: backup.path, token: session.token } : { path: backup.path }
		);
		return `/api/servers/${encodeURIComponent(server.id)}/backups/download?${params}`;
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
				<span class="text-ink-3 font-sans text-sm font-normal">({backups.length})</span>
			{/if}
		</h3>
		{#if info?.supported}
			<button class="btn-outline h-8 px-3 text-xs" onclick={() => fileInput?.click()} disabled={busy}>
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
		<p
			class="mb-4 flex items-center gap-2 rounded-xl bg-rose-500/10 px-3 py-2 text-sm text-rose-700 dark:text-rose-400"
		>
			<Icon name="alert" size={16} />{loadError}
		</p>
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
				class="mb-4 flex items-start gap-3 rounded-xl px-3 py-2.5 text-sm {job.phase === 'failed'
					? 'bg-rose-500/10 text-rose-700 dark:text-rose-400'
					: job.phase === 'done'
						? 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-400'
						: 'bg-accent-soft text-accent'}"
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
			<p class="text-ink-3 py-4 text-center text-sm">
				No backups found. The server's own backups are listed here once it has written some.
			</p>
		{:else}
			<ul class="space-y-1.5">
				{#each shown as backup (backup.path)}
					<li class="bg-surface-2 flex items-center gap-3 rounded-xl px-3 py-2">
						<Icon name="hard-drive" size={16} class="text-ink-3 shrink-0" />
						<div class="min-w-0 flex-1">
							<p class="truncate font-mono text-sm" title={backup.path}>{backup.file}</p>
							<p class="text-ink-3 text-xs">
								{when(backup.created)} · {formatBytes(backup.size)} ·
								{#if backup.gamefleet}copy kept before a restore{:else}<span class="font-mono"
										>{backup.folder}</span
									>{/if}
							</p>
						</div>
						<button
							class="btn-outline h-8 px-2.5 text-xs"
							title="Restore this backup"
							disabled={busy}
							onclick={() => open({ backup })}
						>
							<Icon name="history" size={14} />Restore
						</button>
						<a
							class="btn-ghost btn-icon h-8 w-8"
							href={downloadUrl(backup)}
							download={backup.file}
							rel="external"
							title="Download"
							aria-label="Download {backup.file}"><Icon name="download" size={15} /></a
						>
					</li>
				{/each}
			</ul>
			{#if backups.length > SHOWN}
				<button class="btn-ghost mt-2 h-8 px-3 text-xs" onclick={() => (showAll = !showAll)}>
					<Icon name="chevron-down" size={14} class={showAll ? 'rotate-180' : ''} />
					{showAll ? 'Show fewer' : `Show all ${backups.length}`}
				</button>
			{/if}
		{/if}
		{#if info.locations?.length}
			<p class="text-ink-3 mt-3 text-xs">
				Searched <span class="font-mono">{info.locations.join(', ')}</span> in the container.
			</p>
		{/if}
	{/if}
</section>

{#if pending && info}
	<Modal title="Restore backup" onClose={() => uploadProgress == null && (pending = null)}>
		<div class="space-y-4 text-sm">
			<div class="bg-surface-2 flex items-center gap-3 rounded-xl px-3 py-2.5">
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
				<div class="rounded-xl bg-amber-500/10 px-3 py-2.5 text-amber-800 dark:text-amber-300">
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
				<p class="text-ink-2 text-xs">{info.hint}</p>
			{:else}
				<p class="text-ink-2 text-xs">
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
					<div class="bg-surface-3 h-1.5 overflow-hidden rounded-full">
						<div
							class="h-full rounded-full bg-accent transition-all"
							style="width: {uploadProgress * 100}%"
						></div>
					</div>
				</div>
			{/if}
			{#if error}
				<p
					class="flex items-center gap-2 rounded-xl bg-rose-500/10 px-3 py-2 text-rose-700 dark:text-rose-400"
				>
					<Icon name="alert" size={16} />{error}
				</p>
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
