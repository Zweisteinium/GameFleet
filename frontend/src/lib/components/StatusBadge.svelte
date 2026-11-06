<script lang="ts">
	import type { ServerStatus } from '$lib/api/Api';

	interface Props {
		status: ServerStatus;
		isChecking?: boolean;
		size?: 'sm' | 'md';
	}

	let { status, isChecking = false, size = 'sm' }: Props = $props();

	const config = {
		online: { label: 'Online', tone: 'tone-ok' },
		offline: { label: 'Offline', tone: 'tone-bad' },
		unknown: { label: 'Unknown', tone: 'tone-warn' },
		starting: { label: 'Starting', tone: 'tone-accent' }
	};

	const c = $derived(config[status]);
	const label = $derived(isChecking ? 'Checking' : c.label);
</script>

<span class="pill {c.tone} {size === 'md' ? 'h-7 px-2.5 text-sm' : ''}">
	<span class="h-1.5 w-1.5 rounded-full bg-current {isChecking || status === 'starting' ? 'animate-pulse' : ''}"></span>
	{label}
</span>
