<script lang="ts">
	interface Props {
		/** The digits typed so far. */
		value: string;
		id?: string;
		label?: string;
		disabled?: boolean;
		autofocus?: boolean;
		/** Submit the surrounding form once all six digits are in (typed, pasted or autofilled). */
		autosubmit?: boolean;
	}

	let {
		value = $bindable(''),
		id = 'totp',
		label = 'Code from your authenticator app',
		disabled = false,
		autofocus = false,
		autosubmit = true
	}: Props = $props();

	const LENGTH = 6;
	let focused = $state(false);

	function oninput(event: Event) {
		const input = event.currentTarget as HTMLInputElement;
		const digits = input.value.replace(/\D/g, '').slice(0, LENGTH);
		input.value = digits;
		const completed = digits.length === LENGTH && value.length !== LENGTH;
		value = digits;
		if (completed && autosubmit) input.form?.requestSubmit();
	}

	// The slot the next digit goes into (the last one once all are filled), highlighted while focused.
	const active = $derived(focused ? Math.min(value.length, LENGTH - 1) : -1);
</script>

<!--
	One real input (so paste, autofill and screen readers work as usual) laid over six drawn slots. Its own
	text is transparent; the slots show the digits.
-->
<div class="relative w-fit">
	<div class="flex gap-2" aria-hidden="true">
		{#each { length: LENGTH }, i (i)}
			<div
				class="grid h-12 w-10 place-items-center rounded-[var(--radius-control)] border font-mono text-xl transition-colors duration-100
					{i === active
					? 'border-accent bg-accent-soft'
					: value[i]
						? 'border-ink-3 bg-surface-1'
						: 'border-line-2 bg-surface-1'}
					{disabled ? 'opacity-50' : ''}"
			>
				{value[i] ?? ''}
			</div>
		{/each}
	</div>
	<input
		{id}
		name="totp"
		class="code-input absolute inset-0 h-full w-full cursor-text border-0 bg-transparent"
		type="text"
		inputmode="numeric"
		pattern="[0-9]*"
		autocomplete="one-time-code"
		maxlength={LENGTH}
		aria-label={label}
		{value}
		{disabled}
		required
		{oninput}
		onfocus={() => (focused = true)}
		onblur={() => (focused = false)}
		{@attach (input) => {
			if (autofocus) input.focus();
		}}
	/>
</div>

<style>
	.code-input {
		color: transparent;
		caret-color: transparent;
		outline: none;
		letter-spacing: 1.5rem;
	}
	.code-input::selection {
		background: transparent;
	}
</style>
