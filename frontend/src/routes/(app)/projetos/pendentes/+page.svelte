<script lang="ts">
	/**
	 * Tela "Projetos Pendentes" (FASE 2 — leitura). Consome
	 * `GET /api/projetos-pendentes` via `$lib/api/pendentes` e renderiza a lista
	 * com os componentes compartilhados Card/Badge (reusados, não editados) e o
	 * card específico desta tela (`PendingProjectCard`). Filtros de período,
	 * responsável e órgão re-buscam server-side (o `orgao_scope` é aplicado no
	 * backend). Estados de loading/erro/vazio anunciados via aria-live.
	 *
	 * Referência visual: templates/projects/pendentes.html.
	 */
	import { onMount } from 'svelte';
	import { fetchPendentes } from '$lib/api/pendentes';
	import { ApiClientError } from '$lib/api/client';
	import type {
		PendingData,
		PendingFilters,
		PendingPeriodo
	} from '$lib/types/pendentes';
	import PendingProjectCard from '$lib/components/PendingProjectCard.svelte';

	type LoadState = 'loading' | 'ready' | 'error';

	/** Opções de janela (espelham `period_options` do backend). */
	const PERIOD_OPTIONS: { value: PendingPeriodo; label: string }[] = [
		{ value: 'atrasados', label: 'Projetos Atrasados' },
		{ value: '7dias', label: 'Próximos 7 Dias' },
		{ value: '14dias', label: 'Próximos 14 Dias' },
		{ value: '21dias', label: 'Próximos 21 Dias' }
	];

	const PERIOD_LABEL: Record<PendingPeriodo, string> = {
		atrasados: 'Atrasados',
		'7dias': 'Próximos 7 Dias',
		'14dias': 'Próximos 14 Dias',
		'21dias': 'Próximos 21 Dias'
	};

	let loadState = $state<LoadState>('loading');
	let data = $state<PendingData | null>(null);
	let errorMessage = $state<string>('');

	// Filtros controlados pela UI; a busca acontece server-side.
	let periodo = $state<PendingPeriodo>('atrasados');
	let responsavel = $state<string>('');
	let page = $state<number>(1);

	let inFlight: AbortController | null = null;

	async function load(): Promise<void> {
		loadState = data ? loadState : 'loading';
		errorMessage = '';
		inFlight?.abort();
		const controller = new AbortController();
		inFlight = controller;

		const filters: PendingFilters = { periodo, responsavel, page };
		try {
			const next = await fetchPendentes(filters, controller.signal);
			if (controller.signal.aborted) return;
			data = next;
			// Reconcilia os filtros com o que o backend efetivamente aplicou.
			periodo = next.filtro_periodo;
			responsavel = next.selected_responsavel;
			page = next.pagination.page;
			loadState = 'ready';
		} catch (err) {
			if (controller.signal.aborted) return;
			// 401 já redirecionou; aqui tratamos os demais erros.
			if (err instanceof ApiClientError && err.code === 'unauthenticated') return;
			errorMessage =
				err instanceof Error ? err.message : 'Falha ao carregar os projetos pendentes.';
			loadState = 'error';
		}
	}

	function onPeriodoChange(event: Event): void {
		periodo = (event.currentTarget as HTMLSelectElement).value as PendingPeriodo;
		page = 1;
		void load();
	}

	function onResponsavelChange(event: Event): void {
		responsavel = (event.currentTarget as HTMLSelectElement).value;
		page = 1;
		void load();
	}

	function clearFilters(): void {
		periodo = 'atrasados';
		responsavel = '';
		page = 1;
		void load();
	}

	function goToPage(target: number): void {
		page = target;
		void load();
	}

	onMount(() => {
		void load();
		return () => inFlight?.abort();
	});

	const summary = $derived(data?.summary_counts ?? null);
	const pagination = $derived(data?.pagination ?? null);
	const hasActiveFilters = $derived(periodo !== 'atrasados' || responsavel !== '');
</script>

<svelte:head>
	<title>Projetos Pendentes — ProjetosRJ</title>
</svelte:head>

<section aria-labelledby="pendentes-title" class="flex flex-col gap-6">
	<header class="flex flex-col gap-2">
		<div class="flex flex-wrap items-center gap-3">
			<h1 id="pendentes-title" class="font-heading text-2xl font-bold text-text-primary">
				Projetos Pendentes
			</h1>
			{#if summary}
				<span
					class="inline-flex items-center gap-1 rounded-sm border border-primary-500 bg-primary-100 px-2 py-1 text-xs font-medium text-primary-700"
				>
					Projetos no foco: {summary.total_projects}
				</span>
			{/if}
		</div>
		<p class="text-sm text-text-secondary">
			Janela ativa: <strong class="font-semibold text-text-primary">{PERIOD_LABEL[periodo]}</strong>
			{#if responsavel}
				· Responsável: <strong class="font-semibold text-text-primary">{responsavel}</strong>
			{/if}
		</p>
	</header>

	<!-- Filtros (re-buscam server-side) -->
	<form
		class="flex flex-wrap items-end gap-4 rounded-lg border border-border-subtle bg-surface px-5 py-4 shadow-sm"
		aria-label="Filtros de projetos pendentes"
		onsubmit={(e) => e.preventDefault()}
	>
		<div class="flex min-w-[12rem] flex-col gap-1">
			<label for="periodoFilter" class="text-xs font-semibold uppercase tracking-wide text-text-muted">
				Período
			</label>
			<select
				id="periodoFilter"
				value={periodo}
				onchange={onPeriodoChange}
				class="rounded-md border border-border-subtle bg-surface px-3 py-2 text-sm text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
			>
				{#each PERIOD_OPTIONS as option (option.value)}
					<option value={option.value}>{option.label}</option>
				{/each}
			</select>
		</div>

		<div class="flex min-w-[12rem] flex-col gap-1">
			<label
				for="responsavelFilter"
				class="text-xs font-semibold uppercase tracking-wide text-text-muted"
			>
				Responsável
			</label>
			<select
				id="responsavelFilter"
				value={responsavel}
				onchange={onResponsavelChange}
				disabled={!data || data.responsaveis_options.length === 0}
				class="rounded-md border border-border-subtle bg-surface px-3 py-2 text-sm text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-60"
			>
				<option value="">Todos</option>
				{#if data}
					{#each data.responsaveis_options as nome (nome)}
						<option value={nome}>{nome}</option>
					{/each}
				{/if}
			</select>
		</div>

		{#if hasActiveFilters}
			<button
				type="button"
				onclick={clearFilters}
				class="rounded-md border border-border-subtle bg-surface px-4 py-2 text-sm font-medium text-text-primary transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
			>
				Limpar filtros
			</button>
		{/if}
	</form>

	{#if loadState === 'loading'}
		<p role="status" aria-live="polite" class="text-text-secondary">Carregando projetos…</p>
	{:else if loadState === 'error'}
		<div
			role="alert"
			class="flex flex-col items-start gap-3 rounded-lg border border-danger bg-surface px-5 py-4"
		>
			<p class="text-text-primary">{errorMessage}</p>
			<button
				type="button"
				onclick={() => load()}
				class="rounded-md border border-border-subtle bg-surface px-4 py-2 text-sm font-medium text-text-primary transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
			>
				Tentar novamente
			</button>
		</div>
	{:else if data}
		{#if data.projetos.length === 0}
			<div
				role="status"
				aria-live="polite"
				class="rounded-lg border border-border-subtle bg-surface px-5 py-8 text-center text-text-muted"
			>
				Nenhum projeto pendente para os filtros selecionados.
			</div>
		{:else}
			<div class="flex flex-col gap-4" aria-busy={loadState !== 'ready'}>
				{#each data.projetos as row (row.project.id)}
					<PendingProjectCard
						{row}
						bucketMap={data.etapa_bucket_map}
						progressMap={data.etapa_task_progress}
					/>
				{/each}
			</div>

			{#if pagination && pagination.total_pages > 1}
				<nav class="flex items-center justify-center gap-3" aria-label="Paginação de projetos">
					<button
						type="button"
						onclick={() => goToPage(pagination.page - 1)}
						disabled={pagination.page <= 1}
						class="rounded-md border border-border-subtle bg-surface px-4 py-2 text-sm font-medium text-text-primary transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-50"
					>
						Anterior
					</button>
					<span class="text-sm text-text-secondary" aria-live="polite">
						Página {pagination.page} de {pagination.total_pages}
					</span>
					<button
						type="button"
						onclick={() => goToPage(pagination.page + 1)}
						disabled={pagination.page >= pagination.total_pages}
						class="rounded-md border border-border-subtle bg-surface px-4 py-2 text-sm font-medium text-text-primary transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-50"
					>
						Próxima
					</button>
				</nav>
			{/if}
		{/if}
	{/if}
</section>
