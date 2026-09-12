<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { api } from '$lib/api/ApiService';
	import { ServerStatus, type DiscoveredContainer, type GameServerPublic } from '$lib/api/Api';
	import { gameLabel } from '$lib/games';
	import { live, restoreLive, refreshServers } from '$lib/live.svelte';
	import { loadPref, savePref } from '$lib/prefs';
	import ServerCard from '$lib/components/ServerCard.svelte';
	import ServerForm from '$lib/components/ServerForm.svelte';
	import DiscoveredContainers from '$lib/components/DiscoveredContainers.svelte';
	import LoadingSpinner from '$lib/components/LoadingSpinner.svelte';
	import StatCard from '$lib/components/StatCard.svelte';
	import Toolbar, { type ToolbarState } from '$lib/components/Toolbar.svelte';
	import Modal from '$lib/components/Modal.svelte';
	import Icon from '$lib/components/Icon.svelte';

	const REFRESH_INTERVAL_MS = 30000;
	const DEFAULT_TOOLBAR: ToolbarState = {
		search: '',
		games: [],
		status: 'all',
		sortBy: 'name',
		sortDir: 'asc',
		view: 'grid'
	};

	let gameServers = $state<GameServerPublic[]>([]);
	let loading = $state(true);
	let refreshing = $state(false);
	let showForm = $state(false);
	let lastRefresh = $state<Date | null>(null);
	let toolbar = $state<ToolbarState>(DEFAULT_TOOLBAR);
	let discovered = $state<DiscoveredContainer[]>([]);
	let refreshTimer: ReturnType<typeof setInterval>;

	const serverLiveInfo = $derived(live.info);
	const infos = $derived(gameServers.map((s) => live.info[s.id]).filter(Boolean));
	const onlineCount = $derived(infos.filter((info) => info.status === ServerStatus.Online).length);
	const offlineCount = $derived(
		infos.filter((info) => info.status === ServerStatus.Offline).length
	);
	const totalPlayers = $derived(
		infos.reduce((total, info) => total + (info.players_online ?? 0), 0)
	);

	const availableGames = $derived(
		[...new Set(gameServers.map((s) => s.game))].sort((a, b) =>
			gameLabel(a).localeCompare(gameLabel(b))
		)
	);

	const STATUS_RANK: Record<string, number> = { online: 0, unknown: 1, offline: 2 };

	const visibleServers = $derived.by(() => {
		const query = toolbar.search.trim().toLowerCase();
		const filtered = gameServers.filter((server) => {
			const info = serverLiveInfo[server.id];
			if (toolbar.games.length && !toolbar.games.includes(server.game)) return false;
			if (toolbar.status === 'online' && info?.status !== ServerStatus.Online) return false;
			if (toolbar.status === 'offline' && info?.status === ServerStatus.Online) return false;
			if (!query) return true;
			return [
				server.name,
				server.address,
				gameLabel(server.game),
				info?.map_name,
				info?.server_name
			]
				.filter(Boolean)
				.some((text) => String(text).toLowerCase().includes(query));
		});
		const dir = toolbar.sortDir === 'asc' ? 1 : -1;
		return filtered.sort((a, b) => {
			const ia = serverLiveInfo[a.id];
			const ib = serverLiveInfo[b.id];
			let cmp = 0;
			switch (toolbar.sortBy) {
				case 'game':
					cmp = gameLabel(a.game).localeCompare(gameLabel(b.game));
					break;
				case 'status':
					cmp =
						(STATUS_RANK[ia?.status ?? 'unknown'] ?? 1) -
						(STATUS_RANK[ib?.status ?? 'unknown'] ?? 1);
					break;
				case 'players':
					cmp = (ib?.players_online ?? -1) - (ia?.players_online ?? -1); // most players first when ascending
					break;
				case 'latency':
					cmp = (ia?.latency ?? Infinity) - (ib?.latency ?? Infinity);
					break;
			}
			return (cmp || a.name.localeCompare(b.name)) * dir;
		});
	});

	async function loadServers() {
		try {
			gameServers = (await api.getServers()).data;
		} catch (error) {
			console.error('Failed to fetch servers:', error);
		}
	}

	/** Docker discovery also imports labelled/known containers, so the server list is reloaded afterwards. */
	async function loadDiscovered() {
		try {
			const status = (await api.status.getDockerStatus()).data;
			if (!status.available) return;
			discovered = (await api.discovered.getDiscoveredContainers()).data;
			const known = new Set(gameServers.map((s) => s.id));
			if (discovered.some((item) => item.server_id && !known.has(item.server_id))) {
				await loadServers();
				await refreshLiveInfo();
			}
		} catch (error) {
			console.error('Docker discovery failed:', error);
		}
	}

	async function onDiscoveryChanged() {
		await loadServers();
		await loadDiscovered();
		await refreshLiveInfo();
	}

	async function refreshLiveInfo() {
		refreshing = true;
		try {
			// One request per server, in parallel: fast servers fill in while slow ones are still loading.
			await refreshServers(gameServers.map((s) => s.id));
			lastRefresh = new Date();
		} finally {
			refreshing = false;
		}
	}

	onMount(async () => {
		toolbar = loadPref('dashboard', DEFAULT_TOOLBAR);
		restoreLive();
		await loadServers();
		loading = false;
		await Promise.all([refreshLiveInfo(), loadDiscovered()]);
		refreshTimer = setInterval(refreshLiveInfo, REFRESH_INTERVAL_MS);
	});

	onDestroy(() => clearInterval(refreshTimer));

	$effect(() => {
		savePref('dashboard', $state.snapshot(toolbar));
	});

	async function onServerAdded(server: GameServerPublic) {
		showForm = false;
		gameServers = [...gameServers, server];
		await refreshLiveInfo();
	}
</script>

<svelte:head>
	<title>Servers · GameFleet</title>
</svelte:head>

<div class="space-y-6 pt-6">
	<div class="flex flex-wrap items-end justify-between gap-4">
		<div>
			<h1 class="font-display text-3xl font-semibold tracking-tight">Servers</h1>
			<p class="text-ink-2 mt-1 text-sm">
				{#if lastRefresh}
					Live data refreshed at {lastRefresh.toLocaleTimeString()} · auto-refresh every 30s
				{:else}
					Fetching live data from your servers…
				{/if}
			</p>
		</div>
		<div class="flex items-center gap-2">
			<button
				class="btn-outline"
				onclick={refreshLiveInfo}
				disabled={refreshing}
				aria-label="Refresh now"
			>
				<Icon name="refresh" size={16} class={refreshing ? 'animate-spin' : ''} />
				<span class="hidden sm:inline">Refresh</span>
			</button>
			<button class="btn-primary" onclick={() => (showForm = true)}>
				<Icon name="plus" size={16} />
				Add server
			</button>
		</div>
	</div>

	{#if loading}
		<div class="py-24">
			<LoadingSpinner size="lg" message="Loading your fleet…" />
		</div>
	{:else if gameServers.length === 0 && discovered.length === 0}
		<div class="card rise mx-auto max-w-lg px-8 py-16 text-center">
			<span
				class="mx-auto mb-5 grid h-14 w-14 place-items-center rounded-2xl bg-accent-soft text-accent"
			>
				<Icon name="sparkles" size={26} />
			</span>
			<h2 class="font-display text-xl font-semibold">Your fleet is empty</h2>
			<p class="text-ink-2 mx-auto mt-2 mb-6 max-w-sm text-sm">
				Add a game server and GameFleet will keep an eye on its status, players and details for you.
			</p>
			<button class="btn-primary" onclick={() => (showForm = true)}>
				<Icon name="plus" size={16} />
				Add your first server
			</button>
		</div>
	{:else}
		<div class="grid grid-cols-2 gap-3 lg:grid-cols-4">
			<StatCard icon="server" title="Servers" value={gameServers.length} size="sm" />
			<StatCard icon="activity" title="Online" value={onlineCount} tone="success" size="sm" />
			<StatCard
				icon="wifi-off"
				title="Offline"
				value={offlineCount}
				tone={offlineCount ? 'danger' : 'neutral'}
				size="sm"
			/>
			<StatCard icon="users" title="Players" value={totalPlayers} tone="accent" size="sm" />
		</div>

		<DiscoveredContainers items={discovered} onChanged={onDiscoveryChanged} />

		<Toolbar bind:state={toolbar} {availableGames} resultCount={visibleServers.length} />

		{#if visibleServers.length === 0}
			<div class="text-ink-2 py-16 text-center text-sm">No servers match the current filters.</div>
		{:else if toolbar.view === 'list'}
			<div class="space-y-2">
				{#each visibleServers as server (server.id)}
					<ServerCard
						{server}
						liveInfo={serverLiveInfo[server.id]}
						host={live.host[server.id]}
						pending={live.pending[server.id]}
						variant="list"
					/>
				{/each}
			</div>
		{:else}
			<div class="grid gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
				{#each visibleServers as server (server.id)}
					<ServerCard
						{server}
						liveInfo={serverLiveInfo[server.id]}
						host={live.host[server.id]}
						pending={live.pending[server.id]}
					/>
				{/each}
			</div>
		{/if}
	{/if}
</div>

{#if showForm}
	<Modal title="Add server" onClose={() => (showForm = false)}>
		<ServerForm onSaved={onServerAdded} onCancel={() => (showForm = false)} />
	</Modal>
{/if}
