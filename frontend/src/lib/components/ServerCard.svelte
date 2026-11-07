<script lang="ts">
	import { ServerStatus, type GameServerPublic, type HostStats } from '$lib/api/Api';
	import type { LiveServerInfo } from '$lib/api/types';
	import { resolve } from '$app/paths';
	import { gameLabel } from '$lib/games';
	import { formatBytes, hostStateLabel } from '$lib/gameinfo';
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
	const href = $derived(resolve('/server/[id]', { id: server.id }));
</script>

{#snippet tags()}
	{#if local}
		<!-- Tags stay grey: the status badge is the one coloured thing on a card. -->
		<span
			class="pill tone-neutral h-5 shrink-0 px-1.5 text-[11px]"
			title={host ? `Container ${hostStateLabel(host).toLowerCase()} · ${host.status}` : 'Runs in Docker on this host'}
		>
			<Icon name="box" size={11} />Docker
		</span>
	{/if}
	{#if server.is_public && session.authEnabled && loggedIn()}
		<span class="pill tone-neutral h-5 shrink-0 px-1.5 text-[11px]" title="Visible without signing in">
			<Icon name="eye" size={11} />Public
		</span>
	{/if}
{/snippet}

{#snippet facts(size: number)}
	{#if liveInfo?.map_name}<span class="meta"><Icon name="map" {size} />{liveInfo.map_name}</span>{/if}
	{#if liveInfo?.version}<span class="meta"><Icon name="tag" {size} />{liveInfo.version}</span>{/if}
	{#if liveInfo?.latency}<span class="meta"
			><Icon name="zap" {size} />{Math.trunc(liveInfo.latency)} ms</span
		>{/if}
	{#if host?.state === 'running'}
		{#if host.cpu_share != null}<span class="meta" title="CPU, of what the container may use"
				><Icon name="cpu" {size} />{host.cpu_share.toFixed(0)}%</span
			>{/if}
		{#if host.memory_used != null}<span class="meta" title="Memory"
				><Icon name="memory" {size} />{formatBytes(host.memory_used)}</span
			>{/if}
	{/if}
{/snippet}

{#if variant === 'list'}
	<a {href} class="card hover:border-line-2 flex items-center gap-4 px-4 py-2.5 transition-colors">
		<GameArt
			game={server.game}
			serverIcon={liveInfo?.icon}
			class="h-12 w-9 rounded-[5px] {offline ? 'grayscale' : ''}"
		/>
		<div class="min-w-0 flex-1">
			<h3 class="flex items-center gap-2.5 truncate text-sm font-semibold">
				{server.name}{@render tags()}
			</h3>
			<p class="text-ink-2 truncate text-xs">
				{gameLabel(server.game)}{#if server.modpack_name}
					· {server.modpack_name}{/if} · <span class="font-mono">{server.address}:{server.port}</span>
			</p>
		</div>
		<div class="hidden items-center gap-4 md:flex">
			{#if loading}
				<Skeleton class="h-3.5 w-20" /><Skeleton class="h-3.5 w-12" />
			{:else}
				{@render facts(13)}
			{/if}
		</div>
		<div class="hidden w-36 sm:block">
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
	<a {href} class="card hover:border-line-2 flex flex-col overflow-hidden transition-colors">
		<div class="flex gap-4 p-4">
			<GameArt
				game={server.game}
				serverIcon={liveInfo?.icon}
				class="h-[5.5rem] w-[3.75rem] shrink-0 rounded-[6px] {offline ? 'grayscale' : ''}"
			/>
			<div class="min-w-0 flex-1">
				<div class="mb-1.5 flex items-start justify-between gap-3">
					<h3 class="truncate text-[15px] leading-tight font-semibold">{server.name}</h3>
					{#if liveInfo}
						<StatusBadge
							status={liveInfo.status}
							isChecking={pending && liveInfo.status === ServerStatus.Unknown}
						/>
					{:else}
						<Skeleton class="h-6 w-16 rounded-full" />
					{/if}
				</div>
				<p class="text-ink-2 mb-3 flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 text-xs">
					<span class="truncate"
						>{gameLabel(server.game)}{#if server.modpack_name}
							· {server.modpack_name}{/if}</span
					>{@render tags()}
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
						<Skeleton class="h-3.5 w-16" />
					{:else}
						{@render facts(13)}
					{/if}
				</div>
			</div>
		</div>

		{#if liveInfo?.error_message && liveInfo.status !== ServerStatus.Starting}
			<div class="border-line text-ink-3 flex items-start gap-2 border-t px-4 py-2 text-xs">
				<Icon name="info" size={14} class="mt-0.5 shrink-0" />
				<span class="line-clamp-2">{liveInfo.error_message}</span>
			</div>
		{/if}
	</a>
{/if}
