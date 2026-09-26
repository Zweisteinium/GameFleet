<script lang="ts">
	import { onDestroy } from 'svelte';
	import { api } from '$lib/api/ApiService';
	import { session } from '$lib/auth.svelte';
	import { GameServerType, type BackupInfo, type BackupJob, type GameServerPublic, type Snapshot } from '$lib/api/Api';
	import { formatBytes } from '$lib/gameinfo';
	import { confirmDialog } from '$lib/confirm.svelte';
	import Icon from './Icon.svelte';
	import Modal from './Modal.svelte';
	import Skeleton from './Skeleton.svelte';

	interface Props {
		server: GameServerPublic;
		/** Container state from the host panel; decides what a restore has to do first. */
		running: boolean;
		/** Called when a job finished so the page can re-query the server. */
		onChanged: () => void;
	}

	let { server, running, onChanged }: Props = $props();

	const POLL_MS = 2000;
	const PHASES: Record<BackupJob['phase'], string> = {
		stopping: 'Stopping the server…',
		snapshot: 'Backing up the current world…',
		applying: 'Applying the backup…',
		starting: 'Starting the server…',
		done: 'Done',
		failed: 'Failed'
	};

	let info = $state<BackupInfo | null>(null);
	let loadError = $state<string | null>(null);
	let error = $state<string | null>(null);
	let fileInput = $state<HTMLInputElement>();
	// A restore waiting for confirmation: an uploaded file or one of the snapshots.
	let pending = $state<{ file?: File; snapshot?: string } | null>(null);
	let keepCopy = $state(true);
	let uploadProgress = $state<number | null>(null);
	let poll: ReturnType<typeof setTimeout> | undefined;

	const job = $derived(info?.job ?? null);
	const snapshots = $derived(info?.snapshots ?? []);
	const busy = $derived((job != null && job.finished_at == null) || uploadProgress != null);
	const pendingName = $derived(pending?.file?.name ?? pending?.snapshot ?? '');

	function detail(err: unknown, fallback: string): string {
		const d = (err as { error?: { detail?: unknown } })?.error?.detail;
		return typeof d === 'string' ? d : fallback;
	}

	export async function load() {
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
		// Finished: the snapshot list changed, and so may the container state.
		await load();
		onChanged();
	}

	function track(started: BackupJob) {
		if (info) info.job = started;
		schedulePoll();
	}

	async function snapshotNow() {
		error = null;
		if (running && server.game !== GameServerType.Minecraft) {
			const go = await confirmDialog({
				title: 'Back up while running',
				message: `"${server.name}" is running. A save the game writes at that moment may be incomplete.`,
				note: 'Stop the server first for a backup that is guaranteed to be consistent.',
				confirmLabel: 'Back up anyway'
			});
			if (!go) return;
		}
		try {
			track((await api.serverId.createSnapshot(server.id)).data);
		} catch (err) {
			error = detail(err, 'Could not start the backup.');
		}
	}

	function pickFile() {
		error = null;
		fileInput?.click();
	}

	function onFilePicked(event: Event) {
		const input = event.currentTarget as HTMLInputElement;
		const file = input.files?.[0];
		input.value = '';
		if (file) {
			keepCopy = true;
			pending = { file };
		}
	}

	function uploadRestore(file: File): Promise<BackupJob> {
		const params = new URLSearchParams({ filename: file.name, keep_copy: String(keepCopy) });
		const url = `/api/servers/${encodeURIComponent(server.id)}/backups/restore?${params}`;
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
					await api.serverId.restoreSnapshot(server.id, source.snapshot!, { keep_copy: keepCopy })
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

	async function remove(snapshot: Snapshot) {
		const go = await confirmDialog({
			title: 'Delete snapshot',
			message: `Delete "${snapshot.file}"?`,
			note: 'It is removed from the server; there is no undo.',
			confirmLabel: 'Delete',
			tone: 'danger'
		});
		if (!go) return;
		error = null;
		try {
			await api.serverId.deleteSnapshot(server.id, snapshot.file);
			if (info) info.snapshots = snapshots.filter((s) => s.file !== snapshot.file);
		} catch (err) {
			error = detail(err, 'Could not delete the snapshot.');
		}
	}

	function downloadUrl(snapshot: Snapshot): string {
		const base = `/api/servers/${encodeURIComponent(server.id)}/backups/${encodeURIComponent(snapshot.file)}`;
		return session.token ? `${base}?token=${encodeURIComponent(session.token)}` : base;
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
				<span class="text-ink-3 font-mono text-sm font-normal">{info.world}</span>
			{/if}
		</h3>
		{#if info?.supported}
			<div class="flex items-center gap-2">
				<button class="btn-outline h-8 px-3 text-xs" onclick={snapshotNow} disabled={busy}>
					<Icon name="archive" size={14} />Back up now
				</button>
				<button class="btn-primary h-8 px-3 text-xs" onclick={pickFile} disabled={busy}>
					<Icon name="upload" size={14} />Restore from file
				</button>
				<input
					type="file"
					class="hidden"
					accept={info.accept ?? undefined}
					bind:this={fileInput}
					onchange={onFilePicked}
				/>
			</div>
		{/if}
	</div>

	{#if error || loadError}
		<p
			class="mb-4 flex items-center gap-2 rounded-xl bg-rose-500/10 px-3 py-2 text-sm text-rose-700 dark:text-rose-400"
		>
			<Icon name="alert" size={16} />{error ?? loadError}
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
						{job.action === 'snapshot' ? 'Backup' : 'Restore'} of
						<span class="font-mono">{job.source}</span>: {PHASES[job.phase]}
					</p>
					{#if job.error}<p class="text-xs">{job.error}</p>{/if}
					{#if job.phase === 'done' && job.action === 'restore'}
						<p class="text-xs">
							{job.restarted ? 'The server was started again.' : 'The server stays stopped.'}
							{#if job.snapshot}The previous world was kept as {job.snapshot}.{/if}
						</p>
					{:else if job.phase === 'failed' && job.action === 'restore' && !job.restarted}
						<p class="text-xs">The server was left stopped so you can look at its data.</p>
					{/if}
					{#if job.warning}<p class="text-xs">{job.warning}</p>{/if}
					{#if job.finished_at == null}
						<p class="text-xs opacity-80">Large worlds take a few minutes.</p>
					{/if}
				</div>
			</div>
		{/if}

		{#if snapshots.length === 0}
			<p class="text-ink-3 py-4 text-center text-sm">
				No snapshots yet. <span class="font-medium">Back up now</span> writes a tar.gz of the world to
				<span class="font-mono">{server.data_path}/gamefleet-backups</span> inside the container.
			</p>
		{:else}
			<ul class="space-y-1.5">
				{#each snapshots as snapshot (snapshot.file)}
					<li class="bg-surface-2 flex items-center gap-3 rounded-xl px-3 py-2">
						<Icon name="hard-drive" size={16} class="text-ink-3 shrink-0" />
						<div class="min-w-0 flex-1">
							<p class="truncate font-mono text-sm">{snapshot.file}</p>
							<p class="text-ink-3 text-xs">{formatBytes(snapshot.size)} · {when(snapshot.created)}</p>
						</div>
						<button
							class="btn-outline h-8 px-2.5 text-xs"
							title="Restore this snapshot"
							disabled={busy}
							onclick={() => {
								keepCopy = true;
								pending = { snapshot: snapshot.file };
							}}
						>
							<Icon name="history" size={14} />Restore
						</button>
						<a
							class="btn-ghost btn-icon h-8 w-8"
							href={downloadUrl(snapshot)}
							download={snapshot.file}
							rel="external"
							title="Download"
							aria-label="Download {snapshot.file}"><Icon name="download" size={15} /></a
						>
						<button
							class="btn-ghost btn-icon h-8 w-8 text-rose-500"
							title="Delete"
							aria-label="Delete {snapshot.file}"
							disabled={busy}
							onclick={() => remove(snapshot)}
						>
							<Icon name="trash" size={15} />
						</button>
					</li>
				{/each}
			</ul>
		{/if}
		<p class="text-ink-3 mt-3 text-xs">
			Snapshots live in <span class="font-mono">{server.data_path}/gamefleet-backups</span>, next to the
			server's data.
		</p>
	{/if}
</section>

{#if pending && info}
	<Modal title="Restore backup" onClose={() => uploadProgress == null && (pending = null)}>
		<div class="space-y-4 text-sm">
			<div class="bg-surface-2 flex items-center gap-3 rounded-xl px-3 py-2.5">
				<Icon name={pending.file ? 'upload' : 'history'} size={18} class="text-ink-3 shrink-0" />
				<div class="min-w-0">
					<p class="truncate font-mono">{pendingName}</p>
					<p class="text-ink-3 text-xs">
						{#if pending.file}{formatBytes(pending.file.size)}{:else}snapshot on the server{/if}
						→ <span class="font-mono">{info.target}</span>
					</p>
				</div>
			</div>
			{#if pending.file}
				<p class="text-ink-2 text-xs">{info.hint}</p>
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
						>A snapshot is taken before anything is replaced, so this restore can be undone.</span
					>
				</span>
			</label>
			{#if uploadProgress != null}
				<div>
					<p class="text-ink-2 mb-1 text-xs">Uploading… {Math.round(uploadProgress * 100)}%</p>
					<div class="bg-surface-3 h-1.5 overflow-hidden rounded-full">
						<div class="h-full rounded-full bg-accent transition-all" style="width: {uploadProgress * 100}%"></div>
					</div>
				</div>
			{/if}
			{#if error}
				<p class="flex items-center gap-2 rounded-xl bg-rose-500/10 px-3 py-2 text-rose-700 dark:text-rose-400">
					<Icon name="alert" size={16} />{error}
				</p>
			{/if}
			<div class="flex justify-end gap-2 pt-1">
				<button class="btn-ghost h-9" onclick={() => (pending = null)} disabled={uploadProgress != null}>
					Cancel
				</button>
				<button class="btn-danger h-9" onclick={confirmRestore} disabled={uploadProgress != null}>
					<Icon name="history" size={15} />{uploadProgress != null ? 'Uploading…' : 'Restore'}
				</button>
			</div>
		</div>
	</Modal>
{/if}
