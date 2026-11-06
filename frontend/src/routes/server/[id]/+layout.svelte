<script lang="ts">
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { onMount, onDestroy, type Snippet } from 'svelte';
	import { api } from '$lib/api/ApiService';
	import type { GameServerPublic, HostStats, PowerConflictDetail } from '$lib/api/Api';
	import { gameArtUrl, gameLabel } from '$lib/games';
	import { setServerPage } from '$lib/serverPage.svelte';
	import {
		live,
		restoreLive,
		refreshServer,
		refreshHostStats,
		forgetServer
	} from '$lib/live.svelte';
	import StatusBadge from '$lib/components/StatusBadge.svelte';
	import LoadingSpinner from '$lib/components/LoadingSpinner.svelte';
	import ServerForm from '$lib/components/ServerForm.svelte';
	import ServerProperties from '$lib/components/ServerProperties.svelte';
	import HostPanel from '$lib/components/HostPanel.svelte';
	import { loggedIn } from '$lib/auth.svelte';
	import { confirmDialog } from '$lib/confirm.svelte';
	import GameArt from '$lib/components/GameArt.svelte';
	import Modal from '$lib/components/Modal.svelte';
	import Icon from '$lib/components/Icon.svelte';
	import Skeleton from '$lib/components/Skeleton.svelte';

	let { children }: { children: Snippet } = $props();

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

	const MODPACK_SITES: Record<string, string> = {
		modrinth: 'Modrinth',
		curseforge: 'CurseForge',
		ftb: 'Feed The Beast',
		official: 'Website'
	};
	/** Link label for a typed URL: Modrinth and CurseForge by name, anything else by host. */
	function modpackHost(url: string): string {
		try {
			const host = new URL(url).hostname.replace(/^www\./, '');
			return host === 'modrinth.com' ? 'Modrinth' : host === 'curseforge.com' ? 'CurseForge' : host;
		} catch {
			return 'Link';
		}
	}
	const running = $derived(hostStats?.state === 'running');
	const admin = $derived(isLocal && loggedIn());

	type TabRoute =
		| '/server/[id]'
		| '/server/[id]/settings'
		| '/server/[id]/mods'
		| '/server/[id]/backups'
		| '/server/[id]/files';
	// Tabs below the header; a server with nothing but live data gets none.
	const tabs = $derived.by(() => {
		const list: { route: TabRoute; label: string; icon: string; count?: number }[] = [
			{ route: '/server/[id]', label: 'Overview', icon: 'activity' }
		];
		if (admin) list.push({ route: '/server/[id]/settings', label: 'Settings', icon: 'sliders' });
		if (liveInfo?.mods?.length)
			list.push({
				route: '/server/[id]/mods',
				label: 'Mods',
				icon: 'layers',
				count: liveInfo.mods.length
			});
		if (admin) {
			list.push({ route: '/server/[id]/backups', label: 'Backups', icon: 'archive' });
			list.push({ route: '/server/[id]/files', label: 'Files', icon: 'file-text' });
		}
		return list;
	});
	const activeTab = $derived(page.route.id);

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

	/** Run a container action; a 409 with GameFleet servers holding the port offers to stop those first. */
	async function withPortCheck(run: (stopConflicting: boolean) => Promise<HostStats>) {
		if (!server) return;
		try {
			live.host[server.id] = await run(false);
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
			live.host[server.id] = await run(true);
			for (const holder of holders) if (holder.server_id) refreshServer(holder.server_id);
		}
		settle();
	}

	function power(action: 'start' | 'stop' | 'restart') {
		return withPortCheck(
			async (stop) =>
				(await api.serverId.powerServer(serverId, { action, stop_conflicting: stop })).data
		);
	}

	function recreate() {
		return withPortCheck(
			async (stop) => (await api.serverId.recreateServer(serverId, { stop_conflicting: stop })).data
		);
	}

	/** Re-query a few times after the container changed: games need a while to come up or go down. */
	function settle() {
		for (const delay of [3000, 10000, 25000]) setTimeout(() => refreshServer(serverId), delay);
	}

	async function deleteServer() {
		if (!server) return;
		const remove = await confirmDialog({
			title: 'Remove server',
			message: `Remove "${server.name}" from GameFleet?`,
			note: isLocal ? 'You can choose next whether the container goes with it.' : undefined,
			confirmLabel: 'Remove',
			tone: 'danger'
		});
		if (!remove) return;
		let removeContainer = false;
		if (isLocal) {
			removeContainer = await confirmDialog({
				title: 'Remove the container too?',
				message: `Stop and delete the container "${server.container_name}" as well? Its data folder and volumes stay on the host.`,
				note: 'Keep it to remove the server from GameFleet only.',
				confirmLabel: 'Delete container',
				tone: 'danger'
			});
		}
		try {
			await api.serverId.deleteServer(server.id, { remove_container: removeContainer });
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

	setServerPage({
		get server() {
			return server!;
		},
		get liveInfo() {
			return liveInfo;
		},
		get hostStats() {
			return hostStats;
		},
		get isLocal() {
			return isLocal;
		},
		get running() {
			return running;
		},
		get refreshing() {
			return refreshing;
		},
		power,
		recreate,
		refresh: refreshLiveInfo,
		settle
	});

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
	<a href={resolve('/main')} class="btn-ghost -ml-2.5 h-8 px-2.5 text-sm">
		<Icon name="arrow-left" size={15} />
		All servers
	</a>
</div>

{#if loading}
	<div class="py-24"><LoadingSpinner size="lg" message="Loading server…" /></div>
{:else if error && !server}
	<div class="card mx-auto mt-6 max-w-md px-8 py-14 text-center">
		<Icon name="alert" size={24} class="mx-auto mb-4 text-bad" />
		<h2 class="text-lg font-semibold">Something went wrong</h2>
		<p class="mt-1 mb-6 text-sm text-ink-2">{error}</p>
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
						class="h-32 w-[5.4rem] shrink-0 rounded-[8px] shadow-card"
					/>
					<div class="min-w-0 pb-1">
						<p class="caption flex items-center gap-2">
							{gameLabel(server.game)}
							{#if isLocal}
								<span class="pill tone-neutral h-5 px-1.5 text-[11px] normal-case"
									><Icon name="box" size={11} />Docker</span
								>
							{/if}
						</p>
						<h1 class="mt-1 text-2xl font-semibold">{server.name}</h1>
						{#if !liveInfo}
							<Skeleton class="mt-2 h-4 w-56" />
						{:else if liveInfo.server_name && liveInfo.server_name !== server.name}
							<p class="mt-1 truncate text-sm text-ink-2">“{liveInfo.server_name}”</p>
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
						{#if server.modpack_name}
							<div class="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
								{#if server.modpack_icon}
									<img
										src={server.modpack_icon}
										alt=""
										class="h-6 w-6 rounded-[5px]"
										loading="lazy"
									/>
								{:else}
									<Icon name="puzzle" size={16} class="text-ink-3" />
								{/if}
								<span class="font-medium">{server.modpack_name}</span>
								{#if server.modpack_version}<span class="text-ink-3">{server.modpack_version}</span
									>{/if}
								{#if server.modpack_url}
									<a
										href={server.modpack_url}
										target="_blank"
										rel="external noreferrer"
										class="inline-flex items-center gap-1 text-xs font-medium text-accent hover:underline"
									>
										{MODPACK_SITES[server.modpack_source ?? ''] ?? modpackHost(server.modpack_url)}
										<Icon name="external-link" size={12} />
									</a>
								{/if}
							</div>
						{/if}
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
						<button class="btn-outline" onclick={refreshLiveInfo} disabled={refreshing}>
							<Icon name="refresh" size={15} class={refreshing ? 'animate-spin' : ''} />Refresh
						</button>
						{#if loggedIn()}
							<button class="btn-outline" onclick={() => (editing = true)}
								><Icon name="pencil" size={15} />Edit</button
							>
							<button class="btn-danger" onclick={deleteServer}
								><Icon name="trash" size={15} />Remove</button
							>
						{/if}
					</div>
				</div>
			</div>
		</section>

		{#if error}
			<p class="notice tone-bad"><Icon name="alert" size={16} class="mt-0.5 shrink-0" />{error}</p>
		{/if}

		{#if isLocal}
			<HostPanel {server} stats={hostStats} onPower={power} />
		{/if}

		{#if tabs.length > 1}
			<nav
				class="-mb-1 flex gap-1 overflow-x-auto border-b border-line"
				aria-label="Server sections"
			>
				{#each tabs as tab (tab.route)}
					<a
						href={resolve(tab.route, { id: serverId })}
						class="-mb-px flex h-10 shrink-0 items-center gap-2 border-b-2 px-3 text-sm font-medium transition-colors {activeTab ===
						tab.route
							? 'border-accent text-ink'
							: 'border-transparent text-ink-2 hover:text-ink'}"
						aria-current={activeTab === tab.route ? 'page' : undefined}
						data-sveltekit-noscroll
					>
						<Icon
							name={tab.icon}
							size={15}
							class={activeTab === tab.route ? 'text-accent' : 'text-ink-3'}
						/>
						{tab.label}
						{#if tab.count}<span class="text-xs font-normal text-ink-3">{tab.count}</span>{/if}
					</a>
				{/each}
			</nav>
		{/if}

		{@render children()}
	</div>
{/if}

{#if editing && server}
	<Modal title="Edit server" onClose={() => (editing = false)}>
		<ServerForm initial={server} onSaved={onServerSaved} onCancel={() => (editing = false)} />
	</Modal>
{/if}
