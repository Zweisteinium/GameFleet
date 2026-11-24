<script lang="ts">
	interface Props {
		username: string;
	}

	let { username }: Props = $props();
</script>

<!--
	For password managers, in the steps after the password: names the user the form is about. Without it they
	put the user name into the only text field there, the code field. Not shown, not focusable.
-->
<input
	type="text"
	name="username"
	autocomplete="username"
	value={username}
	readonly
	tabindex="-1"
	aria-hidden="true"
	class="sr-only"
/>
