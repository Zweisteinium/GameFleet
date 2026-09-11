<script lang="ts">
	import type { GameServerType } from '$lib/api/Api';
	import { gameArtUrl, gameLabel } from '$lib/games';

	interface Props {
		game: GameServerType;
		kind?: 'poster' | 'hero';
		/** Base64 PNG advertised by the server itself (Minecraft); takes precedence over the game poster. */
		serverIcon?: string | null;
		class?: string;
	}

	let { game, kind = 'poster', serverIcon = null, class: className = '' }: Props = $props();

	let failed = $state(false);

	const iconSrc = $derived(
		serverIcon
			? serverIcon.startsWith('data:')
				? serverIcon
				: `data:image/png;base64,${serverIcon}`
			: null
	);
	const src = $derived(iconSrc ?? gameArtUrl(game, kind));
	const label = $derived(gameLabel(game));

	// Deterministic hue per game for the fallback tile.
	const hue = $derived([...game].reduce((h, ch) => (h * 31 + ch.charCodeAt(0)) % 360, 7));
	const initials = $derived(
		label
			.replace(/\(.*?\)/g, '')
			.split(/[\s:]+/)
			.filter(Boolean)
			.slice(0, 2)
			.map((w) => w[0]?.toUpperCase())
			.join('')
	);
</script>

{#if !failed}
	<img
		{src}
		alt={label}
		loading="lazy"
		decoding="async"
		class="object-cover {className} {iconSrc ? 'image-pixelated aspect-square h-auto!' : ''}"
		onerror={() => (failed = true)}
	/>
{:else}
	<div
		class="grid place-items-center font-display font-semibold text-white {className}"
		style="background: linear-gradient(145deg, hsl({hue} 60% 45%), hsl({(hue + 40) % 360} 65% 30%))"
		aria-label={label}
	>
		{initials}
	</div>
{/if}

<style>
	.image-pixelated {
		image-rendering: pixelated;
	}
</style>
