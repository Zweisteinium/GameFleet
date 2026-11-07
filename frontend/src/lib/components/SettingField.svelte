<script lang="ts">
	import MotdEditor from './MotdEditor.svelte';
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

	const numeric = $derived(type === 'int' || type === 'float');
</script>

<div class="min-w-0 {multiline || motd ? 'sm:col-span-2' : ''}" title={description}>
	{#if type === 'bool'}
		<label class="flex items-start gap-3 py-1 text-sm {disabled ? 'opacity-60' : ''}">
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
		{:else if motd}
			<MotdEditor
				{id}
				value={value == null ? '' : String(value)}
				{placeholder}
				{disabled}
				onchange={(v) => onchange(v)}
			/>
		{:else if multiline}
			<textarea
				{id}
				class="input h-auto min-h-[4.5rem] resize-y py-2 font-mono text-sm leading-5"
				rows="2"
				{disabled}
				{placeholder}
				value={value == null ? '' : String(value)}
				oninput={(e) => onchange((e.currentTarget as HTMLTextAreaElement).value)}></textarea>
		{:else if type === 'secret'}
			<!-- The current password is never sent here: the field only takes a new one. -->
			<input
				{id}
				class="input font-mono"
				type="password"
				autocomplete="new-password"
				{disabled}
				{placeholder}
				value={value ?? ''}
				oninput={(e) => onchange((e.currentTarget as HTMLInputElement).value)}
			/>
		{:else}
			<input
				{id}
				class="input {numeric ? 'font-mono' : ''}"
				type={numeric ? 'number' : 'text'}
				step={type === 'float' ? 'any' : undefined}
				{disabled}
				{placeholder}
				value={value ?? ''}
				onchange={(e) => {
					const raw = (e.currentTarget as HTMLInputElement).value;
					onchange(numeric ? Number(raw) : raw);
				}}
			/>
		{/if}
	{/if}
	{#if note}<p class="hint mt-1">{note}</p>{/if}
	{#if description && type !== 'bool'}<p class="hint mt-1">{description}</p>{/if}
</div>
