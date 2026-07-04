<script lang="ts">
	/**
	 * Form "Novo órgão" (Admin > Órgãos). URL `/spa/admin/orgaos/novo`. Carrega os
	 * catálogos (tipos + candidatos a pai) via `GET /api/admin/orgaos` e cria o
	 * órgão via `POST /api/admin/orgaos`. Aceita `?pai_id=` na query (vindo do
	 * botão "adicionar subunidade" da árvore) para pré-selecionar o pai.
	 *
	 * O backend determina `is_root` (primeiro órgão sem pai). Quando ainda não há
	 * raiz, o form opera em modo raiz: o pai é fixo em "— raiz —" e o tipo deve
	 * ser um tipo `permite_raiz`. Validações (tipo/pai/hierarquia/profundidade)
	 * são do backend: erros 422/409 viram mensagem no topo do form. Sucesso
	 * navega de volta para a árvore. Links base-aware (`$app/paths`).
	 *
	 * Referência visual: templates/admin/orgao_form.html.
	 */
	import { onMount } from 'svelte';
	import { base } from '$app/paths';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { fetchOrgaoTree, createOrgao } from '$lib/api/adminOrgaos';
	import { ApiClientError } from '$lib/api/client';
	import type { CandidatoPai, OrgaoTipo } from '$lib/types/adminOrgaos';
	import OrgaoFormFields from '$lib/components/OrgaoFormFields.svelte';

	type LoadState = 'loading' | 'ready' | 'error';

	let loadState = $state<LoadState>('loading');
	let loadError = $state<string>('');
	let errorKind = $state<'forbidden' | 'generic'>('generic');

	let tipos = $state<OrgaoTipo[]>([]);
	let candidatosPai = $state<CandidatoPai[]>([]);
	/** True quando ainda não há órgão raiz: o primeiro órgão criado é a raiz. */
	let isRoot = $state(false);

	// Campos do form (controlados; enviados como payload string/number).
	let nome = $state('');
	let sigla = $state('');
	let tipoId = $state('');
	let paiId = $state('');
	let ordem = $state('0');
	let ativo = $state(true);
	let codigoExterno = $state('');
	let dataInicio = $state('');
	let dataFim = $state('');

	let submitting = $state(false);
	let submitError = $state('');

	const preselectedPaiId = $derived($page.url.searchParams.get('pai_id') ?? '');

	let inFlight: AbortController | null = null;

	async function load(): Promise<void> {
		loadState = 'loading';
		loadError = '';
		errorKind = 'generic';
		inFlight?.abort();
		const controller = new AbortController();
		inFlight = controller;
		try {
			const data = await fetchOrgaoTree(controller.signal);
			if (controller.signal.aborted) return;
			tipos = data.tipos;
			candidatosPai = data.candidatos_pai;
			isRoot = data.total === 0;
			if (!isRoot && preselectedPaiId) paiId = preselectedPaiId;
			loadState = 'ready';
		} catch (err) {
			if (controller.signal.aborted) return;
			if (err instanceof ApiClientError && err.code === 'unauthenticated') return;
			if (err instanceof ApiClientError && err.code === 'forbidden') {
				errorKind = 'forbidden';
				loadError = 'Você não tem permissão para gerenciar órgãos.';
			} else {
				loadError = err instanceof Error ? err.message : 'Falha ao carregar o formulário.';
			}
			loadState = 'error';
		}
	}

	async function onSubmit(event: SubmitEvent): Promise<void> {
		event.preventDefault();
		if (submitting) return;
		submitting = true;
		submitError = '';
		try {
			await createOrgao({
				nome,
				sigla,
				tipo_id: tipoId,
				pai_id: isRoot ? null : paiId,
				ordem,
				ativo: ativo ? '1' : '0',
				codigo_externo: codigoExterno,
				data_inicio_vigencia: dataInicio,
				data_fim_vigencia: dataFim
			});
			await goto(`${base}/admin/orgaos`);
		} catch (err) {
			if (err instanceof ApiClientError && err.code === 'unauthenticated') return;
			submitError = err instanceof Error ? err.message : 'Não foi possível criar o órgão.';
		} finally {
			submitting = false;
		}
	}

	onMount(() => {
		void load();
		return () => inFlight?.abort();
	});
</script>

<svelte:head>
	<title>Novo órgão — ProjetosRJ</title>
</svelte:head>

<section aria-labelledby="novo-orgao-title" class="flex flex-col gap-6">
	<header class="flex flex-col gap-2">
		<a
			href={`${base}/admin/orgaos`}
			class="w-fit text-sm text-text-secondary hover:text-text-primary hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
		>
			← Voltar à árvore
		</a>
		<h1 id="novo-orgao-title" class="font-heading text-2xl font-bold text-text-primary">
			Novo órgão
		</h1>
	</header>

	{#if loadState === 'loading'}
		<p role="status" aria-live="polite" class="text-text-secondary">Carregando formulário…</p>
	{:else if loadState === 'error'}
		<div role="alert" class="flex flex-col items-start gap-3 rounded-lg border border-danger bg-surface px-5 py-4">
			<p class="text-text-primary">{loadError}</p>
			{#if errorKind !== 'forbidden'}
				<button
					type="button"
					onclick={() => load()}
					class="rounded-md border border-border-subtle bg-surface px-4 py-2 text-sm font-medium text-text-primary hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
				>
					Tentar novamente
				</button>
			{/if}
		</div>
	{:else}
		<form class="flex flex-col gap-5" onsubmit={onSubmit}>
			{#if submitError}
				<div role="alert" class="rounded-md border border-danger bg-surface px-4 py-3 text-sm text-text-primary">
					{submitError}
				</div>
			{/if}

			<OrgaoFormFields
				{tipos}
				{candidatosPai}
				{isRoot}
				bind:nome
				bind:sigla
				bind:tipoId
				bind:paiId
				bind:ordem
				bind:ativo
				bind:codigoExterno
				bind:dataInicio
				bind:dataFim
			/>

			<div class="flex items-center gap-3">
				<button
					type="submit"
					disabled={submitting}
					class="inline-flex h-9 items-center rounded-md bg-primary-600 px-3.5 text-sm font-semibold text-white shadow-sm transition-all duration-fast hover:bg-primary-700 hover:shadow-md focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 disabled:shadow-none"
				>
					{submitting ? 'Criando…' : 'Criar órgão'}
				</button>
				<a
					href={`${base}/admin/orgaos`}
					class="rounded-md border border-border-subtle bg-surface px-5 py-2 text-sm font-medium text-text-primary hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
				>
					Cancelar
				</a>
			</div>
		</form>
	{/if}
</section>
