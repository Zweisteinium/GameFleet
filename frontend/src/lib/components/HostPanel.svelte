<script lang="ts">
	import type { GameServerPublic, HostStats } from '$lib/api/Api';
	import { formatBytes, formatUptime, hostStateLabel, hostTone, toneClass } from '$lib/gameinfo';
	import Icon from './Icon.svelte';
	import Skeleton from './Skeleton.svelte';
	import { confirmDialog } from '$lib/confirm.svelte';

	type PowerAction = 'start' | 'stop' | 'restart';

	interface Props {
		server: GameServerPublic;
		stats?: HostStats;
		onPower: (action: PowerAction) => Promise<void>;
	}

	let { server, stats, onPower }: Props = $props();

	let busy = $state<PowerAction | null>(null);
	let error = $state<string | null>(null);

	const bars = {
		neutral: 'bg-ink-3',
		accent: 'bg-accent',
		success: 'bg-ok',
		danger: 'bg-bad',
		warning: 'bg-warn'
	};

	const running = $derived(stats?.state === 'running');
	const cpuRatio = $derived(stats?.cpu_share != null ? Math.min(1, stats.cpu_share / 100) : 0);
	const count = (n: number) => (n % 1 ? n.toFixed(1) : String(n));
	// Docker counts CPUs in threads. The share is relative to what the container may use: its limit, else the host.
	const cpuScope = $derived(
		!stats?.cpu_limit
			? ''
			: stats.cpu_limited && stats.host_threads
				? `limit ${count(stats.cpu_limit)} of ${stats.host_threads} threads`
				: `of ${count(stats.cpu_limit)} threads`
	);
	const cpuTitle = $derived(
		[
			stats?.cpu_percent != null ? `${stats.cpu_percent.toFixed(1)}% of one thread, as docker stats shows it` : '',
			stats?.host_threads
				? `Host: ${stats.host_cores ? `${stats.host_cores} cores, ` : ''}${stats.host_threads} threads` +
					(stats.host_cpu_percent != null ? `, ${stats.host_cpu_percent.toFixed(0)}% busy in total` : '')
				: ''
		]
			.filter(Boolean)
			.join('\n')
	);
	const memRatio = $derived(
		stats?.memory_used != null && stats.memory_limit
			? Math.min(1, stats.memory_used / stats.memory_limit)
			: 0
	);
	const memTitle = $derived(
		stats?.host_memory_total && stats.host_memory_used != null
			? `Host: ${formatBytes(stats.host_memory_used)} of ${formatBytes(stats.host_memory_total)} in use in total`
			: ''
	);

	/** Bar parts as fractions: this server, everything running on the host, and the container's limit. */
	interface Usage {
		own: number;
		total: number | null;
		limit: number | null;
	}
	const fraction = (value: number) => Math.min(1, Math.max(0, value));
	// With whole-host figures the bar is the whole machine; without them it is the container's allowance.
	const cpuBar = $derived.by((): Usage => {
		const threads = stats?.host_threads;
		if (stats?.cpu_percent == null || stats.host_cpu_percent == null || !threads)
			return { own: cpuRatio, total: null, limit: null };
		const own = fraction(stats.cpu_percent / (threads * 100));
		return {
			own,
			total: Math.max(own, fraction(stats.host_cpu_percent / 100)),
			limit: stats.cpu_limited && stats.cpu_limit ? fraction(stats.cpu_limit / threads) : null
		};
	});
	const memBar = $derived.by((): Usage => {
		const total = stats?.host_memory_total;
		if (stats?.memory_used == null || stats.host_memory_used == null || !total)
			return { own: memRatio, total: null, limit: null };
		const own = fraction(stats.memory_used / total);
		return {
			own,
			total: Math.max(own, fraction(stats.host_memory_used / total)),
			limit: stats.memory_limit && stats.memory_limit < total * 0.98 ? fraction(stats.memory_limit / total) : null
		};
	});
	const usageTone = (ratio: number) =>
		ratio >= 0.9 ? 'danger' : ratio >= 0.7 ? 'warning' : 'success';

	async function run(action: PowerAction) {
		if (action !== 'start') {
			const label = action === 'stop' ? 'Stop' : 'Restart';
			const go = await confirmDialog({
				title: `${label} server`,
				message: `${label} "${server.name}"?`,
				note: 'Players will be disconnected.',
				confirmLabel: label,
				tone: 'danger'
			});
			if (!go) return;
		}
		busy = action;
		error = null;
		try {
			await onPower(action);
		} catch (err) {
			const detail = (err as { error?: { detail?: string | { message?: string } } })?.error?.detail;
			error =
				(typeof detail === 'string' ? detail : detail?.message) ??
				`Could not ${action} the container.`;
		} finally {
			busy = null;
		}
	}
</script>

{#snippet path(icon: string, label: string, value: string, title = '')}
	<span class="inline-flex items-baseline gap-1.5" {title}>
		<Icon name={icon} size={13} class="self-center" />{label}
		<span class="font-mono text-ink-2">{value}</span>
	</span>
{/snippet}

{#snippet usageBar(usage: Usage, tone: keyof typeof bars)}
	<!-- Solid: this server. Faded: everything running on the host. Tick: the container's limit. -->
	<div class="track mt-1.5">
		{#if usage.total != null}
			<div
				class="absolute inset-y-0 left-0 rounded-full opacity-25 transition-all duration-500 {bars[tone]}"
				style="width: {usage.total * 100}%"
			></div>
		{/if}
		<div
			class="absolute inset-y-0 left-0 rounded-full transition-all duration-500 {bars[tone]}"
			style="width: {usage.own > 0 ? Math.max(usage.own * 100, 1) : 0}%"
		></div>
		{#if usage.limit != null}
			<div class="bg-ink-3 absolute inset-y-0 w-0.5" style="left: calc({usage.limit * 100}% - 1px)"></div>
		{/if}
	</div>
{/snippet}

<section class="card p-5">
	<div class="mb-4 flex flex-wrap items-center justify-between gap-3">
		<h3 class="section-title">
			<Icon name="box" size={16} class="text-ink-3" />Host container
			<span class="text-ink-3 font-mono text-xs font-normal">{server.container_name}</span>
		</h3>
		<div class="flex items-center gap-2">
			{#if stats}
				<span class="pill {toneClass(hostTone(stats.state))} h-7 px-2.5">
					<span class="h-1.5 w-1.5 rounded-full bg-current"></span>{hostStateLabel(stats)}
				</span>
			{:else}
				<Skeleton class="h-7 w-20 rounded-full" />
			{/if}
			{#if stats && stats.state !== 'missing'}
				{#if running}
					<button
						class="btn-outline btn-sm"
						onclick={() => run('restart')}
						disabled={busy !== null}
					>
						<Icon name="rotate-cw" size={14} class={busy === 'restart' ? 'animate-spin' : ''} />
						{busy === 'restart' ? 'Restarting…' : 'Restart'}
					</button>
					<button
						class="btn-danger btn-sm"
						onclick={() => run('stop')}
						disabled={busy !== null}
					>
						<Icon name="square" size={14} />{busy === 'stop' ? 'Stopping…' : 'Stop'}
					</button>
				{:else}
					<button
						class="btn-primary btn-sm"
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
		<p class="notice tone-bad mb-4"><Icon name="alert" size={16} class="mt-0.5 shrink-0" />{error}</p>
	{/if}

	{#if stats?.error && stats.state === 'missing'}
		<p class="text-ink-2 text-sm">
			No container named <span class="font-mono">{server.container_name}</span> exists any more. Remove
			this server or recreate the container with the same name.
		</p>
	{:else}
		<div class="grid grid-cols-2 gap-3 lg:grid-cols-4">
			<!-- CPU -->
			<div class="tile" title={cpuTitle}>
				<p class="caption flex items-center gap-1.5">
					<Icon name="cpu" size={12} />CPU
				</p>
				{#if !stats}
					<Skeleton class="mt-1.5 h-5 w-16" />
				{:else}
					<p class="mt-0.5 text-lg font-semibold tabular-nums">
						{#if stats.cpu_share != null}
							{stats.cpu_share.toFixed(1)}%
							{#if cpuScope}<span class="text-ink-3 text-xs font-normal">{cpuScope}</span>{/if}
						{:else if running}
							<span class="text-ink-3 text-sm font-normal">measuring…</span>
						{:else}
							—
						{/if}
					</p>
					{@render usageBar(cpuBar, usageTone(cpuRatio))}
				{/if}
			</div>
			<!-- Memory -->
			<div class="tile" title={memTitle}>
				<p class="caption flex items-center gap-1.5">
					<Icon name="memory" size={12} />Memory
				</p>
				{#if !stats}
					<Skeleton class="mt-1.5 h-5 w-24" />
				{:else}
					<p class="mt-0.5 text-lg font-semibold tabular-nums">
						{#if stats.memory_used != null}
							{formatBytes(stats.memory_used)}
							{#if stats.memory_limit}<span class="text-ink-3 text-xs font-normal"
									>of {formatBytes(stats.memory_limit)}</span
								>{/if}
						{:else}
							—
						{/if}
					</p>
					{@render usageBar(memBar, usageTone(memRatio))}
				{/if}
			</div>
			<!-- Storage -->
			<div class="tile">
				<p class="caption flex items-center gap-1.5">
					<Icon name="hard-drive" size={12} />Data
				</p>
				{#if !stats}
					<Skeleton class="mt-1.5 h-5 w-20" />
				{:else}
					<p class="mt-0.5 text-lg font-semibold tabular-nums">
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
			<div class="tile">
				<p class="caption flex items-center gap-1.5">
					<Icon name="clock" size={12} />Uptime
				</p>
				{#if !stats}
					<Skeleton class="mt-1.5 h-5 w-16" />
				{:else}
					<p class="mt-0.5 text-lg font-semibold tabular-nums">
						{formatUptime(stats.started_at) ?? '—'}
					</p>
					<p class="text-ink-3 truncate text-xs">{stats.status}</p>
				{/if}
			</div>
		</div>

		{#if server.world_path || server.data_path || stats?.compose_dir}
			<!-- Label and path share a baseline (sans and mono sit differently in a centred box); the icon is centred. -->
			<p class="mt-3 flex flex-wrap items-center gap-x-5 gap-y-1 text-xs text-ink-3">
				{#if stats?.compose_dir}{@render path('box', 'compose', stats.compose_dir, `Compose project ${stats.compose_project ?? ''}`)}{/if}
				{#if server.data_path}{@render path('folder', 'data', server.data_path)}{/if}
				{#if server.world_path}{@render path('database', 'world', server.world_path)}{/if}
			</p>
		{/if}
	{/if}
</section>
