<script lang="ts">
	import { onMount } from 'svelte';
	import Icon from './Icon.svelte';

	let isDark = $state(false);

	onMount(() => {
		isDark = document.documentElement.dataset.theme === 'dark';
		const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
		const handleChange = (e: MediaQueryListEvent) => {
			if (!localStorage.getItem('theme')) apply(e.matches);
		};
		mediaQuery.addEventListener('change', handleChange);
		return () => mediaQuery.removeEventListener('change', handleChange);
	});

	function apply(dark: boolean) {
		isDark = dark;
		document.documentElement.dataset.theme = dark ? 'dark' : 'light';
	}

	function toggle() {
		apply(!isDark);
		try {
			localStorage.setItem('theme', isDark ? 'dark' : 'light');
		} catch {
			// Storage can be unavailable (private mode, quota); the value is only a convenience.
		}
	}
</script>

<button
	class="btn-ghost btn-icon"
	onclick={toggle}
	aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
	title={isDark ? 'Light mode' : 'Dark mode'}
>
	<Icon name={isDark ? 'sun' : 'moon'} size={18} />
</button>
