<script lang="ts">
	/**
	 * Tela "Lista de Projetos".
	 *
	 * Consome `GET /api/projetos` via `$lib/api/projects` e reproduz o conjunto
	 * COMPLETO de filtros do original: busca livre (debounce), Órgão, Status,
	 * Prioridade (linha essencial) + painel "Mais filtros" (Tipo de entrega,
	 * Prazo/atraso, Objetivo EEGD, Indicador ABEP combobox). Os filtros
	 * re-buscam server-side (o `orgao_scope` é aplicado no backend).
	 *
	 * CLICK-THROUGH dos KPIs do Dashboard: os query params da URL
	 * (`?status=`/`?atraso=`/`?prioridade=`/`?orgao=`/`?special_project=`/
	 * `?delivery_type=`/`?objetivo=`/`?abep_indicator=`/`?search=`/`?page=`)
	 * são lidos no mount e populam os filtros — abrindo o painel avançado se
	 * houver filtro avançado ativo. Os filtros são refletidos de volta na URL
	 * (replaceState) para deep-link / voltar / reload preservarem o estado,
	 * espelhando o `?status=...` do form GET Jinja.
	 */
	import { onMount, onDestroy } from 'svelte';
	import { base } from '$app/paths';
	import { goto, replaceState } from '$app/navigation';
	import { page as pageState } from '$app/state';
	import {
		fetchProjects,
		fetchObjetivosCatalogo,
		deleteProject,
		peekProjects,
		type CreateProjectResult,
		type ObjetivoCatalogo
	} from '$lib/api/projects';
	import { ApiClientError } from '$lib/api/client';
	import { orgaoScopeQuery } from '$lib/stores/orgaoScope';
	import type { ProjectsListData, ProjectsListQuery } from '$lib/types/projects';
	import type { Project } from '$lib/types/entities';
	import { isAcessoPorConvite } from '$lib/utils/projectMembers';
	import PageHeader from '$lib/components/PageHeader.svelte';
	import CountBadge from '$lib/components/CountBadge.svelte';
	import Button from '$lib/components/Button.svelte';
	import CriarProjetoModal from '$lib/components/CriarProjetoModal.svelte';
	import Modal from '$lib/components/Modal.svelte';
	import ImportarCsvModal from '$lib/components/ImportarCsvModal.svelte';
	import LoadErrorState from '$lib/components/LoadErrorState.svelte';
	import PaginationBar from '$lib/components/PaginationBar.svelte';
	import ProjetosSkeleton from '$lib/components/skeletons/ProjetosSkeleton.svelte';
	import OrgaoTreeSelect from '$lib/components/OrgaoTreeSelect.svelte';
	import type { OrgaoSelectOption } from '$lib/types/orgaoTreeSelect';
	import SelectMenu from '$lib/components/SelectMenu.svelte';
	import type { SelectMenuOption } from '$lib/types/selectMenu';
	import { flash } from '$lib/stores/flash';
	import { auth } from '$lib/stores/auth';

	type LoadState = 'loading' | 'ready' | 'error';

	const DEBOUNCE_MS = 300;

	/** Status default aplicado pelo backend quando ?status= é omitido. */
	const DEFAULT_STATUS = 'Vigente';

	/**
	 * Indicador ABEP é LEGADO (jun/2026): o campo sai da UI mas o código fica
	 * intacto para reativação futura — basta alternar para `true`. O backend
	 * continua aceitando/filtrando `abep_indicator` normalmente.
	 */
	const SHOW_ABEP = false;

	// Filtros controlados pela UI; a busca acontece server-side.
	let search = $state<string>('');
	let orgao = $state<string>(''); // value do <select> (id como string)
	let status = $state<string>(DEFAULT_STATUS);
	let prioridade = $state<string>('');
	let deliveryType = $state<string>('');
	let atraso = $state<string>('');
	let objetivo = $state<string>(''); // id como string
	let specialProject = $state<string>('');
	let abepIndicator = $state<string>(''); // value canônico (hidden)
	let abepLabel = $state<string>(''); // texto exibido no combobox
	let page = $state<number>(1);

	// Painel "Mais filtros" (advanced): aberto se houver filtro avançado ativo.
	let advancedOpen = $state<boolean>(false);

	// Catálogo de objetivos EEGD para o select avançado (carregado sob demanda;
	// o payload de /api/projetos NÃO traz a lista de objetivos).
	let objetivosCatalog = $state<ObjetivoCatalogo[]>([]);
	let objetivosLoaded = $state<boolean>(false);

	// Combobox ABEP: estado de abertura e item destacado por teclado.
	let abepOpen = $state<boolean>(false);
	let abepActiveIndex = $state<number>(-1);

	// Modal de criação de projeto (Quick Create).
	let createModalOpen = $state<boolean>(false);
	// Modal de importação de projetos via CSV (Admin).
	let importModalOpen = $state<boolean>(false);

	/** Só admin importa projetos via CSV (espelha @admin_required do backend). */
	const isAdmin = $derived($auth.user?.is_admin ?? false);

	/** F3-9: usuário só-convite não vê o seletor de órgão (e nunca toma o 422). */
	const temVinculoDeArea = $derived($auth.user?.tem_vinculo_de_area ?? true);

	/** Sucesso da importação CSV: flash + recarrega a lista. */
	function onProjectsImported(count: number): void {
		importModalOpen = false;
		flash.success(`${count} projeto(s) importado(s) com sucesso.`);
		void load();
	}

	/**
	 * Sucesso da criação: replica o flash success + redirect do Jinja.
	 */
	function onProjectCreated(result: CreateProjectResult): void {
		createModalOpen = false;
		flash.success(result.message);
		const target = result.redirect_to.startsWith('/')
			? `${base}${result.redirect_to}`
			: result.redirect_to;
		void goto(target);
	}

	/** Sucesso dispensado sem "Ver o projeto": flash + lista atualizada. */
	function onProjectCreatedDismissed(result: CreateProjectResult): void {
		flash.success(result.message);
		void load();
	}

	// Guarda o rótulo do item selecionado para não filtrar a lista logo após
	// escolher uma opção (o input passa a exibir o rótulo completo).
	let lastSelectedAbepLabel = $state<string>('');

	let debounceTimer: ReturnType<typeof setTimeout> | null = null;
	let inFlight: AbortController | null = null;

	// Escopo de órgão global (seletor do topnav). `orgaoScopeQuery` é a derived
	// pronta para anexar às chamadas /api (`'orgao=<id>'` | `''`). Quando o filtro
	// de órgão PRÓPRIO da tela está vazio, propagamos o escopo global; o filtro
	// explícito da tela tem precedência. A autorização continua server-side.
	let scopeQuery = $state<string>('');
	const unsubscribeScope = orgaoScopeQuery.subscribe((value) => {
		scopeQuery = value;
	});

	/** Extrai o id numérico do escopo global de órgão (ou `undefined`). */
	function scopeOrgaoId(): number | undefined {
		const match = scopeQuery.match(/orgao=(\d+)/);
		if (!match) return undefined;
		const id = Number.parseInt(match[1], 10);
		return Number.isFinite(id) ? id : undefined;
	}

	const hasActiveFilters = $derived(
		search.trim() !== '' ||
			orgao !== '' ||
			status !== DEFAULT_STATUS ||
			prioridade !== '' ||
			deliveryType !== '' ||
			atraso !== '' ||
			objetivo !== '' ||
			specialProject !== '' ||
			abepIndicator !== ''
	);

	/** Há algum filtro AVANÇADO ativo? (controla a abertura inicial do painel) */
	const hasAdvancedActive = $derived(
		deliveryType !== '' || atraso !== '' || objetivo !== '' || abepIndicator !== ''
	);

	/** Subconjunto de indicadores ABEP que casa com o texto digitado. */
	const abepVisible = $derived.by(() => {
		const term = abepLabel.trim().toLowerCase();
		if (!term || term === lastSelectedAbepLabel.toLowerCase()) return abepOptions;
		return abepOptions.filter(
			(o) =>
				o.label.toLowerCase().includes(term) || o.value.toLowerCase().includes(term)
		);
	});

	/**
	 * Lê os query params da URL e popula os filtros (suporte a click-through dos
	 * KPIs do Dashboard e a deep-links). Executado uma única vez no mount, ANTES
	 * do primeiro load. `status` ausente cai no default "Vigente" (igual Jinja).
	 */
	function hydrateFiltersFromUrl(): void {
		const params = pageState.url.searchParams;
		const statusParam = params.get('status');
		status = statusParam === null ? DEFAULT_STATUS : statusParam;
		search = params.get('search') ?? params.get('q') ?? '';
		orgao = params.get('orgao') ?? '';
		prioridade = params.get('prioridade') ?? '';
		deliveryType = params.get('delivery_type') ?? '';
		atraso = params.get('atraso') ?? '';
		objetivo = params.get('objetivo') ?? '';
		specialProject = params.get('special_project') ?? '';
		abepIndicator = params.get('abep_indicator') ?? '';
		const pageParam = Number.parseInt(params.get('page') ?? '1', 10);
		page = Number.isFinite(pageParam) && pageParam > 0 ? pageParam : 1;
		// Abre o painel avançado se chegou com filtro avançado ativo.
		if (hasAdvancedActive) {
			advancedOpen = true;
			void ensureObjetivos();
		}
	}

	// Hidrata os filtros a partir da URL ANTES do estado/peek inicial — a chave
	// de cache (`buildProjectsQuery()`) precisa refletir os filtros já
	// resolvidos (click-through de KPIs, deep-link) para casar com o que
	// `load()` vai buscar.
	hydrateFiltersFromUrl();

	/** Monta o `ProjectsListQuery` atual a partir dos filtros controlados pela UI. */
	function buildProjectsQuery(): ProjectsListQuery {
		return {
			status,
			prioridade: prioridade || undefined,
			delivery_type: deliveryType || undefined,
			atraso: atraso || undefined,
			objetivo: objetivo || undefined,
			special_project: specialProject || undefined,
			abep_indicator: abepIndicator || undefined,
			// Filtro de órgão da tela tem precedência; senão, herda o escopo global
			// do topnav (orgaoScopeQuery). Vazio => sem filtro ("Todos os órgãos").
			orgao: orgao ? Number.parseInt(orgao, 10) : scopeOrgaoId(),
			q: search.trim() || undefined,
			page
		};
	}

	// SWR: reabre com o último payload bom para a chave de filtros corrente
	// (cache de módulo em $lib/api/projects) e revalida em background — sem
	// flash de loading ao voltar para a rota. O skeleton só aparece quando NÃO
	// há cache para esses filtros (1ª visita ou combinação nunca carregada).
	const initialData = peekProjects(buildProjectsQuery());
	let data = $state<ProjectsListData | null>(initialData);
	let loadState = $state<LoadState>(initialData ? 'ready' : 'loading');
	let errorMessage = $state<string>('');

	/** Opções do GET /api/projetos repassadas ao modal (órgãos/ABEP/etc.). */
	const createOptions = $derived(data?.options ?? null);

	/** Opções de filtro derivadas do payload (com fallbacks canônicos). */
	const statusOptions = $derived(data?.options.statuses ?? ['Vigente', 'Finalizado']);
	const priorityOptions = $derived(data?.options.priorities ?? []);
	const deliveryOptions = $derived(data?.options.delivery_types_options ?? []);
	const atrasoOptions = $derived(data?.options.atrasos_options ?? []);
	const orgaoOptions = $derived(data?.options.orgaos_options ?? []);
	// Opções achatadas p/ o OrgaoTreeSelect (a árvore é montada por `pai_id`).
	const orgaoTreeOptions = $derived(
		orgaoOptions.map(
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
	const specialOptions = $derived(data?.options.special_projects_options ?? []);
	const abepOptions = $derived(data?.options.abep_indicadores_options ?? []);
	const pagination = $derived(data?.pagination ?? null);
	const totalProjects = $derived(data?.pagination.total ?? 0);
	const lastPage = $derived(Math.max(1, pagination?.total_pages ?? 1));
	/**
	 * Lista vazia com o filtro ainda tendo resultados = a página pedida não
	 * existe (itens apagados, ou deep-link antigo). Sem isso a tela acusa os
	 * filtros por um problema que é de paginação.
	 */
	const pageOutOfRange = $derived(
		data !== null && data.projetos.length === 0 && totalProjects > 0
	);

	/** Dot semântico de status (spec §3): só os 3 valores mapeados; demais sem dot. */
	function statusDot(value: string): string | undefined {
		switch (value.toLowerCase()) {
			case 'vigente':
				return 'var(--ds-color-fill-success)';
			case 'suspenso':
				return 'var(--ds-color-fill-warning)';
			case 'finalizado':
				return 'var(--ds-color-status-finalizada)';
			default:
				return undefined;
		}
	}

	// Opções dos filtros nativos convertidas para SelectMenuOption[] (sem duplicar dados).
	const statusMenuOptions = $derived<SelectMenuOption[]>(
		statusOptions.map((o) => ({ value: o, label: o, dot: statusDot(o) }))
	);
	const priorityMenuOptions = $derived<SelectMenuOption[]>(
		priorityOptions.map((o) => ({
			value: o,
			label: capitalize(o),
			dot: `var(--ds-color-priority-${o.toLowerCase()})`
		}))
	);
	const deliveryMenuOptions = $derived<SelectMenuOption[]>(
		deliveryOptions.map((o) => ({ value: o, label: o }))
	);
	const atrasoMenuOptions = $derived<SelectMenuOption[]>(
		atrasoOptions.map((o) => ({ value: o.value, label: o.label }))
	);
	const objetivoMenuOptions = $derived<SelectMenuOption[]>(
		objetivosCatalog.map((o) => ({ value: String(o.id), label: o.descricao }))
	);

	/** Reflete os filtros ativos na URL (replaceState) para reload/voltar/deep-link. */
	function syncUrlFromFilters(): void {
		const params = new URLSearchParams();
		if (search.trim()) params.set('search', search.trim());
		if (orgao) params.set('orgao', orgao);
		// Mantém ?status na URL sempre que difere do default OU foi limpo ("Todos").
		if (status !== DEFAULT_STATUS) params.set('status', status);
		if (prioridade) params.set('prioridade', prioridade);
		if (deliveryType) params.set('delivery_type', deliveryType);
		if (atraso) params.set('atraso', atraso);
		if (objetivo) params.set('objetivo', objetivo);
		if (specialProject) params.set('special_project', specialProject);
		if (abepIndicator) params.set('abep_indicator', abepIndicator);
		if (page > 1) params.set('page', String(page));
		const qs = params.toString();
		const target = `${base}/projetos${qs ? `?${qs}` : ''}`;
		try {
			replaceState(target, {});
		} catch {
			// replaceState exige contexto de roteamento; ignora fora dele (SSR/teste).
		}
	}

	async function load(): Promise<void> {
		inFlight?.abort();
		const controller = new AbortController();
		inFlight = controller;

		const query = buildProjectsQuery();

		// SWR: com cache para esses filtros mostra o dado antigo já (sem
		// skeleton) e a revalidação abaixo troca em silêncio; sem cache,
		// skeleton.
		const cached = peekProjects(query);
		if (cached) {
			data = cached;
			loadState = 'ready';
		} else {
			data = null;
			loadState = 'loading';
		}
		errorMessage = '';
		try {
			const next = await fetchProjects(query, controller.signal);
			if (controller.signal.aborted) return;
			data = next;
			// Reconcilia os filtros com o que o backend efetivamente aplicou.
			status = next.filters.status ?? DEFAULT_STATUS;
			prioridade = next.filters.prioridade ?? '';
			deliveryType = next.filters.delivery_type ?? '';
			atraso = next.filters.atraso ?? '';
			objetivo = next.filters.objetivo ?? '';
			specialProject = next.filters.special_project ?? '';
			abepIndicator = next.filters.abep_indicator ?? '';
			orgao = next.filters.selected_orgao != null ? String(next.filters.selected_orgao) : '';
			page = next.pagination.page;
			syncAbepLabelFromValue();
			syncUrlFromFilters();
			loadState = 'ready';
		} catch (err) {
			if (controller.signal.aborted) return;
			if (err instanceof ApiClientError && err.code === 'unauthenticated') return;
			const message =
				err instanceof Error ? err.message : 'Falha ao carregar os projetos.';
			// Revalidação falhou com dado stale na tela: mantém o dado e avisa
			// via flash, em vez de trocar a lista inteira pelo painel de erro.
			if (data) {
				flash.danger(message);
				return;
			}
			errorMessage = message;
			loadState = 'error';
		}
	}

	/** Carrega o catálogo de objetivos EEGD uma única vez (select avançado). */
	async function ensureObjetivos(): Promise<void> {
		if (objetivosLoaded) return;
		objetivosLoaded = true;
		try {
			objetivosCatalog = await fetchObjetivosCatalogo();
		} catch {
			objetivosLoaded = false; // permite nova tentativa ao reabrir o painel
		}
	}

	/** Casa o `abep_indicator` (value) com o rótulo exibido no combobox. */
	function syncAbepLabelFromValue(): void {
		if (!abepIndicator) {
			abepLabel = '';
			lastSelectedAbepLabel = '';
			return;
		}
		const match = (data?.options.abep_indicadores_options ?? []).find(
			(o) => o.value === abepIndicator
		);
		abepLabel = match?.label ?? abepLabel;
		lastSelectedAbepLabel = abepLabel;
	}

	/** Busca textual com debounce: agenda o reload ao parar de digitar. */
	function onSearchInput(): void {
		if (debounceTimer) clearTimeout(debounceTimer);
		debounceTimer = setTimeout(() => {
			page = 1;
			void load();
		}, DEBOUNCE_MS);
	}

	/** Submit do form: dispara a busca imediatamente (sem esperar o debounce). */
	function onSubmit(event: SubmitEvent): void {
		event.preventDefault();
		if (debounceTimer) clearTimeout(debounceTimer);
		page = 1;
		void load();
	}

	/** Mudança de qualquer <select> de filtro: re-busca a partir da página 1. */
	function applyFilterChange(): void {
		page = 1;
		void load();
	}

	/** Seleção no OrgaoTreeSelect (null = "Todos os órgãos"): mesmo fluxo do onchange. */
	function onOrgaoSelect(selecionado: number | null): void {
		orgao = selecionado == null ? '' : String(selecionado);
		applyFilterChange();
	}

	/** Alterna o painel "Mais filtros" (slide animado + inert/aria). */
	function toggleAdvanced(): void {
		advancedOpen = !advancedOpen;
		if (advancedOpen) void ensureObjetivos();
	}

	function clearFilters(): void {
		if (debounceTimer) clearTimeout(debounceTimer);
		search = '';
		orgao = '';
		status = DEFAULT_STATUS;
		prioridade = '';
		deliveryType = '';
		atraso = '';
		objetivo = '';
		specialProject = '';
		abepIndicator = '';
		abepLabel = '';
		lastSelectedAbepLabel = '';
		abepOpen = false;
		page = 1;
		void load();
	}

	function goToPage(target: number): void {
		const tp = pagination?.total_pages ?? 1;
		if (target < 1 || target > tp || target === page) return;
		page = target;
		void load();
	}

	// --- Combobox ABEP (acessível: role=combobox + listbox) ---------------

	function openAbep(): void {
		abepOpen = true;
		abepActiveIndex = -1;
	}

	function closeAbep(): void {
		abepOpen = false;
		abepActiveIndex = -1;
	}

	function onAbepInput(): void {
		// Digitar invalida a seleção atual até escolher uma opção.
		abepIndicator = '';
		lastSelectedAbepLabel = '';
		openAbep();
	}

	function selectAbep(value: string, label: string): void {
		abepIndicator = value;
		abepLabel = label;
		lastSelectedAbepLabel = label;
		closeAbep();
		page = 1;
		void load();
	}

	function onAbepKeydown(event: KeyboardEvent): void {
		const list = abepVisible;
		if (event.key === 'Escape') {
			closeAbep();
			return;
		}
		if (event.key === 'ArrowDown') {
			event.preventDefault();
			if (!abepOpen) openAbep();
			if (list.length === 0) return;
			abepActiveIndex = Math.min(abepActiveIndex + 1, list.length - 1);
			return;
		}
		if (event.key === 'ArrowUp') {
			event.preventDefault();
			if (list.length === 0) return;
			abepActiveIndex = Math.max(abepActiveIndex - 1, 0);
			return;
		}
		if (event.key === 'Enter') {
			if (abepOpen && abepActiveIndex >= 0 && abepActiveIndex < list.length) {
				event.preventDefault();
				const chosen = list[abepActiveIndex];
				selectAbep(chosen.value, chosen.label);
			}
		}
	}

	// --- Exclusão de projeto: confirmação em dois passos + EXCLUSÃO REAL ----
	// Persiste via DELETE /api/projetos/<id> (client `del`). A linha só some da
	// UI APÓS o sucesso da chamada (fade-out de 280ms, igual ao list.js); em erro
	// mostramos flash e MANTEMOS a linha. `deletingId` trava o botão durante a
	// requisição (evita duplo-submit / clique no overlay).
	let pendingDelete = $state<{ id: number; titulo: string } | null>(null);
	let removingIds = $state<Set<number>>(new Set());
	let deletingId = $state<number | null>(null);

	function requestDelete(project: Project): void {
		pendingDelete = { id: project.id, titulo: project.titulo };
	}

	function cancelDelete(): void {
		if (deletingId !== null) return; // não cancela no meio da exclusão
		pendingDelete = null;
	}

	async function confirmDelete(): Promise<void> {
		if (!pendingDelete || deletingId !== null) return;
		const id = pendingDelete.id;
		const titulo = pendingDelete.titulo;
		deletingId = id;
		try {
			await deleteProject(id);
		} catch (err) {
			// Falha: mantém a linha e informa o motivo (403/404/500 do envelope).
			deletingId = null;
			pendingDelete = null;
			flash.danger(
				err instanceof Error ? err.message : 'Não foi possível excluir o projeto.'
			);
			return;
		}
		// Sucesso: fecha o modal e só então faz o fade-out + remove do payload.
		deletingId = null;
		pendingDelete = null;
		removingIds = new Set([...removingIds, id]);
		setTimeout(() => {
			if (data) {
				const total = Math.max(0, data.pagination.total - 1);
				const totalPages = Math.max(1, Math.ceil(total / data.pagination.per_page));
				data = {
					...data,
					projetos: data.projetos.filter((p) => p.id !== id),
					pagination: { ...data.pagination, total, total_pages: totalPages }
				};
				// Apagar o último item da última página deixaria a tela vazia com
				// o pager escondido e o contador cheio. Recua e recarrega.
				if (data.projetos.length === 0 && total > 0) {
					page = Math.min(page, totalPages);
					void load();
				}
			}
			removingIds = new Set([...removingIds].filter((x) => x !== id));
			flash.success(`Projeto "${titulo}" excluído.`);
		}, 280);
	}

	/**
	 * Atalho de 1 clique do dashboard ("Novo Projeto"): se a URL chega com
	 * `?new=1`, abre o modal de criação automaticamente e LIMPA o param via
	 * replaceState (para reload/voltar não reabrirem o modal). Não interfere no
	 * fluxo manual do modal. Roda APÓS hydrateFiltersFromUrl, que ignora `new`.
	 */
	function openCreateModalFromUrl(): void {
		const params = pageState.url.searchParams;
		if (params.get('new') !== '1') return;
		createModalOpen = true;
		params.delete('new');
		const qs = params.toString();
		const target = `${base}/projetos${qs ? `?${qs}` : ''}`;
		try {
			replaceState(target, {});
		} catch {
			// replaceState exige contexto de roteamento; ignora fora dele (SSR/teste).
		}
	}

	onMount(() => {
		// Filtros já foram hidratados da URL no topo do script (antes do peek
		// inicial); aqui só o atalho "Novo Projeto" e o load/revalidação.
		openCreateModalFromUrl();
		void load();
		return () => inFlight?.abort();
	});

	onDestroy(() => {
		if (debounceTimer) clearTimeout(debounceTimer);
		inFlight?.abort();
		unsubscribeScope();
	});

	/** Detalhe do projeto: rota SPA base-aware (Fase 5a migrada). */
	function projectDetailHref(project: Project): string {
		return `${base}/projetos/${project.id}`;
	}

	/** Link de edição: detalhe com query ?edit=true (igual ao list.html). */
	function projectEditHref(project: Project): string {
		return `${base}/projetos/${project.id}?edit=true`;
	}

	/** Formata uma data ISO em pt-BR; vazio vira travessão. */
	function formatDateBr(iso: string | null): string {
		if (!iso) return '—';
		const parsed = new Date(iso);
		if (Number.isNaN(parsed.getTime())) return '—';
		return parsed.toLocaleDateString('pt-BR', {
			day: '2-digit',
			month: '2-digit',
			year: 'numeric',
			timeZone: 'UTC'
		});
	}

	/** Tom do badge de prioridade conforme a severidade (paridade list.css). */
	function priorityTone(
		prioridade: string | null
	): 'neutral' | 'info' | 'warning' | 'danger' {
		switch ((prioridade ?? '').toLowerCase()) {
			case 'urgente':
				return 'danger';
			case 'alta':
				return 'warning';
			case 'media':
				return 'info';
			default:
				return 'neutral'; // baixa / desconhecida
		}
	}

	/**
	 * Tom do badge de status, fiel às cores do list.css:
	 *   vigente/em andamento → success/info, finalizado → neutral,
	 *   suspenso/pausado → warning, cancelado → danger.
	 */
	function statusTone(
		status: string | null
	): 'neutral' | 'success' | 'warning' | 'danger' | 'info' {
		const key = (status ?? '').toLowerCase().replace(/\s+/g, '_');
		if (key === 'vigente') return 'success';
		if (key === 'em_andamento') return 'info';
		if (key === 'suspenso' || key === 'pausado') return 'warning';
		if (key === 'cancelado' || key === 'cancelada') return 'danger';
		return 'neutral'; // finalizado e demais
	}

	function capitalize(value: string | null): string {
		if (!value) return '—';
		return value.charAt(0).toUpperCase() + value.slice(1);
	}

	// Cor do texto por tom (SEM fundo/pilula). Espelha os tons do Badge, mas para
	// renderizar Prioridade/Status como TEXTO colorido em vez de badge preenchido.
	const toneTextClass: Record<string, string> = {
		neutral: 'text-text-secondary',
		primary: 'text-brand',
		success: 'text-success',
		warning: 'text-warning',
		danger: 'text-danger',
		info: 'text-brand'
	};
</script>

<svelte:head>
	<title>Todos os Projetos — ProjetosRJ</title>
</svelte:head>

<section aria-labelledby="projetos-title" class="flex flex-col gap-4">
	<!-- CARD ÚNICO header + filtros (padrão da tela de Tarefas): chrome de card
		 no wrapper, PageHeader compacto `embedded` e a zona de filtros embutida
		 abaixo de um divisor fino — uma só seção, menos vertical. -->
	<div class="rounded-xl border border-border-subtle bg-surface shadow-sm">
	<PageHeader
		labelId="projetos-title"
		compact
		embedded
		class="min-h-[3.5rem]"
		subtitle="Visualize, filtre e acompanhe seus projetos."
	>
		{#snippet titleContent()}
			<span>Todos os Projetos</span>
			{#if data}
				<!-- Meta-pill de contagem padronizada (Projetos/Tarefas/Pendentes). -->
				<CountBadge class="ml-2">{totalProjects} projeto{totalProjects === 1 ? '' : 's'}</CountBadge>
			{/if}
		{/snippet}
		{#snippet actions()}
			<!--
				Botão primário (btn-projects-v4-primary): gradiente da marca + sombra
				elevada. Reproduzido com o token primary e leve elevação no hover.
				(Exportar CSV migrou para o menu de usuário no topnav — AppTopnav.)
			-->
			{#if isAdmin}
				<Button size="sm" variant="secondary" onclick={() => (importModalOpen = true)}>
					{#snippet icon()}
						<i class="fas fa-file-import" aria-hidden="true"></i>
					{/snippet}
					Importar CSV
				</Button>
			{/if}
			<Button size="sm" onclick={() => (createModalOpen = true)}>
				{#snippet icon()}
					<i class="fas fa-plus" aria-hidden="true"></i>
				{/snippet}
				Novo Projeto
			</Button>
		{/snippet}
	</PageHeader>

	<!-- Zona de filtros embutida no card: campos em linha, SEM rótulos — os
		 placeholders "Todos os..." identificam cada um (acessibilidade via
		 aria-label). O painel "Mais filtros" mantém o slide animado. -->
	<form
		class="flex flex-col border-t border-border-subtle px-4 py-2.5"
		role="search"
		aria-label="Filtros de projetos"
		onsubmit={onSubmit}
	>
		<!-- Linha essencial: busca/órgão/status/prioridade + ações à direita. -->
		<div class="flex flex-wrap items-center gap-2">
			<!-- Largura FIXA e idêntica nas 3 telas (Projetos/Pendentes/Tarefas). -->
			<div class="relative w-full min-w-[14rem] max-w-[26rem]">
				<i
					class="fas fa-search pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-sm text-text-muted"
					aria-hidden="true"
				></i>
				<input
					id="projetosSearch"
					name="search"
					type="search"
					autocomplete="off"
					bind:value={search}
					oninput={onSearchInput}
					aria-label="Busca livre"
					placeholder="Digite título, órgão ou indicador…"
					class="h-9 w-full rounded-lg border border-border-subtle bg-surface pl-8 pr-2.5 text-sm text-text-primary placeholder:text-text-muted transition-colors duration-fast focus:border-brand focus:outline-none"
				/>
			</div>

			{#if temVinculoDeArea && orgaoTreeOptions.length > 0}
				<div class="min-w-[10rem] flex-1">
					<OrgaoTreeSelect
						id="projetosOrgao"
						options={orgaoTreeOptions}
						value={orgao ? Number(orgao) : null}
						onSelect={onOrgaoSelect}
						allowTodos
						ariaLabel="Filtrar por órgão"
						placeholder="Todos os órgãos"
					/>
				</div>
			{/if}

			<div class="min-w-[10rem] flex-1">
				<SelectMenu
					id="projetosStatus"
					options={statusMenuOptions}
					value={status || null}
					onSelect={(v) => {
						status = v ?? '';
						applyFilterChange();
					}}
					allowAll
					allLabel="Todos os status"
					ariaLabel="Filtrar por status"
				/>
			</div>

			<div class="min-w-[10rem] flex-1">
				<SelectMenu
					id="projetosPrioridade"
					options={priorityMenuOptions}
					value={prioridade || null}
					onSelect={(v) => {
						prioridade = v ?? '';
						applyFilterChange();
					}}
					allowAll
					allLabel="Todas as prioridades"
					ariaLabel="Filtrar por prioridade"
				/>
			</div>

			<!-- Ações empurradas para a direita. O botão "Filtrar" foi removido: a
				 seleção em qualquer campo já re-busca server-side (a busca textual tem
				 debounce e o Enter ainda submete o form). -->
			<div class="ml-auto flex items-center gap-2">
				<!-- Toggle "Mais filtros" (btn-projects-v4-toggle). -->
				<button
					type="button"
					onclick={toggleAdvanced}
					aria-expanded={advancedOpen}
					aria-controls="projetosAdvancedPanel"
					title={advancedOpen ? 'Menos filtros' : 'Mais filtros'}
					class="inline-flex h-9 items-center justify-center gap-1.5 rounded-lg border px-3 text-sm font-semibold transition-all duration-fast ease-out focus:outline-none focus-visible:ring-2 focus-visible:ring-brand {advancedOpen
						? 'border-primary-500/50 bg-wash-brand text-brand'
						: 'border-border-subtle bg-surface text-text-secondary hover:border-border-strong hover:bg-surface-muted hover:text-brand'}"
				>
					<i class="fas fa-sliders-h" aria-hidden="true"></i>
					{advancedOpen ? 'Menos filtros' : 'Mais filtros'}
				</button>
				{#if hasActiveFilters}
					<button
						type="button"
						onclick={clearFilters}
						title="Limpar filtros"
						aria-label="Limpar filtros"
						class="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-border-subtle bg-surface text-text-secondary transition-all duration-fast ease-out hover:border-border-strong hover:bg-surface-muted hover:text-brand focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
					>
						<i class="fas fa-filter-circle-xmark" aria-hidden="true"></i>
					</button>
				{/if}
			</div>
		</div>

		<!--
			Painel avançado (projects-v4-filter-advanced): slide via grid-rows
			0fr→1fr, com opacidade/translate. `inert` quando fechado para tirar do
			tab-order, espelhando o list.js.
		-->
		<div
			id="projetosAdvancedPanel"
			class="grid transition-[grid-template-rows,opacity,margin-top,padding-top] duration-300 ease-out {advancedOpen
				? 'mt-0.5 grid-rows-[1fr] pt-3 opacity-100'
				: 'grid-rows-[0fr] opacity-0'}"
			aria-hidden={!advancedOpen}
			inert={!advancedOpen}
		>
			<div class="min-h-0 overflow-visible">
				<div class="flex flex-wrap items-center gap-2">
					<div class="min-w-[11rem] flex-1">
						<SelectMenu
							id="projetosDelivery"
							options={deliveryMenuOptions}
							value={deliveryType || null}
							onSelect={(v) => {
								deliveryType = v ?? '';
								applyFilterChange();
							}}
							allowAll
							allLabel="Todos os tipos de entrega"
							ariaLabel="Filtrar por tipo de entrega"
						/>
					</div>

					<div class="min-w-[11rem] flex-1">
						<SelectMenu
							id="projetosAtraso"
							options={atrasoMenuOptions}
							value={atraso || null}
							onSelect={(v) => {
								atraso = v ?? '';
								applyFilterChange();
							}}
							allowAll
							allLabel="Todos os prazos"
							ariaLabel="Filtrar por prazo"
						/>
					</div>

					<div class="min-w-[16rem] flex-[2]">
						<SelectMenu
							id="projetosObjetivo"
							options={objetivoMenuOptions}
							value={objetivo || null}
							onSelect={(v) => {
								objetivo = v ?? '';
								applyFilterChange();
							}}
							allowAll
							allLabel="Todos os objetivos EEGD"
							ariaLabel="Filtrar por objetivo EEGD"
						/>
					</div>

					<!-- Indicador ABEP (LEGADO, oculto via SHOW_ABEP): combobox filtrável
						 e navegável por teclado. Código mantido para reativação futura. -->
					{#if SHOW_ABEP}
					<div class="relative min-w-[18rem] flex-[2.4]">
						<input
							id="projetosAbep"
							type="text"
							autocomplete="off"
							role="combobox"
							aria-expanded={abepOpen}
							aria-controls="projetosAbepListbox"
							aria-autocomplete="list"
							aria-activedescendant={abepActiveIndex >= 0
								? `abep-option-${abepActiveIndex}`
								: undefined}
							bind:value={abepLabel}
							oninput={onAbepInput}
							onfocus={openAbep}
							onkeydown={onAbepKeydown}
							onblur={() => setTimeout(closeAbep, 120)}
							aria-label="Filtrar por indicador ABEP"
							placeholder="Indicador ABEP (número ou título)…"
							class="h-9 w-full rounded-lg border border-border-subtle bg-surface px-2.5 text-sm text-text-primary placeholder:text-text-muted transition-colors duration-fast focus:border-brand focus:outline-none"
						/>
						{#if abepOpen}
							<!--
								projects-v4-abep-dropdown: painel flutuante com entrada suave
								(animate-dropdown-in — keyframes do kit Fase 1).
							-->
							<ul
								id="projetosAbepListbox"
								role="listbox"
								aria-label="Indicadores ABEP"
								class="absolute left-0 right-0 top-full z-dropdown mt-1 max-h-[220px] origin-top animate-dropdown-in overflow-y-auto rounded-md border border-border-subtle bg-surface py-1 shadow-lg"
							>
								{#if abepVisible.length === 0}
									<li class="px-2.5 py-2 text-sm italic text-text-muted">
										Nenhum indicador encontrado
									</li>
								{:else}
									{#each abepVisible as option, index (option.value)}
										<li class="contents">
											<button
												type="button"
												id={`abep-option-${index}`}
												role="option"
												aria-selected={option.value === abepIndicator}
												class="block w-full cursor-pointer px-2.5 py-2 text-left text-sm text-text-primary transition-colors duration-fast hover:bg-wash-neutral hover:text-brand {index ===
												abepActiveIndex
													? 'bg-wash-neutral text-brand'
													: ''}"
												onmousedown={(e) => e.preventDefault()}
												onclick={() => selectAbep(option.value, option.label)}
											>
												{option.label}
											</button>
										</li>
									{/each}
								{/if}
							</ul>
						{/if}
					</div>
					{/if}
				</div>
			</div>
		</div>
	</form>
	</div>

	{#if loadState === 'loading'}
		<p role="status" aria-live="polite" class="sr-only">Carregando projetos…</p>
		<ProjetosSkeleton />
	{:else if loadState === 'error'}
		<LoadErrorState message={errorMessage} onRetry={() => load()} />
	{:else if data}
		<div role="status" aria-live="polite" class="sr-only">
			{totalProjects} projeto{totalProjects === 1 ? '' : 's'} encontrado{totalProjects === 1
				? ''
				: 's'}.
		</div>

		{#if data.projetos.length === 0}
			<!--
				Estado vazio (projects-v4-empty-state): borda tracejada, ícone em
				quadro suave, título e texto centralizados.
			-->
			<div
				class="rounded-lg border border-dashed border-border-strong bg-surface-muted/40 px-4 py-8 text-center"
			>
				<div
					class="mx-auto mb-3 inline-flex h-14 w-14 items-center justify-center rounded-xl border border-primary-500/25 bg-wash-neutral text-xl text-brand"
				>
					<i class="fas fa-folder-open" aria-hidden="true"></i>
				</div>
				<h2 class="m-0 font-heading text-xl font-bold text-text-primary">
					{pageOutOfRange ? 'Esta página não existe mais' : 'Nenhum projeto encontrado'}
				</h2>
				<p class="mb-3.5 mt-1.5 text-sm text-text-muted">
					{#if pageOutOfRange}
						Os {totalProjects} projetos deste filtro cabem em {lastPage}
						{lastPage === 1 ? 'página' : 'páginas'}. Você está na {page}.
					{:else}
						Os filtros aplicados não retornaram resultados. Ajuste os filtros ou crie um
						novo projeto.
					{/if}
				</p>
				{#if pageOutOfRange}
					<button
						type="button"
						onclick={() => goToPage(lastPage)}
						class="inline-flex h-9 items-center justify-center gap-1.5 rounded-md bg-brand px-3 text-sm font-semibold text-on-brand shadow-sm transition-all duration-fast ease-out hover:bg-brand-hover hover:shadow-md focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
					>
						<i class="fas fa-arrow-left" aria-hidden="true"></i>
						Ir para a última página
					</button>
				{:else}
					<button
						type="button"
						onclick={() => (createModalOpen = true)}
						class="inline-flex h-9 items-center justify-center gap-1.5 rounded-md bg-brand px-3 text-sm font-semibold text-on-brand shadow-sm transition-all duration-fast ease-out hover:bg-brand-hover hover:shadow-md focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
					>
						<i class="fas fa-plus" aria-hidden="true"></i>
						Criar projeto
					</button>
				{/if}
			</div>
		{:else}
			<!--
				Tabela-card (projects-v4-table-card): superfície com borda + sombra e
				overflow-hidden para os cantos arredondarem a tabela.
			-->
			<div class="overflow-hidden rounded-lg border border-border-subtle bg-surface shadow-sm">
				<div class="overflow-x-auto" aria-busy={loadState !== 'ready'}>
					<table class="m-0 w-full min-w-[980px] border-separate border-spacing-0 text-sm">
						<caption class="sr-only">Lista de projetos filtrados</caption>
						<thead>
							<!-- Cabeçalho: fundo suave, MAIÚSCULAS com letter-spacing caps. -->
							<tr class="text-left text-text-muted">
								<th
									scope="col"
									class="w-16 border-b border-border-subtle bg-surface-muted px-2.5 py-2 text-center text-xs font-bold uppercase tracking-caps whitespace-nowrap"
								>
									ID
								</th>
								<th
									scope="col"
									class="min-w-[220px] border-b border-border-subtle bg-surface-muted px-2.5 py-2 text-xs font-bold uppercase tracking-caps whitespace-nowrap"
								>
									Título
								</th>
								<th
									scope="col"
									class="border-b border-border-subtle bg-surface-muted px-2.5 py-2 text-center text-xs font-bold uppercase tracking-caps whitespace-nowrap"
								>
									Órgão
								</th>
								<th
									scope="col"
									class="border-b border-border-subtle bg-surface-muted px-2.5 py-2 text-center text-xs font-bold uppercase tracking-caps whitespace-nowrap"
								>
									Prioridade
								</th>
								<th
									scope="col"
									class="border-b border-border-subtle bg-surface-muted px-2.5 py-2 text-center text-xs font-bold uppercase tracking-caps whitespace-nowrap"
								>
									Status
								</th>
								<th
									scope="col"
									class="border-b border-border-subtle bg-surface-muted px-2.5 py-2 text-center text-xs font-bold uppercase tracking-caps whitespace-nowrap"
								>
									Tipo de entrega
								</th>
								<th
									scope="col"
									class="border-b border-border-subtle bg-surface-muted px-2.5 py-2 text-xs font-bold uppercase tracking-caps whitespace-nowrap"
								>
									Data Início
								</th>
								<th
									scope="col"
									class="border-b border-border-subtle bg-surface-muted px-2.5 py-2 text-xs font-bold uppercase tracking-caps whitespace-nowrap"
								>
									Data Fim
								</th>
								<th
									scope="col"
									class="border-b border-border-subtle bg-surface-muted px-2.5 py-2 text-center text-xs font-bold uppercase tracking-caps whitespace-nowrap"
								>
									Etapas
								</th>
								<th
									scope="col"
									class="w-28 border-b border-border-subtle bg-surface-muted px-2.5 py-2 text-center text-xs font-bold uppercase tracking-caps whitespace-nowrap"
								>
									Ações
								</th>
							</tr>
						</thead>
						<tbody>
							{#each data.projetos as project (project.id)}
								<!-- Linha com hover suave + fade-out na remoção (260ms). -->
								<tr
									class="group transition-[background-color,opacity] duration-fast hover:bg-surface-muted/60 {removingIds.has(
										project.id
									)
										? 'pointer-events-none opacity-0'
										: 'opacity-100'}"
								>
									<td class="border-t border-border-subtle px-2.5 py-2.5 text-center align-middle">
										<!-- ID em texto simples (sem chip/fundo). -->
										<span class="text-xs font-bold text-text-muted">
											{project.id}
										</span>
									</td>
									<td class="border-t border-border-subtle px-2.5 py-2.5 align-middle">
										<a
											href={projectDetailHref(project)}
											class="text-base font-medium text-brand no-underline transition-colors duration-fast hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
										>
											{project.titulo}
										</a>
										{#if isAcessoPorConvite(project.access_via)}
											<span
												title="Você acessa este projeto por convite"
												class="ml-2 inline-flex items-center gap-1 rounded-full bg-wash-neutral px-2 py-0.5 align-middle text-2xs font-bold uppercase tracking-wide text-brand"
											>
												<i class="fas fa-user-check" aria-hidden="true"></i>Convidado
											</span>
										{/if}
									</td>
									<td
										class="border-t border-border-subtle px-2.5 py-2.5 text-center align-middle text-text-secondary"
									>
										<span class="text-xs font-semibold uppercase tracking-wide">
											{project.orgao_sigla ?? project.orgao ?? '—'}
										</span>
									</td>
									<td
										class="border-t border-border-subtle px-2.5 py-2.5 text-center align-middle"
									>
										{#if project.prioridade}
											<span
												class="text-xs font-semibold uppercase tracking-wide {toneTextClass[
													priorityTone(project.prioridade)
												]}"
											>
												{capitalize(project.prioridade)}
											</span>
										{:else}
											<span class="italic text-text-muted">—</span>
										{/if}
									</td>
									<td
										class="border-t border-border-subtle px-2.5 py-2.5 text-center align-middle"
									>
										{#if project.status}
											<span
												class="text-xs font-semibold uppercase tracking-wide {toneTextClass[
													statusTone(project.status)
												]}"
											>
												{project.status}
											</span>
										{:else}
											<span class="italic text-text-muted">—</span>
										{/if}
									</td>
									<td
										class="border-t border-border-subtle px-2.5 py-2.5 text-center align-middle text-text-secondary"
									>
										{#if project.delivery_type}
											<span class="text-xs font-semibold uppercase tracking-wide">
												{project.delivery_type}
											</span>
										{:else}
											<span class="italic text-text-muted">—</span>
										{/if}
									</td>
									<td
										class="border-t border-border-subtle px-2.5 py-2.5 align-middle font-mono font-medium whitespace-nowrap text-text-secondary"
									>
										{#if project.data_inicio_projeto}
											<time datetime={project.data_inicio_projeto}>
												{formatDateBr(project.data_inicio_projeto)}
											</time>
										{:else}
											<span class="italic text-text-muted">—</span>
										{/if}
									</td>
									<td
										class="border-t border-border-subtle px-2.5 py-2.5 align-middle font-mono font-medium whitespace-nowrap text-text-secondary"
									>
										{#if project.data_fim_projeto}
											<time datetime={project.data_fim_projeto}>
												{formatDateBr(project.data_fim_projeto)}
											</time>
										{:else}
											<span class="italic text-text-muted">—</span>
										{/if}
									</td>
									<td
										class="border-t border-border-subtle px-2.5 py-2.5 text-center align-middle font-mono whitespace-nowrap text-text-secondary"
									>
										{#if project.total_workflow_etapas > 0}
											<span
												class="text-xs font-semibold {project.todas_etapas_concluidas
													? 'text-success'
													: ''}"
											>
												{project.etapas_concluidas}/{project.total_workflow_etapas}
											</span>
										{:else}
											<span class="italic text-text-muted">—</span>
										{/if}
									</td>
									<!--
										Ações (projects-v4-actions): editar (link p/ detalhe?edit=true)
										e excluir (confirm em dois passos + DELETE real persistido em
										/api/projetos/<id>; a linha some com fade só após o sucesso).
									-->
									<td
										class="border-t border-border-subtle px-2.5 py-2.5 text-center align-middle"
									>
										<div class="inline-flex items-center justify-center gap-1.5">
											<a
												href={projectEditHref(project)}
												title="Editar projeto"
												aria-label="Editar projeto"
												class="inline-flex h-8 w-8 items-center justify-center text-sm text-text-muted transition-colors duration-fast hover:text-brand focus:outline-none focus-visible:rounded-md focus-visible:ring-2 focus-visible:ring-brand"
											>
												<i class="fas fa-pen" aria-hidden="true"></i>
											</a>
											<button
												type="button"
												onclick={() => requestDelete(project)}
												title="Excluir projeto"
												aria-label="Excluir projeto"
												class="inline-flex h-8 w-8 items-center justify-center text-sm text-text-muted transition-colors duration-fast hover:text-danger focus:outline-none focus-visible:rounded-md focus-visible:ring-2 focus-visible:ring-danger"
											>
												<i class="fas fa-trash" aria-hidden="true"></i>
											</button>
										</div>
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
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
		{/if}
	{/if}
</section>

<!-- Modal de criação (Quick Create) com a mesma UX do add_form Jinja. -->
<CriarProjetoModal
	open={createModalOpen}
	options={createOptions}
	onClose={() => (createModalOpen = false)}
	onCreated={onProjectCreated}
	onCreatedDismissed={onProjectCreatedDismissed}
/>

<!-- Importação de projetos via CSV (Admin) — sucessor do import_modal.html Jinja. -->
<ImportarCsvModal
	open={importModalOpen}
	options={createOptions}
	onClose={() => (importModalOpen = false)}
	onImported={onProjectsImported}
/>

<!--
	Confirmação de exclusão em dois passos. A persistência é REAL: confirmar
	dispara DELETE /api/projetos/<id> e a linha só some (com fade) após o
	sucesso; em erro mantém a linha + flash.
-->
<svelte:window
	onkeydown={(e) => {
		if (pendingDelete && e.key === 'Escape') cancelDelete();
	}}
/>

{#if pendingDelete}
	<Modal labelId="deleteProjectTitle" onBackdrop={cancelDelete}>
		<h2
			id="deleteProjectTitle"
			class="m-0 flex items-center gap-2 font-heading text-lg font-bold text-text-primary"
		>
			<i class="fas fa-triangle-exclamation text-danger" aria-hidden="true"></i>
			Excluir projeto
		</h2>
		<p class="mt-3 text-sm text-text-secondary">
			Tem certeza que deseja excluir <strong class="text-text-primary"
				>{pendingDelete.titulo}</strong
			>? Esta ação não pode ser desfeita.
		</p>
		<div class="mt-5 flex justify-end gap-2">
			<button
				type="button"
				onclick={cancelDelete}
				disabled={deletingId !== null}
				class="inline-flex h-9 items-center justify-center gap-1.5 rounded-md border border-border-subtle bg-surface px-3 text-sm font-semibold text-text-secondary transition-all duration-fast ease-out hover:border-border-strong hover:bg-surface-muted hover:text-brand focus:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-50"
			>
				Cancelar
			</button>
			<button
				type="button"
				onclick={confirmDelete}
				disabled={deletingId !== null}
				class="inline-flex h-9 items-center justify-center gap-1.5 rounded-md border border-danger/30 bg-danger px-3 text-sm font-semibold text-on-danger transition-all duration-fast ease-out hover:opacity-90 focus:outline-none focus-visible:ring-2 focus-visible:ring-danger disabled:cursor-not-allowed disabled:opacity-60"
			>
				{#if deletingId !== null}
					<i class="fas fa-spinner fa-spin" aria-hidden="true"></i>
					Excluindo…
				{:else}
					<i class="fas fa-trash" aria-hidden="true"></i>
					Excluir
				{/if}
			</button>
		</div>
	</Modal>
{/if}
