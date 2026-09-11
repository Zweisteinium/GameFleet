<script lang="ts">
	import { onMount } from 'svelte';
	import { api } from '$lib/api/ApiService';
	import {
		GameServerType,
		QueryProtocol,
		type GameServerPublic,
		type GameTypeInfo
	} from '$lib/api/Api';
	import Icon from './Icon.svelte';

	interface Props {
		/** When set, the form edits this server instead of creating a new one. */
		initial?: GameServerPublic;
		onSaved: (server: GameServerPublic) => void;
		onCancel: () => void;
	}

	let { initial, onSaved, onCancel }: Props = $props();

	// The form deliberately snapshots the initial values once; edits live in local state until saved.
	// svelte-ignore state_referenced_locally
	const seed = initial;

	let gameTypes = $state<GameTypeInfo[]>([]);
	let name = $state(seed?.name ?? '');
	let game = $state<GameServerType>(seed?.game ?? GameServerType.Minecraft);
	let address = $state(seed?.address ?? '');
	let port = $state<number>(seed?.port ?? 25565);
	let queryPort = $state<number | null>(seed?.query_port ?? null);
	let rconPort = $state<number | null>(seed?.rcon_port ?? null);
	let rconPassword = $state('');
	let saving = $state(false);
	let error = $state<string | null>(null);

	const spec = $derived(gameTypes.find((t) => t.type === game));
	const showQueryPort = $derived(spec?.protocol === QueryProtocol.A2S);
	const showRcon = $derived(spec?.default_rcon_port != null);

	onMount(async () => {
		try {
			gameTypes = (await api.gameTypes.getGameTypes()).data;
		} catch (err) {
			console.error('Failed to load game types:', err);
			error = 'Could not load game types from the backend';
		}
	});

	function onGameChange() {
		if (!initial && spec) port = spec.default_port;
		queryPort = null;
		rconPort = null;
	}

	async function submit(event: SubmitEvent) {
		event.preventDefault();
		saving = true;
		error = null;
		try {
			const payload = {
				name: name.trim(),
				game,
				address: address.trim(),
				port,
				query_port: queryPort || null,
				rcon_port: rconPort || null,
				...(rconPassword ? { rcon_password: rconPassword } : {})
			};
			const response = initial
				? await api.serverId.updateServer(initial.id, payload)
				: await api.postServer(payload);
			onSaved(response.data);
		} catch (err) {
			console.error('Failed to save server:', err);
			error = 'Could not save the server. Check the values and that the backend is reachable.';
		} finally {
			saving = false;
		}
	}
</script>

<form class="space-y-4" onsubmit={submit}>
	<div>
		<label class="label" for="sf-name">Display name</label>
		<input
			id="sf-name"
			class="input"
			type="text"
			bind:value={name}
			required
			maxlength="100"
			placeholder="Weekend survival"
		/>
	</div>

	<div>
		<label class="label" for="sf-game">Game</label>
		<div class="relative">
			<select
				id="sf-game"
				class="input appearance-none pr-9"
				bind:value={game}
				onchange={onGameChange}
			>
				{#each gameTypes as type (type.type)}
					<option value={type.type}>{type.label}</option>
				{/each}
			</select>
			<Icon
				name="chevron-down"
				size={16}
				class="text-ink-3 pointer-events-none absolute top-1/2 right-3 -translate-y-1/2"
			/>
		</div>
	</div>

	<div class="grid grid-cols-[1fr_7rem] gap-3">
		<div>
			<label class="label" for="sf-address">Address</label>
			<input
				id="sf-address"
				class="input font-mono"
				type="text"
				bind:value={address}
				required
				maxlength="100"
				placeholder="play.example.com"
			/>
		</div>
		<div>
			<label class="label" for="sf-port">Port</label>
			<input
				id="sf-port"
				class="input font-mono"
				type="number"
				bind:value={port}
				required
				min="1"
				max="65535"
			/>
		</div>
	</div>

	{#if showQueryPort}
		<div>
			<label class="label" for="sf-qport"
				>Query port <span class="text-ink-3 normal-case"
					>· optional, default {spec?.default_query_port}</span
				></label
			>
			<input
				id="sf-qport"
				class="input font-mono"
				type="number"
				bind:value={queryPort}
				min="1"
				max="65535"
				placeholder={String(spec?.default_query_port ?? '')}
			/>
		</div>
	{/if}

	{#if showRcon}
		<div class="bg-surface-2 space-y-3 rounded-xl p-3">
			<div class="grid grid-cols-[7rem_1fr] gap-3">
				<div>
					<label class="label" for="sf-rport">RCON port</label>
					<input
						id="sf-rport"
						class="input font-mono"
						type="number"
						bind:value={rconPort}
						min="1"
						max="65535"
						placeholder={String(spec?.default_rcon_port ?? '')}
					/>
				</div>
				<div>
					<label class="label" for="sf-rpw"
						>RCON password {spec?.needs_rcon ? '' : '· optional'}</label
					>
					<input
						id="sf-rpw"
						class="input font-mono"
						type="password"
						bind:value={rconPassword}
						required={spec?.needs_rcon && !initial?.has_rcon}
						placeholder={initial?.has_rcon ? '•••••••• (unchanged)' : ''}
						autocomplete="off"
					/>
				</div>
			</div>
			<p class="text-ink-2 flex items-start gap-2 text-xs">
				<Icon name="info" size={14} class="mt-0.5" />
				{#if game === GameServerType.Factorio}
					Factorio has no public query protocol. Start the server with --rcon-port and
					--rcon-password.
				{:else}
					Public and Nitrado servers are found automatically. RCON is only needed for private
					servers.
				{/if}
			</p>
		</div>
	{/if}

	{#if error}
		<p
			class="flex items-center gap-2 rounded-xl bg-rose-500/10 px-3 py-2 text-sm text-rose-700 dark:text-rose-400"
		>
			<Icon name="alert" size={16} />{error}
		</p>
	{/if}

	<div class="flex justify-end gap-2 pt-2">
		<button type="button" class="btn-ghost" onclick={onCancel} disabled={saving}>Cancel</button>
		<button type="submit" class="btn-primary" disabled={saving}>
			{saving ? 'Saving…' : initial ? 'Save changes' : 'Add server'}
		</button>
	</div>
</form>
