<script lang="ts">
	/** The GameFleet mark: three hulls in echelon formation. Inherits `currentColor`. */
	interface Props {
		size?: number;
		class?: string;
	}
	let { size = 22, class: className = '' }: Props = $props();
</script>

<svg
	width={size}
	height={size}
	viewBox="0 0 32 32"
	class={className}
	aria-hidden="true"
	fill="currentColor"
	stroke="currentColor"
	stroke-width="1.2"
	stroke-linejoin="round"
>
	<path d="M3 6.5h11l3.5 3-3.5 3H3z" />
	<path d="M8 14.5h13l3.5 3-3.5 3H8z" />
	<path d="M13 22.5h11l3.5 3-3.5 3H13z" />
</svg>
