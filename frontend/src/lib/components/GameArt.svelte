<script lang="ts">
	import type { GameServerType } from '$lib/api/Api';
	import { gameArtUrl, gameLabel } from '$lib/games';

	interface Props {
		game: GameServerType;
		kind?: 'poster' | 'hero';
		/** Base64 PNG advertised by the server itself (Minecraft); shown centered inside the poster frame. */
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

{#if iconSrc}
	<!-- Square server icons keep the same frame as game posters: a blurred copy fills the frame, the icon sits centered. -->
	<div class="relative overflow-hidden {className}" aria-label={label}>
		<img
			src={iconSrc}
			alt=""
			aria-hidden="true"
			class="absolute inset-0 h-full w-full scale-150 object-cover opacity-70 blur-md"
		/>
		<div class="absolute inset-0 bg-black/10"></div>
		<img
			src={iconSrc}
			alt={label}
			class="image-pixelated absolute top-1/2 left-1/2 w-[72%] -translate-x-1/2 -translate-y-1/2 rounded-md shadow-lg"
		/>
	</div>
{:else if !failed}
	<img
		src={gameArtUrl(game, kind)}
		alt={label}
		loading="lazy"
		decoding="async"
		class="object-cover {className}"
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
