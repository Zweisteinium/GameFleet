<script lang="ts">
	import { GameServerType, type DiscoveredContainer } from '$lib/api/Api';
	import { api } from '$lib/api/ApiService';
	import { GAME_LABELS, gameLabel } from '$lib/games';
	import Icon from './Icon.svelte';

	interface Props {
		items: DiscoveredContainer[];
		/** Called after an import so the dashboard can reload its server list. */
		onChanged: () => Promise<void> | void;
	}

	let { items, onChanged }: Props = $props();

	let busy = $state<string | null>(null);
	let error = $state<string | null>(null);
	let choice = $state<Record<string, GameServerType>>({});
	let showHidden = $state(false);

	const candidates = $derived(items.filter((item) => !item.server_id && !item.ignored));
	const hidden = $derived(items.filter((item) => !item.server_id && item.ignored));
	const games = Object.entries(GAME_LABELS).sort((a, b) => a[1].localeCompare(b[1]));

	const CONFIDENCE: Record<string, { label: string; tone: string }> = {
		label: { label: 'labelled', tone: 'bg-accent-soft text-accent' },
		image: { label: 'known image', tone: 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-400' },
		keyword: { label: 'name match', tone: 'bg-amber-500/10 text-amber-700 dark:text-amber-400' },
		port: { label: 'port match', tone: 'bg-amber-500/10 text-amber-700 dark:text-amber-400' }
	};

	async function act(name: string, fn: () => Promise<unknown>) {
		busy = name;
		error = null;
		try {
			await fn();
			await onChanged();
		} catch (err) {
			const detail = (err as { error?: { detail?: string } })?.error?.detail;
			error = detail ?? 'The request failed.';
		} finally {
			busy = null;
		}
	}

	function importContainer(item: DiscoveredContainer) {
		const game = choice[item.container.name] ?? item.detected?.game;
		return act(item.container.name, () =>
			api.import.importContainer({ container_name: item.container.name, game })
		);
	}
</script>

{#if candidates.length > 0 || hidden.length > 0}
	<section class="card rise p-4 sm:p-5">
		<div class="mb-3 flex flex-wrap items-center justify-between gap-2">
			<h2 class="section-title">
				<Icon name="box" size={16} class="text-ink-3" />
				Containers on this host
				{#if candidates.length}<span class="text-ink-3 font-sans text-sm font-normal"
						>({candidates.length} not imported)</span
					>{/if}
			</h2>
			{#if hidden.length}
				<button class="btn-ghost h-8 px-2 text-xs" onclick={() => (showHidden = !showHidden)}>
					<Icon name={showHidden ? 'eye-off' : 'eye'} size={14} />
					{showHidden ? 'Hide' : 'Show'}
					{hidden.length} hidden
				</button>
			{/if}
		</div>

		{#if error}
			<p
				class="mb-3 flex items-center gap-2 rounded-xl bg-rose-500/10 px-3 py-2 text-sm text-rose-700 dark:text-rose-400"
			>
				<Icon name="alert" size={16} />{error}
			</p>
		{/if}

		{#if candidates.length === 0}
			<p class="text-ink-3 text-sm">Every detected game server is already in your fleet.</p>
		{/if}

		<ul class="divide-line divide-y">
			{#each [...candidates, ...(showHidden ? hidden : [])] as item (item.container.name)}
				{@const detected = item.detected}
				{@const guessed = detected?.confidence === 'keyword' || detected?.confidence === 'port'}
				<li class="flex flex-wrap items-center gap-x-4 gap-y-2 py-3 {item.ignored ? 'opacity-60' : ''}">
					<span
						class="grid h-9 w-9 shrink-0 place-items-center rounded-xl {item.container.state ===
						'running'
							? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
							: 'bg-surface-2 text-ink-3'}"
						title={item.container.status}
					>
						<Icon name="box" size={16} />
					</span>
					<div class="min-w-0 flex-1 basis-48">
						<p class="truncate font-mono text-sm font-semibold">{item.container.name}</p>
						<p class="text-ink-3 truncate text-xs">
							{item.container.image} · {item.container.status}{#if item.container.compose_dir}
								· <span class="font-mono">{item.container.compose_dir}</span>{/if}
						</p>
					</div>
					{#if detected}
						<div class="flex min-w-0 flex-wrap items-center gap-2 text-xs">
							{#if guessed && !item.ignored}
								<div class="relative">
									<select
										class="input h-8 w-48 appearance-none pr-8 text-xs"
										value={choice[item.container.name] ?? detected.game}
										onchange={(e) =>
											(choice[item.container.name] = (e.currentTarget as HTMLSelectElement)
												.value as GameServerType)}
										aria-label="Game"
									>
										{#each games as [value, label] (value)}
											<option {value}>{label}</option>
										{/each}
									</select>
									<Icon
										name="chevron-down"
										size={14}
										class="text-ink-3 pointer-events-none absolute top-1/2 right-2.5 -translate-y-1/2"
									/>
								</div>
							{:else}
								<span class="font-medium">{gameLabel(detected.game)}</span>
							{/if}
							<span
								class="inline-flex h-6 items-center rounded-full px-2 font-medium {CONFIDENCE[
									detected.confidence
								]?.tone ?? ''}"
								title={detected.reasons.join('; ')}
							>
								{CONFIDENCE[detected.confidence]?.label ?? detected.confidence}
							</span>
							<span class="meta font-mono"
								><Icon name="globe" size={12} />{detected.address}:{detected.port}</span
							>
							{#if detected.has_rcon_password}<span class="meta" title="RCON password found in the container"
									><Icon name="key" size={12} />RCON</span
								>{/if}
						</div>
					{/if}
					<div class="ml-auto flex items-center gap-1.5">
						{#if item.ignored}
							<button
								class="btn-ghost h-8 px-3 text-xs"
								disabled={busy !== null}
								onclick={() =>
									act(item.container.name, () =>
										api.ignored.unignoreContainer(item.container.name)
									)}
							>
								<Icon name="eye" size={14} />Show again
							</button>
						{:else}
							<button
								class="btn-ghost h-8 px-2 text-xs"
								disabled={busy !== null}
								title="Hide this container from discovery"
								onclick={() =>
									act(item.container.name, () => api.ignored.ignoreContainer(item.container.name))}
							>
								<Icon name="eye-off" size={14} />
							</button>
							<button
								class="btn-primary h-8 px-3 text-xs"
								disabled={busy !== null || !detected}
								onclick={() => importContainer(item)}
							>
								<Icon name="download" size={14} />
								{busy === item.container.name ? 'Importing…' : 'Import'}
							</button>
						{/if}
					</div>
				</li>
			{/each}
		</ul>
	</section>
{/if}
