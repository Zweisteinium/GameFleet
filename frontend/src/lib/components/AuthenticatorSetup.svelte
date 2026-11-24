<script lang="ts">
	import type { LoginResult } from '$lib/api/Api';
	import CodeInput from './CodeInput.svelte';
	import QrCode from './QrCode.svelte';

	interface Props {
		/** An `enroll` result: QR data and the user name. */
		challenge: LoginResult;
		code: string;
		disabled?: boolean;
	}

	let { challenge, code = $bindable(''), disabled = false }: Props = $props();

	/** The base32 key in groups of four, easier to type into an app by hand. */
	const groupedSecret = $derived((challenge.totp_secret ?? '').replace(/(.{4})/g, '$1 ').trim());
</script>

<!-- Fields only: the page around it provides the form, the submit button and the errors. -->
<ol class="space-y-5 text-sm">
	<li>
		<p class="mb-3">
			1. Scan this code with an authenticator app (Aegis, Google Authenticator, 1Password, Bitwarden
			…).
		</p>
		<div class="flex flex-col items-center gap-3">
			{#if challenge.totp_uri}
				<QrCode value={challenge.totp_uri} label="QR code for the authenticator app" />
			{/if}
			<details class="w-full text-center">
				<summary class="hint cursor-pointer">Can't scan it? Enter the key by hand</summary>
				<p class="mt-2 font-mono text-sm break-all select-all">{groupedSecret}</p>
				<p class="hint mt-1">Time-based, 6 digits, 30 seconds.</p>
			</details>
		</div>
	</li>
	<li>
		<p class="mb-3">2. Enter the 6-digit code the app shows to confirm it works.</p>
		<div class="flex justify-center">
			<CodeInput bind:value={code} {disabled} label="Code from the new authenticator" />
		</div>
	</li>
</ol>
