<script lang="ts">
	import { encode } from 'uqr';

	interface Props {
		value: string;
		/** Rendered width and height in pixels. */
		size?: number;
		label?: string;
	}

	let { value, size = 184, label = 'QR code' }: Props = $props();

	// One path for all dark modules, drawn as SVG elements rather than an HTML string.
	const qr = $derived(encode(value, { ecc: 'M', border: 2 }));
	const path = $derived(
		qr.data.flatMap((row, y) => row.map((dark, x) => (dark ? `M${x} ${y}h1v1h-1z` : ''))).join('')
	);
</script>

<svg
	viewBox="0 0 {qr.data.length} {qr.data.length}"
	width={size}
	height={size}
	class="rounded-md bg-white"
	shape-rendering="crispEdges"
	role="img"
	aria-label={label}
>
	<path d={path} fill="#000" />
</svg>
