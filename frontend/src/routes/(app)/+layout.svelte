<script lang="ts">
	/**
	 * Layout do grupo autenticado (PILOTO).
	 *
	 * - Carrega `/api/me` no boot (store de auth).
	 * - Guard: enquanto carrega, mostra estado de loading; se 401, `client.ts`
	 *   ja navegou top-level para /login (aqui so evitamos renderizar conteudo
	 *   protegido).
	 * - Renderiza a AppTopnav minima (titulo + theme toggle).
	 *
	 * Stubs visuais de notificacoes/busca/chatbot NAO entram nesta etapa.
	 */
	import { onMount } from 'svelte';
	import type { Snippet } from 'svelte';
	import { auth, loadCurrentUser } from '$lib/stores/auth';
	import AppTopnav from '$lib/components/AppTopnav.svelte';
	import FlashToasts from '$lib/components/FlashToasts.svelte';

	let { children }: { children: Snippet } = $props();

	onMount(() => {
		void loadCurrentUser();
	});
</script>

<div class="flex min-h-screen flex-col bg-canvas text-text-primary">
	<AppTopnav user={$auth.user} />

	<main class="mx-auto w-full max-w-6xl flex-1 px-5 py-6">
		{#if $auth.status === 'authenticated'}
			{@render children()}
		{:else if $auth.status === 'unauthenticated' && $auth.error}
			<div
				role="alert"
				class="rounded-lg border border-danger bg-surface px-5 py-4 text-text-primary"
			>
				{$auth.error}
			</div>
		{:else}
			<div
				class="flex items-center gap-3 text-text-secondary"
				role="status"
				aria-live="polite"
			>
				<span
					class="h-4 w-4 animate-spin rounded-full border-2 border-border-subtle border-t-primary-600"
					aria-hidden="true"
				></span>
				<span>Carregando…</span>
			</div>
		{/if}
	</main>

	<FlashToasts />
</div>
