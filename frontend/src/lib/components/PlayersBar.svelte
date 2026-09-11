<script lang="ts">
	interface Props {
		online: number | null | undefined;
		max: number | null | undefined;
		compact?: boolean;
	}

	let { online, max, compact = false }: Props = $props();

	const ratio = $derived(max && online != null ? Math.min(1, online / max) : 0);
	const tone = $derived(
		ratio >= 0.9 ? 'bg-rose-500' : ratio >= 0.6 ? 'bg-amber-500' : 'bg-emerald-500'
	);
</script>

{#if online != null}
	<div class="flex items-center gap-2 {compact ? '' : 'w-full'}">
		<span class="text-ink font-display text-sm font-semibold tabular-nums">
			{online}<span class="text-ink-3 font-sans font-normal">{max ? ` / ${max}` : ' online'}</span>
		</span>
		{#if max}
			<div
				class="bg-surface-3 h-1.5 flex-1 overflow-hidden rounded-full {compact
					? 'w-16 flex-none'
					: ''}"
			>
				<div
					class="h-full rounded-full transition-all duration-500 {tone}"
					style="width: {Math.max(2, ratio * 100)}%"
				></div>
			</div>
		{/if}
	</div>
{/if}
