<script lang="ts">
	import type { LiveServerInfo } from '$lib/api/types';
	import { serverProperties } from '$lib/gameinfo';
	import Icon from './Icon.svelte';

	interface Props {
		info: LiveServerInfo;
		size?: 'sm' | 'md';
	}

	let { info, size = 'md' }: Props = $props();

	const tones = {
		neutral: 'bg-surface-2 text-ink-2',
		accent: 'bg-accent-soft text-accent',
		success: 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-400',
		danger: 'bg-rose-500/10 text-rose-700 dark:text-rose-400',
		warning: 'bg-amber-500/10 text-amber-700 dark:text-amber-400'
	};

	const items = $derived(serverProperties(info));
</script>

{#if items.length > 0}
	<ul class="flex flex-wrap gap-1.5" aria-label="Server properties">
		{#each items as item (item.key)}
			<li
				class="inline-flex items-center gap-1.5 rounded-full font-medium {tones[item.tone]} {size === 'md'
					? 'h-7 px-2.5 text-xs'
					: 'h-6 px-2 text-[11px]'}"
				title={item.title}
			>
				<Icon name={item.icon} size={size === 'md' ? 13 : 12} />{item.label}
			</li>
		{/each}
	</ul>
{/if}
