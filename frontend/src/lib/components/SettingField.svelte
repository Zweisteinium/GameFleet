<script lang="ts">
	import MinecraftMOTD from './MinecraftMOTD.svelte';
	import Icon from './Icon.svelte';

	type Value = string | number | boolean | null;

	interface Props {
		id: string;
		label: string;
		type: string;
		value: Value;
		options?: string[];
		description?: string;
		edited?: boolean;
		disabled?: boolean;
		/** Shown under the field: why it is locked, or where the value comes from. */
		note?: string | null;
		placeholder?: string;
		/** A text area instead of a single line. */
		multiline?: boolean;
		/** A Minecraft MOTD: § code buttons and the rendered text below the field. */
		motd?: boolean;
		onchange: (value: string | number | boolean) => void;
	}

	let {
		id,
		label,
		type,
		value,
		options = [],
		description = '',
		edited = false,
		disabled = false,
		note = null,
		placeholder = '',
		multiline = false,
		motd = false,
		onchange
	}: Props = $props();

	let area = $state<HTMLTextAreaElement>();

	// Minecraft's formatting codes: the 16 colours, then the styles.
	const COLOURS: [string, string][] = [
		['0', '#000000'],
		['1', '#0000AA'],
		['2', '#00AA00'],
		['3', '#00AAAA'],
		['4', '#AA0000'],
		['5', '#AA00AA'],
		['6', '#FFAA00'],
		['7', '#AAAAAA'],
		['8', '#555555'],
		['9', '#5555FF'],
		['a', '#55FF55'],
		['b', '#55FFFF'],
		['c', '#FF5555'],
		['d', '#FF55FF'],
		['e', '#FFFF55'],
		['f', '#FFFFFF']
	];
	const STYLES: [string, string, string][] = [
		['l', 'B', 'Bold'],
		['o', 'I', 'Italic'],
		['n', 'U', 'Underline'],
		['m', 'S', 'Strikethrough'],
		['k', '?', 'Obfuscated'],
		['r', 'R', 'Reset']
	];

	/** Put §code at the cursor of the text area and keep editing there. */
	function insert(code: string) {
		const text = String(value ?? '');
		const start = area?.selectionStart ?? text.length;
		const end = area?.selectionEnd ?? text.length;
		const next = text.slice(0, start) + '§' + code + text.slice(end);
		onchange(next);
		requestAnimationFrame(() => {
			area?.focus();
			area?.setSelectionRange(start + 2, start + 2);
		});
	}
</script>

<div class="min-w-0 {multiline ? 'sm:col-span-2' : ''}" title={description}>
	{#if type === 'bool'}
		<label
			class="flex cursor-pointer items-start gap-3 py-1 text-sm {disabled ? 'opacity-60' : ''}"
		>
			<input
				type="checkbox"
				class="mt-0.5 h-4 w-4 accent-accent"
				checked={Boolean(value)}
				{disabled}
				onchange={(e) => onchange((e.currentTarget as HTMLInputElement).checked)}
			/>
			<span>
				<span class="inline-flex items-center gap-2"
					>{label}{#if edited}<span class="h-1.5 w-1.5 rounded-full bg-accent"></span>{/if}</span
				>
				{#if description}<span class="hint block">{description}</span>{/if}
			</span>
		</label>
	{:else}
		<label class="label flex items-center gap-2" for={id}>
			{label}
			{#if edited}<span class="h-1.5 w-1.5 rounded-full bg-accent"></span>{/if}
		</label>
		{#if type === 'enum'}
			<div class="relative">
				<select
					{id}
					class="input appearance-none pr-8"
					{disabled}
					value={String(value ?? '')}
					onchange={(e) => onchange((e.currentTarget as HTMLSelectElement).value)}
				>
					{#if value == null}<option value="" disabled>{placeholder || 'not set'}</option>{/if}
					{#each options as option (option)}
						<option value={option}>{option}</option>
					{/each}
				</select>
				<Icon
					name="chevron-down"
					size={14}
					class="pointer-events-none absolute top-1/2 right-2.5 -translate-y-1/2 text-ink-3"
				/>
			</div>
		{:else if multiline}
			{#if motd && !disabled}
				<div
					class="mb-1.5 flex flex-wrap items-center gap-1"
					role="toolbar"
					aria-label="Formatting codes"
				>
					{#each COLOURS as [code, colour] (code)}
						<button
							type="button"
							class="h-5 w-5 cursor-pointer rounded-[4px] border border-line-2"
							style="background: {colour}"
							title="Colour §{code}"
							aria-label="Colour §{code}"
							onclick={() => insert(code)}
						></button>
					{/each}
					<span class="mx-1 h-4 w-px bg-line"></span>
					{#each STYLES as [code, letter, name] (code)}
						<button
							type="button"
							class="btn-ghost h-5 min-w-5 px-1 font-mono text-[11px]"
							title="{name} §{code}"
							aria-label="{name} §{code}"
							onclick={() => insert(code)}>{letter}</button
						>
					{/each}
				</div>
			{/if}
			<textarea
				{id}
				bind:this={area}
				class="input h-auto min-h-[4.5rem] resize-y py-2 font-mono text-sm leading-5"
				rows="2"
				{disabled}
				{placeholder}
				value={value == null ? '' : String(value)}
				oninput={(e) => onchange((e.currentTarget as HTMLTextAreaElement).value)}></textarea>
			{#if motd}
				<div class="mt-2 rounded-[var(--radius-control)] bg-[#1e1e1e] px-3 py-2 text-sm leading-5">
					{#if value || placeholder}
						<MinecraftMOTD motd={String(value || placeholder)} class="whitespace-pre-line" />
					{:else}
						<span class="text-ink-3">Preview</span>
					{/if}
				</div>
			{/if}
		{:else}
			<input
				{id}
				class="input {type === 'int' ? 'font-mono' : ''}"
				type={type === 'int' ? 'number' : 'text'}
				{disabled}
				{placeholder}
				value={value ?? ''}
				onchange={(e) => {
					const raw = (e.currentTarget as HTMLInputElement).value;
					onchange(type === 'int' ? Number(raw) : raw);
				}}
			/>
		{/if}
	{/if}
	{#if note}<p class="hint mt-1">{note}</p>{/if}
	{#if description && type !== 'bool'}<p class="hint mt-1">{description}</p>{/if}
</div>
