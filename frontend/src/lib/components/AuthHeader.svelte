<script lang="ts">
	import Logo from './Logo.svelte';

	interface Props {
		title: string;
		subtitle: string;
	}

	let { title, subtitle }: Props = $props();
</script>

<div class="mb-6 flex items-center gap-3">
	<Logo size={26} class="text-accent" />
	<div>
		<h1 class="text-lg font-semibold">{title}</h1>
		<p class="text-sm text-ink-2">{subtitle}</p>
	</div>
</div>
