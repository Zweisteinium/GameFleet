<script lang="ts">
	import type { GameServerPublic, HostStats } from '$lib/api/Api';
	import { formatBytes, formatUptime, hostStateLabel, hostTone } from '$lib/gameinfo';
	import Icon from './Icon.svelte';
	import Skeleton from './Skeleton.svelte';

	type PowerAction = 'start' | 'stop' | 'restart';

	interface Props {
		server: GameServerPublic;
		stats?: HostStats;
		onPower: (action: PowerAction) => Promise<void>;
	}

	let { server, stats, onPower }: Props = $props();

	let busy = $state<PowerAction | null>(null);
	let error = $state<string | null>(null);

	const tones = {
		neutral: 'bg-surface-2 text-ink-2',
		accent: 'bg-accent-soft text-accent',
		success: 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-400',
		danger: 'bg-rose-500/10 text-rose-700 dark:text-rose-400',
		warning: 'bg-amber-500/10 text-amber-700 dark:text-amber-400'
	};
	const bars = {
		neutral: 'bg-ink-3',
		accent: 'bg-accent',
		success: 'bg-emerald-500',
		danger: 'bg-rose-500',
		warning: 'bg-amber-500'
	};

	const running = $derived(stats?.state === 'running');
	const cpuRatio = $derived(
		stats?.cpu_percent != null && stats.cpu_limit
			? Math.min(1, stats.cpu_percent / (stats.cpu_limit * 100))
			: 0
	);
	const memRatio = $derived(
		stats?.memory_used != null && stats.memory_limit
			? Math.min(1, stats.memory_used / stats.memory_limit)
			: 0
	);
	const usageTone = (ratio: number) =>
		ratio >= 0.9 ? 'danger' : ratio >= 0.7 ? 'warning' : 'success';

	async function run(action: PowerAction) {
		const prompts: Record<PowerAction, string | null> = {
			start: null,
			stop: `Stop "${server.name}"? Players will be disconnected.`,
			restart: `Restart "${server.name}"? Players will be disconnected.`
		};
		if (prompts[action] && !confirm(prompts[action])) return;
		busy = action;
		error = null;
		try {
			await onPower(action);
		} catch (err) {
			const detail = (err as { error?: { detail?: string } })?.error?.detail;
			error = detail ?? `Could not ${action} the container.`;
		} finally {
			busy = null;
		}
	}
</script>

<section class="card p-5">
	<div class="mb-4 flex flex-wrap items-center justify-between gap-3">
		<h3 class="section-title">
			<Icon name="box" size={16} class="text-ink-3" />Host container
			<span class="text-ink-3 font-mono text-sm font-normal">{server.container_name}</span>
		</h3>
		<div class="flex items-center gap-2">
			{#if stats}
				<span
					class="inline-flex h-7 items-center gap-1.5 rounded-full px-2.5 text-xs font-medium {tones[
						hostTone(stats.state)
					]}"
				>
					<span class="h-1.5 w-1.5 rounded-full bg-current"></span>{hostStateLabel(stats)}
				</span>
			{:else}
				<Skeleton class="h-7 w-20 rounded-full" />
			{/if}
			{#if stats && stats.state !== 'missing'}
				{#if running}
					<button
						class="btn-outline h-8 px-3 text-xs"
						onclick={() => run('restart')}
						disabled={busy !== null}
					>
						<Icon name="rotate-cw" size={14} class={busy === 'restart' ? 'animate-spin' : ''} />
						{busy === 'restart' ? 'Restarting…' : 'Restart'}
					</button>
					<button
						class="btn-danger h-8 px-3 text-xs"
						onclick={() => run('stop')}
						disabled={busy !== null}
					>
						<Icon name="square" size={14} />{busy === 'stop' ? 'Stopping…' : 'Stop'}
					</button>
				{:else}
					<button
						class="btn-primary h-8 px-3 text-xs"
						onclick={() => run('start')}
						disabled={busy !== null}
					>
						<Icon name="play" size={14} />{busy === 'start' ? 'Starting…' : 'Start'}
					</button>
				{/if}
			{/if}
		</div>
	</div>

	{#if error}
		<p
			class="mb-4 flex items-center gap-2 rounded-xl bg-rose-500/10 px-3 py-2 text-sm text-rose-700 dark:text-rose-400"
		>
			<Icon name="alert" size={16} />{error}
		</p>
	{/if}

	{#if stats?.error && stats.state === 'missing'}
		<p class="text-ink-2 text-sm">
			No container named <span class="font-mono">{server.container_name}</span> exists any more. Remove
			this server or recreate the container with the same name.
		</p>
	{:else}
		<div class="grid grid-cols-2 gap-3 lg:grid-cols-4">
			<!-- CPU -->
			<div class="bg-surface-2 rounded-xl px-3 py-2.5">
				<p class="text-ink-3 flex items-center gap-1.5 text-[11px] font-semibold tracking-wide uppercase">
					<Icon name="cpu" size={12} />CPU
				</p>
				{#if !stats}
					<Skeleton class="mt-1.5 h-5 w-16" />
				{:else}
					<p class="font-display mt-0.5 text-lg font-semibold tabular-nums">
						{#if stats.cpu_percent != null}
							{stats.cpu_percent.toFixed(1)}%
							{#if stats.cpu_limit}<span class="text-ink-3 font-sans text-xs font-normal"
									>of {stats.cpu_limit % 1 ? stats.cpu_limit.toFixed(1) : stats.cpu_limit} CPUs</span
								>{/if}
						{:else if running}
							<span class="text-ink-3 text-sm font-normal">measuring…</span>
						{:else}
							—
						{/if}
					</p>
					<div class="bg-surface-3 mt-1.5 h-1.5 overflow-hidden rounded-full">
						<div
							class="h-full rounded-full transition-all duration-500 {bars[usageTone(cpuRatio)]}"
							style="width: {cpuRatio * 100}%"
						></div>
					</div>
				{/if}
			</div>
			<!-- Memory -->
			<div class="bg-surface-2 rounded-xl px-3 py-2.5">
				<p class="text-ink-3 flex items-center gap-1.5 text-[11px] font-semibold tracking-wide uppercase">
					<Icon name="memory" size={12} />Memory
				</p>
				{#if !stats}
					<Skeleton class="mt-1.5 h-5 w-24" />
				{:else}
					<p class="font-display mt-0.5 text-lg font-semibold tabular-nums">
						{#if stats.memory_used != null}
							{formatBytes(stats.memory_used)}
							{#if stats.memory_limit}<span class="text-ink-3 font-sans text-xs font-normal"
									>of {formatBytes(stats.memory_limit)}</span
								>{/if}
						{:else}
							—
						{/if}
					</p>
					<div class="bg-surface-3 mt-1.5 h-1.5 overflow-hidden rounded-full">
						<div
							class="h-full rounded-full transition-all duration-500 {bars[usageTone(memRatio)]}"
							style="width: {Math.max(memRatio * 100, stats.memory_used ? 1 : 0)}%"
						></div>
					</div>
				{/if}
			</div>
			<!-- Storage -->
			<div class="bg-surface-2 rounded-xl px-3 py-2.5">
				<p class="text-ink-3 flex items-center gap-1.5 text-[11px] font-semibold tracking-wide uppercase">
					<Icon name="hard-drive" size={12} />Data
				</p>
				{#if !stats}
					<Skeleton class="mt-1.5 h-5 w-20" />
				{:else}
					<p class="font-display mt-0.5 text-lg font-semibold tabular-nums">
						{formatBytes(stats.data_size) ?? '—'}
					</p>
					<p class="text-ink-3 truncate text-xs" title={server.data_path ?? ''}>
						{#if stats.world_size != null}
							world {formatBytes(stats.world_size)}
						{:else if server.data_path}
							<span class="font-mono">{server.data_path}</span>
						{:else}
							no data path known
						{/if}
					</p>
				{/if}
			</div>
			<!-- Uptime -->
			<div class="bg-surface-2 rounded-xl px-3 py-2.5">
				<p class="text-ink-3 flex items-center gap-1.5 text-[11px] font-semibold tracking-wide uppercase">
					<Icon name="clock" size={12} />Uptime
				</p>
				{#if !stats}
					<Skeleton class="mt-1.5 h-5 w-16" />
				{:else}
					<p class="font-display mt-0.5 text-lg font-semibold tabular-nums">
						{formatUptime(stats.started_at) ?? '—'}
					</p>
					<p class="text-ink-3 truncate text-xs">{stats.status}</p>
				{/if}
			</div>
		</div>

		{#if server.world_path || server.data_path}
			<p class="text-ink-3 mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs">
				{#if server.data_path}<span class="meta"
						><Icon name="folder" size={13} />data <span class="font-mono">{server.data_path}</span
						></span
					>{/if}
				{#if server.world_path}<span class="meta"
						><Icon name="database" size={13} />world <span class="font-mono">{server.world_path}</span
						></span
					>{/if}
			</p>
		{/if}
	{/if}
</section>
