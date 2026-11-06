<script lang="ts">
	import { serverPage } from '$lib/serverPage.svelte';
	import ComposeSettings from '$lib/components/ComposeSettings.svelte';
	import SettingsPanel from '$lib/components/SettingsPanel.svelte';

	const ctx = serverPage();
	// Unknown until the compose file was read; a server without one keeps the settings file as its form.
	let compose = $state<boolean | null>(null);
</script>

<svelte:head><title>Settings · {ctx.server.name} · GameFleet</title></svelte:head>

<div class="space-y-5">
	{#if compose !== false}
		<ComposeSettings
			server={ctx.server}
			running={ctx.running}
			playersOnline={ctx.liveInfo?.players_online ?? null}
			onRecreate={ctx.recreate}
			onLoaded={(info) => (compose = info.supported)}
		/>
	{/if}
	{#if compose !== null}
		<SettingsPanel
			server={ctx.server}
			running={ctx.running}
			onRestart={() => ctx.power('restart')}
			advanced={compose}
		/>
	{/if}
</div>
