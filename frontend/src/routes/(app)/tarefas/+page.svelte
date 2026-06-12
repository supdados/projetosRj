<script lang="ts">
	/**
	 * Tela "Hub de Tarefas" em MODO LISTA (sem Kanban). Consome
	 * `GET /api/tarefas` via `$lib/api/tasks` e renderiza a hierarquia
	 * PROJETO → ETAPA → TAREFA (redesign variation-d): cada projeto é uma
	 * `<section>` com `ProjectGroupHeader` (código #id, contagens, donut %) e
	 * colapso próprio; dentro, as tarefas são sub-agrupadas por etapa (a partir de
	 * `etapa_titulo`/`is_first_of_stage`, já calculados no backend) sob um
	 * `StageGroupHeader` (barra azul que embute os rótulos de coluna). Cada tarefa
	 * vira uma `TaskHubTaskRow` (chips de prioridade/tipo/status/responsável
	 * preservados); os comentários expandem INLINE na linha (`InlineCommentsTree`).
	 * "+ Nova tarefa" é por ETAPA (revela form inline); o clique no texto da
	 * descrição abre o `TaskDrawer` completo.
	 *
	 * Os filtros de projeto e órgão re-buscam server-side (o `orgao_scope` é
	 * aplicado no backend); a alternância de status (ativas/arquivadas/
	 * finalizadas) traduz para o `?modo=` do endpoint. Estados de loading/erro/
	 * vazio são anunciados via aria-live. Colapso de projeto/etapa em localStorage.
	 */
	import { onMount, setContext, tick } from 'svelte';
	import { slide, fly } from 'svelte/transition';
	import { cubicOut } from 'svelte/easing';
	import { SvelteSet } from 'svelte/reactivity';
	import { get as readStore } from 'svelte/store';
	import {
		fetchTarefas,
		deleteTarefa,
		archiveFinalizadas,
		createTarefa
	} from '$lib/api/tasks';
	import { ApiClientError } from '$lib/api/client';
	import type {
		TaskAssignee,
		TaskCard,
		TaskHubData,
		TaskHubGroup,
		TaskHubModo,
		TaskHubQuery
	} from '$lib/types/tasks';
	import PageHeader from '$lib/components/PageHeader.svelte';
	import TaskHubTaskRow from '$lib/components/TaskHubTaskRow.svelte';
	import ProjectGroupHeader from '$lib/components/ProjectGroupHeader.svelte';
	import StageGroupHeader from '$lib/components/StageGroupHeader.svelte';
	import { projectCode } from '$lib/utils/taskProgress';
	import AssigneePicker from '$lib/components/AssigneePicker.svelte';
	import KanbanBoard from '$lib/components/KanbanBoard.svelte';
	import KanbanComposer from '$lib/components/KanbanComposer.svelte';
	import TaskViewToggle from '$lib/components/TaskViewToggle.svelte';
	import PaginationBar from '$lib/components/PaginationBar.svelte';
	import CountBadge from '$lib/components/CountBadge.svelte';
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

	/** Visualização da tela: lista (default) ou kanban. */
	type ViewMode = 'list' | 'kanban';

	// Rótulos, tons e cor da barra de status vivem em $lib/utils/taskLabels.ts e
	// são usados pelos componentes da lista (TaskHubTaskRow). As opções dos
	// selects do form de "+ Nova tarefa" continuam abaixo (ADD_*_OPTIONS).

	let loadState = $state<LoadState>('loading');
	let data = $state<TaskHubData | null>(null);
	let errorMessage = $state<string>('');

	// Filtros controlados pela UI; a busca acontece server-side.
	let modo = $state<TaskHubModo>('ativas');
	let project = $state<string>('');
	let orgao = $state<string>('');

	// Página da lista (paginada por GRUPO de projeto no backend). Filtros e
	// troca de modo voltam para a página 1.
	let listPage = $state<number>(1);

	// Filtros vindos por DEEP-LINK na URL (ex.: Dashboard -> /tarefas?tipo=bug).
	// A API/hub ja filtram por estes campos; aqui apenas os lemos da URL e os
	// repassamos a `load()`. Aplicam-se a visao LISTA (o board so mostra ativas).
	let tipo = $state<string>('');
	let prioridade = $state<string>('');
	let statusFilter = $state<string>('');
	let responsavel = $state<string>('');

	let inFlight: AbortController | null = null;

	// Visualização (lista default <-> kanban). O board tem sua própria store
	// canônica; o modo lista mantém seu fluxo atual intocado.
	let view = $state<ViewMode>('list');
	const board = createBoardStore();
	let boardInFlight: AbortController | null = null;
	let boardLoaded = $state<boolean>(false);

	// No kanban os filtros somem e o quadro toma toda a vertical.
	const boardExpanded = $derived(view === 'kanban');

	const PREFERS_REDUCED_MOTION =
		typeof window !== 'undefined' &&
		window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
	const EXPAND_IN_MS = PREFERS_REDUCED_MOTION ? 0 : 420;
	const EXPAND_OUT_MS = PREFERS_REDUCED_MOTION ? 0 : 300;

	// Curvas M3 por direção — strings estáticas (Tailwind não gera classe de
	// valor computado); durações DEVEM casar com EXPAND_IN_MS/EXPAND_OUT_MS.
	const EXPAND_MOTION_IN =
		'motion-safe:duration-[420ms] motion-safe:[transition-timing-function:cubic-bezier(0.05,0.7,0.1,1)]';
	const EXPAND_MOTION_OUT =
		'motion-safe:duration-300 motion-safe:[transition-timing-function:cubic-bezier(0.3,0,0.8,0.15)]';
	const expandMotion = $derived(boardExpanded ? EXPAND_MOTION_IN : EXPAND_MOTION_OUT);

	// Filtros deslizam em ~0.7× (hierarquia M3: o secundário sai antes).
	const filtersSlideMs = $derived(
		Math.round((boardExpanded ? EXPAND_IN_MS : EXPAND_OUT_MS) * 0.7)
	);

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
		// Órgão do board: o filtro LOCAL da tela vence (paridade com a Lista, que
		// usa `orgao` direto); sem ele, cai no ESCOPO DE ÓRGÃO global do topnav.
		// Sem essa precedência, selecionar no filtro local não fazia efeito quando
		// havia um escopo global ativo (caso de quem tem acesso a vários órgãos).
		const scopeId = readStore(orgaoScope).selectedId;
		const query: BoardQuery = {
			project: project || undefined,
			orgao: orgao || (scopeId !== null ? String(scopeId) : undefined),
			// Mesmos filtros da barra compartilhada aplicados ao board (o endpoint
			// do Kanban os suporta) — sem isso a lista filtra e o board nao.
			tipo: tipo || undefined,
			prioridade: prioridade || undefined,
			status: statusFilter || undefined,
			responsavel: responsavel || undefined
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

		const query: TaskHubQuery = {
			modo,
			project,
			orgao,
			tipo: tipo || undefined,
			prioridade: prioridade || undefined,
			status: statusFilter || undefined,
			responsavel: responsavel || undefined,
			page: listPage
		};
		try {
			const next = await fetchTarefas(query, controller.signal);
			if (controller.signal.aborted) return;
			data = next;
			// Reconcilia página/filtros com o que o backend efetivamente aplicou
			// (o backend clampa páginas fora do intervalo).
			listPage = next.pagination.page;
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
	setContext('requestArchiveFinalizadas', openArchiveConfirm);
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

	// EXCLUIR na LISTA: a confirmação inline (mini-confirm, paridade com o kanban)
	// agora vive em TaskHubTaskRow, que chama `deleteCard` via a prop `onDelete`.
	// `deleteCard` re-busca a lista no sucesso (recolhe grupos/etapas vazios).

	// ADD-TAREFA NO MODO LISTA (paridade com o add inline do hub Jinja legado, já
	// removido do codebase): cada GRUPO de projeto ganha um botão "+ Nova tarefa" que
	// abre um form inline. Cria via a MESMA chamada do KanbanComposer (`createTarefa`)
	// e re-busca a lista. Apenas UM form aberto por vez (controlado pela página).
	type AddDraft = {
		descricao: string;
		prioridade: string;
		tipo: string;
		status: string;
		assignees: TaskAssignee[];
		saving: boolean;
		error: string | null;
	};

	const ADD_STATUS_OPTIONS: { value: string; label: string }[] = [
		{ value: 'nao_iniciada', label: 'Não iniciada' },
		{ value: 'em_andamento', label: 'Em andamento' },
		{ value: 'para_validacao', label: 'Para validação' },
		{ value: 'para_ajustes', label: 'Para ajustes' },
		{ value: 'finalizada', label: 'Finalizada' }
	];
	const ADD_PRIORIDADE_OPTIONS: { value: string; label: string }[] = [
		{ value: '', label: 'Prioridade' },
		{ value: 'baixa', label: 'Baixa' },
		{ value: 'media', label: 'Média' },
		{ value: 'alta', label: 'Alta' },
		{ value: 'urgente', label: 'Urgente' }
	];
	// Sem "implementacao": é tipo LEGADO (`LEGACY_TIPOS`) — a criação via
	// /api/tarefas só aceita VALID_TIPOS e descartaria o valor silenciosamente.
	const ADD_TIPO_OPTIONS: { value: string; label: string }[] = [
		{ value: '', label: 'Tipo' },
		{ value: 'bug', label: 'Bug' },
		{ value: 'melhoria', label: 'Melhoria' },
		{ value: 'duvida', label: 'Dúvida' },
		{ value: 'outros', label: 'Outros' }
	];
	// O FILTRO inclui o legado: tarefas antigas ainda carregam "implementacao"
	// e o Dashboard faz deep-link /tarefas?tipo=implementacao.
	const FILTER_TIPO_OPTIONS: { value: string; label: string }[] = [
		...ADD_TIPO_OPTIONS.slice(1),
		{ value: 'implementacao', label: 'Implementação' }
	];

	// Chave do grupo cujo form de adição está aberto (só um por vez), + rascunho.
	// "+ Nova tarefa" POR ETAPA: só um form aberto por vez (chave = stageKey). A
	// tarefa nasce na etapa alvo (etapa_id) e no projeto do grupo.
	let addOpenKey = $state<string | null>(null);
	let addTarget = $state<{ projectValue: string; projectId: number | null; etapaId: number | null } | null>(null);
	let addDraft = $state<AddDraft>(emptyAddDraft());

	function emptyAddDraft(): AddDraft {
		return {
			descricao: '',
			prioridade: '',
			tipo: '',
			status: 'nao_iniciada',
			assignees: [],
			saving: false,
			error: null
		};
	}

	function openAddForm(
		group: TaskHubGroup,
		stage: { titulo: string | null; tasks: TaskCard[] }
	): void {
		addOpenKey = stageKey(group, stage);
		addTarget = {
			projectValue: group.project_value,
			projectId: group.project_id,
			etapaId: stage.tasks[0]?.etapa_id ?? null
		};
		addDraft = emptyAddDraft();
	}

	function cancelAddForm(): void {
		addOpenKey = null;
		addTarget = null;
		addDraft = emptyAddDraft();
	}

	/**
	 * Action: fecha o form de "+ Nova tarefa" ao clicar FORA dele — só se nada foi
	 * digitado (não descarta texto em andamento). Captura no `pointerdown`.
	 */
	function closeOnClickOutside(node: HTMLElement) {
		function handle(event: PointerEvent): void {
			if (node.contains(event.target as Node)) return;
			if (!addDraft.descricao.trim()) cancelAddForm();
		}
		document.addEventListener('pointerdown', handle, true);
		return {
			destroy() {
				document.removeEventListener('pointerdown', handle, true);
			}
		};
	}

	/** Auto-resize da textarea de descrição (piso 34px = min-h; teto via max-h CSS). */
	function autoResizeAdd(event: Event): void {
		const el = event.currentTarget as HTMLTextAreaElement;
		el.style.height = 'auto';
		el.style.height = `${Math.max(34, el.scrollHeight)}px`;
	}

	function onAddTextareaKeydown(event: KeyboardEvent): void {
		if (event.key === 'Escape') {
			event.preventDefault();
			cancelAddForm();
			return;
		}
		if (event.key === 'Enter' && !event.shiftKey) {
			event.preventDefault();
			void submitAddForm();
		}
	}

	async function submitAddForm(): Promise<void> {
		if (!addTarget || addDraft.saving) return;
		addDraft.error = null;
		// Descrição vazia: paridade com o composer — apenas não submete.
		if (!addDraft.descricao.trim()) return;

		addDraft.saving = true;
		try {
			await createTarefa({
				project: addTarget.projectValue,
				etapa: addTarget.etapaId ?? undefined,
				descricao: addDraft.descricao.trim(),
				status: addDraft.status,
				assignee_ids: addDraft.assignees.map((a) => a.id),
				prioridade: addDraft.prioridade || null,
				tipo_pedido: addDraft.tipo || null
			});
			// Re-busca a lista para refletir a nova tarefa na etapa correta
			// (o backend recalcula o agrupamento).
			cancelAddForm();
			void load();
		} catch (err) {
			addDraft.error =
				err instanceof ApiClientError ? err.message : 'Erro ao adicionar tarefa.';
			addDraft.saving = false;
		}
	}

	/** Re-busca a visualização ativa após mudança de filtro (lista e/ou board). */
	function reloadActiveView(): void {
		cancelAddForm();
		listPage = 1;
		void load();
		if (view === 'kanban') void loadBoard();
	}

	/** Navega para outra página da lista (paginada por grupo no backend). */
	function goToListPage(target: number): void {
		cancelAddForm();
		listPage = target;
		void load();
	}

	/** Alterna entre ver tarefas ativas e arquivadas (botão-ícone de arquivo).
	 *  Arquivadas só existem no modo lista (o board mostra apenas ativas), então
	 *  ao ligar arquivadas no Kanban caímos para a Lista. */
	function toggleArchived(): void {
		modo = modo === 'arquivadas' ? 'ativas' : 'arquivadas';
		if (modo === 'arquivadas' && view !== 'list') selectView('list');
		cancelAddForm();
		listPage = 1;
		void load();
	}

	function clearFilters(): void {
		project = '';
		orgao = '';
		tipo = '';
		prioridade = '';
		statusFilter = '';
		responsavel = '';
		closeProjectFilter();
		reloadActiveView();
	}

	// ── Filtro de PROJETO pesquisável (produção tem centenas de projetos) ──────
	// Combobox boxed: fechado mostra o rótulo do projeto; aberto vira input de
	// busca + listbox filtrada (paridade com o project-search do v4.5).
	let projectQuery = $state('');
	let projectOpen = $state(false);
	let projectActiveIndex = $state(0);
	let projectInputEl = $state<HTMLInputElement | null>(null);

	/** Rótulo exibido no estado fechado (selecionado ou "Todos os projetos"). */
	const selectedProjectLabel = $derived.by(() => {
		if (!project) return 'Todos os projetos';
		return data?.project_options.find((o) => o.value === project)?.label ?? project;
	});

	/** Opções filtradas pelo texto digitado (inclui "Todos os projetos"). */
	const projectFilterList = $derived.by(() => {
		const all = [
			{ value: '', label: 'Todos os projetos' },
			...(data?.project_options ?? []).map((o) => ({ value: o.value, label: o.label }))
		];
		const q = projectQuery.trim().toLowerCase();
		return q ? all.filter((o) => o.label.toLowerCase().includes(q)) : all;
	});

	async function openProjectFilter(): Promise<void> {
		if (!data || data.project_options.length === 0) return;
		projectQuery = '';
		projectActiveIndex = 0;
		projectOpen = true;
		await tick();
		projectInputEl?.focus();
	}
	function closeProjectFilter(): void {
		projectOpen = false;
		projectQuery = '';
	}
	function pickProject(value: string): void {
		closeProjectFilter();
		if (value === project) return;
		project = value;
		reloadActiveView();
	}
	function onProjectFilterKeydown(event: KeyboardEvent): void {
		if (event.key === 'ArrowDown') {
			event.preventDefault();
			projectActiveIndex = Math.min(projectFilterList.length - 1, projectActiveIndex + 1);
		} else if (event.key === 'ArrowUp') {
			event.preventDefault();
			projectActiveIndex = Math.max(0, projectActiveIndex - 1);
		} else if (event.key === 'Enter') {
			event.preventDefault();
			const opt = projectFilterList[projectActiveIndex];
			if (opt) pickProject(opt.value);
		} else if (event.key === 'Escape') {
			event.preventDefault();
			closeProjectFilter();
		}
	}

	onMount(() => {
		// Filtros por deep-link (ex.: chips "Por tipo" do Dashboard -> ?tipo=bug).
		// Lidos uma vez na entrada; o servidor aplica o filtro na lista.
		const params = new URLSearchParams(window.location.search);
		tipo = params.get('tipo') ?? '';
		prioridade = params.get('prioridade') ?? '';
		statusFilter = params.get('status') ?? '';
		responsavel = params.get('responsavel') ?? '';
		// Deep-links resolvidos pelo Flask via 302 para ca (KEEP-ENDPOINTs sem
		// rota client-side propria): /tarefas/arquivadas -> ?modo=arquivadas e
		// /projeto/<id>/tarefas -> ?project=<id>. Notificacoes/busca acrescentam
		// ?focus_task=<id> (task_detail) -> abre o drawer da tarefa em foco.
		project = params.get('project') ?? '';
		const modoParam = params.get('modo');
		if (modoParam === 'arquivadas' || modoParam === 'finalizadas') modo = modoParam;
		const focusTaskId = Number(params.get('focus_task'));
		if (Number.isInteger(focusTaskId) && focusTaskId > 0) openTask(focusTaskId, 'list');
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
	 * Opções de órgão para o filtro local: vêm do backend (`orgaos_options`,
	 * mesma fonte de Pendentes) com `value` = ID de OrgaoUnidade — o
	 * sanitizador de `?orgao=` espera o id; siglas derivadas localmente eram
	 * rejeitadas com 422 ("Filtro de órgão inválido").
	 */
	const orgaoOptions = $derived(data?.orgaos_options ?? []);

	const hasActiveFilters = $derived(
		project !== '' ||
			orgao !== '' ||
			tipo !== '' ||
			prioridade !== '' ||
			statusFilter !== '' ||
			responsavel !== ''
	);
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

	/** Chave estável de uma etapa dentro do grupo (prefere etapa_id; cai p/ título). */
	function stageKey(group: TaskHubGroup, stage: { titulo: string | null; tasks: TaskCard[] }): string {
		const etapaId = stage.tasks[0]?.etapa_id ?? null;
		const sub = etapaId != null ? `e:${etapaId}` : stage.titulo ? `t:${stage.titulo}` : '__sem_etapa__';
		return `${group.key}::${sub}`;
	}

	// Colapso de PROJETOS e ETAPAS, persistido em localStorage (default: tudo
	// expandido). Chaves separadas; o mesmo toggleSet serve aos dois conjuntos.
	const COLLAPSE_STAGES_KEY = 'tarefas:list:collapsed:stages';
	const COLLAPSE_PROJECTS_KEY = 'tarefas:list:collapsed:projects';
	let collapsedStages = $state(new SvelteSet<string>());
	let collapsedProjects = $state(new SvelteSet<string>());

	function toggleSet(set: SvelteSet<string>, key: string): void {
		if (set.has(key)) set.delete(key);
		else set.add(key);
	}

	// Hidrata SÍNCRONO (SPA é CSR-only): garante que o $effect de persistência não
	// sobrescreva o armazenado com vazio antes da hidratação.
	function hydrateSet(key: string, set: SvelteSet<string>): void {
		if (typeof localStorage === 'undefined') return;
		try {
			const raw = localStorage.getItem(key);
			if (raw) for (const k of JSON.parse(raw) as string[]) set.add(k);
		} catch {
			// JSON corrompido / storage indisponível: começa tudo expandido.
		}
	}
	hydrateSet(COLLAPSE_STAGES_KEY, collapsedStages);
	hydrateSet(COLLAPSE_PROJECTS_KEY, collapsedProjects);

	$effect(() => {
		// Persiste sempre que o conjunto de etapas recolhidas mudar (best-effort).
		try {
			localStorage.setItem(COLLAPSE_STAGES_KEY, JSON.stringify([...collapsedStages]));
		} catch {
			// storage indisponível/cota: ignora.
		}
	});

	$effect(() => {
		// Persiste o conjunto de projetos recolhidos (best-effort).
		try {
			localStorage.setItem(COLLAPSE_PROJECTS_KEY, JSON.stringify([...collapsedProjects]));
		} catch {
			// storage indisponível/cota: ignora.
		}
	});
</script>

<svelte:head>
	<title>Tarefas — ProjetosRJ</title>
</svelte:head>

<section
	aria-labelledby="tarefas-title"
	class="flex flex-col motion-safe:transition-[gap] {expandMotion} {boardExpanded
		? 'gap-3'
		: 'gap-6'}"
>
	<!-- CARD ÚNICO header + filtros: uma só seção (chrome de card no wrapper; o
		 PageHeader entra `embedded`, sem chrome próprio). A linha de filtros vive
		 abaixo de um divisor fino — ocupa menos vertical que os dois cards
		 separados de antes. -->
	<div class="rounded-xl border border-border-subtle bg-surface shadow-sm">
	<PageHeader
		labelId="tarefas-title"
		compact
		embedded
		class="min-h-[3.5rem]"
		subtitle={view === 'kanban'
			? 'Tarefas ativas por status. Arraste os cards entre colunas para mudar o status.'
			: 'Tarefas agrupadas por projeto.'}
	>
		{#snippet titleContent()}
			<span class="align-middle">Tarefas</span>
			<CountBadge class="ml-2">{totalItems} tarefa{totalItems === 1 ? '' : 's'}</CountBadge>
		{/snippet}
		{#snippet actions()}
			{#if view === 'kanban' && orgaoOptions.length > 1}
				<!-- No Kanban a barra de filtros some, mas quem tem acesso a mais de
					 um órgão ainda precisa restringir o quadro: filtro de órgão
					 compacto no header, replicando o select da Lista. -->
				<select
					id="kanban_filter_orgao"
					bind:value={orgao}
					onchange={reloadActiveView}
					aria-label="Filtrar por órgão"
					class="h-9 w-48 rounded-md border border-border-subtle bg-surface px-2.5 text-sm text-text-primary transition-colors duration-fast hover:bg-surface-muted focus:border-primary-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
				>
					<option value="">Todos os órgãos</option>
					{#each orgaoOptions as orgaoOption (orgaoOption.value)}
						<option value={orgaoOption.value}>{orgaoOption.label}</option>
					{/each}
				</select>
			{/if}

			{#if view === 'list'}
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

			<!-- Tarefas arquivadas: botão-ícone (histórico). Ativo quando exibindo
				 arquivadas; alterna de volta para as ativas. -->
			<button
				type="button"
				onclick={toggleArchived}
				aria-pressed={modo === 'arquivadas'}
				aria-label={modo === 'arquivadas'
					? 'Voltar para as tarefas ativas'
					: 'Mostrar tarefas arquivadas'}
				title={modo === 'arquivadas'
					? 'Voltar para as tarefas ativas'
					: 'Mostrar tarefas arquivadas'}
				class="inline-flex h-9 w-9 items-center justify-center rounded-md border transition-colors duration-fast focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 {modo ===
				'arquivadas'
					? 'border-primary-500 bg-primary-100 text-primary-700'
					: 'border-border-subtle bg-surface text-text-primary hover:bg-surface-muted'}"
			>
				<i class="fas fa-clock-rotate-left" aria-hidden="true"></i>
			</button>

			<!-- Alternância de visualização (Lista ⇄ Kanban) — porte fiel do v4.5. -->
			<TaskViewToggle {view} onSelect={selectView} />
		{/snippet}
	</PageHeader>

	<!-- Linha de filtros embutida no card (re-buscam server-side): campos em UMA
		 linha, SEM rótulos — os placeholders "Todos os..." identificam cada campo
		 (acessibilidade via aria-label). SÓ NA VISÃO LISTA: no kanban a linha some
		 para o quadro tomar a vertical (os filtros aplicados continuam valendo).
		 O slide usa ~0.7× da duração da troca (filtersSlideMs): o secundário sai
		 antes de o primário assentar. -->
	{#if !boardExpanded}
	<form
		transition:slide={{ duration: filtersSlideMs }}
		class="flex items-center gap-2 border-t border-border-subtle px-4 py-2.5"
		aria-label="Filtros de tarefas"
		onsubmit={(e) => e.preventDefault()}
	>
		<div class="relative min-w-0 flex-[1.9]">
			{#if projectOpen}
				<input
					bind:this={projectInputEl}
					id="filter_project"
					type="text"
					bind:value={projectQuery}
					oninput={() => (projectActiveIndex = 0)}
					onkeydown={onProjectFilterKeydown}
					onblur={() => setTimeout(closeProjectFilter, 120)}
					role="combobox"
					aria-expanded="true"
					aria-controls="filter_project_listbox"
					aria-autocomplete="list"
					aria-label="Filtrar por projeto"
					placeholder="Buscar projeto…"
					autocomplete="off"
					class="h-9 w-full rounded-lg border border-border-subtle bg-surface px-2.5 text-sm text-text-primary placeholder:text-text-muted focus:outline-none"
				/>
				<ul
					id="filter_project_listbox"
					role="listbox"
					class="thin-scroll absolute left-0 right-0 top-full z-20 mt-1 max-h-64 overflow-auto rounded-lg border border-border-subtle bg-surface py-1 shadow-md"
				>
					{#each projectFilterList as opt, i (opt.value)}
						<li class="contents">
							<button
								type="button"
								role="option"
								aria-selected={opt.value === project}
								onmousedown={(e) => {
									e.preventDefault();
									pickProject(opt.value);
								}}
								class="block w-full truncate px-3 py-1.5 text-left text-sm text-text-primary transition-colors duration-fast hover:bg-surface-muted {i ===
								projectActiveIndex
									? 'bg-surface-muted'
									: ''}"
							>
								{opt.label}
							</button>
						</li>
					{/each}
					{#if projectFilterList.length === 0}
						<li class="px-3 py-1.5 text-sm text-text-muted">Nenhum projeto encontrado</li>
					{/if}
				</ul>
			{:else}
				<button
					id="filter_project"
					type="button"
					onclick={openProjectFilter}
					disabled={!data || data.project_options.length === 0}
					aria-haspopup="listbox"
					aria-label="Filtrar por projeto"
					class="flex h-9 w-full items-center justify-between gap-2 rounded-lg border border-border-subtle bg-surface px-2.5 text-sm text-text-primary transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-60"
				>
					<span class="min-w-0 flex-1 truncate text-left {project === '' ? 'text-text-muted' : ''}"
						>{selectedProjectLabel}</span
					>
					<i class="fas fa-chevron-down shrink-0 text-xs text-text-muted" aria-hidden="true"></i>
				</button>
			{/if}
		</div>

		<select
			id="filter_orgao"
			bind:value={orgao}
			onchange={reloadActiveView}
			disabled={orgaoOptions.length === 0}
			aria-label="Filtrar por órgão"
			class="h-9 min-w-0 flex-1 rounded-lg border border-border-subtle bg-surface px-2.5 text-sm text-text-primary focus:border-primary-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-60"
		>
			<option value="">Todos os órgãos</option>
			{#each orgaoOptions as orgaoOption (orgaoOption.value)}
				<option value={orgaoOption.value}>{orgaoOption.label}</option>
			{/each}
		</select>

		<select
			id="filter_prioridade"
			bind:value={prioridade}
			onchange={reloadActiveView}
			aria-label="Filtrar por prioridade"
			class="h-9 min-w-0 flex-1 rounded-lg border border-border-subtle bg-surface px-2.5 text-sm text-text-primary focus:border-primary-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
		>
			<option value="">Todas as prioridades</option>
			{#each ADD_PRIORIDADE_OPTIONS.slice(1) as option (option.value)}
				<option value={option.value}>{option.label}</option>
			{/each}
		</select>

		<select
			id="filter_tipo"
			bind:value={tipo}
			onchange={reloadActiveView}
			aria-label="Filtrar por tipo"
			class="h-9 min-w-0 flex-1 rounded-lg border border-border-subtle bg-surface px-2.5 text-sm text-text-primary focus:border-primary-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
		>
			<option value="">Todos os tipos</option>
			{#each FILTER_TIPO_OPTIONS as option (option.value)}
				<option value={option.value}>{option.label}</option>
			{/each}
		</select>

		<select
			id="filter_status"
			bind:value={statusFilter}
			onchange={reloadActiveView}
			aria-label="Filtrar por status"
			class="h-9 min-w-0 flex-1 rounded-lg border border-border-subtle bg-surface px-2.5 text-sm text-text-primary focus:border-primary-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
		>
			<option value="">Todos os status</option>
			{#each ADD_STATUS_OPTIONS as option (option.value)}
				<option value={option.value}>{option.label}</option>
			{/each}
		</select>

		{#if hasActiveFilters}
			<button
				type="button"
				onclick={clearFilters}
				class="h-9 shrink-0 rounded-lg border border-border-subtle bg-surface px-3.5 text-sm font-medium text-text-secondary transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
			>
				Limpar
			</button>
		{/if}
	</form>
	{/if}
	</div>

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
		<!-- Sem placeholder de texto na PRIMEIRA carga: a board store já fornece 5
			 colunas vazias e o container tem altura fixa, então renderizamos o board
			 direto (com aria-busy) em vez de colapsar o layout para uma linha de
			 texto — era isso que causava o "mini refresh" só na primeira troca para
			 Kanban (o ramo `!boardLoaded` encolhia e reexpandia a página). -->
		{#if $board.status === 'error' && !boardLoaded}
			<LoadErrorState message={$board.error ?? ''} onRetry={() => loadBoard()} />
		{:else}
			<!-- Entrada via fly (transform+opacity, compositor-only): sem morph de
				 layout, barato mesmo com muitos cards. -->
			<div
				aria-busy={$board.status === 'loading'}
				in:fly={{ y: 8, duration: PREFERS_REDUCED_MOTION ? 0 : 300, easing: cubicOut }}
			>
				<KanbanBoard store={board}>
					{#snippet composer(status: TaskStatus)}
						<!-- Só habilita o composer DEPOIS do 1º load concluir (`boardLoaded`).
							 Durante a primeira carga renderizamos as colunas vazias (layout
							 estável), mas um card criado aqui via `addCard` seria sobrescrito
							 quando o `board.load()` em voo resolvesse com o snapshot anterior
							 (a tarefa some até outro reload). -->
						{#if boardLoaded}
							<KanbanComposer
								{status}
								projectOptions={data?.project_options ?? []}
								defaultProject={project}
								open={activeComposer === status}
								onCreated={onComposerCreated}
								onRequestOpen={(s) => (activeComposer = s)}
								onRequestClose={() => (activeComposer = null)}
							/>
						{/if}
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
					{@const pKey = group.key}
					{@const pCollapsed = collapsedProjects.has(pKey)}
					{@const groupStages = stagesOf(group.tasks)}
					<!-- Nivel 1 - PROJETO: header rico (codigo #id, contagens, donut) + colapso. -->
					<section
						aria-label={group.project_titulo}
						class="overflow-hidden rounded-lg border border-border-subtle bg-surface shadow-sm"
					>
						<ProjectGroupHeader
							titulo={group.project_titulo}
							code={projectCode(group)}
							orgaoSigla={group.project_orgao_sigla}
							taskCount={group.tasks.length}
							stagesCount={groupStages.length}
							open={!pCollapsed}
							onToggle={() => toggleSet(collapsedProjects, pKey)}
							controlsId={`project-${pKey}`}
						/>

						<div class="task-collapse border-t border-border-subtle" data-collapsed={pCollapsed} id={`project-${pKey}`}>
							<div>
								<div class="flex flex-col gap-3 p-3">
								{#each groupStages as stage (stageKey(group, stage))}
									{@const sKey = stageKey(group, stage)}
									{@const stCollapsed = collapsedStages.has(sKey)}
									<div class="overflow-hidden rounded-lg border border-border-subtle">
										<!-- Scroller horizontal UNICO: header de etapa (com labels) + linhas compartilham o mesmo scroll -> colunas alinhadas. -->
										<div class="overflow-x-auto overflow-y-hidden">
											<StageGroupHeader
												stageCode={stage.tasks[0]?.etapa_display_id ?? null}
												titulo={stage.titulo}
												count={stage.tasks.length}
												collapsed={stCollapsed}
												onToggle={() => toggleSet(collapsedStages, sKey)}
												controlsId={`stage-${sKey}`}
											/>

											<div class="task-collapse" data-collapsed={stCollapsed} id={`stage-${sKey}`}>
												<div>
												{#each stage.tasks as task (task.id)}
													<TaskHubTaskRow
														{task}
														onOpen={(id) => openTask(id, 'list')}
														onDelete={deleteCard}
														onChanged={() => void load()}
													/>
												{/each}
												{#if addOpenKey === sKey}
													<!-- Aparece INSTANTÂNEO e no MESMO lugar (sem slide/fade) — paridade
													     com a main (display swap), focando a descrição. Fecha ao clicar
													     fora se estiver vazio. -->
													<form
														use:closeOnClickOutside
														class="border-t border-border-subtle bg-surface {addDraft.saving
															? 'pointer-events-none opacity-[0.72]'
															: ''}"
														aria-label="Nova tarefa em {stage.titulo ?? 'Sem etapa'}"
														onsubmit={(e) => {
															e.preventDefault();
															void submitAddForm();
														}}
													>
														<div class="task-hub-grid min-h-[44px] items-center px-3">
															<!-- svelte-ignore a11y_autofocus -->
															<textarea
																bind:value={addDraft.descricao}
																onkeydown={onAddTextareaKeydown}
																oninput={autoResizeAdd}
																disabled={addDraft.saving}
																rows="1"
																autofocus
																placeholder="Descreva a tarefa…"
																aria-label="Descrição da tarefa"
																class="max-h-[120px] min-h-[34px] w-full min-w-0 resize-y rounded-[5px] border border-border-subtle bg-surface px-2 py-1.5 text-xs leading-normal text-text-primary transition-colors duration-fast focus:border-primary-500 focus:outline-none disabled:opacity-60 2xl:text-sm"
															></textarea>
															<select
																bind:value={addDraft.prioridade}
																disabled={addDraft.saving}
																aria-label="Prioridade"
																class="h-[34px] w-full rounded-[5px] border border-border-subtle bg-surface px-1.5 text-xs text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-60"
															>
																{#each ADD_PRIORIDADE_OPTIONS as opt (opt.value)}
																	<option value={opt.value}>{opt.label}</option>
																{/each}
															</select>
															<select
																bind:value={addDraft.tipo}
																disabled={addDraft.saving}
																aria-label="Tipo de pedido"
																class="h-[34px] w-full rounded-[5px] border border-border-subtle bg-surface px-1.5 text-xs text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-60"
															>
																{#each ADD_TIPO_OPTIONS as opt (opt.value)}
																	<option value={opt.value}>{opt.label}</option>
																{/each}
															</select>
															<select
																bind:value={addDraft.status}
																disabled={addDraft.saving}
																aria-label="Status"
																class="h-[34px] w-full rounded-[5px] border border-border-subtle bg-surface px-1.5 text-xs text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-60"
															>
																{#each ADD_STATUS_OPTIONS as opt (opt.value)}
																	<option value={opt.value}>{opt.label}</option>
																{/each}
															</select>
															<AssigneePicker
																projectValue={addTarget?.projectValue}
																bind:assignees={addDraft.assignees}
																disabled={addDraft.saving}
															/>
															<div class="flex items-center justify-center gap-1">
																<button
																	type="submit"
																	disabled={addDraft.saving}
																	title="Salvar"
																	aria-label="Salvar tarefa"
																	class="inline-flex h-[30px] w-[30px] items-center justify-center rounded-[5px] border border-primary-500 bg-primary-100 text-primary-700 transition-colors duration-fast hover:bg-primary-100/80 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-50"
																>
																	<i class="fas fa-check text-xs" aria-hidden="true"></i>
																</button>
																<button
																	type="button"
																	onclick={cancelAddForm}
																	disabled={addDraft.saving}
																	title="Cancelar"
																	aria-label="Cancelar"
																	class="inline-flex h-[30px] w-[30px] items-center justify-center rounded-[5px] border border-border-subtle text-text-secondary transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-50"
																>
																	<i class="fas fa-xmark text-xs" aria-hidden="true"></i>
																</button>
															</div>
														</div>
														{#if addDraft.error}
															<p role="alert" class="px-3 pb-2 text-xs text-danger">{addDraft.error}</p>
														{/if}
													</form>
												{:else}
													<button
														type="button"
														onclick={() => openAddForm(group, stage)}
														class="flex min-h-[44px] w-full items-center gap-2 border-t border-border-subtle px-3 text-left text-sm font-medium text-text-secondary transition-colors duration-fast hover:bg-primary-100/30 hover:text-primary-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary-500"
													>
														<i class="fas fa-plus text-2xs text-primary-500" aria-hidden="true"></i>
														Adicionar nova tarefa
													</button>
												{/if}
												</div>
											</div>
										</div>
									</div>
								{/each}
								</div>
							</div>
						</div>
					</section>
				{/each}
			</div>

			<div class="mt-5">
				<PaginationBar
					page={data.pagination.page}
					totalPages={data.pagination.total_pages}
					label="Paginação de projetos da lista"
					disabled={loadState !== 'ready'}
					onChange={goToListPage}
				/>
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
