<script lang="ts">
	interface Props {
		size?: 'sm' | 'md' | 'lg' | 'xl';
		message?: string;
	}

	let { size = 'md', message }: Props = $props();

	const sizes = { sm: 'h-5 w-5', md: 'h-8 w-8', lg: 'h-10 w-10', xl: 'h-12 w-12' };
</script>

<div class="text-ink-2 flex items-center justify-center gap-3">
	<div class="border-line-2 animate-spin rounded-full border-2 border-t-accent {sizes[size]}"></div>
	{#if message}
		<span class="text-sm font-medium">{message}</span>
	{/if}
</div>
