<script lang="ts">
	import parse from '@sfirew/minecraft-motd-parser';

	interface Props {
		motd: string;
		class?: string;
	}

	let { motd, class: className = '' }: Props = $props();

	function toHtml(text: string): string {
		try {
			return parse.textToHTML(text);
		} catch (error) {
			console.warn('Failed to parse Minecraft MOTD:', error);
			return parse.htmlStringFormatting(text.replace(/§[0-9a-fk-or]/gi, ''));
		}
	}

	const html = $derived(toHtml(motd));
</script>

<div class="minecraft-motd {className}">
	<!-- eslint-disable-next-line svelte/no-at-html-tags -- textToHTML/htmlStringFormatting escape the server-provided text -->
	{@html html}
</div>
