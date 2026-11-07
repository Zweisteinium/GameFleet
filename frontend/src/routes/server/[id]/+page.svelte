<script lang="ts">
	import { resolve } from '$app/paths';
	import { isMinecraft } from '$lib/games';
	import { capabilities, overviewTiles, playerInitial, playersEmptyMessage } from '$lib/gameinfo';
	import { serverPage } from '$lib/serverPage.svelte';
	import StatCard from '$lib/components/StatCard.svelte';
	import MinecraftMOTD from '$lib/components/MinecraftMOTD.svelte';
	import GameDetails from '$lib/components/GameDetails.svelte';
	import PlayersBar from '$lib/components/PlayersBar.svelte';
	import Icon from '$lib/components/Icon.svelte';
	import Skeleton from '$lib/components/Skeleton.svelte';

	const ctx = serverPage();
	const server = $derived(ctx.server);
	const liveInfo = $derived(ctx.liveInfo);
	const tiles = $derived(liveInfo ? overviewTiles(liveInfo, server.game) : []);
	const caps = $derived(liveInfo ? capabilities(liveInfo) : null);
	// A stopped container is not an error: the container panel above says so and offers Start.
	const stopped = $derived(
		ctx.isLocal && ctx.hostStats != null && ctx.hostStats.state !== 'running'
	);
</script>

<div class="space-y-5">
	{#if !liveInfo}
		<!-- Live data placeholders -->
		<div class="grid grid-cols-2 gap-3 md:grid-cols-4">
			{#each [0, 1, 2, 3] as i (i)}
				<div class="card flex items-center gap-3 p-4">
					<Skeleton class="h-9 w-9 rounded-[7px]" />
					<div class="flex-1 space-y-2">
						<Skeleton class="h-3 w-16" /><Skeleton class="h-5 w-24" />
					</div>
				</div>
			{/each}
		</div>
		<div class="grid gap-5 lg:grid-cols-5">
			<div class="card space-y-3 p-5 lg:col-span-3">
				<Skeleton class="h-5 w-40" /><Skeleton class="h-3 w-24" /><Skeleton class="h-12 w-full" />
			</div>
			<div class="card space-y-3 p-5 lg:col-span-2">
				<Skeleton class="h-5 w-32" /><Skeleton class="h-9 w-full" /><Skeleton class="h-9 w-full" />
			</div>
		</div>
	{:else}
		{#if liveInfo.status === 'starting'}
			<div class="notice tone-accent items-center py-2.5">
				<Icon name="refresh" size={16} class="shrink-0 animate-spin" />
				<p>The server is starting. Live data appears once it answers.</p>
			</div>
		{:else if liveInfo.error_message && !stopped}
			<div class="notice tone-warn py-2.5">
				<Icon name="alert" size={16} class="mt-0.5 shrink-0" />
				<div>
					<p class="font-medium">Could not read live data</p>
					<p class="mt-0.5 text-xs">{liveInfo.error_message}</p>
				</div>
			</div>
		{/if}

		<!-- Overview: player count plus three headline tiles chosen per game -->
		<div
			class="card grid grid-cols-2 divide-y divide-line sm:divide-x sm:divide-y-0 md:grid-cols-4"
		>
			<div class="flex items-center gap-3 px-4 py-3">
				<span
					class="pill tone-accent grid h-9 w-9 shrink-0 place-items-center rounded-[var(--radius-control)] px-0"
					><Icon name="users" size={17} /></span
				>
				<div class="min-w-0 flex-1">
					<p class="caption">Players</p>
					{#if liveInfo.players_online != null}
						<PlayersBar online={liveInfo.players_online} max={liveInfo.players_max} />
					{:else}
						<p class="text-lg font-semibold">—</p>
					{/if}
				</div>
			</div>
			{#each tiles as tile (tile.key)}
				<StatCard
					icon={tile.icon}
					title={tile.title}
					value={tile.value ?? '—'}
					subtitle={tile.value ? tile.subtitle : undefined}
					tone={tile.value ? (tile.tone ?? 'neutral') : 'neutral'}
				/>
			{/each}
		</div>

		<div class="grid gap-5 lg:grid-cols-5">
			<!-- Info -->
			<section class="card p-5 lg:col-span-3">
				<h3 class="section-title mb-4">
					<Icon name="info" size={16} class="text-ink-3" />Server information
				</h3>
				<dl class="space-y-4">
					{#if liveInfo.description}
						<div>
							<dt class="label">{isMinecraft(server.game) ? 'MOTD' : 'Description'}</dt>
							<dd class="tile text-sm">
								{#if isMinecraft(server.game)}
									<MinecraftMOTD motd={liveInfo.description} />
								{:else}
									{liveInfo.description}
								{/if}
							</dd>
						</div>
					{/if}
					{#if liveInfo.game_mode && liveInfo.map_name}
						<div>
							<dt class="label">Game mode</dt>
							<dd class="text-sm font-medium">{liveInfo.game_mode}</dd>
						</div>
					{/if}
					{#if !liveInfo.description && !(liveInfo.game_mode && liveInfo.map_name)}
						<p class="text-sm text-ink-3">
							{caps?.description
								? `This server does not publish ${isMinecraft(server.game) ? 'a MOTD' : 'a description'}.`
								: 'This game does not publish a description.'}
						</p>
					{/if}
				</dl>
			</section>

			<!-- Players -->
			<section class="card p-5 lg:col-span-2">
				<h3 class="section-title mb-4">
					<Icon name="users" size={16} class="text-ink-3" />
					Players online
					{#if liveInfo.player_list?.length}<span class="text-sm font-normal text-ink-3"
							>({liveInfo.player_list.length})</span
						>{/if}
				</h3>
				{#if liveInfo.player_list && liveInfo.player_list.length > 0}
					<ul class="max-h-80 space-y-1.5 overflow-y-auto pr-1">
						{#each liveInfo.player_list as player, index (index)}
							<li class="tile flex items-center gap-3">
								<span
									class="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-accent-soft text-xs font-semibold text-accent"
								>
									{playerInitial(player)}
								</span>
								<span class="truncate text-sm">{player}</span>
							</li>
						{/each}
					</ul>
				{:else}
					<p class="py-6 text-center text-sm text-ink-3">{playersEmptyMessage(liveInfo)}</p>
				{/if}
			</section>
		</div>

		<GameDetails info={liveInfo} />

		{#if liveInfo.mods && liveInfo.mods.length > 0}
			<a
				href={resolve('/server/[id]/mods', { id: server.id })}
				class="card flex items-center gap-3 p-4 transition-colors hover:border-line-2"
			>
				<Icon name="layers" size={16} class="text-ink-3" />
				<span class="text-sm font-medium">{liveInfo.mods.length} mods</span>
				<span class="min-w-0 flex-1 truncate text-sm text-ink-3"
					>{liveInfo.mods
						.slice(0, 6)
						.map((m: { name?: string | null; id?: string | null }) => m.name || m.id)
						.join(', ')}{liveInfo.mods.length > 6 ? ', …' : ''}</span
				>
				<Icon name="chevron-right" size={15} class="text-ink-3" />
			</a>
		{/if}
	{/if}
</div>
