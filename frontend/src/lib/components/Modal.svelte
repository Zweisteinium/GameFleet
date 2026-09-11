<script lang="ts">
	import type { Snippet } from 'svelte';
	import Icon from './Icon.svelte';

	interface Props {
		title: string;
		onClose: () => void;
		children: Snippet;
	}

	let { title, onClose, children }: Props = $props();
</script>

<svelte:window onkeydown={(e) => e.key === 'Escape' && onClose()} />

<div class="fixed inset-0 z-50 grid place-items-center bg-black/50 p-4 backdrop-blur-sm">
	<div
		class="card rise w-full max-w-lg p-6 shadow-pop"
		role="dialog"
		aria-modal="true"
		aria-label={title}
		tabindex="-1"
	>
		<div class="mb-5 flex items-center justify-between">
			<h2 class="font-display text-lg font-semibold">{title}</h2>
			<button class="btn-ghost btn-icon" onclick={onClose} aria-label="Close">
				<Icon name="x" size={18} />
			</button>
		</div>
		{@render children()}
	</div>
</div>
