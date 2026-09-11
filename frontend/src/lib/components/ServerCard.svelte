<script lang="ts">
    import { type GameServerPublic, ServerStatus } from '$lib/api/Api'
    import type { LiveServerInfo } from '$lib/api/types'
    import { gameEmoji, gameLabel } from '$lib/games'
    import StatusBadge from './StatusBadge.svelte'

    interface Props {
        server: GameServerPublic
        liveInfo?: LiveServerInfo
        onClick?: (serverId: string) => void
    }

    let { server, liveInfo, onClick }: Props = $props()

    function handleClick() {
        onClick?.(server.id)
    }

    function handleKeyPress(event: KeyboardEvent) {
        if (event.key === 'Enter') onClick?.(server.id)
    }
</script>

<div class="glass-card server-card" onclick={handleClick} role="button" tabindex="0" onkeypress={handleKeyPress}>
    <div class="card-header">
        {#if liveInfo}
            <StatusBadge status={liveInfo.status} />
        {:else}
            <StatusBadge status={ServerStatus.Unknown} isChecking={true} />
        {/if}
    </div>

    <div class="card-body">
        <div class="mb-4">
            <h3 class="server-title">{server.name}</h3>
            <p class="server-game">{gameEmoji(server.game)} {gameLabel(server.game)}</p>
        </div>

        <div class="server-details">
            <div class="detail-item">
                <span class="detail-icon">🌐</span>
                <span class="detail-value">{server.address}:{server.port}</span>
            </div>

            {#if liveInfo?.players_online != null}
                <div class="detail-item">
                    <span class="detail-icon">👥</span>
                    <span class="detail-value">
                        {liveInfo.players_online}{liveInfo.players_max ? `/${liveInfo.players_max}` : ''} players
                    </span>
                </div>
            {/if}

            {#if liveInfo?.map_name}
                <div class="detail-item">
                    <span class="detail-icon">🗺️</span>
                    <span class="detail-value">{liveInfo.map_name}</span>
                </div>
            {/if}

            {#if liveInfo?.latency}
                <div class="detail-item">
                    <span class="detail-icon">⚡</span>
                    <span class="detail-value">{Math.trunc(liveInfo.latency)}ms</span>
                </div>
            {/if}

            {#if liveInfo?.version}
                <div class="detail-item">
                    <span class="detail-icon">🔧</span>
                    <span class="detail-value">v{liveInfo.version}</span>
                </div>
            {/if}
        </div>

        {#if liveInfo?.error_message}
            <div class="error-message">⚠️ {liveInfo.error_message}</div>
        {/if}
    </div>
</div>
