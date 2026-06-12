<script lang="ts">
	/**
	 * Tela "Projetos Pendentes". Consome `GET /api/projetos-pendentes` via
	 * `$lib/api/pendentes` e renderiza a lista com os componentes compartilhados
	 * Card/Badge (reusados, não editados) e o card específico desta tela
	 * (`PendingProjectCard`). Filtros de período, responsável e órgão re-buscam
	 * server-side (o `orgao_scope` é aplicado no backend).
	 *
	 * PARIDADE DE MUTAÇÃO (templates/projects/pendentes.html): botão de status
	 * cíclico por etapa, quick-add de tarefas (drawer por etapa reusando o
	 * TaskDrawer), expandir/recolher "outras etapas" com persistência em
	 * localStorage e botões globais Expandir/Recolher todas. Avisos via
	 * `<FlashToasts>` (equivalente a `window.showFlash`). Sem som/confete (o
	 * fluxo legado não tem).
	 */
	import { onMount } from 'svelte';
	import { fetchPendentes } from '$lib/api/pendentes';
	import { ApiClientError } from '$lib/api/client';
	import type {
		PendingData,
		PendingFilters,
		PendingPeriodo
	} from '$lib/types/pendentes';
	import PageHeader from '$lib/components/PageHeader.svelte';
	import CountBadge from '$lib/components/CountBadge.svelte';
	import PendingProjectCard from '$lib/components/PendingProjectCard.svelte';
	import PaginationBar from '$lib/components/PaginationBar.svelte';
	import StageTaskQuickAdd from '$lib/components/StageTaskQuickAdd.svelte';
	import TaskDrawer from '$lib/components/TaskDrawer.svelte';
	import LoadErrorState from '$lib/components/LoadErrorState.svelte';
	import { createTaskDrawerStore } from '$lib/stores/taskDrawer';

	/** Chave de persistência do estado expandido (mesma semântica do legado). */
	const EXPANDED_STORAGE_KEY = 'pendingExpandedProjects';

	/**
	 * Rótulos de período conhecidos no cliente (espelham `period_label_map` do
	 * backend, routes/projects/views.py). Servem de fallback síncrono para o
	 * subtítulo do header renderizar JUNTO com o título no primeiro paint, sem
	 * esperar o fetch. Quando `data` chega, o mapa do backend tem precedência.
	 */
	const PERIOD_LABELS: Record<PendingPeriodo, string> = {
		atrasados: 'Atrasados',
		'7dias': 'Próximos 7 Dias',
		'14dias': 'Próximos 14 Dias',
		'21dias': 'Próximos 21 Dias'
	};

	type LoadState = 'loading' | 'ready' | 'error';

	let loadState = $state<LoadState>('loading');
	let data = $state<PendingData | null>(null);
	let errorMessage = $state<string>('');

	/** Janela de debounce da busca textual (ms) — paridade com a tela de Projetos. */
	const DEBOUNCE_MS = 300;

	/** Opções de prioridade (lista canônica; o backend filtra por igualdade). */
	const PRIORIDADE_OPTIONS: { value: string; label: string }[] = [
		{ value: 'baixa', label: 'Baixa' },
		{ value: 'media', label: 'Média' },
		{ value: 'alta', label: 'Alta' },
		{ value: 'urgente', label: 'Urgente' }
	];

	// Filtros controlados pela UI; a busca acontece server-side.
	let periodo = $state<PendingPeriodo>('atrasados');
	let search = $state<string>('');
	let responsavel = $state<string>('');
	let prioridade = $state<string>('');
	let orgao = $state<number | null>(null);
	let page = $state<number>(1);

	let inFlight: AbortController | null = null;
	let debounceTimer: ReturnType<typeof setTimeout> | null = null;

	async function load(): Promise<void> {
		loadState = data ? loadState : 'loading';
		errorMessage = '';
		inFlight?.abort();
		const controller = new AbortController();
		inFlight = controller;

		const filters: PendingFilters = { periodo, search, responsavel, prioridade, orgao, page };
		try {
			const next = await fetchPendentes(filters, controller.signal);
			if (controller.signal.aborted) return;
			data = next;
			// Reset do decremento local: o backend já reflete o estado atual.
			focusDelta = 0;
			cardRefs = {};
			// Reconcilia os filtros com o que o backend efetivamente aplicou.
			periodo = next.filtro_periodo;
			search = next.search_query;
			responsavel = next.selected_responsavel;
			prioridade = next.selected_priority;
			orgao = next.selected_orgao;
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

	/** Busca textual com debounce: agenda o reload ao parar de digitar. */
	function onSearchInput(): void {
		if (debounceTimer) clearTimeout(debounceTimer);
		debounceTimer = setTimeout(() => {
			page = 1;
			void load();
		}, DEBOUNCE_MS);
	}

	/** Enter na busca: dispara imediatamente (sem esperar o debounce). */
	function onSearchSubmit(event: SubmitEvent): void {
		event.preventDefault();
		if (debounceTimer) clearTimeout(debounceTimer);
		page = 1;
		void load();
	}

	function onResponsavelChange(event: Event): void {
		responsavel = (event.currentTarget as HTMLSelectElement).value;
		page = 1;
		void load();
	}

	function onPrioridadeChange(event: Event): void {
		prioridade = (event.currentTarget as HTMLSelectElement).value;
		page = 1;
		void load();
	}

	function onOrgaoChange(event: Event): void {
		const raw = (event.currentTarget as HTMLSelectElement).value;
		orgao = raw === '' ? null : Number(raw);
		page = 1;
		void load();
	}

	function clearFilters(): void {
		if (debounceTimer) clearTimeout(debounceTimer);
		periodo = 'atrasados';
		search = '';
		responsavel = '';
		prioridade = '';
		orgao = null;
		page = 1;
		void load();
	}

	function goToPage(target: number): void {
		page = target;
		void load();
	}

	// ── Mutações (paridade com o Jinja) ──────────────────────────────────────

	/** Store do drawer reusada pelo quick-add (NÃO recriar dentro do drawer). */
	const drawer = createTaskDrawerStore();

	/** Set de IDs de projeto expandidos (persistido em localStorage). */
	let expandedProjects = $state<Set<string>>(new Set());

	/** Decremento local do contador global "Projetos no foco". */
	let focusDelta = $state<number>(0);

	/** Referências aos cards montados, para sincronizar progresso pós quick-add. */
	let cardRefs = $state<Record<number, PendingProjectCard | undefined>>({});

	/** Pedido de quick-add ativo (ou `null` quando fechado). */
	interface QuickAddRequest {
		projectId: number;
		projectTitulo: string;
		etapaId: number;
		etapaDescricao: string;
		etapaDatas: string;
		stageDone: boolean;
	}
	let quickAdd = $state<QuickAddRequest | null>(null);

	function readExpandedSet(): Set<string> {
		if (typeof localStorage === 'undefined') return new Set();
		try {
			const raw = localStorage.getItem(EXPANDED_STORAGE_KEY);
			if (!raw) return new Set();
			const parsed = JSON.parse(raw) as unknown;
			return Array.isArray(parsed) ? new Set(parsed.map(String)) : new Set();
		} catch {
			return new Set();
		}
	}

	function saveExpandedSet(set: Set<string>): void {
		if (typeof localStorage === 'undefined') return;
		try {
			localStorage.setItem(EXPANDED_STORAGE_KEY, JSON.stringify([...set]));
		} catch {
			// localStorage indisponível (modo privado): ignora a persistência.
		}
	}

	function setProjectExpanded(projectId: number, expanded: boolean): void {
		const next = new Set(expandedProjects);
		if (expanded) next.add(String(projectId));
		else next.delete(String(projectId));
		expandedProjects = next;
		saveExpandedSet(next);
	}

	function openQuickAdd(request: QuickAddRequest): void {
		quickAdd = request;
	}

	function closeQuickAdd(): void {
		quickAdd = null;
	}

	/** Sincroniza a pílula done/total do card após mutação no quick-add. */
	function syncEtapaProgress(etapaId: number, done: number, total: number): void {
		if (!quickAdd) return;
		cardRefs[quickAdd.projectId]?.syncEtapaProgress(etapaId, done, total);
	}

	/** Um projeto saiu do foco (todas as etapas concluídas): decrementa o total. */
	function onProjectDefocused(): void {
		focusDelta += 1;
	}

	onMount(() => {
		void load();
		expandedProjects = readExpandedSet();
		return () => {
			if (debounceTimer) clearTimeout(debounceTimer);
			inFlight?.abort();
		};
	});

	const summary = $derived(data?.summary_counts ?? null);
	const pagination = $derived(data?.pagination ?? null);
	/** Opções de período rotuladas pelo backend (`period_options`). */
	const periodOptions = $derived(data?.period_options ?? []);
	/**
	 * Rótulo da janela ativa. Deriva do estado local `periodo` (já definido no
	 * primeiro render) via `PERIOD_LABELS`, então o subtítulo aparece JUNTO com o
	 * título — sem o flicker de esperar o `periodo_label` vindo do fetch. O mapa
	 * do backend tem precedência assim que `data` carrega.
	 */
	const periodoLabel = $derived(data?.period_label_map?.[periodo] ?? PERIOD_LABELS[periodo]);
	const hasActiveFilters = $derived(
		periodo !== 'atrasados' ||
			search.trim() !== '' ||
			responsavel !== '' ||
			prioridade !== '' ||
			orgao !== null
	);
	const selectedOrgaoLabel = $derived(
		orgao === null
			? ''
			: (data?.orgaos_options.find((o) => o.value === String(orgao))?.label ?? '')
	);
	/** Subtítulo plano do header (PageHeader recebe texto, não markup). */
	const headerSubtitle = $derived(
		[
			periodoLabel ? `Janela ativa: ${periodoLabel}` : '',
			responsavel ? `Responsável: ${responsavel}` : '',
			selectedOrgaoLabel ? `Órgão: ${selectedOrgaoLabel}` : ''
		]
			.filter(Boolean)
			.join(' · ')
	);
</script>

<svelte:head>
	<title>Projetos Pendentes — ProjetosRJ</title>
</svelte:head>

<section aria-labelledby="pendentes-title" class="flex flex-col gap-6">
	<!-- CARD ÚNICO header + filtros (padrão da tela de Tarefas): chrome de card
		 no wrapper, PageHeader compacto `embedded` e a linha de filtros embutida
		 abaixo de um divisor fino. -->
	<div class="rounded-xl border border-border-subtle bg-surface shadow-sm">
	<PageHeader compact embedded class="min-h-[3.5rem]" subtitle={headerSubtitle} labelId="pendentes-title">
		{#snippet titleContent()}
			<span class="align-middle">Projetos pendentes</span>
			{#if summary}
				<CountBadge class="ml-2">Projetos no foco: {Math.max(0, summary.total_projects - focusDelta)}</CountBadge>
			{/if}
		{/snippet}
	</PageHeader>

	<!-- Linha de filtros embutida (re-buscam server-side). Ordem: Período · Busca
		 · Órgãos (só quando o usuário acessa mais de um) · Responsáveis · Prioridade.
		 Campos SEM rótulos — os placeholders identificam cada um (aria-label cobre a
		 acessibilidade), no MESMO estilo dos selects da tela de Tarefas/Projetos. -->
	<form
		class="flex flex-wrap items-center gap-2 border-t border-border-subtle px-4 py-2.5"
		role="search"
		aria-label="Filtros de projetos pendentes"
		onsubmit={onSearchSubmit}
	>
		<div class="relative min-w-[14rem] flex-1">
			<i
				class="fas fa-search pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-sm text-text-muted"
				aria-hidden="true"
			></i>
			<input
				id="pendentesSearch"
				name="search"
				type="search"
				autocomplete="off"
				bind:value={search}
				oninput={onSearchInput}
				aria-label="Busca livre"
				placeholder="Digite título, órgão ou indicador…"
				class="h-9 w-full rounded-lg border border-border-subtle bg-surface pl-8 pr-2.5 text-sm text-text-primary placeholder:text-text-muted transition-colors duration-fast focus:border-primary-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
			/>
		</div>

		<select
			id="periodoFilter"
			value={periodo}
			onchange={onPeriodoChange}
			disabled={periodOptions.length === 0}
			aria-label="Filtrar por período"
			class="h-9 min-w-[11rem] rounded-lg border border-border-subtle bg-surface px-2.5 text-sm text-text-primary focus:border-primary-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-60"
		>
			{#each periodOptions as option (option.value)}
				<option value={option.value}>{option.label}</option>
			{/each}
		</select>

		{#if data && data.orgaos_options.length > 1}
			<select
				id="orgaoFilter"
				value={orgao === null ? '' : String(orgao)}
				onchange={onOrgaoChange}
				aria-label="Filtrar por órgão"
				class="h-9 min-w-[10rem] rounded-lg border border-border-subtle bg-surface px-2.5 text-sm text-text-primary focus:border-primary-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
			>
				<option value="">Todos os órgãos</option>
				{#each data.orgaos_options as orgaoOption (orgaoOption.value)}
					<option value={orgaoOption.value}>{orgaoOption.label}</option>
				{/each}
			</select>
		{/if}

		<select
			id="responsavelFilter"
			value={responsavel}
			onchange={onResponsavelChange}
			disabled={!data || data.responsaveis_options.length === 0}
			aria-label="Filtrar por responsável"
			class="h-9 w-44 shrink-0 truncate rounded-lg border border-border-subtle bg-surface px-2.5 text-sm text-text-primary focus:border-primary-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-60"
		>
			<option value="">Todos os responsáveis</option>
			{#if data}
				{#each data.responsaveis_options as nome (nome)}
					<option value={nome}>{nome}</option>
				{/each}
			{/if}
		</select>

		<select
			id="prioridadeFilter"
			value={prioridade}
			onchange={onPrioridadeChange}
			aria-label="Filtrar por prioridade"
			class="h-9 min-w-[10rem] rounded-lg border border-border-subtle bg-surface px-2.5 text-sm text-text-primary focus:border-primary-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
		>
			<option value="">Todas as prioridades</option>
			{#each PRIORIDADE_OPTIONS as option (option.value)}
				<option value={option.value}>{option.label}</option>
			{/each}
		</select>

		{#if hasActiveFilters}
			<button
				type="button"
				onclick={clearFilters}
				title="Limpar filtros"
				aria-label="Limpar filtros"
				class="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-border-subtle bg-surface text-text-secondary transition-colors duration-fast hover:bg-surface-muted hover:text-primary-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
			>
				<i class="fas fa-filter-circle-xmark" aria-hidden="true"></i>
			</button>
		{/if}
	</form>
	</div>

	{#if loadState === 'loading'}
		<p role="status" aria-live="polite" class="text-text-secondary">Carregando projetos…</p>
	{:else if loadState === 'error'}
		<LoadErrorState message={errorMessage} onRetry={() => load()} />
	{:else if data}
		{#if data.projetos.length === 0}
			<div
				role="status"
				aria-live="polite"
				class="flex flex-col items-center gap-2 rounded-lg border border-dashed border-border-subtle bg-surface px-5 py-8 text-center"
			>
				<i class="fas fa-check-circle text-4xl text-primary-600" aria-hidden="true"></i>
				<h2 class="font-heading text-xl font-bold text-text-primary">
					Nenhum projeto pendente para os filtros selecionados.
				</h2>
				<p class="text-sm text-text-secondary">
					Ajuste os filtros para explorar outras frentes de acompanhamento.
				</p>
			</div>
		{:else}
			<div class="flex flex-col gap-4" aria-busy={loadState !== 'ready'}>
				{#each data.projetos as row (row.project.id)}
					<PendingProjectCard
						bind:this={cardRefs[row.project.id]}
						{row}
						bucketMap={data.etapa_bucket_map}
						progressMap={data.etapa_task_progress}
						{drawer}
						{expandedProjects}
						onToggleExpanded={setProjectExpanded}
						onOpenQuickAdd={openQuickAdd}
						{onProjectDefocused}
					/>
				{/each}
			</div>

			{#if pagination}
				<PaginationBar
					page={pagination.page}
					totalPages={pagination.total_pages}
					label="Paginação de projetos"
					disabled={loadState !== 'ready'}
					onChange={goToPage}
				/>
			{/if}
		{/if}
	{/if}
</section>

<!-- Quick-add de tarefas por etapa (drawer lateral). Reusa o TaskDrawer para editar. -->
{#if quickAdd}
	<StageTaskQuickAdd
		projectId={quickAdd.projectId}
		projectTitulo={quickAdd.projectTitulo}
		etapaId={quickAdd.etapaId}
		etapaDescricao={quickAdd.etapaDescricao}
		etapaDatas={quickAdd.etapaDatas}
		stageDone={quickAdd.stageDone}
		{drawer}
		onClose={closeQuickAdd}
		onProgressChange={syncEtapaProgress}
	/>
{/if}

<!-- Drawer de tarefa (reusado da lane fe:tarefas-drawer; não reescrito). -->
<TaskDrawer store={drawer} />
