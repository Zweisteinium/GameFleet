<script lang="ts">
    import { onMount, onDestroy } from 'svelte'
    import { goto } from '$app/navigation'
    import { api } from '$lib/api/ApiService'
    import type { GameServerPublic } from '$lib/api/Api'
    import type { LiveServerInfo } from '$lib/api/types'
    import ServerCard from '$lib/components/ServerCard.svelte'
    import ServerForm from '$lib/components/ServerForm.svelte'
    import LoadingSpinner from '$lib/components/LoadingSpinner.svelte'
    import ThemeToggle from '$lib/components/ThemeToggle.svelte'

    const REFRESH_INTERVAL_MS = 30000

    let gameServers = $state<GameServerPublic[]>([])
    let serverLiveInfo = $state<Record<string, LiveServerInfo>>({})
    let loading = $state(true)
    let showForm = $state(false)
    let lastRefresh = $state<Date | null>(null)
    let refreshTimer: ReturnType<typeof setInterval>

    const infos = $derived(Object.values(serverLiveInfo))
    const onlineCount = $derived(infos.filter((info) => info.status === 'online').length)
    const offlineCount = $derived(infos.filter((info) => info.status === 'offline').length)
    const totalPlayers = $derived(infos.reduce((total, info) => total + (info.players_online ?? 0), 0))

    async function loadServers() {
        try {
            gameServers = (await api.getServers()).data
        } catch (error) {
            console.error('Failed to fetch servers:', error)
        }
    }

    async function refreshLiveInfo() {
        try {
            // One request: the backend queries every server concurrently.
            serverLiveInfo = (await api.liveInfo.getAllServersLiveInfo()).data
            lastRefresh = new Date()
        } catch (error) {
            console.error('Failed to fetch live info:', error)
        }
    }

    onMount(async () => {
        await loadServers()
        loading = false
        await refreshLiveInfo()
        refreshTimer = setInterval(refreshLiveInfo, REFRESH_INTERVAL_MS)
    })

    onDestroy(() => clearInterval(refreshTimer))

    function navigateToServer(serverId: string) {
        goto(`/server/${serverId}`)
    }

    async function onServerAdded(server: GameServerPublic) {
        showForm = false
        gameServers = [...gameServers, server]
        await refreshLiveInfo()
    }
</script>

<svelte:head>
    <title>Game Server Dashboard</title>
</svelte:head>

<div class="page-container">
    <div class="background-pattern"></div>

    <div class="page-content">
        <div class="page-header">
            <div class="header-controls">
                <ThemeToggle />
            </div>
            <h1 class="page-title">🎮 Game Server Dashboard</h1>
            <p class="page-subtitle">Monitor and manage all your game servers in one place</p>
            <div class="header-actions">
                <div class="header-badge">
                    <span>🚀 {lastRefresh ? `Updated ${lastRefresh.toLocaleTimeString()}` : 'Real-time monitoring'}</span>
                </div>
                <button class="btn-game" onclick={() => (showForm = true)}>➕ Add Server</button>
            </div>
        </div>

        {#if loading}
            <div class="loading-container">
                <LoadingSpinner size="lg" message="🔍 Discovering servers..." />
            </div>
        {:else if gameServers.length === 0}
            <div class="empty-state">
                <div class="empty-state-icon">🏗️</div>
                <h3 class="empty-state-title">Ready to get started?</h3>
                <p class="empty-state-description">Add your first game server and start monitoring its performance in real-time</p>
                <button class="btn-game" onclick={() => (showForm = true)}>➕ Add Your First Server</button>
            </div>
        {:else}
            <div class="server-grid">
                {#each gameServers as server (server.id)}
                    <ServerCard {server} liveInfo={serverLiveInfo[server.id]} onClick={navigateToServer} />
                {/each}
            </div>

            <div class="stats-container">
                <h2 class="stats-title">📊 Server Overview</h2>
                <div class="stats-grid">
                    <div class="stat-card total">
                        <div class="stat-value total">{gameServers.length}</div>
                        <div class="stat-label">🏢 Total Servers</div>
                    </div>
                    <div class="stat-card online">
                        <div class="stat-value online">{onlineCount}</div>
                        <div class="stat-label">🟢 Online</div>
                    </div>
                    <div class="stat-card offline">
                        <div class="stat-value offline">{offlineCount}</div>
                        <div class="stat-label">🔴 Offline</div>
                    </div>
                    <div class="stat-card players">
                        <div class="stat-value players">{totalPlayers}</div>
                        <div class="stat-label">👥 Total Players</div>
                    </div>
                </div>
            </div>
        {/if}
    </div>
</div>

<svelte:window onkeydown={(e) => e.key === 'Escape' && (showForm = false)} />

{#if showForm}
    <div class="modal-backdrop">
        <div class="modal glass-card" role="dialog" aria-modal="true" tabindex="-1">
            <ServerForm onSaved={onServerAdded} onCancel={() => (showForm = false)} />
        </div>
    </div>
{/if}
