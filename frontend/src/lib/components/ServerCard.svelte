<script lang="ts">
	import { ServerStatus, type GameServerPublic, type HostStats } from '$lib/api/Api';
	import type { LiveServerInfo } from '$lib/api/types';
	import { resolve } from '$app/paths';
	import { gameLabel } from '$lib/games';
	import { formatBytes, hostStateLabel, hostTone } from '$lib/gameinfo';
	import StatusBadge from './StatusBadge.svelte';
	import GameArt from './GameArt.svelte';
	import PlayersBar from './PlayersBar.svelte';
	import Skeleton from './Skeleton.svelte';
	import Icon from './Icon.svelte';
	import { session, loggedIn } from '$lib/auth.svelte';

	interface Props {
		server: GameServerPublic;
		liveInfo?: LiveServerInfo;
		/** Container stats for servers that run in Docker on this host. */
		host?: HostStats;
		/** True while a query is in flight; only shows placeholders when there is no data yet. */
		pending?: boolean;
		variant?: 'grid' | 'list';
	}

	let { server, liveInfo, host, pending = false, variant = 'grid' }: Props = $props();

	const loading = $derived(!liveInfo);
	const offline = $derived(liveInfo?.status === ServerStatus.Offline);
	const local = $derived(server.source === 'docker');

	const hostDot: Record<string, string> = {
		success: 'bg-emerald-500',
		warning: 'bg-amber-500',
		danger: 'bg-rose-500',
		neutral: 'bg-ink-3',
		accent: 'bg-accent'
	};
</script>

{#snippet hostChip()}
	{#if server.is_public && session.authEnabled && loggedIn()}
		<span
			class="bg-surface-2 text-ink-2 inline-flex h-5 items-center gap-1 rounded-full px-1.5 text-[10px] font-medium"
			title="Visible without signing in"
		>
			<Icon name="eye" size={11} />Public
		</span>
	{/if}
	{#if local}
		<span
			class="bg-surface-2 text-ink-2 inline-flex h-5 items-center gap-1 rounded-full px-1.5 text-[10px] font-medium"
			title={host ? `${hostStateLabel(host)} · ${host.status}` : 'Runs in Docker on this host'}
		>
			<Icon name="box" size={11} />
			{#if host}<span class="h-1.5 w-1.5 rounded-full {hostDot[hostTone(host.state)]}"></span>{/if}
			Docker
		</span>
	{/if}
{/snippet}

{#snippet hostMeta(size: number)}
	{#if host?.state === 'running'}
		{#if host.cpu_percent != null}<span class="meta" title="CPU"
				><Icon name="cpu" size={size} />{host.cpu_percent.toFixed(0)}%</span
			>{/if}
		{#if host.memory_used != null}<span class="meta" title="Memory"
				><Icon name="memory" size={size} />{formatBytes(host.memory_used)}</span
			>{/if}
	{/if}
{/snippet}

{#if variant === 'list'}
	<a
		href={resolve('/server/[id]', { id: server.id })}
		class="card hover:border-line-2 group flex items-center gap-4 px-4 py-3 transition-all hover:-translate-y-px"
	>
		<GameArt
			game={server.game}
			serverIcon={liveInfo?.icon}
			class="h-12 w-9 rounded-md {offline ? 'grayscale' : ''}"
		/>
		<div class="min-w-0 flex-1">
			<h3 class="flex items-center gap-2 truncate font-semibold group-hover:text-accent">
				{server.name}{@render hostChip()}
			</h3>
			<p class="text-ink-2 truncate text-xs">
				{gameLabel(server.game)} · {server.address}:{server.port}
			</p>
		</div>
		<div class="text-ink-2 hidden items-center gap-4 text-xs md:flex">
			{#if loading}
				<Skeleton class="h-3.5 w-20" /><Skeleton class="h-3.5 w-12" />
			{:else}
				{#if liveInfo?.map_name}<span class="meta"
						><Icon name="map" size={14} />{liveInfo.map_name}</span
					>{/if}
				{#if liveInfo?.latency}<span class="meta"
						><Icon name="zap" size={14} />{Math.trunc(liveInfo.latency)} ms</span
					>{/if}
				{@render hostMeta(14)}
			{/if}
		</div>
		<div class="hidden w-40 sm:block">
			{#if loading}
				<Skeleton class="h-3.5 w-28" />
			{:else}
				<PlayersBar online={liveInfo?.players_online} max={liveInfo?.players_max} compact />
			{/if}
		</div>
		{#if liveInfo}
			<StatusBadge
				status={liveInfo.status}
				isChecking={pending && liveInfo.status === ServerStatus.Unknown}
			/>
		{:else}
			<Skeleton class="h-6 w-16 rounded-full" />
		{/if}
	</a>
{:else}
	<a
		href={resolve('/server/[id]', { id: server.id })}
		class="card hover:border-line-2 group flex flex-col overflow-hidden transition-all hover:-translate-y-0.5 hover:shadow-pop"
	>
		<div class="flex gap-4 p-4">
			<GameArt
				game={server.game}
				serverIcon={liveInfo?.icon}
				class="h-24 w-16 shrink-0 rounded-lg shadow-card transition-transform duration-300 group-hover:scale-[1.03] {offline
					? 'grayscale'
					: ''}"
			/>
			<div class="min-w-0 flex-1">
				<div class="mb-1 flex items-start justify-between gap-2">
					<h3
						class="font-display truncate text-base leading-tight font-semibold group-hover:text-accent"
					>
						{server.name}
					</h3>
					{#if liveInfo}
						<StatusBadge
							status={liveInfo.status}
							isChecking={pending && liveInfo.status === ServerStatus.Unknown}
						/>
					{:else}
						<Skeleton class="h-6 w-16 rounded-full" />
					{/if}
				</div>
				<p class="text-ink-2 mb-3 flex items-center gap-2 text-xs font-medium">
					{gameLabel(server.game)}{@render hostChip()}
				</p>

				{#if loading}
					<div class="flex items-center gap-2">
						<Skeleton class="h-4 w-14" />
						<Skeleton class="h-1.5 flex-1 rounded-full" />
					</div>
				{:else}
					<PlayersBar online={liveInfo?.players_online} max={liveInfo?.players_max} />
				{/if}

				<div class="mt-3 flex flex-wrap gap-x-3 gap-y-1">
					<span class="meta font-mono"
						><Icon name="globe" size={13} />{server.address}:{server.port}</span
					>
					{#if loading}
						<Skeleton class="h-3.5 w-16" /><Skeleton class="h-3.5 w-10" />
					{:else}
						{#if liveInfo?.map_name}<span class="meta"
								><Icon name="map" size={13} />{liveInfo.map_name}</span
							>{/if}
						{#if liveInfo?.latency}<span class="meta"
								><Icon name="zap" size={13} />{Math.trunc(liveInfo.latency)} ms</span
							>{/if}
						{#if liveInfo?.version}<span class="meta"
								><Icon name="tag" size={13} />{liveInfo.version}</span
							>{/if}
						{@render hostMeta(13)}
					{/if}
				</div>
			</div>
		</div>

		{#if liveInfo?.error_message}
			<div
				class="border-line flex items-start gap-2 border-t bg-rose-500/5 px-4 py-2 text-xs text-rose-700 dark:text-rose-400"
			>
				<Icon name="alert" size={14} class="mt-0.5" />
				<span class="line-clamp-2">{liveInfo.error_message}</span>
			</div>
		{/if}
	</a>
{/if}
