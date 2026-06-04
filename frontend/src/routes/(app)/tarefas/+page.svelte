<script lang="ts">
	/**
	 * Tela "Hub de Tarefas" em MODO LISTA (sem Kanban). Consome
	 * `GET /api/tarefas` via `$lib/api/tasks` e renderiza a hierarquia
	 * PROJETO → ETAPA → TAREFA: cada projeto é um `Card`; dentro dele, as tarefas
	 * são sub-agrupadas por etapa (a partir de `etapa_titulo`/`is_first_of_stage`,
	 * já calculados no backend) em seções colapsáveis; cada tarefa vira uma
	 * `TaskHubTaskRow` (linha estilo "main": grade de colunas + chips padronizados).
	 * "+ Nova tarefa" é por ETAPA (revela form inline com slide); comentários/anexos
	 * abrem o `TaskDrawer` e mostram contagem na linha.
	 *
	 * Os filtros de projeto e órgão re-buscam server-side (o `orgao_scope` é
	 * aplicado no backend); a alternância de status (ativas/arquivadas/
	 * finalizadas) traduz para o `?modo=` do endpoint. Estados de loading/erro/
	 * vazio são anunciados via aria-live.
	 *
	 * Design: estilo da branch main (templates/tasks/hub.html) + nível de etapa.
	 * Decisões e pesquisa em frontend/docs/lista-tarefas-hierarquica.md.
	 */
	import { onMount, setContext } from 'svelte';
	import { SvelteSet } from 'svelte/reactivity';
	import { get as readStore } from 'svelte/store';
	import {
		fetchTarefas,
		deleteTarefa,
		archiveFinalizadas,
		createTarefa,
		fetchHubResponsaveis
	} from '$lib/api/tasks';
	import { ApiClientError } from '$lib/api/client';
	import type {
		TaskCard,
		TaskHubData,
		TaskHubGroup,
		TaskHubModo,
		TaskHubQuery,
		HubResponsavelSuggestion
	} from '$lib/types/tasks';
	import PageHeader from '$lib/components/PageHeader.svelte';
	import Card from '$lib/components/Card.svelte';
	import TaskHubTaskRow from '$lib/components/TaskHubTaskRow.svelte';
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

	/** Visualização da tela: lista (default) ou kanban. */
	type ViewMode = 'list' | 'kanban';

	/** Modos da topnav (espelham `?modo=` do endpoint). */
	const MODO_OPTIONS: { value: TaskHubModo; label: string }[] = [
		{ value: 'ativas', label: 'Ativas' },
		{ value: 'finalizadas', label: 'Finalizadas' },
		{ value: 'arquivadas', label: 'Arquivadas' }
	];

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

	// EXCLUIR na LISTA: a confirmação inline (mini-confirm, paridade com o kanban)
	// agora vive em TaskHubTaskRow, que chama `deleteCard` via a prop `onDelete`.
	// `deleteCard` re-busca a lista no sucesso (recolhe grupos/etapas vazios).

	// ADD-TAREFA NO MODO LISTA (paridade com add-item-inline.js + render_hub_add_row
	// do hub.html legado): cada GRUPO de projeto ganha um botão "+ Nova tarefa" que
	// abre um form inline. Cria via a MESMA chamada do KanbanComposer (`createTarefa`)
	// e re-busca a lista. Apenas UM form aberto por vez (controlado pela página).
	type AddDraft = {
		descricao: string;
		prioridade: string;
		tipo: string;
		status: string;
		responsavel: string;
		responsavelOptions: HubResponsavelSuggestion[];
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
	const ADD_TIPO_OPTIONS: { value: string; label: string }[] = [
		{ value: '', label: 'Tipo' },
		{ value: 'bug', label: 'Bug' },
		{ value: 'melhoria', label: 'Melhoria' },
		{ value: 'duvida', label: 'Dúvida' },
		{ value: 'outros', label: 'Outros' },
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
			responsavel: '',
			responsavelOptions: [],
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
		void loadAddResponsaveis(group.project_id, group.project_value, addOpenKey);
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

	// Sugestões de responsável carregadas sob demanda por projeto (paridade com o
	// composer do Kanban). Projetos "sem id" não consultam.
	async function loadAddResponsaveis(
		projectId: number | null,
		projectValue: string,
		key: string
	): Promise<void> {
		if (!projectId) return;
		try {
			const result = await fetchHubResponsaveis({ project: projectValue });
			if (addOpenKey === key) addDraft.responsavelOptions = result.users;
		} catch {
			if (addOpenKey === key) addDraft.responsavelOptions = [];
		}
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
				responsavel: addDraft.responsavel || null,
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

	function selectModo(next: TaskHubModo): void {
		if (modo === next) return;
		cancelAddForm();
		modo = next;
		void load();
	}

	/** Re-busca a visualização ativa após mudança de filtro (lista e/ou board). */
	function reloadActiveView(): void {
		cancelAddForm();
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

	/** Chave estável de uma etapa dentro do grupo (prefere etapa_id; cai p/ título). */
	function stageKey(group: TaskHubGroup, stage: { titulo: string | null; tasks: TaskCard[] }): string {
		const etapaId = stage.tasks[0]?.etapa_id ?? null;
		const sub = etapaId != null ? `e:${etapaId}` : stage.titulo ? `t:${stage.titulo}` : '__sem_etapa__';
		return `${group.key}::${sub}`;
	}

	// Colapso de etapas, persistido em localStorage (default: tudo expandido).
	const COLLAPSE_STAGES_KEY = 'tarefas:list:collapsed:stages';
	let collapsedStages = $state(new SvelteSet<string>());

	function toggleSet(set: SvelteSet<string>, key: string): void {
		if (set.has(key)) set.delete(key);
		else set.add(key);
	}

	// Hidrata SÍNCRONO (SPA é CSR-only): garante que o $effect de persistência não
	// sobrescreva o armazenado com vazio antes da hidratação.
	if (typeof localStorage !== 'undefined') {
		try {
			const raw = localStorage.getItem(COLLAPSE_STAGES_KEY);
			if (raw) for (const k of JSON.parse(raw) as string[]) collapsedStages.add(k);
		} catch {
			// JSON corrompido / storage indisponível: começa tudo expandido.
		}
	}

	$effect(() => {
		// Persiste sempre que o conjunto de etapas recolhidas mudar (best-effort).
		try {
			localStorage.setItem(COLLAPSE_STAGES_KEY, JSON.stringify([...collapsedStages]));
		} catch {
			// storage indisponível/cota: ignora.
		}
	});
</script>

<svelte:head>
	<title>Tarefas — ProjetosRJ</title>
</svelte:head>

<section aria-labelledby="tarefas-title" class="flex flex-col gap-6">
	<PageHeader
		title="Tarefas"
		labelId="tarefas-title"
		subtitle={view === 'kanban'
			? 'Tarefas ativas por status. Arraste os cards entre colunas para mudar o status.'
			: 'Tarefas agrupadas por projeto.'}
	>
		{#snippet actions()}
			<span
				class="inline-flex items-center gap-1 rounded-sm border border-primary-500 bg-primary-100 px-2 py-1 text-xs font-medium text-primary-700"
			>
				{totalItems} tarefa{totalItems === 1 ? '' : 's'}
			</span>
		{/snippet}
	</PageHeader>

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

						<div class="flex flex-col gap-3">
							{#each stagesOf(group.tasks) as stage (stageKey(group, stage))}
								{@const sKey = stageKey(group, stage)}
								{@const stCollapsed = collapsedStages.has(sKey)}
								<div class="overflow-hidden rounded-lg border border-border-subtle">
									<!-- Nível 2 — ETAPA: sub-cabeçalho leve e colapsável -->
									<button
										type="button"
										onclick={() => toggleSet(collapsedStages, sKey)}
										aria-expanded={!stCollapsed}
										aria-controls={`stage-${sKey}`}
										class="flex w-full items-center gap-2 border-b border-border-subtle bg-surface-muted px-3 py-[0.5rem] text-left transition-colors duration-fast hover:bg-primary-100/50 focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary-500"
									>
										<i
											class="fas fa-chevron-right text-2xs text-text-muted transition-transform duration-fast motion-reduce:transition-none {stCollapsed
												? ''
												: 'rotate-90'}"
											aria-hidden="true"
										></i>
										<span class="text-sm font-semibold text-primary-700">{stage.titulo ?? 'Sem etapa'}</span>
										<span
											class="rounded-full bg-surface px-2 py-0.5 text-2xs font-semibold text-text-secondary"
										>
											{stage.tasks.length}
										</span>
									</button>

									<!-- Corpo colapsável: cabeçalho de colunas + linhas (mesma grade) -->
									<div class="task-collapse" data-collapsed={stCollapsed} id={`stage-${sKey}`}>
										<div>
											<div class="overflow-x-auto overflow-y-hidden">
												<!-- Cabeçalho de colunas (mesma .task-hub-grid das linhas → alinha). -->
												<div class="task-hub-grid border-b border-border-subtle bg-surface-muted/70 px-3 py-1.5">
													<span class="text-2xs font-bold uppercase tracking-[0.04em] text-text-muted">Descrição</span>
													<span class="text-center text-2xs font-bold uppercase tracking-[0.04em] text-text-muted">Prioridade</span>
													<span class="text-center text-2xs font-bold uppercase tracking-[0.04em] text-text-muted">Tipo</span>
													<span class="text-center text-2xs font-bold uppercase tracking-[0.04em] text-text-muted">Status</span>
													<span class="text-center text-2xs font-bold uppercase tracking-[0.04em] text-text-muted">Responsável</span>
													<span class="text-center text-2xs font-bold uppercase tracking-[0.04em] text-text-muted">Ações</span>
												</div>
												{#each stage.tasks as task (task.id)}
													<TaskHubTaskRow
														{task}
														projectValue={group.project_value}
														onOpen={(id) => openTask(id, 'list')}
														onDelete={deleteCard}
														onChanged={() => void load()}
													/>
												{/each}
											</div>

											<!-- "+ Nova tarefa" POR ETAPA, na MESMA grade das linhas: cada campo
											     cai sob a sua coluna (a descrição NÃO ocupa a largura toda). Tem o
											     próprio overflow-x-auto p/ não ser cortado e alinhar as colunas;
											     o form revela com slide fluido (estilo da main). -->
											<div class="overflow-x-auto overflow-y-hidden">
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
																class="max-h-[120px] min-h-[34px] w-full min-w-0 resize-y rounded-[5px] border border-border-subtle bg-surface px-2 py-1.5 text-sm leading-normal text-text-primary transition-shadow duration-fast focus:border-primary-500 focus:outline-none focus:shadow-[0_0_0_3px_rgba(31,92,168,0.12)] disabled:opacity-60"
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
															{#if addDraft.responsavelOptions.length > 0}
																<select
																	bind:value={addDraft.responsavel}
																	disabled={addDraft.saving}
																	aria-label="Responsável"
																	class="h-[34px] w-full rounded-[5px] border border-border-subtle bg-surface px-1.5 text-xs text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-60"
																>
																	<option value="">Sem responsável</option>
																	{#each addDraft.responsavelOptions as user (user.id)}
																		<option value={user.name}>{user.name}</option>
																	{/each}
																</select>
															{:else}
																<span class="text-center text-2xs italic text-text-muted">—</span>
															{/if}
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
