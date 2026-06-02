<script lang="ts">
	/**
	 * Tela "Projetos Pendentes". Consome `GET /api/projetos-pendentes` via
	 * `$lib/api/pendentes` e renderiza a lista com os componentes compartilhados
	 * Card/Badge (reusados, não editados) e o card específico desta tela
	 * (`PendingProjectCard`). Filtros de período, responsável e órgão re-buscam
	 * server-side (o `orgao_scope` é aplicado no backend).
	 *
	 * PARIDADE DE MUTAÇÃO (templates/projects/pendentes.html): botão de status
	 * cíclico por etapa, quick-add de tarefas (modal por etapa reusando o
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
	import PendingProjectCard from '$lib/components/PendingProjectCard.svelte';
	import StageTaskQuickAdd from '$lib/components/StageTaskQuickAdd.svelte';
	import TaskDrawer from '$lib/components/TaskDrawer.svelte';
	import { createTaskDrawerStore } from '$lib/stores/taskDrawer';

	/** Chave de persistência do estado expandido (mesma semântica do legado). */
	const EXPANDED_STORAGE_KEY = 'pendingExpandedProjects';

	type LoadState = 'loading' | 'ready' | 'error';

	let loadState = $state<LoadState>('loading');
	let data = $state<PendingData | null>(null);
	let errorMessage = $state<string>('');

	// Filtros controlados pela UI; a busca acontece server-side.
	let periodo = $state<PendingPeriodo>('atrasados');
	let responsavel = $state<string>('');
	let orgao = $state<number | null>(null);
	let page = $state<number>(1);

	let inFlight: AbortController | null = null;

	async function load(): Promise<void> {
		loadState = data ? loadState : 'loading';
		errorMessage = '';
		inFlight?.abort();
		const controller = new AbortController();
		inFlight = controller;

		const filters: PendingFilters = { periodo, responsavel, orgao, page };
		try {
			const next = await fetchPendentes(filters, controller.signal);
			if (controller.signal.aborted) return;
			data = next;
			// Reset do decremento local: o backend já reflete o estado atual.
			focusDelta = 0;
			cardRefs = {};
			// Reconcilia os filtros com o que o backend efetivamente aplicou.
			periodo = next.filtro_periodo;
			responsavel = next.selected_responsavel;
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

	function onResponsavelChange(event: Event): void {
		responsavel = (event.currentTarget as HTMLSelectElement).value;
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
		periodo = 'atrasados';
		responsavel = '';
		orgao = null;
		page = 1;
		void load();
	}

	function goToPage(target: number): void {
		page = target;
		void load();
	}

	// ── Mutações (paridade com o Jinja) ──────────────────────────────────────

	/** Store do drawer reusada pelo quick-add (NÃO recriar dentro do modal). */
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

	function expandAll(): void {
		if (!data) return;
		const next = new Set(expandedProjects);
		for (const row of data.projetos) {
			if (row.qtd_outras > 0) next.add(String(row.project.id));
		}
		expandedProjects = next;
		saveExpandedSet(next);
	}

	function collapseAll(): void {
		expandedProjects = new Set();
		saveExpandedSet(expandedProjects);
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
		return () => inFlight?.abort();
	});

	const summary = $derived(data?.summary_counts ?? null);
	const pagination = $derived(data?.pagination ?? null);
	/** Opções de período rotuladas pelo backend (`period_options`). */
	const periodOptions = $derived(data?.period_options ?? []);
	/** Rótulo da janela ativa, servido pelo backend (`periodo_label`). */
	const periodoLabel = $derived(data?.periodo_label ?? '');
	const hasActiveFilters = $derived(
		periodo !== 'atrasados' || responsavel !== '' || orgao !== null
	);
	const selectedOrgaoLabel = $derived(
		orgao === null
			? ''
			: (data?.orgaos_options.find((o) => o.value === String(orgao))?.label ?? '')
	);
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
					Projetos no foco: {Math.max(0, summary.total_projects - focusDelta)}
				</span>
			{/if}
		</div>
		<p class="text-sm text-text-secondary">
			Janela ativa: <strong class="font-semibold text-text-primary">{periodoLabel}</strong>
			{#if responsavel}
				· Responsável: <strong class="font-semibold text-text-primary">{responsavel}</strong>
			{/if}
			{#if selectedOrgaoLabel}
				· Órgão: <strong class="font-semibold text-text-primary">{selectedOrgaoLabel}</strong>
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
				disabled={periodOptions.length === 0}
				class="rounded-md border border-border-subtle bg-surface px-3 py-2 text-sm text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-60"
			>
				{#each periodOptions as option (option.value)}
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

		<div class="flex min-w-[12rem] flex-col gap-1">
			<label
				for="orgaoFilter"
				class="text-xs font-semibold uppercase tracking-wide text-text-muted"
			>
				Órgão
			</label>
			<select
				id="orgaoFilter"
				value={orgao === null ? '' : String(orgao)}
				onchange={onOrgaoChange}
				disabled={!data || data.orgaos_options.length === 0}
				class="rounded-md border border-border-subtle bg-surface px-3 py-2 text-sm text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-60"
			>
				<option value="">Todos</option>
				{#if data}
					{#each data.orgaos_options as orgaoOption (orgaoOption.value)}
						<option value={orgaoOption.value}>{orgaoOption.label}</option>
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

		<!-- Ferramentas de expansão global (paridade com pendentes.html) -->
		<div class="ml-auto flex items-end gap-2">
			<button
				type="button"
				onclick={expandAll}
				class="inline-flex items-center gap-1.5 rounded-md border border-border-subtle bg-surface px-3 py-2 text-sm font-medium text-text-primary transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
			>
				<i class="fas fa-plus-square" aria-hidden="true"></i> Expandir todas
			</button>
			<button
				type="button"
				onclick={collapseAll}
				class="inline-flex items-center gap-1.5 rounded-md border border-border-subtle bg-surface px-3 py-2 text-sm font-medium text-text-primary transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
			>
				<i class="fas fa-minus-square" aria-hidden="true"></i> Recolher todas
			</button>
		</div>
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

<!-- Quick-add de tarefas por etapa (modal). Reusa o TaskDrawer para editar. -->
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
