<script lang="ts">
	/**
	 * Tela "Hub de Tarefas" em MODO LISTA (sem Kanban). Consome
	 * `GET /api/tarefas` via `$lib/api/tasks` e renderiza as tarefas agrupadas
	 * por projeto, reusando os componentes compartilhados Card/Badge (apenas
	 * lidos/reusados, nunca editados). Dentro de cada grupo as tarefas são
	 * sub-agrupadas por etapa a partir de `etapa_titulo`/`is_first_of_stage`,
	 * já calculados no backend.
	 *
	 * Os filtros de projeto e órgão re-buscam server-side (o `orgao_scope` é
	 * aplicado no backend); a alternância de status (ativas/arquivadas/
	 * finalizadas) traduz para o `?modo=` do endpoint. Estados de loading/erro/
	 * vazio são anunciados via aria-live.
	 *
	 * Referência visual: templates/tasks/hub.html.
	 */
	import { onMount, setContext } from 'svelte';
	import { get as readStore } from 'svelte/store';
	import { fetchTarefas, deleteTarefa, archiveFinalizadas } from '$lib/api/tasks';
	import { ApiClientError } from '$lib/api/client';
	import type { TaskCard, TaskHubData, TaskHubModo, TaskHubQuery } from '$lib/types/tasks';
	import Card from '$lib/components/Card.svelte';
	import Badge from '$lib/components/Badge.svelte';
	import KanbanBoard from '$lib/components/KanbanBoard.svelte';
	import KanbanComposer from '$lib/components/KanbanComposer.svelte';
	import TaskDrawer from '$lib/components/TaskDrawer.svelte';
	import LoadErrorState from '$lib/components/LoadErrorState.svelte';
	import { createBoardStore } from '$lib/stores/board';
	import { createTaskDrawerStore } from '$lib/stores/taskDrawer';
	import { orgaoScope } from '$lib/stores/orgaoScope';
	import type { BoardCard, BoardQuery } from '$lib/types/board';
	import { normalizeStatus, type TaskStatus } from '$lib/utils/taskStatus';
	import {
		triggerTaskFinalizeConfetti,
		type CelebrationOriginLike
	} from '$lib/celebration/confettiEpic';
	import '$lib/celebration/confetti.css';

	type LoadState = 'loading' | 'ready' | 'error';
	type BadgeTone = 'neutral' | 'primary' | 'success' | 'warning' | 'danger' | 'info';

	/** Visualização da tela: lista (default) ou kanban. */
	type ViewMode = 'list' | 'kanban';

	/** Modos da topnav (espelham `?modo=` do endpoint). */
	const MODO_OPTIONS: { value: TaskHubModo; label: string }[] = [
		{ value: 'ativas', label: 'Ativas' },
		{ value: 'finalizadas', label: 'Finalizadas' },
		{ value: 'arquivadas', label: 'Arquivadas' }
	];

	/** Rótulos PT dos status (espelham `status_labels` do hub Jinja). */
	const STATUS_LABEL: Record<string, string> = {
		nao_iniciada: 'Não iniciada',
		em_andamento: 'Em andamento',
		para_validacao: 'Para validação',
		para_ajustes: 'Para ajustes',
		finalizada: 'Finalizada'
	};

	/** Tom semântico do Badge por status. */
	const STATUS_TONE: Record<string, BadgeTone> = {
		nao_iniciada: 'neutral',
		em_andamento: 'info',
		para_validacao: 'primary',
		para_ajustes: 'warning',
		finalizada: 'success'
	};

	/** Rótulos PT das prioridades (espelham `prioridade_labels` do hub Jinja). */
	const PRIORIDADE_LABEL: Record<string, string> = {
		baixa: 'Baixa',
		media: 'Média',
		alta: 'Alta',
		urgente: 'Urgente'
	};

	/** Tom semântico do Badge por prioridade. */
	const PRIORIDADE_TONE: Record<string, BadgeTone> = {
		baixa: 'neutral',
		media: 'info',
		alta: 'warning',
		urgente: 'danger'
	};

	/** Rótulos PT dos tipos de pedido (espelham `tipo_labels` do hub Jinja). */
	const TIPO_LABEL: Record<string, string> = {
		bug: 'Bug',
		melhoria: 'Melhoria',
		duvida: 'Dúvida',
		outros: 'Outros',
		implementacao: 'Implementação'
	};

	function statusLabel(value: string): string {
		return STATUS_LABEL[value] ?? value;
	}
	function statusTone(value: string): BadgeTone {
		return STATUS_TONE[value] ?? 'neutral';
	}
	function prioridadeLabel(value: string | null): string | null {
		if (!value) return null;
		return PRIORIDADE_LABEL[value] ?? value;
	}
	function prioridadeTone(value: string | null): BadgeTone {
		if (!value) return 'neutral';
		return PRIORIDADE_TONE[value] ?? 'neutral';
	}
	function tipoLabel(value: string | null): string | null {
		if (!value) return null;
		return TIPO_LABEL[value] ?? value;
	}

	let loadState = $state<LoadState>('loading');
	let data = $state<TaskHubData | null>(null);
	let errorMessage = $state<string>('');

	// Filtros controlados pela UI; a busca acontece server-side.
	let modo = $state<TaskHubModo>('ativas');
	let project = $state<string>('');
	let orgao = $state<string>('');

	let inFlight: AbortController | null = null;

	// Visualização (lista default <-> kanban). O board tem sua própria store
	// canônica; o modo lista mantém seu fluxo atual intocado.
	let view = $state<ViewMode>('list');
	const board = createBoardStore();
	let boardInFlight: AbortController | null = null;
	let boardLoaded = $state<boolean>(false);

	/**
	 * CONFETE ao concluir tarefa — paridade com `taskFinalizeCelebration.trigger`
	 * disparado por `updateItemStatus` no legado quando uma tarefa transita para
	 * "finalizada". Reusa o motor de confete portado (`triggerTaskFinalizeConfetti`),
	 * originando a celebração no card/ponteiro do drop (ou no botão do drawer).
	 * Respeita `prefers-reduced-motion` (no-op dentro da lib).
	 */
	function celebrateFinalize(origin?: CelebrationOriginLike): void {
		triggerTaskFinalizeConfetti(origin);
	}
	// KanbanBoard dispara a celebração via contexto ao mover um card p/ Finalizada.
	setContext('celebrateFinalize', celebrateFinalize);

	// Rastreia o status conhecido de cada card aberto no drawer, para detectar a
	// transição -> "finalizada" feita pelo seletor/botão do drawer e celebrar
	// (o drawer reconcilia o board removendo o card; aqui só observamos a mudança).
	const lastKnownStatus = new Map<number, TaskStatus>();

	// Drawer de tarefa (Fase 5b-2): reconcilia mutações no card do board sem
	// duplicar estado (upsert/remove na board store). Em modo lista, a lista é
	// re-buscada ao fechar o drawer (abaixo).
	const drawer = createTaskDrawerStore({
		onCardChanged: (card) => {
			const prev = lastKnownStatus.get(card.id);
			const next = normalizeStatus(card.status);
			if (next === 'finalizada' && prev && prev !== 'finalizada') {
				celebrateFinalize();
			}
			lastKnownStatus.set(card.id, next);
			board.upsertCard(card);
		},
		onCardRemoved: (id) => {
			// Finalizar/arquivar via drawer remove o card do board. Só celebra a
			// TRANSIÇÃO de um status ATIVO conhecido -> "finalizada" (paridade com
			// shouldCelebrateFinalize). Abrir um card JÁ finalizado dispara este
			// reconciler sem `prev` ativo registrado -> não celebra (evita confete
			// ao só visualizar uma tarefa concluída). Arquivar também não celebra.
			const prev = lastKnownStatus.get(id);
			const detail = readStore(drawer).detail;
			const becameFinalized = !!(
				detail &&
				detail.id === id &&
				!detail.is_archived &&
				normalizeStatus(detail.status) === 'finalizada'
			);
			if (becameFinalized && prev && prev !== 'finalizada') {
				celebrateFinalize();
			}
			lastKnownStatus.delete(id);
			board.removeCard(id);
		}
	});

	function openTask(taskId: number, mode: 'board' | 'list' | 'etapa'): void {
		void drawer.open(taskId, { mode });
	}

	// KanbanCard abre o drawer via contexto (evita prop drilling por Board/Column).
	setContext('openTaskDrawer', (id: number) => openTask(id, 'board'));

	// EXCLUIR card no Kanban (mini-confirm inline no card): a página executa a
	// chamada e remove o card da board store; fecha o drawer se aberto nesse item
	// (paridade com `deleteKanbanItem` -> removeTaskItemFromDom + fechar drawer).
	async function deleteCard(taskId: number): Promise<boolean> {
		try {
			await deleteTarefa(taskId);
		} catch (err) {
			if (err instanceof ApiClientError && err.code === 'unauthenticated') return false;
			return false;
		}
		board.removeCard(taskId);
		if ($drawer.taskId === taskId) void drawer.close();
		// Em modo lista, re-busca para refletir a remoção e recolher grupos vazios.
		if (view === 'list') void load();
		return true;
	}
	setContext('deleteTaskCard', deleteCard);

	// "Abrir um confirm fecha os demais" (paridade board-dnd.js): cada card que
	// abre o seu confirm registra um fechador; ao registrar um novo, fechamos o
	// anterior. Sem estado global — só o último confirm aberto fica visível.
	let closeOpenDeleteConfirm: (() => void) | null = null;
	setContext('registerDeleteConfirm', (close: () => void) => {
		closeOpenDeleteConfirm?.();
		closeOpenDeleteConfirm = close;
	});

	// "Abrir um composer fecha os demais" (paridade composer.js): só UM composer
	// fica aberto por vez. Controlado pela página (estado canônico único).
	let activeComposer = $state<TaskStatus | null>(null);

	// Inserção otimista do composer na coluna do status (board store).
	function onComposerCreated(card: BoardCard, status: TaskStatus): void {
		board.addCard(card, status);
		activeComposer = null;
	}

	// Ao FECHAR o drawer (depois de aberto), recarrega a LISTA para refletir
	// mutações; o board já reconcilia ao vivo via upsert/removeCard.
	let drawerWasOpen = false;
	$effect(() => {
		const open = $drawer.status !== 'closed';
		if (drawerWasOpen && !open && view === 'list') void load();
		drawerWasOpen = open;
	});

	/**
	 * Carrega o board aplicando os MESMOS filtros de projeto/órgão do modo lista
	 * (o board mostra só tarefas ativas; `modo` é específico da lista). Reusa o
	 * `orgao_scope` do backend via `BoardQuery.orgao`.
	 */
	async function loadBoard(): Promise<void> {
		boardInFlight?.abort();
		const controller = new AbortController();
		boardInFlight = controller;
		// Propaga o ESCOPO DE ÓRGÃO global (topnav) nas chamadas de board desta
		// tela — paridade com `?orgao=` do legado (orgaoScopeQuery). O escopo global
		// tem precedência; sem ele cai no filtro local de órgão da própria tela.
		const scopeId = readStore(orgaoScope).selectedId;
		const query: BoardQuery = {
			project: project || undefined,
			orgao: scopeId !== null ? String(scopeId) : orgao || undefined
		};
		await board.load(query, controller.signal);
		if (!controller.signal.aborted) boardLoaded = true;
	}

	function selectView(next: ViewMode): void {
		if (view === next) return;
		view = next;
		if (next === 'kanban') void loadBoard();
	}

	async function load(): Promise<void> {
		loadState = data ? loadState : 'loading';
		errorMessage = '';
		inFlight?.abort();
		const controller = new AbortController();
		inFlight = controller;

		const query: TaskHubQuery = { modo, project, orgao };
		try {
			const next = await fetchTarefas(query, controller.signal);
			if (controller.signal.aborted) return;
			data = next;
			// Reconcilia os filtros com o que o backend efetivamente aplicou.
			project = next.filters.project ?? '';
			orgao =
				next.filters.selected_orgao === null || next.filters.selected_orgao === undefined
					? ''
					: String(next.filters.selected_orgao);
			loadState = 'ready';
		} catch (err) {
			if (controller.signal.aborted) return;
			// 401 já redirecionou; aqui tratamos os demais erros.
			if (err instanceof ApiClientError && err.code === 'unauthenticated') return;
			errorMessage =
				err instanceof Error ? err.message : 'Falha ao carregar as tarefas.';
			loadState = 'error';
		}
	}

	// ARQUIVAR FINALIZADAS em lote (modo lista). Confirmação via modal SPA com o
	// MESMO texto do legado; sucesso remove as rows pelos ids e re-busca; sem ids
	// mostra o aviso 'Nenhuma tarefa…'. SEM toast/som/confete (paridade).
	let confirmingArchive = $state(false);
	let archiving = $state(false);
	let archiveNotice = $state<string | null>(null);

	function openArchiveConfirm(): void {
		archiveNotice = null;
		confirmingArchive = true;
	}
	function cancelArchiveConfirm(): void {
		confirmingArchive = false;
	}
	async function confirmArchive(): Promise<void> {
		archiving = true;
		archiveNotice = null;
		try {
			const result = await archiveFinalizadas({
				project: project || undefined,
				orgao: orgao || undefined
			});
			confirmingArchive = false;
			if (result.archived_count === 0) {
				// Paridade: aviso quando não há nada a arquivar no escopo.
				archiveNotice = result.message;
			} else {
				// Remove os cards do board (se carregado) e re-busca a lista.
				for (const id of result.archived_task_ids) board.removeCard(Number(id));
				void load();
			}
		} catch (err) {
			archiveNotice =
				err instanceof ApiClientError ? err.message : 'Erro ao arquivar tarefas.';
			confirmingArchive = false;
		} finally {
			archiving = false;
		}
	}

	// EXCLUIR row na LISTA (mini-confirm inline, paridade com o kanban). Um confirm
	// aberto por vez; em sucesso re-busca (recolhe grupos vazios via `load`).
	let confirmDeleteRowId = $state<number | null>(null);
	let deletingRowId = $state<number | null>(null);
	let rowDeleteError = $state<string | null>(null);

	function openRowDeleteConfirm(taskId: number): void {
		rowDeleteError = null;
		confirmDeleteRowId = taskId;
	}
	function cancelRowDeleteConfirm(): void {
		confirmDeleteRowId = null;
	}
	async function confirmRowDelete(taskId: number): Promise<void> {
		deletingRowId = taskId;
		rowDeleteError = null;
		const ok = await deleteCard(taskId);
		deletingRowId = null;
		if (ok) {
			confirmDeleteRowId = null;
		} else {
			rowDeleteError = 'Não foi possível excluir a tarefa.';
		}
	}

	function selectModo(next: TaskHubModo): void {
		if (modo === next) return;
		modo = next;
		void load();
	}

	/** Re-busca a visualização ativa após mudança de filtro (lista e/ou board). */
	function reloadActiveView(): void {
		void load();
		if (view === 'kanban') void loadBoard();
	}

	function onProjectChange(event: Event): void {
		project = (event.currentTarget as HTMLSelectElement).value;
		reloadActiveView();
	}

	function onOrgaoChange(event: Event): void {
		orgao = (event.currentTarget as HTMLSelectElement).value;
		reloadActiveView();
	}

	function clearFilters(): void {
		project = '';
		orgao = '';
		reloadActiveView();
	}

	onMount(() => {
		void load();
		return () => {
			inFlight?.abort();
			boardInFlight?.abort();
		};
	});

	// Re-busca o board quando o ESCOPO DE ÓRGÃO global muda (topnav), enquanto a
	// visão kanban está ativa — o escopo é propagado em `loadBoard`.
	let lastScopeId: number | null | undefined;
	let scopeInitialized = false;
	$effect(() => {
		const scopeId = $orgaoScope.selectedId;
		if (!scopeInitialized) {
			scopeInitialized = true;
			lastScopeId = scopeId;
			return;
		}
		if (scopeId === lastScopeId) return;
		lastScopeId = scopeId;
		if (view === 'kanban') void loadBoard();
	});

	/**
	 * Opções de órgão para o filtro local: siglas distintas presentes nas
	 * opções de projeto devolvidas pelo backend (que já respeitam o escopo).
	 */
	const orgaoOptions = $derived.by(() => {
		if (!data) return [] as string[];
		const seen = new Set<string>();
		for (const option of data.project_options) {
			const sigla = option.orgao_sigla?.trim();
			if (sigla) seen.add(sigla);
		}
		return Array.from(seen).sort((a, b) => a.localeCompare(b, 'pt-BR'));
	});

	const hasActiveFilters = $derived(project !== '' || orgao !== '');
	const totalItems = $derived(
		view === 'kanban' ? $board.total : (data?.total_items ?? 0)
	);

	/**
	 * Divide as tarefas de um grupo em subgrupos por etapa, respeitando o
	 * `is_first_of_stage` calculado no backend (cada `true` abre um bloco).
	 */
	function stagesOf(tasks: TaskCard[]): { titulo: string | null; tasks: TaskCard[] }[] {
		const blocks: { titulo: string | null; tasks: TaskCard[] }[] = [];
		for (const task of tasks) {
			if (task.is_first_of_stage || blocks.length === 0) {
				blocks.push({ titulo: task.etapa_titulo, tasks: [task] });
			} else {
				blocks[blocks.length - 1].tasks.push(task);
			}
		}
		return blocks;
	}
</script>

<svelte:head>
	<title>Tarefas — ProjetosRJ</title>
</svelte:head>

<section aria-labelledby="tarefas-title" class="flex flex-col gap-6">
	<header class="flex flex-col gap-2">
		<div class="flex flex-wrap items-center gap-3">
			<h1 id="tarefas-title" class="font-heading text-2xl font-bold text-text-primary">
				Tarefas
			</h1>
			<span
				class="inline-flex items-center gap-1 rounded-sm border border-primary-500 bg-primary-100 px-2 py-1 text-xs font-medium text-primary-700"
			>
				{totalItems} tarefa{totalItems === 1 ? '' : 's'}
			</span>
		</div>
		<p class="text-sm text-text-secondary">
			{view === 'kanban'
				? 'Tarefas ativas por status. Arraste os cards entre colunas para mudar o status.'
				: 'Tarefas agrupadas por projeto.'}
		</p>
	</header>

	<div class="flex flex-wrap items-center gap-3">
		<!-- Alternância de status (ativas/finalizadas/arquivadas) — só no modo lista -->
		{#if view === 'list'}
			<div
				role="group"
				aria-label="Visão das tarefas"
				class="inline-flex w-fit rounded-md border border-border-subtle bg-surface p-1"
			>
				{#each MODO_OPTIONS as option (option.value)}
					<button
						type="button"
						aria-pressed={modo === option.value}
						onclick={() => selectModo(option.value)}
						class="rounded-sm px-4 py-1.5 text-sm font-medium transition-colors duration-fast focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 {modo ===
						option.value
							? 'bg-primary-100 text-primary-700'
							: 'text-text-secondary hover:bg-surface-muted'}"
					>
						{option.label}
					</button>
				{/each}
			</div>

			<!-- Arquivar finalizados em lote (escopo dos filtros ativos) -->
			<button
				type="button"
				onclick={openArchiveConfirm}
				disabled={archiving || loadState !== 'ready'}
				class="inline-flex items-center gap-1.5 rounded-md border border-border-subtle bg-surface px-3 py-1.5 text-sm font-medium text-text-primary transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-50"
				title="Arquivar tarefas finalizadas do escopo atual"
			>
				Arquivar finalizados
			</button>
		{/if}

		<!-- Alternância de visualização (Lista <-> Kanban); Lista é o default -->
		<div
			role="group"
			aria-label="Modo de visualização"
			class="ml-auto inline-flex w-fit rounded-md border border-border-subtle bg-surface p-1"
		>
			<button
				type="button"
				data-view="list"
				aria-pressed={view === 'list'}
				onclick={() => selectView('list')}
				class="rounded-sm px-4 py-1.5 text-sm font-medium transition-colors duration-fast focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 {view ===
				'list'
					? 'bg-primary-100 text-primary-700'
					: 'text-text-secondary hover:bg-surface-muted'}"
			>
				Lista
			</button>
			<button
				type="button"
				data-view="kanban"
				aria-pressed={view === 'kanban'}
				onclick={() => selectView('kanban')}
				class="rounded-sm px-4 py-1.5 text-sm font-medium transition-colors duration-fast focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 {view ===
				'kanban'
					? 'bg-primary-100 text-primary-700'
					: 'text-text-secondary hover:bg-surface-muted'}"
			>
				Kanban
			</button>
		</div>
	</div>

	<!-- Filtros (re-buscam server-side) -->
	<form
		class="flex flex-wrap items-end gap-4 rounded-lg border border-border-subtle bg-surface px-5 py-4 shadow-sm"
		aria-label="Filtros de tarefas"
		onsubmit={(e) => e.preventDefault()}
	>
		<div class="flex min-w-[14rem] flex-col gap-1">
			<label for="projectFilter" class="text-xs font-semibold uppercase tracking-wide text-text-muted">
				Projeto
			</label>
			<select
				id="projectFilter"
				value={project}
				onchange={onProjectChange}
				disabled={!data || data.project_options.length === 0}
				class="rounded-md border border-border-subtle bg-surface px-3 py-2 text-sm text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-60"
			>
				<option value="">Todos os projetos</option>
				{#if data}
					{#each data.project_options as option (option.value)}
						<option value={option.value}>{option.label}</option>
					{/each}
				{/if}
			</select>
		</div>

		<div class="flex min-w-[12rem] flex-col gap-1">
			<label for="orgaoFilter" class="text-xs font-semibold uppercase tracking-wide text-text-muted">
				Órgão
			</label>
			<select
				id="orgaoFilter"
				value={orgao}
				onchange={onOrgaoChange}
				disabled={orgaoOptions.length === 0}
				class="rounded-md border border-border-subtle bg-surface px-3 py-2 text-sm text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-60"
			>
				<option value="">Todos os órgãos</option>
				{#each orgaoOptions as sigla (sigla)}
					<option value={sigla}>{sigla}</option>
				{/each}
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

	{#if archiveNotice}
		<!-- Aviso pós-arquivamento (paridade com o alert legado: sem ids / erro) -->
		<div
			role="status"
			aria-live="polite"
			class="rounded-md border border-border-subtle bg-surface px-4 py-2 text-sm text-text-secondary"
		>
			{archiveNotice}
		</div>
	{/if}

	{#if view === 'kanban'}
		{#if $board.status === 'loading' && !boardLoaded}
			<p role="status" aria-live="polite" class="text-text-secondary">Carregando board…</p>
		{:else if $board.status === 'error' && !boardLoaded}
			<LoadErrorState message={$board.error ?? ''} onRetry={() => loadBoard()} />
		{:else}
			<div aria-busy={$board.status === 'loading'}>
				<KanbanBoard store={board}>
					{#snippet composer(status: TaskStatus)}
						<KanbanComposer
							{status}
							projectOptions={data?.project_options ?? []}
							defaultProject={project}
							open={activeComposer === status}
							onCreated={onComposerCreated}
							onRequestOpen={(s) => (activeComposer = s)}
							onRequestClose={() => (activeComposer = null)}
						/>
					{/snippet}
				</KanbanBoard>
			</div>
		{/if}
	{:else if loadState === 'loading'}
		<p role="status" aria-live="polite" class="text-text-secondary">Carregando tarefas…</p>
	{:else if loadState === 'error'}
		<LoadErrorState message={errorMessage} onRetry={() => load()} />
	{:else if data}
		{#if data.groups.length === 0}
			<div
				role="status"
				aria-live="polite"
				class="rounded-lg border border-border-subtle bg-surface px-5 py-8 text-center text-text-muted"
			>
				Nenhuma tarefa para os filtros selecionados.
			</div>
		{:else}
			<div class="flex flex-col gap-5" aria-busy={loadState !== 'ready'}>
				{#each data.groups as group (group.key)}
					{@const labelId = `group-${group.key}`}
					<Card {labelId}>
						{#snippet header()}
							<div class="flex flex-wrap items-baseline gap-2">
								<h2 id={labelId} class="font-heading text-lg font-semibold text-text-primary">
									{group.project_titulo}
								</h2>
								<span class="text-xs font-medium text-text-secondary">
									{group.project_orgao_sigla || 'Não informado'}
								</span>
								<span class="text-xs text-text-muted">
									· {group.tasks.length} tarefa{group.tasks.length === 1 ? '' : 's'}
								</span>
							</div>
						{/snippet}

						<div class="flex flex-col gap-5">
							{#each stagesOf(group.tasks) as stage (stage.titulo ?? '__sem_etapa__')}
								<div class="flex flex-col gap-2">
									<h3 class="text-xs font-semibold uppercase tracking-wide text-text-muted">
										{stage.titulo ?? 'Sem etapa'}
									</h3>
									<ul class="flex flex-col gap-2">
										{#each stage.tasks as task (task.id)}
											<li class="flex flex-col gap-2 rounded-md border border-border-subtle bg-surface px-4 py-3">
												<div class="flex items-start justify-between gap-2">
													<button
														type="button"
														onclick={() => openTask(task.id, 'list')}
														class="flex-1 text-left text-sm text-text-primary hover:text-primary-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
													>
														{task.descricao}
													</button>
													{#if confirmDeleteRowId !== task.id}
														<button
															type="button"
															onclick={() => openRowDeleteConfirm(task.id)}
															aria-label="Excluir tarefa"
															title="Excluir tarefa"
															class="shrink-0 text-xs font-medium text-danger hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-danger"
														>
															Excluir
														</button>
													{/if}
												</div>
												<div class="flex flex-wrap items-center gap-2">
													<Badge tone={statusTone(task.status)}>
														{statusLabel(task.status)}
													</Badge>
													{#if prioridadeLabel(task.prioridade)}
														<Badge tone={prioridadeTone(task.prioridade)}>
															{prioridadeLabel(task.prioridade)}
														</Badge>
													{/if}
													{#if tipoLabel(task.tipo_pedido)}
														<span class="text-xs text-text-secondary">
															{tipoLabel(task.tipo_pedido)}
														</span>
													{/if}
													{#if task.responsavel}
														<span class="text-xs text-text-muted">
															· {task.responsavel}
														</span>
													{/if}
												</div>
												{#if confirmDeleteRowId === task.id}
													<!-- Mini-confirm inline (paridade com o kanban) -->
													<div
														role="alertdialog"
														aria-label="Confirmar exclusão da tarefa"
														class="flex flex-col gap-2 rounded-md border border-danger bg-surface px-3 py-2"
													>
														<p class="text-xs text-text-primary">Excluir esta tarefa?</p>
														{#if rowDeleteError}
															<p role="alert" class="text-xs text-danger">{rowDeleteError}</p>
														{/if}
														<div class="flex gap-2">
															<button
																type="button"
																onclick={cancelRowDeleteConfirm}
																disabled={deletingRowId === task.id}
																class="rounded-md border border-border-subtle px-2 py-1 text-xs font-medium text-text-secondary hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-50"
															>
																Cancelar
															</button>
															<button
																type="button"
																onclick={() => void confirmRowDelete(task.id)}
																disabled={deletingRowId === task.id}
																class="rounded-md bg-danger px-2 py-1 text-xs font-medium text-white hover:opacity-90 focus:outline-none focus-visible:ring-2 focus-visible:ring-danger disabled:opacity-50"
															>
																{deletingRowId === task.id ? 'Excluindo…' : 'Excluir'}
															</button>
														</div>
													</div>
												{/if}
											</li>
										{/each}
									</ul>
								</div>
							{/each}
						</div>
					</Card>
				{/each}
			</div>
		{/if}
	{/if}
</section>

{#if confirmingArchive}
	<!-- Confirmação de arquivamento (modal SPA com o MESMO texto do legado) -->
	<div class="fixed inset-0 z-modal bg-black/40" role="presentation" onclick={cancelArchiveConfirm}></div>
	<div
		role="alertdialog"
		aria-modal="true"
		aria-labelledby="archive-confirm-title"
		class="fixed left-1/2 top-1/2 z-modal flex w-full max-w-md -translate-x-1/2 -translate-y-1/2 flex-col gap-4 rounded-lg border border-border-subtle bg-surface p-5 shadow-lg"
	>
		<h2 id="archive-confirm-title" class="font-heading text-lg font-bold text-text-primary">
			Arquivar finalizados
		</h2>
		<p class="text-sm text-text-secondary">Arquivar tarefas finalizadas do escopo atual?</p>
		<div class="flex justify-end gap-2">
			<button
				type="button"
				onclick={cancelArchiveConfirm}
				disabled={archiving}
				class="rounded-md border border-border-subtle px-4 py-2 text-sm font-medium text-text-secondary hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-50"
			>
				Cancelar
			</button>
			<button
				type="button"
				onclick={() => void confirmArchive()}
				disabled={archiving}
				class="rounded-md bg-primary-500 px-4 py-2 text-sm font-medium text-white hover:opacity-90 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-50"
			>
				{archiving ? 'Arquivando…' : 'Arquivar'}
			</button>
		</div>
	</div>
{/if}

<TaskDrawer store={drawer} />
