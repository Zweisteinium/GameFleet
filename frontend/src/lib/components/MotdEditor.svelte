<script lang="ts">
	import MinecraftMOTD from './MinecraftMOTD.svelte';
	import { applyCode, clearCodes, type Edit } from '$lib/motd';

	interface Props {
		id: string;
		value: string;
		placeholder?: string;
		disabled?: boolean;
		onchange: (value: string) => void;
	}

	let { id, value, placeholder = '', disabled = false, onchange }: Props = $props();

	let area = $state<HTMLTextAreaElement>();

	// Minecraft's formatting codes: the 16 colours, then the styles. A colour code also ends every style.
	const COLOURS: [string, string, string][] = [
		['0', '#000000', 'Black'],
		['1', '#0000AA', 'Dark blue'],
		['2', '#00AA00', 'Dark green'],
		['3', '#00AAAA', 'Dark aqua'],
		['4', '#AA0000', 'Dark red'],
		['5', '#AA00AA', 'Dark purple'],
		['6', '#FFAA00', 'Gold'],
		['7', '#AAAAAA', 'Grey'],
		['8', '#555555', 'Dark grey'],
		['9', '#5555FF', 'Blue'],
		['a', '#55FF55', 'Green'],
		['b', '#55FFFF', 'Aqua'],
		['c', '#FF5555', 'Red'],
		['d', '#FF55FF', 'Light purple'],
		['e', '#FFFF55', 'Yellow'],
		['f', '#FFFFFF', 'White']
	];
	const STYLES: [string, string, string, string][] = [
		['l', 'B', 'Bold', 'font-bold'],
		['o', 'I', 'Italic', 'italic'],
		['n', 'U', 'Underline', 'underline'],
		['m', 'S', 'Strikethrough', 'line-through'],
		['k', '?', 'Obfuscated', '']
	];

	const lines = $derived((value || '').split('\n').length);

	/** Replace text through the editing commands, so Ctrl+Z undoes it like typing. */
	function replace(from: number, to: number, text: string, select: [number, number]) {
		if (!area) return;
		area.focus();
		area.setSelectionRange(from, to);
		if (!document.execCommand('insertText', false, text)) {
			area.setRangeText(text, from, to, 'end');
			area.dispatchEvent(new Event('input', { bubbles: true }));
		}
		area.setSelectionRange(...select);
	}

	function run(edit: (text: string, start: number, end: number) => Edit) {
		if (!area || disabled) return;
		const { from, to, insert, select } = edit(area.value, area.selectionStart, area.selectionEnd);
		replace(from, to, insert, select);
	}
</script>

{#if !disabled}
	<div
		class="mb-1.5 flex flex-wrap items-center gap-1"
		role="toolbar"
		aria-label="Formatting codes"
		title="Select text to format just that part"
	>
		{#each COLOURS as [code, colour, name] (code)}
			<button
				type="button"
				class="h-5 w-5 rounded-[4px] border border-line-2 transition-transform hover:scale-110"
				style="background: {colour}"
				title="{name} §{code}"
				aria-label="{name} §{code}"
				onmousedown={(e) => e.preventDefault()}
				onclick={() => run((t, a, b) => applyCode(t, a, b, code))}
			></button>
		{/each}
		<span class="mx-1 h-4 w-px bg-line"></span>
		{#each STYLES as [code, letter, name, style] (code)}
			<button
				type="button"
				class="btn-ghost h-5 min-w-5 px-1 font-mono text-[11px] {style}"
				title="{name} §{code}"
				aria-label="{name} §{code}"
				onmousedown={(e) => e.preventDefault()}
				onclick={() => run((t, a, b) => applyCode(t, a, b, code))}>{letter}</button
			>
		{/each}
		<span class="mx-1 h-4 w-px bg-line"></span>
		<button
			type="button"
			class="btn-ghost h-5 px-1.5 text-[11px]"
			title="Reset §r: plain text from here, or for the selection"
			onmousedown={(e) => e.preventDefault()}
			onclick={() => run((t, a, b) => applyCode(t, a, b, 'r'))}>Reset</button
		>
		<button
			type="button"
			class="btn-ghost h-5 px-1.5 text-[11px]"
			title="Remove all codes from the selection, or from the whole text"
			onmousedown={(e) => e.preventDefault()}
			onclick={() => run(clearCodes)}>Clear</button
		>
	</div>
{/if}
<textarea
	{id}
	bind:this={area}
	class="input h-auto min-h-[4.5rem] resize-y py-2 font-mono text-sm leading-5"
	rows="2"
	spellcheck="false"
	{disabled}
	{placeholder}
	{value}
	oninput={(e) => onchange((e.currentTarget as HTMLTextAreaElement).value)}></textarea>
<!-- As the multiplayer list shows it: two lines on a dark background. -->
<div class="mt-2 rounded-[var(--radius-control)] bg-[#1e1e1e] px-3 py-2 text-sm leading-5">
	{#if value || placeholder}
		<MinecraftMOTD motd={value || placeholder} class="whitespace-pre-line" />
	{:else}
		<span class="text-[#8a8a8a]">Preview</span>
	{/if}
</div>
{#if lines > 2}
	<p class="mt-1 text-xs text-warn">The server list shows only the first two lines.</p>
{/if}
