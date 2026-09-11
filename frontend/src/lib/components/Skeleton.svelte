<script lang="ts">
	interface Props {
		class?: string;
	}

	let { class: className = 'h-4 w-24' }: Props = $props();
</script>

<span class="skeleton {className}" aria-hidden="true"></span>
