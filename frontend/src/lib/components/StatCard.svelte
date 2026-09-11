<script lang="ts">
	import Icon from './Icon.svelte';

	interface Props {
		icon: string;
		title: string;
		value: string | number;
		subtitle?: string;
		tone?: 'neutral' | 'accent' | 'success' | 'danger' | 'warning';
		size?: 'sm' | 'md';
	}

	let { icon, title, value, subtitle, tone = 'neutral', size = 'md' }: Props = $props();

	const tones = {
		neutral: 'bg-surface-2 text-ink-2',
		accent: 'bg-accent-soft text-accent',
		success: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400',
		danger: 'bg-rose-500/10 text-rose-600 dark:text-rose-400',
		warning: 'bg-amber-500/10 text-amber-600 dark:text-amber-400'
	};
</script>

<div class="card flex items-center gap-3 {size === 'sm' ? 'px-4 py-3' : 'p-4'}">
	<span class="grid h-10 w-10 shrink-0 place-items-center rounded-xl {tones[tone]}">
		<Icon name={icon} size={18} />
	</span>
	<div class="min-w-0">
		<p class="text-ink-3 text-[11px] font-semibold tracking-wide uppercase">{title}</p>
		<p
			class="font-display truncate font-semibold tabular-nums {size === 'sm'
				? 'text-lg'
				: 'text-xl'}"
			title={String(value)}
		>
			{value}{#if subtitle}<span class="text-ink-3 ml-1 font-sans text-sm font-normal"
					>{subtitle}</span
				>{/if}
		</p>
	</div>
</div>
