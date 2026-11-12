<script lang="ts">
	import Icon from './Icon.svelte';

	interface Props {
		codes: string[];
		username: string;
	}

	let { codes, username }: Props = $props();

	let copied = $state(false);

	const text = $derived(
		`GameFleet recovery codes for ${username}\nEach code works once, instead of a code from the authenticator.\n\n${codes.join('\n')}\n`
	);

	async function copy() {
		try {
			await navigator.clipboard.writeText(text);
			copied = true;
			setTimeout(() => (copied = false), 2000);
		} catch {
			// Clipboard access can be refused; the codes stay on screen and can be downloaded.
		}
	}

	function download() {
		const url = URL.createObjectURL(new Blob([text], { type: 'text/plain' }));
		const link = document.createElement('a');
		link.href = url;
		link.download = `gamefleet-recovery-codes-${username}.txt`;
		link.click();
		URL.revokeObjectURL(url);
	}
</script>

<div class="rounded-[var(--radius-control)] border border-line bg-surface-2 p-4">
	<ul class="grid grid-cols-2 gap-x-6 gap-y-1.5 font-mono text-sm">
		{#each codes as code (code)}<li>{code}</li>{/each}
	</ul>
	<div class="mt-4 flex gap-2">
		<button type="button" class="btn-outline btn-sm" onclick={copy}>
			<Icon name={copied ? 'check' : 'save'} size={14} />{copied ? 'Copied' : 'Copy'}
		</button>
		<button type="button" class="btn-outline btn-sm" onclick={download}>
			<Icon name="upload" size={14} class="rotate-180" />Download .txt
		</button>
	</div>
</div>
