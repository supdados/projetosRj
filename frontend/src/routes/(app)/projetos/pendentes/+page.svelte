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
	import { base } from '$app/paths';
	import { goto } from '$app/navigation';
	import { fetchPendentes, peekPendentes } from '$lib/api/pendentes';
	import { fetchProjects, type CreateProjectResult } from '$lib/api/projects';
	import { ApiClientError } from '$lib/api/client';
	import type {
		PendingData,
		PendingFilters,
		PendingPeriodo
	} from '$lib/types/pendentes';
	import type { ProjectsListOptions } from '$lib/types/projects';
	import PageHeader from '$lib/components/PageHeader.svelte';
	import Button from '$lib/components/Button.svelte';
	import CountBadge from '$lib/components/CountBadge.svelte';
	import PendingProjectCard from '$lib/components/PendingProjectCard.svelte';
	import PaginationBar from '$lib/components/PaginationBar.svelte';
	import OrgaoTreeSelect from '$lib/components/OrgaoTreeSelect.svelte';
	import type { OrgaoSelectOption } from '$lib/types/orgaoTreeSelect';
	import StageTaskQuickAdd from '$lib/components/StageTaskQuickAdd.svelte';
	import TaskDrawer from '$lib/components/TaskDrawer.svelte';
	import CriarProjetoModal from '$lib/components/CriarProjetoModal.svelte';
	import LoadErrorState from '$lib/components/LoadErrorState.svelte';
	import PendentesSkeleton from '$lib/components/skeletons/PendentesSkeleton.svelte';
	import SelectMenu from '$lib/components/SelectMenu.svelte';
	import type { SelectMenuOption } from '$lib/types/selectMenu';
	import { createTaskDrawerStore } from '$lib/stores/taskDrawer';
	import { flash } from '$lib/stores/flash';

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

	/**
	 * SWR: chave = os mesmos filtros default do estado inicial (nenhum vem de
	 * querystring de rota nesta tela). Com cache mostra os pendentes já e revalida
	 * em silêncio; sem cache, skeleton (ver `load()` abaixo).
	 */
	const initialFilters: PendingFilters = {
		periodo: 'atrasados',
		search: '',
		responsavel: '',
		prioridade: '',
		orgao: null,
		page: 1
	};
	const initialData = peekPendentes(initialFilters);
	let loadState = $state<LoadState>(initialData ? 'ready' : 'loading');
	let data = $state<PendingData | null>(initialData);
	let errorMessage = $state<string>('');

	/** Janela de debounce da busca textual (ms) — paridade com a tela de Projetos. */
	const DEBOUNCE_MS = 300;

	/** Opções de prioridade (lista canônica; o backend filtra por igualdade). */
	const PRIORIDADE_OPTIONS: SelectMenuOption[] = [
		{ value: 'baixa', label: 'Baixa', dot: 'var(--ds-color-priority-baixa)' },
		{ value: 'media', label: 'Média', dot: 'var(--ds-color-priority-media)' },
		{ value: 'alta', label: 'Alta', dot: 'var(--ds-color-priority-alta)' },
		{ value: 'urgente', label: 'Urgente', dot: 'var(--ds-color-priority-urgente)' }
	];

	// Filtros controlados pela UI; a busca acontece server-side.
	let periodo = $state<PendingPeriodo>('atrasados');
	let search = $state<string>('');
	let responsavel = $state<string>('');
	let prioridade = $state<string>('');
	let orgao = $state<number | null>(null);
	let page = $state<number>(1);

	// Criar projeto pelo header (mesmo botão/fluxo de Home e Projetos): as opções
	// do formulário vivem no payload de /api/projetos; busca sob demanda na 1ª
	// abertura e reaproveita. Sucesso fecha, avisa e vai ao projeto.
	let createModalOpen = $state(false);
	let createOptions = $state<ProjectsListOptions | null>(null);
	let openingCreate = $state(false);

	async function openCreateModal(): Promise<void> {
		if (openingCreate) return;
		if (!createOptions) {
			openingCreate = true;
			try {
				createOptions = (await fetchProjects({})).options;
			} catch (err) {
				flash.danger(
					err instanceof Error ? err.message : 'Falha ao preparar o formulário de novo projeto.'
				);
				return;
			} finally {
				openingCreate = false;
			}
		}
		createModalOpen = true;
	}

	function onProjectCreated(result: CreateProjectResult): void {
		createModalOpen = false;
		flash.success(result.message);
		const target = result.redirect_to.startsWith('/')
			? `${base}${result.redirect_to}`
			: result.redirect_to;
		void goto(target);
	}

	let inFlight: AbortController | null = null;
	let debounceTimer: ReturnType<typeof setTimeout> | null = null;

	async function load(): Promise<void> {
		const filters: PendingFilters = { periodo, search, responsavel, prioridade, orgao, page };
		// SWR: com cache dos filtros correntes mostra o dado antigo já (sem
		// skeleton) e a revalidação abaixo troca em silêncio; sem cache, skeleton.
		const cached = peekPendentes(filters);
		if (cached) {
			data = cached;
			loadState = 'ready';
		} else {
			data = null;
			loadState = 'loading';
		}
		errorMessage = '';
		inFlight?.abort();
		const controller = new AbortController();
		inFlight = controller;

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
			const message =
				err instanceof Error ? err.message : 'Falha ao carregar os projetos pendentes.';
			// Revalidação falhou com dado stale na tela: mantém o dado e avisa via
			// flash, em vez de trocar a lista inteira pelo painel de erro.
			if (data) {
				flash.danger(message);
				return;
			}
			errorMessage = message;
			loadState = 'error';
		}
	}

	function onPeriodoSelect(value: string | null): void {
		periodo = (value ?? 'atrasados') as PendingPeriodo;
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

	function onResponsavelSelect(value: string | null): void {
		responsavel = value ?? '';
		page = 1;
		void load();
	}

	function onPrioridadeSelect(value: string | null): void {
		prioridade = value ?? '';
		page = 1;
		void load();
	}

	/** Seleção no OrgaoTreeSelect (null = "Todos os órgãos"): mesmo fluxo do onchange. */
	function onOrgaoSelect(selecionado: number | null): void {
		orgao = selecionado;
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
	const periodoMenuOptions = $derived<SelectMenuOption[]>(
		periodOptions.map((option) => ({ value: option.value, label: option.label }))
	);
	const responsavelMenuOptions = $derived<SelectMenuOption[]>(
		(data?.responsaveis_options ?? []).map((nome) => ({ value: nome, label: nome }))
	);
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
	// Opções achatadas p/ o OrgaoTreeSelect (a árvore é montada por `pai_id`).
	const orgaoTreeOptions = $derived(
		(data?.orgaos_options ?? []).map(
			(o): OrgaoSelectOption => ({
				value: Number(o.value),
				label: o.label,
				sigla: o.sigla,
				nome: o.nome,
				pai_id: o.pai_id,
				is_inactive: o.is_inactive
			})
		)
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

<section aria-labelledby="pendentes-title" class="flex flex-col gap-4">
	<!-- CARD ÚNICO header + filtros (padrão da tela de Tarefas): chrome de card
		 no wrapper, PageHeader compacto `embedded` e a linha de filtros embutida
		 abaixo de um divisor fino. -->
	<div class="rounded-xl border border-border-subtle bg-surface shadow-sm">
	<PageHeader compact embedded class="min-h-[3.5rem]" subtitle={headerSubtitle} labelId="pendentes-title">
		{#snippet titleContent()}
			<span>Projetos pendentes</span>
			{#if summary}
				<CountBadge class="ml-2">Projetos no foco: {Math.max(0, summary.total_projects - focusDelta)}</CountBadge>
			{/if}
		{/snippet}
		{#snippet actions()}
			<!-- Mesmo botão "Novo Projeto" de Home e Projetos (Button size="sm"). -->
			<Button size="sm" onclick={openCreateModal} disabled={openingCreate}>
				{#snippet icon()}
					<i class="fas fa-plus" aria-hidden="true"></i>
				{/snippet}
				Novo Projeto
			</Button>
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
		<!-- Largura FIXA e idêntica nas 3 telas (Projetos/Pendentes/Tarefas):
			 flex-1 fazia a busca variar conforme os filtros vizinhos de cada tela. -->
		<div class="relative w-full min-w-[14rem] max-w-[26rem]">
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

		<div class="min-w-[10rem] flex-1">
			<SelectMenu
				id="periodoFilter"
				options={periodoMenuOptions}
				value={periodo}
				onSelect={onPeriodoSelect}
				disabled={periodOptions.length === 0}
				ariaLabel="Filtrar por período"
			/>
		</div>

		{#if data && data.orgaos_options.length > 1}
			<div class="min-w-[10rem] flex-1">
				<OrgaoTreeSelect
					id="orgaoFilter"
					options={orgaoTreeOptions}
					value={orgao}
					onSelect={onOrgaoSelect}
					allowTodos
					ariaLabel="Filtrar por órgão"
					placeholder="Todos os órgãos"
				/>
			</div>
		{/if}

		<div class="min-w-[10rem] flex-1">
			<SelectMenu
				id="responsavelFilter"
				options={responsavelMenuOptions}
				value={responsavel || null}
				onSelect={onResponsavelSelect}
				disabled={!data || data.responsaveis_options.length === 0}
				allowAll
				allLabel="Todos os responsáveis"
				ariaLabel="Filtrar por responsável"
			/>
		</div>

		<div class="min-w-[10rem] flex-1">
			<SelectMenu
				id="prioridadeFilter"
				options={PRIORIDADE_OPTIONS}
				value={prioridade || null}
				onSelect={onPrioridadeSelect}
				allowAll
				allLabel="Todas as prioridades"
				ariaLabel="Filtrar por prioridade"
			/>
		</div>

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
		<p role="status" aria-live="polite" class="sr-only">Carregando projetos pendentes…</p>
		<PendentesSkeleton />
	{:else if loadState === 'error'}
		<LoadErrorState message={errorMessage} onRetry={() => load()} />
	{:else if data}
		{#if data.projetos.length === 0}
			<!-- Estado vazio no MESMO padrão da lista de Projetos: quadro suave com
				 ícone emoldurado (primary-100), título heading e texto muted. -->
			<div
				role="status"
				aria-live="polite"
				class="rounded-lg border border-dashed border-border-strong bg-surface-muted/40 px-4 py-8 text-center"
			>
				<div
					class="mx-auto mb-3 inline-flex h-14 w-14 items-center justify-center rounded-xl border border-primary-500/25 bg-primary-100 text-xl text-primary-700"
				>
					<i class="fas fa-check-circle" aria-hidden="true"></i>
				</div>
				<h2 class="m-0 font-heading text-xl font-bold text-text-primary">
					Nenhum projeto pendente para os filtros selecionados.
				</h2>
				<p class="mb-0 mt-1.5 text-sm text-text-muted">
					Ajuste os filtros para explorar outras frentes de acompanhamento.
				</p>
			</div>
		{:else}
			<!-- Lista + pager num wrapper gap-4 → distância padrão (16px) até o pager. -->
			<div class="flex flex-col gap-4">
				<div class="flex flex-col gap-4" aria-busy={loadState !== 'ready'}>
					{#each data.projetos as row (row.project.id)}
						<PendingProjectCard
							bind:this={cardRefs[row.project.id]}
							{row}
							bucketMap={data.etapa_bucket_map}
							positionMap={data.etapa_position_map}
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
						total={pagination.total}
						perPage={pagination.per_page}
						itemLabel="projetos"
						label="Paginação de projetos"
						disabled={loadState !== 'ready'}
						onChange={goToPage}
					/>
				{/if}
			</div>
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

<!-- Modal de criação de projeto (mesmo fluxo de Home/Projetos). -->
<CriarProjetoModal
	open={createModalOpen}
	options={createOptions}
	onClose={() => (createModalOpen = false)}
	onCreated={onProjectCreated}
/>
