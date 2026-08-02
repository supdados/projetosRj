<script lang="ts">
	/**
	 * REDIRECT: o histórico do projeto virou um DRAWER no detalhe
	 * (`ProjectHistoryDrawer`, aberto pelo botão "Ver Histórico" ou pelo
	 * query-param `?historico=1`). Esta rota permanece SÓ para manter os
	 * deep-links antigos vivos — o path segue no matcher de `routes/spa.py`
	 * e na matriz de testes de rotas, então NÃO pode ser removido.
	 */
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { base } from '$app/paths';
	import { page } from '$app/stores';

	onMount(() => {
		void goto(`${base}/projetos/${$page.params.id}?historico=1`, { replaceState: true });
	});
</script>

<svelte:head>
	<title>ProjetosRJ — Histórico do projeto</title>
</svelte:head>

<p role="status" aria-live="polite" class="text-text-secondary">Abrindo histórico…</p>
