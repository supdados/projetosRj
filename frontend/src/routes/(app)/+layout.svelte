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
	import { afterNavigate } from '$app/navigation';
	import type { Snippet } from 'svelte';
	import { auth, loadCurrentUser } from '$lib/stores/auth';
	import AppTopnav from '$lib/components/AppTopnav.svelte';
	import FlashToasts from '$lib/components/FlashToasts.svelte';

	let { children }: { children: Snippet } = $props();

	// O scroller da pagina agora e o <main> (nao mais a janela), entao a
	// restauracao de scroll do Kit nao se aplica: reposiciona no topo a cada
	// navegacao para nao herdar o scroll da pagina anterior.
	let mainEl = $state<HTMLElement | null>(null);

	onMount(() => {
		void loadCurrentUser();
	});

	afterNavigate(() => {
		mainEl?.scrollTo(0, 0);
	});
</script>

<div class="app-shell flex flex-col overflow-hidden bg-canvas text-text-primary">
	<AppTopnav user={$auth.user} />

	<!-- Sem teto de largura: o conteudo (itens) cresce com a tela. O respiro lateral
	     e um padding responsivo que escala em telas menores e TRAVA em ~7rem a partir
	     do tamanho de notebook -> respiro constante em telas grandes, itens aumentam.
	     overflow-y-auto: a barra de rolagem da pagina vive aqui, comecando logo abaixo
	     do topnav fixo (mesmo padrao do painel Projetos Recentes). -->
	<main
		bind:this={mainEl}
		class="mx-auto w-full min-h-0 flex-1 overflow-y-auto px-[clamp(1.5rem,8vw,7rem)] py-6"
	>
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
