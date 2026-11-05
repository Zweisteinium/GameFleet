<script lang="ts">
	import type { Snippet } from 'svelte';
	import Icon from './Icon.svelte';

	interface Props {
		title: string;
		onClose: () => void;
		/** Width of the dialog; "lg" for editors and multi-column forms. */
		size?: 'md' | 'lg';
		children: Snippet;
	}

	let { title, onClose, size = 'md', children }: Props = $props();
</script>

<svelte:window onkeydown={(e) => e.key === 'Escape' && onClose()} />

<div
	class="fixed inset-0 z-50 grid place-items-center overflow-y-auto bg-black/40 p-4"
	role="presentation"
	onclick={(e) => e.target === e.currentTarget && onClose()}
>
	<div
		class="card rise shadow-pop my-auto w-full p-5 {size === 'lg' ? 'max-w-3xl' : 'max-w-lg'}"
		role="dialog"
		aria-modal="true"
		aria-label={title}
		tabindex="-1"
	>
		<div class="mb-4 flex items-center justify-between">
			<h2 class="text-base font-semibold">{title}</h2>
			<button class="btn-ghost btn-icon h-8 w-8" onclick={onClose} aria-label="Close">
				<Icon name="x" size={16} />
			</button>
		</div>
		{@render children()}
	</div>
</div>
