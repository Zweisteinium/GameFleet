<script lang="ts">
    import { page } from '$app/state'
    import { goto } from '$app/navigation'
    import { api } from '$lib/api/ApiService'
    import type { GameServerPublic } from '$lib/api/Api'
    import type { LiveServerInfo } from '$lib/api/types'
    import { gameEmoji, gameLabel, isMinecraft } from '$lib/games'
    import { onMount, onDestroy } from 'svelte'
    import StatusBadge from '$lib/components/StatusBadge.svelte'
    import LoadingSpinner from '$lib/components/LoadingSpinner.svelte'
    import StatCard from '$lib/components/StatCard.svelte'
    import MinecraftMOTD from '$lib/components/MinecraftMOTD.svelte'
    import ThemeToggle from '$lib/components/ThemeToggle.svelte'
    import GameDetails from '$lib/components/GameDetails.svelte'
    import ServerForm from '$lib/components/ServerForm.svelte'

    const REFRESH_INTERVAL_MS = 30000

    let server = $state<GameServerPublic | null>(null)
    let liveInfo = $state<LiveServerInfo | null>(null)
    let loading = $state(true)
    let error = $state<string | null>(null)
    let editing = $state(false)
    let refreshInterval: ReturnType<typeof setInterval>

    const serverId = page.params.id

    async function fetchServerData() {
        if (!serverId) {
            error = 'Server ID is required'
            loading = false
            return
        }
        try {
            const [serverResponse, liveResponse] = await Promise.all([
                api.serverId.getServerById(serverId),
                api.serverId.getServerLiveInfoById(serverId)
            ])
            server = serverResponse.data
            liveInfo = liveResponse.data
            error = null
        } catch (err) {
            console.error('Failed to fetch server data:', err)
            error = 'Failed to load server information'
        } finally {
            loading = false
        }
    }

    async function refreshLiveInfo() {
        if (!serverId) return
        try {
            liveInfo = (await api.serverId.getServerLiveInfoById(serverId)).data
        } catch (err) {
            console.error('Failed to refresh live info:', err)
        }
    }

    async function deleteServer() {
        if (!server || !confirm(`Delete "${server.name}" from the dashboard?`)) return
        try {
            await api.serverId.deleteServer(server.id)
            goto('/main')
        } catch (err) {
            console.error('Failed to delete server:', err)
            error = 'Failed to delete server'
        }
    }

    async function onServerSaved(saved: GameServerPublic) {
        server = saved
        editing = false
        await refreshLiveInfo()
    }

    onMount(() => {
        fetchServerData()
        refreshInterval = setInterval(refreshLiveInfo, REFRESH_INTERVAL_MS)
    })

    onDestroy(() => clearInterval(refreshInterval))

    function goBack() {
        goto('/main')
    }
</script>

<svelte:head>
    <title>{server ? server.name : 'Server Details'} - Game Server Dashboard</title>
</svelte:head>

<div class="server-detail-container">
    <div class="background-pattern"></div>

    <div class="server-detail-header">
        <div class="server-detail-header-content">
            <div class="flex items-center justify-between">
                <div class="flex items-center">
                    <button onclick={goBack} class="back-button" aria-label="Go back" title="Go back">
                        <span class="text-xl font-semibold text-shadow">← Back</span>
                    </button>
                    <h1 class="detail-page-title">🎮 Server Details</h1>
                </div>
                <ThemeToggle />
            </div>
        </div>
    </div>

    <div class="server-detail-content">
        {#if loading}
            <div class="loading-container">
                <LoadingSpinner size="md" message="🔍 Loading server information..." />
            </div>
        {:else if error && !server}
            <div class="empty-state">
                <div class="empty-state-icon">😕</div>
                <h3 class="empty-state-title">Oops! Something went wrong</h3>
                <p class="empty-state-description">{error}</p>
                <button onclick={goBack} class="btn-game">🏠 Go Back Home</button>
            </div>
        {:else if server && liveInfo}
            <div class="space-y-8">
                <!-- Server header -->
                <div class="glass-card card-content server-header-card">
                    <div class="server-main-info">
                        {#if liveInfo.icon}
                            <img class="server-icon" src="data:image/png;base64,{liveInfo.icon.replace(/^data:image\/png;base64,/, '')}" alt="" />
                        {/if}
                        <div>
                            <h2>{server.name}</h2>
                            {#if liveInfo.server_name && liveInfo.server_name !== server.name}
                                <p class="server-advertised-name">“{liveInfo.server_name}”</p>
                            {/if}
                            <p class="server-game-type">{gameEmoji(server.game)} {gameLabel(server.game)}</p>
                            <p class="server-address">
                                🌐 {server.address}:{server.port}
                                {#if server.query_port}<span class="server-address-extra">query {server.query_port}</span>{/if}
                                {#if server.has_rcon}<span class="server-address-extra">rcon {server.rcon_port ?? 'default'}</span>{/if}
                            </p>
                        </div>
                    </div>

                    <div class="server-header-actions">
                        <StatusBadge status={liveInfo.status} />
                        <div class="button-row">
                            <button class="btn-secondary" onclick={() => (editing = !editing)}>✏️ Edit</button>
                            <button class="btn-danger" onclick={deleteServer}>🗑️ Delete</button>
                        </div>
                    </div>
                </div>

                {#if editing}
                    <div class="glass-card card-content">
                        <ServerForm initial={server} onSaved={onServerSaved} onCancel={() => (editing = false)} />
                    </div>
                {/if}

                {#if error}
                    <div class="error-message">⚠️ {error}</div>
                {/if}

                <!-- Server stats grid -->
                <div class="stats-grid-detail">
                    <StatCard
                        icon="👥"
                        title="Players"
                        value={liveInfo.players_online ?? 'N/A'}
                        subtitle={liveInfo.players_max ? `/ ${liveInfo.players_max}` : undefined}
                        bgColor="primary"
                    />

                    {#if liveInfo.latency != null}
                        <StatCard icon="⚡" title="Latency" value="{Math.trunc(liveInfo.latency)}ms" bgColor="accent" />
                    {/if}

                    {#if liveInfo.version}
                        <StatCard icon="🔧" title="Version" value={liveInfo.version} bgColor="secondary" type="version" />
                    {/if}

                    {#if liveInfo.password_protected != null || liveInfo.anti_cheat_enabled != null}
                        <div class="glass-card server-card">
                            <div class="security-card-component">
                                <div class="stat-icon warning"><span>🔒</span></div>
                                <div class="stat-info">
                                    <p class="stat-title">Security</p>
                                    <div class="security-details">
                                        {#if liveInfo.password_protected != null}
                                            <p class="security-item">{liveInfo.password_protected ? '🔐 Password Required' : '🔓 No Password'}</p>
                                        {/if}
                                        {#if liveInfo.anti_cheat_enabled != null}
                                            <p class="security-item">{liveInfo.anti_cheat_enabled ? '🛡️ Anti-cheat On' : '⚠️ Anti-cheat Off'}</p>
                                        {/if}
                                    </div>
                                </div>
                            </div>
                        </div>
                    {/if}
                </div>

                <div class="detail-grid">
                    <!-- Description and game info -->
                    <div class="glass-card card-content">
                        <h3 class="section-title">📋 Server Information</h3>

                        {#if liveInfo.description}
                            <div class="info-section">
                                <h4>📝 Description</h4>
                                <div class="info-content">
                                    {#if isMinecraft(server.game)}
                                        <MinecraftMOTD motd={liveInfo.description} />
                                    {:else}
                                        {liveInfo.description}
                                    {/if}
                                </div>
                            </div>
                        {/if}

                        {#if liveInfo.game_mode}
                            <div class="info-section">
                                <h4>🎮 Game Mode</h4>
                                <p class="info-content large-text">{liveInfo.game_mode}</p>
                            </div>
                        {/if}

                        {#if liveInfo.map_name}
                            <div class="info-section">
                                <h4>🗺️ Current Map</h4>
                                <p class="info-content large-text">{liveInfo.map_name}</p>
                            </div>
                        {/if}

                        {#if !liveInfo.description && !liveInfo.game_mode && !liveInfo.map_name}
                            <p class="empty-players-text">No additional information reported by this server.</p>
                        {/if}
                    </div>

                    <!-- Players online -->
                    <div class="glass-card card-content">
                        <h3 class="section-title">
                            👥 Players Online{#if liveInfo.player_list?.length} ({liveInfo.player_list.length}){/if}
                        </h3>
                        {#if liveInfo.player_list && liveInfo.player_list.length > 0}
                            <div class="players-list">
                                {#each liveInfo.player_list as player, index (index)}
                                    <div class="player-item">
                                        <div class="player-avatar">{player.charAt(0).toUpperCase()}</div>
                                        <span class="player-name">{player}</span>
                                    </div>
                                {/each}
                            </div>
                        {:else}
                            <div class="empty-players">
                                <div class="empty-players-icon">😴</div>
                                <p class="empty-players-text">
                                    {liveInfo.players_online ? 'This server does not publish player names' : 'No players currently online'}
                                </p>
                            </div>
                        {/if}
                    </div>
                </div>

                <GameDetails info={liveInfo} />

                <!-- Mods section -->
                {#if liveInfo.mods && liveInfo.mods.length > 0}
                    <div class="glass-card card-content">
                        <h3 class="section-title">🔧 Installed Mods ({liveInfo.mods.length})</h3>
                        <div class="mods-grid">
                            {#each liveInfo.mods as mod, index (index)}
                                <div class="mod-item">
                                    <p class="mod-name">{mod.name || (mod.id ? `Mod #${mod.id}` : 'Unknown Mod')}</p>
                                    {#if mod.version}
                                        <p class="mod-version">v{mod.version}</p>
                                    {/if}
                                </div>
                            {/each}
                        </div>
                    </div>
                {/if}

                <!-- Error message -->
                {#if liveInfo.error_message}
                    <div class="error-section">
                        <h3 class="error-title">⚠️ Connection Error</h3>
                        <p class="error-message">{liveInfo.error_message}</p>
                    </div>
                {/if}

                <div class="auto-refresh-indicator">
                    <div class="refresh-badge">
                        <span class="refresh-icon">🔄</span>
                        <span class="refresh-text">Auto-refreshing every 30 seconds</span>
                    </div>
                </div>
            </div>
        {/if}
    </div>
</div>
