<script lang="ts">
	import Icon from './Icon.svelte';
	import { toneClass, type Tone } from '$lib/gameinfo';

	interface Props {
		icon: string;
		title: string;
		value: string | number;
		subtitle?: string;
		tone?: Tone;
	}

	let { icon, title, value, subtitle, tone = 'neutral' }: Props = $props();
</script>

<div class="flex items-center gap-3 px-4 py-3">
	<span
		class="pill {toneClass(tone)} grid h-9 w-9 shrink-0 place-items-center rounded-[var(--radius-control)] px-0"
	>
		<Icon name={icon} size={17} />
	</span>
	<div class="min-w-0">
		<p class="caption">{title}</p>
		<p class="truncate text-lg font-semibold tabular-nums" title={String(value)}>
			{value}{#if subtitle}<span class="text-ink-3 ml-1 text-sm font-normal">{subtitle}</span>{/if}
		</p>
	</div>
</div>
