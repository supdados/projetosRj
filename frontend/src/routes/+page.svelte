<script lang="ts">
	/**
	 * Raiz da SPA. Usa `goto` com `base` para respeitar paths.base=/static/spa.
	 */
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { base } from '$app/paths';

	onMount(() => {
		void goto(`${base}/dashboard`, { replaceState: true });
	});
</script>

<main class="flex min-h-screen items-center justify-center bg-canvas text-text-secondary">
	<p role="status" aria-live="polite">Redirecionando…</p>
</main>
