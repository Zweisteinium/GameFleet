<script lang="ts">
	import type { LiveServerInfo } from '$lib/api/types';
	import Icon from './Icon.svelte';

	interface Props {
		info: LiveServerInfo;
	}

	let { info }: Props = $props();

	type Row = { label: string; value: string | number | boolean | null | undefined };

	// Headline values (day, game time, tier...) are shown as overview tiles and flags (PvE, secure chat...)
	// as property chips; this grid carries the remaining per-game facts.
	const rows = $derived.by((): Row[] => {
		switch (info.kind) {
			case 'ark':
				return [{ label: 'Cluster', value: info.cluster_id }];
			case 'factorio':
				return [
					{ label: 'Tags', value: info.tags?.join(', ') },
					{ label: 'Seed', value: info.seed },
					...Object.entries(info.evolution ?? {}).map(([surface, factor]) => ({
						label: `Evolution · ${surface}`,
						value: `${(factor * 100).toFixed(1)}%`
					}))
				];
			case 'satisfactory':
				return [
					{ label: 'Session', value: info.session_name },
					{
						label: 'Tick rate',
						value: info.avg_tick_rate != null ? info.avg_tick_rate.toFixed(1) : null
					}
				];
			case 'minecraft':
				return [
					{ label: 'Edition', value: info.edition },
					{ label: 'Protocol', value: info.protocol }
				];
			case 'steam':
				return [
					{ label: 'Game', value: info.game },
					{ label: 'App ID', value: info.app_id },
					{ label: 'Bots', value: info.bot_count },
					{ label: 'Folder', value: info.folder },
					{ label: 'Keywords', value: info.keywords }
				];
			default:
				return [];
		}
	});

	const visibleRows = $derived(rows.filter((row) => row.value != null && row.value !== ''));
	const rules = $derived(info.kind === 'steam' ? Object.entries(info.rules ?? {}) : []);
</script>

{#if visibleRows.length > 0 || rules.length > 0}
	<section class="card p-5">
		<h3 class="section-title mb-4">
			<Icon name="puzzle" size={16} class="text-ink-3" />Game details
		</h3>
		<dl class="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
			{#each visibleRows as row (row.label)}
				<div class="bg-surface-2 min-w-0 rounded-xl px-3 py-2">
					<dt class="text-ink-3 text-[11px] font-semibold tracking-wide uppercase">{row.label}</dt>
					<dd class="truncate text-sm font-medium" title={String(row.value)}>{row.value}</dd>
				</div>
			{/each}
		</dl>
		{#if rules.length > 0}
			<details class="group mt-4">
				<summary
					class="text-ink-2 hover:text-ink flex cursor-pointer list-none items-center gap-1.5 text-sm font-medium"
				>
					<Icon name="chevron-down" size={14} class="transition-transform group-open:rotate-180" />
					Raw server rules ({rules.length})
				</summary>
				<dl class="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
					{#each rules as [key, value] (key)}
						<div class="border-line min-w-0 rounded-lg border px-2.5 py-1.5">
							<dt class="text-ink-3 truncate font-mono text-[10px]">{key}</dt>
							<dd class="truncate text-xs" title={value}>{value}</dd>
						</div>
					{/each}
				</dl>
			</details>
		{/if}
	</section>
{/if}
