<script lang="ts">
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { onMount, onDestroy } from 'svelte';
	import { api } from '$lib/api/ApiService';
	import type { GameServerPublic, PowerConflictDetail } from '$lib/api/Api';
	import { gameArtUrl, gameLabel, isMinecraft } from '$lib/games';
	import { capabilities, overviewTiles, playersEmptyMessage } from '$lib/gameinfo';
	import {
		live,
		restoreLive,
		refreshServer,
		refreshHostStats,
		forgetServer
	} from '$lib/live.svelte';
	import StatusBadge from '$lib/components/StatusBadge.svelte';
	import LoadingSpinner from '$lib/components/LoadingSpinner.svelte';
	import StatCard from '$lib/components/StatCard.svelte';
	import MinecraftMOTD from '$lib/components/MinecraftMOTD.svelte';
	import GameDetails from '$lib/components/GameDetails.svelte';
	import ServerForm from '$lib/components/ServerForm.svelte';
	import ServerProperties from '$lib/components/ServerProperties.svelte';
	import HostPanel from '$lib/components/HostPanel.svelte';
	import { loggedIn } from '$lib/auth.svelte';
	import { confirmDialog } from '$lib/confirm.svelte';
	import GameArt from '$lib/components/GameArt.svelte';
	import PlayersBar from '$lib/components/PlayersBar.svelte';
	import Modal from '$lib/components/Modal.svelte';
	import Icon from '$lib/components/Icon.svelte';
	import Skeleton from '$lib/components/Skeleton.svelte';

	const REFRESH_INTERVAL_MS = 30000;

	let server = $state<GameServerPublic | null>(null);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let editing = $state(false);
	let refreshInterval: ReturnType<typeof setInterval>;

	const serverId = page.params.id ?? '';
	// Live data comes from the shared cache: instant when arriving from the dashboard, refreshed in the background.
	const liveInfo = $derived(live.info[serverId] ?? null);
	const hostStats = $derived(live.host[serverId]);
	const refreshing = $derived(live.pending[serverId] ?? false);
	const isLocal = $derived(server?.source === 'docker');
	const tiles = $derived(liveInfo && server ? overviewTiles(liveInfo, server.game) : []);
	const caps = $derived(liveInfo ? capabilities(liveInfo) : null);

	async function fetchServerData() {
		if (!serverId) {
			error = 'Server ID is required';
			loading = false;
			return;
		}
		try {
			server = (await api.serverId.getServerById(serverId)).data;
			error = null;
		} catch (err) {
			console.error('Failed to fetch server data:', err);
			error = 'This server could not be loaded.';
		} finally {
			loading = false;
		}
		await refreshLiveInfo();
	}

	async function refreshLiveInfo() {
		if (!serverId) return;
		await Promise.all([refreshServer(serverId), isLocal ? refreshHostStats(serverId) : null]);
	}

	async function power(action: 'start' | 'stop' | 'restart') {
		if (!server) return;
		try {
			live.host[server.id] = (await api.serverId.powerServer(server.id, { action })).data;
		} catch (err) {
			// 409: another container holds this server's host port (instances of one game usually share it).
			const detail = (err as { error?: { detail?: PowerConflictDetail } })?.error?.detail;
			const holders = detail?.conflicts ?? [];
			if (!holders.length || !holders.every((c) => c.server_id)) throw err;
			const names = holders.map((c) => `"${c.server_name}"`).join(' and ');
			const stopOthers = await confirmDialog({
				title: 'Port already in use',
				message: `${detail?.message} Stop ${names} and start "${server.name}" instead?`,
				note: 'Players on the stopped server will be disconnected.',
				confirmLabel: 'Stop and start',
				tone: 'danger'
			});
			if (!stopOthers) return;
			live.host[server.id] = (
				await api.serverId.powerServer(server.id, { action, stop_conflicting: true })
			).data;
			for (const holder of holders) if (holder.server_id) refreshServer(holder.server_id);
		}
		// Give the game a moment to come up, then re-query it.
		setTimeout(() => refreshServer(serverId), 3000);
	}

	async function deleteServer() {
		if (!server) return;
		const remove = await confirmDialog({
			title: 'Remove server',
			message: `Remove "${server.name}" from GameFleet?`,
			note: isLocal ? 'The container itself is left untouched.' : undefined,
			confirmLabel: 'Remove',
			tone: 'danger'
		});
		if (!remove) return;
		try {
			await api.serverId.deleteServer(server.id);
			forgetServer(server.id);
			goto(resolve('/main'));
		} catch (err) {
			console.error('Failed to delete server:', err);
			error = 'Failed to delete server';
		}
	}

	async function onServerSaved(saved: GameServerPublic) {
		server = saved;
		editing = false;
		await refreshLiveInfo();
	}

	onMount(() => {
		restoreLive();
		fetchServerData();
		refreshInterval = setInterval(refreshLiveInfo, REFRESH_INTERVAL_MS);
	});

	onDestroy(() => clearInterval(refreshInterval));
</script>

<svelte:head>
	<title>{server ? server.name : 'Server'} · GameFleet</title>
</svelte:head>

<div class="pt-4">
	<a href={resolve('/main')} class="btn-ghost -ml-3 h-9 px-3 text-sm">
		<Icon name="arrow-left" size={16} />
		All servers
	</a>
</div>

{#if loading}
	<div class="py-24"><LoadingSpinner size="lg" message="Loading server…" /></div>
{:else if error && !server}
	<div class="card mx-auto mt-6 max-w-md px-8 py-14 text-center">
		<span
			class="mx-auto mb-4 grid h-12 w-12 place-items-center rounded-2xl bg-rose-500/10 text-rose-500"
		>
			<Icon name="alert" size={22} />
		</span>
		<h2 class="font-display text-lg font-semibold">Something went wrong</h2>
		<p class="text-ink-2 mt-1 mb-6 text-sm">{error}</p>
		<a href={resolve('/main')} class="btn-primary">Back to dashboard</a>
	</div>
{:else if server}
	<div class="rise mt-4 space-y-5">
		<!-- Hero -->
		<section class="card relative overflow-hidden">
			<div class="absolute inset-0">
				<img
					src={gameArtUrl(server.game, 'hero')}
					alt=""
					class="h-full w-full scale-105 object-cover opacity-70 blur-[2px]"
					onerror={(e) => ((e.currentTarget as HTMLImageElement).style.display = 'none')}
				/>
				<div
					class="absolute inset-0"
					style="background: linear-gradient(90deg, var(--surface-1) 15%, color-mix(in oklab, var(--surface-1) 65%, transparent) 60%, color-mix(in oklab, var(--surface-1) 35%, transparent))"
				></div>
				<div
					class="absolute inset-x-0 bottom-0 h-1/2"
					style="background: linear-gradient(to top, var(--surface-1), transparent)"
				></div>
			</div>

			<div class="relative flex flex-col gap-6 p-6 md:flex-row md:items-end md:justify-between">
				<div class="flex items-end gap-5">
					<GameArt
						game={server.game}
						serverIcon={liveInfo?.icon}
						class="h-36 w-24 shrink-0 rounded-xl shadow-pop"
					/>
					<div class="min-w-0 pb-1">
						<p class="text-ink-2 flex items-center gap-2 text-xs font-semibold tracking-wide uppercase">
							{gameLabel(server.game)}
							{#if isLocal}
								<span
									class="bg-surface-2 text-ink-2 inline-flex h-5 items-center gap-1 rounded-full px-1.5 text-[10px] font-medium normal-case"
									><Icon name="box" size={11} />Docker</span
								>
							{/if}
						</p>
						<h1 class="font-display mt-1 text-3xl font-semibold tracking-tight">{server.name}</h1>
						{#if !liveInfo}
							<Skeleton class="mt-2 h-4 w-56" />
						{:else if liveInfo.server_name && liveInfo.server_name !== server.name}
							<p class="text-ink-2 mt-1 truncate text-sm">“{liveInfo.server_name}”</p>
						{/if}
						<div class="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1">
							<span class="meta font-mono"
								><Icon name="globe" size={14} />{server.address}:{server.port}</span
							>
							{#if server.query_port}<span class="meta"
									><Icon name="hash" size={14} />query {server.query_port}</span
								>{/if}
							{#if server.has_rcon}<span class="meta"
									><Icon name="key" size={14} />RCON {server.rcon_port ?? 'default'}</span
								>{/if}
						</div>
						{#if liveInfo}
							<div class="mt-3">
								<ServerProperties info={liveInfo} />
							</div>
						{/if}
					</div>
				</div>

				<div class="flex flex-col items-start gap-3 md:items-end">
					{#if liveInfo}
						<StatusBadge
							status={liveInfo.status}
							size="md"
							isChecking={refreshing && liveInfo.status === 'unknown'}
						/>
					{:else}
						<Skeleton class="h-8 w-24 rounded-full" />
					{/if}
					<div class="flex gap-2">
						<button class="btn-outline h-9" onclick={refreshLiveInfo} disabled={refreshing}>
							<Icon name="refresh" size={15} class={refreshing ? 'animate-spin' : ''} />Refresh
						</button>
						{#if loggedIn()}
							<button class="btn-outline h-9" onclick={() => (editing = true)}
								><Icon name="pencil" size={15} />Edit</button
							>
							<button class="btn-danger h-9" onclick={deleteServer}
								><Icon name="trash" size={15} />Remove</button
							>
						{/if}
					</div>
				</div>
			</div>
		</section>

		{#if error}
			<p
				class="flex items-center gap-2 rounded-xl bg-rose-500/10 px-4 py-3 text-sm text-rose-700 dark:text-rose-400"
			>
				<Icon name="alert" size={16} />{error}
			</p>
		{/if}

		{#if isLocal}
			<HostPanel {server} stats={hostStats} onPower={power} />
		{/if}

		{#if !liveInfo}
			<!-- Live data placeholders -->
			<div class="grid grid-cols-2 gap-3 md:grid-cols-4">
				{#each [0, 1, 2, 3] as i (i)}
					<div class="card flex items-center gap-3 p-4">
						<Skeleton class="h-10 w-10 rounded-xl" />
						<div class="flex-1 space-y-2">
							<Skeleton class="h-3 w-16" /><Skeleton class="h-5 w-24" />
						</div>
					</div>
				{/each}
			</div>
			<div class="grid gap-5 lg:grid-cols-5">
				<div class="card space-y-3 p-5 lg:col-span-3">
					<Skeleton class="h-5 w-40" /><Skeleton class="h-3 w-24" /><Skeleton
						class="h-12 w-full rounded-xl"
					/>
				</div>
				<div class="card space-y-3 p-5 lg:col-span-2">
					<Skeleton class="h-5 w-32" /><Skeleton class="h-9 w-full rounded-xl" /><Skeleton
						class="h-9 w-full rounded-xl"
					/>
				</div>
			</div>
		{:else}
			{#if liveInfo.error_message}
				<div
					class="flex items-start gap-3 rounded-2xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-800 dark:text-amber-300"
				>
					<Icon name="alert" size={18} class="mt-0.5" />
					<div>
						<p class="font-semibold">Could not read live data</p>
						<p class="mt-0.5 opacity-90">{liveInfo.error_message}</p>
					</div>
				</div>
			{/if}

			<!-- Overview: player count plus three headline tiles chosen per game -->
			<div class="grid grid-cols-2 gap-3 md:grid-cols-4">
				<div class="card flex items-center gap-3 p-4">
					<span
						class="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-accent-soft text-accent"
						><Icon name="users" size={18} /></span
					>
					<div class="min-w-0 flex-1">
						<p class="text-ink-3 text-[11px] font-semibold tracking-wide uppercase">Players</p>
						{#if liveInfo.players_online != null}
							<PlayersBar online={liveInfo.players_online} max={liveInfo.players_max} />
						{:else}
							<p class="font-display text-xl font-semibold">—</p>
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
								<dt class="label">Description</dt>
								<dd class="bg-surface-2 rounded-xl px-3 py-2 text-sm">
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
							<p class="text-ink-3 text-sm">
								{caps?.description
									? 'This server does not publish a description.'
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
						{#if liveInfo.player_list?.length}<span class="text-ink-3 font-sans text-sm font-normal"
								>({liveInfo.player_list.length})</span
							>{/if}
					</h3>
					{#if liveInfo.player_list && liveInfo.player_list.length > 0}
						<ul class="max-h-80 space-y-1.5 overflow-y-auto pr-1">
							{#each liveInfo.player_list as player, index (index)}
								<li class="bg-surface-2 flex items-center gap-3 rounded-xl px-3 py-2">
									<span
										class="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-accent-soft text-xs font-semibold text-accent"
									>
										{player.charAt(0).toUpperCase()}
									</span>
									<span class="truncate text-sm">{player}</span>
								</li>
							{/each}
						</ul>
					{:else}
						<p class="text-ink-3 py-6 text-center text-sm">{playersEmptyMessage(liveInfo)}</p>
					{/if}
				</section>
			</div>

			<GameDetails info={liveInfo} />

			{#if liveInfo.mods && liveInfo.mods.length > 0}
				<section class="card p-5">
					<h3 class="section-title mb-4">
						<Icon name="layers" size={16} class="text-ink-3" />Mods
						<span class="text-ink-3 font-sans text-sm font-normal">({liveInfo.mods.length})</span>
					</h3>
					<ul class="grid grid-cols-2 gap-2 md:grid-cols-3 xl:grid-cols-4">
						{#each liveInfo.mods as mod, index (index)}
							<li class="bg-surface-2 min-w-0 rounded-xl px-3 py-2">
								{#if mod.url}
									<a
										href={mod.url}
										target="_blank"
										rel="noreferrer"
										class="flex items-center gap-1.5 truncate text-sm font-medium hover:text-accent"
									>
										{mod.name || `Mod ${mod.id}`}<Icon
											name="external-link"
											size={12}
											class="text-ink-3"
										/>
									</a>
								{:else}
									<p class="truncate text-sm font-medium">
										{mod.name || (mod.id ? `Mod ${mod.id}` : 'Unknown mod')}
									</p>
								{/if}
								{#if mod.version}<p class="text-ink-3 text-xs">v{mod.version}</p>{/if}
							</li>
						{/each}
					</ul>
				</section>
			{/if}
		{/if}
	</div>
{/if}

{#if editing && server}
	<Modal title="Edit server" onClose={() => (editing = false)}>
		<ServerForm initial={server} onSaved={onServerSaved} onCancel={() => (editing = false)} />
	</Modal>
{/if}
