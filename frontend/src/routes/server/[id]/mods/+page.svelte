<script lang="ts">
	import { serverPage } from '$lib/serverPage.svelte';
	import Icon from '$lib/components/Icon.svelte';

	const ctx = serverPage();
	const mods = $derived(ctx.liveInfo?.mods ?? []);
	let query = $state('');

	const shown = $derived.by(() => {
		const q = query.trim().toLowerCase();
		const sorted = [...mods].sort((a, b) =>
			(a.name || a.id || '').localeCompare(b.name || b.id || '', undefined, { sensitivity: 'base' })
		);
		if (!q) return sorted;
		return sorted.filter((m) =>
			`${m.name ?? ''} ${m.id ?? ''} ${m.version ?? ''}`.toLowerCase().includes(q)
		);
	});
</script>

<svelte:head><title>Mods · {ctx.server.name} · GameFleet</title></svelte:head>

<section class="card p-5">
	<div class="mb-4 flex flex-wrap items-center justify-between gap-3">
		<h2 class="section-title">
			<Icon name="layers" size={16} class="text-ink-3" />Mods
			<span class="text-sm font-normal text-ink-3"
				>{query.trim() ? `${shown.length} of ${mods.length}` : mods.length}</span
			>
		</h2>
		<label class="relative w-full sm:w-72">
			<span class="sr-only">Filter mods</span>
			<Icon
				name="search"
				size={14}
				class="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-ink-3"
			/>
			<input class="input pl-8" placeholder="Filter by name, id or version" bind:value={query} />
		</label>
	</div>

	{#if mods.length === 0}
		<p class="py-6 text-center text-sm text-ink-3">The server reports no mods right now.</p>
	{:else if shown.length === 0}
		<p class="py-6 text-center text-sm text-ink-3">No mod matches "{query}".</p>
	{:else}
		<ul class="grid gap-2 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
			{#each shown as mod, index (index)}
				<li class="tile min-w-0">
					{#if mod.url}
						<a
							href={mod.url}
							target="_blank"
							rel="external noreferrer"
							class="flex items-center gap-1.5 truncate text-sm font-medium hover:text-accent"
						>
							<span class="truncate">{mod.name || `Mod ${mod.id}`}</span><Icon
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
					{#if mod.version}<p class="hint truncate">v{mod.version}</p>{/if}
				</li>
			{/each}
		</ul>
	{/if}
</section>
