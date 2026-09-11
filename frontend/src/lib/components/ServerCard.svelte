<script lang="ts">
	import { ServerStatus, type GameServerPublic } from '$lib/api/Api';
	import type { LiveServerInfo } from '$lib/api/types';
	import { gameLabel } from '$lib/games';
	import StatusBadge from './StatusBadge.svelte';
	import GameArt from './GameArt.svelte';
	import PlayersBar from './PlayersBar.svelte';
	import Icon from './Icon.svelte';

	interface Props {
		server: GameServerPublic;
		liveInfo?: LiveServerInfo;
		variant?: 'grid' | 'list';
	}

	let { server, liveInfo, variant = 'grid' }: Props = $props();

	const offline = $derived(liveInfo?.status === ServerStatus.Offline);
</script>

{#if variant === 'list'}
	<a
		href="/server/{server.id}"
		class="card hover:border-line-2 group flex items-center gap-4 px-4 py-3 transition-all hover:-translate-y-px"
	>
		<GameArt
			game={server.game}
			serverIcon={liveInfo?.icon}
			class="h-12 w-9 rounded-md {offline ? 'grayscale' : ''}"
		/>
		<div class="min-w-0 flex-1">
			<div class="flex items-center gap-2">
				<h3 class="truncate font-semibold group-hover:text-accent">{server.name}</h3>
			</div>
			<p class="text-ink-2 truncate text-xs">
				{gameLabel(server.game)} · {server.address}:{server.port}
			</p>
		</div>
		<div class="text-ink-2 hidden items-center gap-4 text-xs md:flex">
			{#if liveInfo?.map_name}<span class="meta"
					><Icon name="map" size={14} />{liveInfo.map_name}</span
				>{/if}
			{#if liveInfo?.latency}<span class="meta"
					><Icon name="zap" size={14} />{Math.trunc(liveInfo.latency)} ms</span
				>{/if}
		</div>
		<div class="hidden w-40 sm:block">
			<PlayersBar online={liveInfo?.players_online} max={liveInfo?.players_max} compact />
		</div>
		{#if liveInfo}
			<StatusBadge status={liveInfo.status} />
		{:else}
			<StatusBadge status={ServerStatus.Unknown} isChecking />
		{/if}
	</a>
{:else}
	<a
		href="/server/{server.id}"
		class="card hover:border-line-2 group flex flex-col overflow-hidden transition-all hover:-translate-y-0.5 hover:shadow-pop"
	>
		<div class="flex gap-4 p-4">
			<div class="relative shrink-0">
				<GameArt
					game={server.game}
					serverIcon={liveInfo?.icon}
					class="h-24 w-16 rounded-lg shadow-card transition-transform duration-300 group-hover:scale-[1.03] {offline
						? 'grayscale'
						: ''}"
				/>
			</div>
			<div class="min-w-0 flex-1">
				<div class="mb-1 flex items-start justify-between gap-2">
					<h3
						class="font-display truncate text-base font-semibold leading-tight group-hover:text-accent"
					>
						{server.name}
					</h3>
					{#if liveInfo}
						<StatusBadge status={liveInfo.status} />
					{:else}
						<StatusBadge status={ServerStatus.Unknown} isChecking />
					{/if}
				</div>
				<p class="text-ink-2 mb-3 text-xs font-medium">{gameLabel(server.game)}</p>

				<PlayersBar online={liveInfo?.players_online} max={liveInfo?.players_max} />

				<div class="mt-3 flex flex-wrap gap-x-3 gap-y-1">
					<span class="meta font-mono"
						><Icon name="globe" size={13} />{server.address}:{server.port}</span
					>
					{#if liveInfo?.map_name}<span class="meta"
							><Icon name="map" size={13} />{liveInfo.map_name}</span
						>{/if}
					{#if liveInfo?.latency}<span class="meta"
							><Icon name="zap" size={13} />{Math.trunc(liveInfo.latency)} ms</span
						>{/if}
					{#if liveInfo?.version}<span class="meta"
							><Icon name="tag" size={13} />{liveInfo.version}</span
						>{/if}
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
