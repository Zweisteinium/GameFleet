// Apply the saved theme before first paint to avoid a light flash in dark mode. A file rather than an inline
// script, so the Content-Security-Policy can forbid inline scripts.
try {
	// ?theme=light|dark overrides the saved preference (handy for sharing links and screenshots).
	const param = new URLSearchParams(location.search).get('theme');
	const stored = param === 'light' || param === 'dark' ? param : localStorage.getItem('theme');
	const dark = stored ? stored === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches;
	document.documentElement.dataset.theme = dark ? 'dark' : 'light';
} catch {
	// Storage can be unavailable (private mode); the system preference applies then.
}
