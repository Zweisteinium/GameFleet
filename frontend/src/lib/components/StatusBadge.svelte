<script lang="ts">
	import type { ServerStatus } from '$lib/api/Api';

	interface Props {
		status: ServerStatus;
		isChecking?: boolean;
		size?: 'sm' | 'md';
	}

	let { status, isChecking = false, size = 'sm' }: Props = $props();

	const config = {
		online: {
			label: 'Online',
			dot: 'bg-emerald-500 text-emerald-500',
			text: 'text-emerald-700 dark:text-emerald-400',
			bg: 'bg-emerald-500/10'
		},
		offline: {
			label: 'Offline',
			dot: 'bg-rose-500 text-rose-500',
			text: 'text-rose-700 dark:text-rose-400',
			bg: 'bg-rose-500/10'
		},
		unknown: {
			label: 'Unknown',
			dot: 'bg-amber-500 text-amber-500',
			text: 'text-amber-700 dark:text-amber-400',
			bg: 'bg-amber-500/10'
		}
	};

	const c = $derived(config[status]);
	const label = $derived(isChecking ? 'Checking' : c.label);
</script>

<span
	class="inline-flex items-center gap-1.5 rounded-full font-medium {c.bg} {c.text} {size === 'md'
		? 'h-8 px-3 text-sm'
		: 'h-6 px-2 text-xs'}"
>
	<span
		class="relative h-1.5 w-1.5 rounded-full {c.dot} {status === 'online'
			? 'pulse-ring'
			: ''} {isChecking ? 'animate-pulse' : ''}"
	></span>
	{label}
</span>
