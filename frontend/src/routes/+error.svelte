<script lang="ts">
	import { page } from '$app/state';
	import { resolve } from '$app/paths';
	import Icon from '$lib/components/Icon.svelte';
</script>

<svelte:head>
	<title>{page.status} · GameFleet</title>
</svelte:head>

<div class="card mx-auto mt-16 max-w-md px-8 py-14 text-center">
	<Icon name="alert" size={24} class="text-ink-3 mx-auto mb-4" />
	<h1 class="text-lg font-semibold">
		{page.status === 404 ? 'Page not found' : `Error ${page.status}`}
	</h1>
	<p class="text-ink-2 mt-2 mb-6 text-sm">
		{page.status === 404 ? 'There is nothing at this address.' : page.error?.message}
	</p>
	<a href={resolve('/main')} class="btn-primary">Back to servers</a>
</div>
