<script lang="ts">
	import type { GameServerType } from '$lib/api/Api';
	import { gameLabel } from '$lib/games';
	import Icon from './Icon.svelte';

	export type SortKey = 'name' | 'game' | 'status' | 'players' | 'latency';
	export type StatusFilter = 'all' | 'online' | 'offline';

	export interface ToolbarState {
		search: string;
		games: GameServerType[];
		status: StatusFilter;
		sortBy: SortKey;
		sortDir: 'asc' | 'desc';
		view: 'grid' | 'list';
	}

	interface Props {
		state: ToolbarState;
		availableGames: GameServerType[];
		resultCount: number;
	}

	let { state = $bindable(), availableGames, resultCount }: Props = $props();

	const sortOptions: { key: SortKey; label: string }[] = [
		{ key: 'name', label: 'Name' },
		{ key: 'game', label: 'Game' },
		{ key: 'status', label: 'Status' },
		{ key: 'players', label: 'Players' },
		{ key: 'latency', label: 'Latency' }
	];

	function toggleGame(game: GameServerType) {
		state.games = state.games.includes(game)
			? state.games.filter((g) => g !== game)
			: [...state.games, game];
	}

	const hasFilters = $derived(
		state.search !== '' || state.games.length > 0 || state.status !== 'all'
	);

	function reset() {
		state.search = '';
		state.games = [];
		state.status = 'all';
	}
</script>

<div class="card p-3 sm:p-4">
	<div class="flex flex-col gap-3 lg:flex-row lg:items-center">
		<label class="relative flex-1">
			<Icon
				name="search"
				size={16}
				class="text-ink-3 pointer-events-none absolute top-1/2 left-3 -translate-y-1/2"
			/>
			<input
				class="input pl-9"
				type="search"
				placeholder="Search by name, address or map"
				bind:value={state.search}
			/>
		</label>

		<div class="segmented" role="group" aria-label="Status filter">
			{#each [['all', 'All'], ['online', 'Online'], ['offline', 'Offline']] as [key, label] (key)}
				<button
					aria-pressed={state.status === key}
					onclick={() => (state.status = key as ToolbarState['status'])}>{label}</button
				>
			{/each}
		</div>

		<div class="flex items-center gap-2">
			<label class="relative">
				<span class="sr-only">Sort by</span>
				<select class="input h-9 w-36 appearance-none pr-8 text-xs" bind:value={state.sortBy}>
					{#each sortOptions as option (option.key)}
						<option value={option.key}>Sort: {option.label}</option>
					{/each}
				</select>
				<Icon
					name="chevron-down"
					size={14}
					class="text-ink-3 pointer-events-none absolute top-1/2 right-2.5 -translate-y-1/2"
				/>
			</label>
			<button
				class="btn-outline btn-icon"
				onclick={() => (state.sortDir = state.sortDir === 'asc' ? 'desc' : 'asc')}
				aria-label="Toggle sort direction"
				title={state.sortDir === 'asc' ? 'Ascending' : 'Descending'}
			>
				<Icon
					name="arrow-up-down"
					size={16}
					class={state.sortDir === 'desc' ? 'scale-y-[-1]' : ''}
				/>
			</button>

			<div class="segmented" role="group" aria-label="View">
				<button
					aria-pressed={state.view === 'grid'}
					onclick={() => (state.view = 'grid')}
					aria-label="Grid view"><Icon name="grid" size={15} /></button
				>
				<button
					aria-pressed={state.view === 'list'}
					onclick={() => (state.view = 'list')}
					aria-label="List view"><Icon name="list" size={15} /></button
				>
			</div>
		</div>
	</div>

	{#if availableGames.length > 1 || hasFilters}
		<div class="mt-3 flex flex-wrap items-center gap-2">
			{#each availableGames as game (game)}
				<button
					class="chip {state.games.includes(game) ? 'chip-active' : ''}"
					onclick={() => toggleGame(game)}
				>
					{gameLabel(game)}
				</button>
			{/each}
			<span class="text-ink-3 ml-auto text-xs tabular-nums">
				{resultCount}
				{resultCount === 1 ? 'server' : 'servers'}
				{#if hasFilters}
					· <button class="cursor-pointer underline-offset-2 hover:underline" onclick={reset}
						>clear filters</button
					>
				{/if}
			</span>
		</div>
	{/if}
</div>
