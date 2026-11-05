<script lang="ts">
	import type { LiveServerInfo } from '$lib/api/types';
	import { serverProperties, toneClass } from '$lib/gameinfo';
	import Icon from './Icon.svelte';

	interface Props {
		info: LiveServerInfo;
		size?: 'sm' | 'md';
	}

	let { info, size = 'md' }: Props = $props();

	const items = $derived(serverProperties(info));
</script>

{#if items.length > 0}
	<ul class="flex flex-wrap gap-1.5" aria-label="Server properties">
		{#each items as item (item.key)}
			<li class="pill {toneClass(item.tone)} {size === 'sm' ? 'h-5 px-1.5 text-[11px]' : ''}" title={item.title}>
				<Icon name={item.icon} size={size === 'md' ? 13 : 12} />{item.label}
			</li>
		{/each}
	</ul>
{/if}
