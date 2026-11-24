<script lang="ts">
	import RecoveryCodes from './RecoveryCodes.svelte';

	interface Props {
		codes: string[];
		username: string;
		onfinish: () => void;
	}

	let { codes, username, onfinish }: Props = $props();

	let saved = $state(false);
</script>

<p class="mb-4 text-sm text-ink-2">
	If you lose your phone, each of these codes signs you in once instead of the app. Keep them
	somewhere safe, apart from your password.
</p>
<RecoveryCodes {codes} {username} />
<label class="mt-5 flex items-center gap-2.5 text-sm">
	<input type="checkbox" class="h-4 w-4 accent-accent" bind:checked={saved} />
	I have saved these codes
</label>
<button type="button" class="btn-primary mt-5 w-full" disabled={!saved} onclick={onfinish}>
	Continue to GameFleet
</button>
