<script lang="ts">
	import { serverPage } from '$lib/serverPage.svelte';
	import BackupPanel from '$lib/components/BackupPanel.svelte';

	const ctx = serverPage();
</script>

<svelte:head><title>Backups · {ctx.server.name} · GameFleet</title></svelte:head>

<BackupPanel
	server={ctx.server}
	running={ctx.running}
	onChanged={() => {
		ctx.refresh();
		ctx.settle();
	}}
/>
