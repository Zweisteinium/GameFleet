<script lang="ts">
    import { onMount } from 'svelte'
    import { api } from '$lib/api/ApiService'
    import { GameServerType, QueryProtocol, type GameServerPublic, type GameTypeInfo } from '$lib/api/Api'
    import { GAME_META } from '$lib/games'

    interface Props {
        /** When set, the form edits this server instead of creating a new one. */
        initial?: GameServerPublic
        onSaved: (server: GameServerPublic) => void
        onCancel: () => void
    }

    let { initial, onSaved, onCancel }: Props = $props()

    // The form deliberately snapshots the initial values once; edits live in local state until saved.
    // svelte-ignore state_referenced_locally
    const seed = initial

    let gameTypes = $state<GameTypeInfo[]>([])
    let name = $state(seed?.name ?? '')
    let game = $state<GameServerType>(seed?.game ?? GameServerType.Minecraft)
    let address = $state(seed?.address ?? '')
    let port = $state<number>(seed?.port ?? 25565)
    let queryPort = $state<number | null>(seed?.query_port ?? null)
    let rconPort = $state<number | null>(seed?.rcon_port ?? null)
    let rconPassword = $state('')
    let saving = $state(false)
    let error = $state<string | null>(null)

    const spec = $derived(gameTypes.find((t) => t.type === game))
    const showQueryPort = $derived(spec?.protocol === QueryProtocol.A2S)
    const showRcon = $derived(spec?.default_rcon_port != null)

    onMount(async () => {
        try {
            gameTypes = (await api.gameTypes.getGameTypes()).data
        } catch (err) {
            console.error('Failed to load game types:', err)
            error = 'Could not load game types from the backend'
        }
    })

    function onGameChange() {
        // Prefill the default port for the newly selected game when creating a server.
        if (!initial && spec) port = spec.default_port
        queryPort = null
        rconPort = null
    }

    async function submit(event: SubmitEvent) {
        event.preventDefault()
        saving = true
        error = null
        try {
            const payload = {
                name: name.trim(),
                game,
                address: address.trim(),
                port,
                query_port: queryPort || null,
                rcon_port: rconPort || null,
                ...(rconPassword ? { rcon_password: rconPassword } : {})
            }
            const response = initial
                ? await api.serverId.updateServer(initial.id, payload)
                : await api.postServer(payload)
            onSaved(response.data)
        } catch (err) {
            console.error('Failed to save server:', err)
            error = 'Failed to save server. Check the values and that the backend is reachable.'
        } finally {
            saving = false
        }
    }
</script>

<form class="server-form" onsubmit={submit}>
    <h3 class="section-title">{initial ? '✏️ Edit Server' : '➕ Add Server'}</h3>

    <label class="form-field">
        <span>Name</span>
        <input type="text" bind:value={name} required maxlength="100" placeholder="My survival server" />
    </label>

    <label class="form-field">
        <span>Game</span>
        <select bind:value={game} onchange={onGameChange}>
            {#each gameTypes as type (type.type)}
                <option value={type.type}>{GAME_META[type.type]?.emoji ?? '🎮'} {type.label}</option>
            {/each}
        </select>
    </label>

    <div class="form-row">
        <label class="form-field grow">
            <span>Address</span>
            <input type="text" bind:value={address} required maxlength="100" placeholder="play.example.com" />
        </label>
        <label class="form-field">
            <span>Port</span>
            <input type="number" bind:value={port} required min="1" max="65535" />
        </label>
    </div>

    {#if showQueryPort}
        <label class="form-field">
            <span>Query port <small>(optional, default {spec?.default_query_port})</small></span>
            <input type="number" bind:value={queryPort} min="1" max="65535" placeholder={String(spec?.default_query_port ?? '')} />
        </label>
    {/if}

    {#if showRcon}
        <div class="form-row">
            <label class="form-field">
                <span>RCON port <small>(default {spec?.default_rcon_port})</small></span>
                <input type="number" bind:value={rconPort} min="1" max="65535" placeholder={String(spec?.default_rcon_port ?? '')} />
            </label>
            <label class="form-field grow">
                <span>RCON password {spec?.needs_rcon ? '' : '(optional)'}</span>
                <input
                    type="password"
                    bind:value={rconPassword}
                    required={spec?.needs_rcon && !initial?.has_rcon}
                    placeholder={initial?.has_rcon ? 'unchanged' : ''}
                    autocomplete="off"
                />
            </label>
        </div>
        {#if game === GameServerType.Factorio}
            <p class="form-hint">Factorio has no public query protocol. Start the server with --rcon-port and --rcon-password.</p>
        {:else if game === GameServerType.ArkAsa}
            <p class="form-hint">Public and Nitrado servers are found automatically. RCON is only needed for private servers.</p>
        {/if}
    {/if}

    {#if error}
        <div class="error-message">⚠️ {error}</div>
    {/if}

    <div class="form-actions">
        <button type="button" class="btn-secondary" onclick={onCancel} disabled={saving}>Cancel</button>
        <button type="submit" class="btn-game" disabled={saving}>{saving ? 'Saving...' : initial ? 'Save' : 'Add server'}</button>
    </div>
</form>
