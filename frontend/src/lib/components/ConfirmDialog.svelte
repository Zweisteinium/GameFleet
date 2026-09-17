<script lang="ts">
	import { pendingConfirm, answerConfirm } from '$lib/confirm.svelte';
	import Icon from './Icon.svelte';

	const options = $derived(pendingConfirm.options);
	const danger = $derived(options?.tone === 'danger');

	let cancelButton = $state<HTMLButtonElement>();
	// Focus starts on Cancel so a stray Enter never confirms.
	$effect(() => {
		if (options) cancelButton?.focus();
	});
</script>

<svelte:window onkeydown={(e) => options && e.key === 'Escape' && answerConfirm(false)} />

{#if options}
	<div
		class="fixed inset-0 z-[60] grid place-items-center bg-black/50 p-4 backdrop-blur-sm"
		role="presentation"
		onclick={(e) => e.target === e.currentTarget && answerConfirm(false)}
	>
		<div
			class="card rise shadow-pop w-full max-w-md p-6"
			role="alertdialog"
			aria-modal="true"
			aria-labelledby="confirm-title"
			aria-describedby="confirm-message"
		>
			<div class="flex items-start gap-4">
				<span
					class="grid h-10 w-10 shrink-0 place-items-center rounded-xl {danger
						? 'bg-rose-500/10 text-rose-600 dark:text-rose-400'
						: 'bg-accent-soft text-accent'}"
				>
					<Icon name={danger ? 'alert' : 'info'} size={20} />
				</span>
				<div class="min-w-0">
					<h2 id="confirm-title" class="font-display text-lg font-semibold">{options.title}</h2>
					<p id="confirm-message" class="text-ink-2 mt-1 text-sm">{options.message}</p>
					{#if options.note}<p class="text-ink-3 mt-2 text-xs">{options.note}</p>{/if}
				</div>
			</div>
			<div class="mt-6 flex justify-end gap-2">
				<button bind:this={cancelButton} class="btn-ghost" onclick={() => answerConfirm(false)}>
					Cancel
				</button>
				<button class={danger ? 'btn-danger' : 'btn-primary'} onclick={() => answerConfirm(true)}>
					{options.confirmLabel ?? 'Confirm'}
				</button>
			</div>
		</div>
	</div>
{/if}
