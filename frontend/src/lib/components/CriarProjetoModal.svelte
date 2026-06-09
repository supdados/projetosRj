<script lang="ts">
	/**
	 * Modal "Criar Novo Projeto" (Quick Create) — paridade fiel com o modal
	 * Bootstrap `templates/projects/add_form.html` + `add_form_js.html`.
	 *
	 * Estrutura: ACORDEÃO multi-seção (estilo "Account Setup"). Todas as 5 seções
	 * ficam visíveis numa lista; cada uma é expansível/colapsável de forma
	 * independente (progressive disclosure — múltiplas abertas ao mesmo tempo).
	 * Cada header traz ícone circular + título + tooltip (i) + descrição + pill de
	 * status + chevron; ao expandir revela um cartão com linhas "ícone+label | input".
	 *
	 * Replica (lógica de negócio preservada do wizard anterior):
	 *   - seção Principal (título*, área*, prioridade, descrição, órgão texto);
	 *   - combobox ABEP filtrável com navegação por teclado (Arrow/Enter/Escape);
	 *   - cascata objetivo→resultado→indicadores com animação escalonada (índice·100ms)
	 *     e LIMITE de 4 indicadores ('Você pode selecionar no máximo 4 indicadores');
	 *   - máscara SEI on-input ('SEI-000000/000000/0000');
	 *   - import de modelo com preview read-only e cálculo de datas no client;
	 *   - botão "Criar Projeto" desabilitado até título + área válidos.
	 *
	 * Submit: `POST /api/projetos` (via `createProject`). Em sucesso o COMPONENTE
	 * NÃO navega nem mostra flash — emite `onCreated(result)`. Em erro, exibe a
	 * mensagem do envelope como flash danger/warning (sem fechar o modal).
	 */
	import { tick, untrack, onDestroy } from 'svelte';
	import { fly } from 'svelte/transition';
	import {
		createProject,
		fetchObjetivosCatalogo,
		fetchResultados,
		fetchIndicadores,
		fetchTemplates,
		fetchTemplateStages,
		type CreateProjectInput,
		type CreateProjectResult,
		type ObjetivoCatalogo,
		type ResultadoCatalogo,
		type IndicadorCatalogo,
		type TemplateOption,
		type TemplateStage
	} from '$lib/api/projects';
	import { ApiClientError } from '$lib/api/client';
	import type {
		AbepIndicadorOption,
		OrgaoOption,
		ProjectsListOptions
	} from '$lib/types/projects';
	import { flash } from '$lib/stores/flash';

	interface Props {
		/** Modal aberto? (controlado pela página). */
		open: boolean;
		/** Opções de filtro do GET /api/projetos (órgãos/ABEP/delivery/especial). */
		options: ProjectsListOptions | null;
		/** Fecha o modal sem criar. */
		onClose: () => void;
		/** Criação concluída com sucesso; a página faz flash + navegação. */
		onCreated: (result: CreateProjectResult) => void;
	}

	let { open, options, onClose, onCreated }: Props = $props();

	const DELIVERY_TYPES = [
		'Sistema',
		'Painel',
		'Norma',
		'Instrumento de parceria',
		'Fluxo Processual',
		'Outro'
	];
	const SPECIAL_PROJECTS = ['ABEP', 'TCE'];
	const PRIORITIES = [
		{ value: 'baixa', label: 'Baixa' },
		{ value: 'media', label: 'Média' },
		{ value: 'alta', label: 'Alta' },
		{ value: 'urgente', label: 'Urgente' }
	];
	const MAX_INDICADORES = 4;

	/**
	 * As 5 seções do acordeão (mesmos grupos do wizard anterior). Só a Principal
	 * é obrigatória; pode-se SALVAR a qualquer momento (canSubmit). `tooltip` e
	 * `description` alimentam o ícone (i) e a linha de subtítulo do header.
	 */
	interface SectionDef {
		id: string;
		title: string;
		icon: string;
		optional: boolean;
		tooltip: string;
		description: string;
	}
	const SECTIONS: SectionDef[] = [
		{
			id: 'principal',
			title: 'Principal',
			icon: 'fa-circle-info',
			optional: false,
			tooltip: 'Título e área são obrigatórios para criar o projeto.',
			description: 'Dados básicos do projeto.'
		},
		{
			id: 'classificacao',
			title: 'Classificação',
			icon: 'fa-sliders',
			optional: true,
			tooltip: 'Categorize o tipo de entrega e marque se é projeto especial (ABEP/TCE).',
			description: 'Tipo de entrega e projetos especiais.'
		},
		{
			id: 'objetivos',
			title: 'Objetivos, resultados e indicadores',
			icon: 'fa-bullseye',
			optional: true,
			tooltip: 'Vincule ao planejamento EEGD e selecione até 4 indicadores.',
			description: 'Vínculo EEGD e indicadores ABEP.'
		},
		{
			id: 'links',
			title: 'Links e observações',
			icon: 'fa-link',
			optional: true,
			tooltip: 'Processo SEI, repositórios e anotações detalhadas.',
			description: 'Processo SEI, links e observações.'
		},
		{
			id: 'etapas',
			title: 'Modelo de etapas',
			icon: 'fa-layer-group',
			optional: true,
			tooltip: 'Importe um modelo de etapas e defina a data de início.',
			description: 'Cronograma a partir de um modelo.'
		}
	];

	// --- Campos da seção Principal ----------------------------------------
	let titulo = $state('');
	let orgaoId = $state('');
	let prioridade = $state('baixa');
	let shortDescription = $state('');
	let orgaoTexto = $state('');

	// --- Classificação -----------------------------------------------------
	let deliveryType = $state('');
	let specialProject = $state('');

	// --- Objetivos/resultados/indicadores ----------------------------------
	let objetivos = $state<ObjetivoCatalogo[]>([]);
	let objetivoId = $state('');
	let resultados = $state<ResultadoCatalogo[]>([]);
	let resultadoId = $state('');
	let resultadosLoading = $state(false);
	let indicadores = $state<IndicadorCatalogo[]>([]);
	let indicadoresLoading = $state(false);
	let selectedIndicadores = $state<number[]>([]);
	// IDs já revelados pela animação escalonada (animate-in).
	let revealedIndicadores = $state<Set<number>>(new Set());
	// Timers pendentes do reveal escalonado — limpos a cada nova cascata/reset/close
	// para não reativar IDs obsoletos numa lista nova (ou escrever estado após
	// desmontar). Ver onResultadoChange / clearRevealTimers.
	let revealTimers: ReturnType<typeof setTimeout>[] = [];

	function clearRevealTimers(): void {
		revealTimers.forEach(clearTimeout);
		revealTimers = [];
	}

	// --- ABEP combobox -----------------------------------------------------
	let abepValue = $state(''); // value canônico (hidden)
	let abepLabel = $state(''); // texto exibido
	let abepOpen = $state(false);
	let abepActiveIndex = $state(-1);
	let lastSelectedAbepLabel = $state('');

	// --- Links e Observação ------------------------------------------------
	let seiProcess = $state('');
	let githubLink = $state('');
	let documentationLink = $state('');
	let productLink = $state('');
	let observacao = $state('');

	// --- Modelo de etapas --------------------------------------------------
	let templates = $state<TemplateOption[]>([]);
	let templateId = $state('');
	let templateStages = $state<TemplateStage[]>([]);
	let templateLoading = $state(false);
	let startDate = $state('');

	// --- Estado geral ------------------------------------------------------
	let submitting = $state(false);
	let catalogsLoaded = $state(false);
	let titleInputEl = $state<HTMLInputElement | null>(null);
	let dialogEl = $state<HTMLElement | null>(null); // container role=dialog (focus trap)
	let triedSubmit = $state(false); // marca erro da seção Principal só após tentativa
	let reduceMotion = $state(false); // espelha prefers-reduced-motion (p/ fly do modal)

	// --- Acordeão: seções abertas ------------------------------------------
	// Múltiplas seções podem estar abertas simultaneamente (progressive
	// disclosure). Principal aberta por padrão. O Set é SEMPRE reatribuído
	// (nunca mutado in-place) para a reatividade de runes funcionar.
	let openSections = $state<Set<string>>(new Set(['principal']));

	function isOpen(id: string): boolean {
		return openSections.has(id);
	}

	function toggleSection(id: string): void {
		const next = new Set(openSections);
		if (next.has(id)) next.delete(id);
		else next.add(id);
		openSections = next;
	}

	function openSection(id: string): void {
		if (openSections.has(id)) return;
		openSections = new Set([...openSections, id]);
	}

	const orgaoOptions = $derived<OrgaoOption[]>(options?.orgaos_options ?? []);
	const abepOptions = $derived<AbepIndicadorOption[]>(
		options?.abep_indicadores_options ?? []
	);
	const deliveryTypes = $derived(options?.delivery_types_options ?? DELIVERY_TYPES);
	const specialOptions = $derived(options?.special_projects_options ?? SPECIAL_PROJECTS);

	// Botão Criar habilita só com título + área (paridade com updateSubmitState).
	const canSubmit = $derived(
		!submitting && titulo.trim().length > 0 && orgaoId.trim().length > 0
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

	// Ao abrir: reseta o formulário, carrega catálogos uma vez e foca o título.
	// IMPORTANTE: o reset é disparado SÓ na transição fechado→aberto. Em Svelte 5
	// um $effect rastreia toda leitura reativa síncrona, inclusive dentro de
	// funções chamadas — e resetForm() lê `options`. Sem o gate + untrack, uma
	// atualização assíncrona de `options` (carga/refresh) com o modal aberto
	// re-disparava o efeito e apagava os dados já digitados (perda de dados).
	let wasOpen = false;
	let openerEl: HTMLElement | null = null;
	$effect(() => {
		const isNowOpen = open;
		if (isNowOpen && !wasOpen) {
			openerEl = (document.activeElement as HTMLElement | null) ?? null;
			untrack(() => {
				resetForm();
				void loadCatalogs();
			});
			void tick().then(() => titleInputEl?.focus());
		}
		wasOpen = isNowOpen;
	});

	// Quando há EXATAMENTE um órgão disponível, pré-seleciona-o assim que as opções
	// chegarem — inclusive de forma ASSÍNCRONA com o modal já aberto (ex.: deep-link
	// /projetos?new=1 que abre o modal ANTES de `options` carregar). Sem isto, o
	// untrack do efeito de abertura faz o `resetForm` (com options vazio) deixar
	// `orgaoId=''` para sempre, e o input de órgão único (desabilitado) impediria
	// `canSubmit`. Efeito ESTREITO de propósito: só preenche `orgaoId` quando está
	// vazio e há 1 opção — NÃO re-roda resetForm nem apaga dados já digitados.
	$effect(() => {
		if (open && orgaoOptions.length === 1 && orgaoId === '') {
			orgaoId = orgaoOptions[0].value;
		}
	});

	// Lê prefers-reduced-motion uma vez (e observa mudanças) p/ condicionar o fly.
	$effect(() => {
		if (typeof window === 'undefined') return;
		const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
		reduceMotion = mq.matches;
		const onChange = (e: MediaQueryListEvent) => (reduceMotion = e.matches);
		mq.addEventListener('change', onChange);
		return () => mq.removeEventListener('change', onChange);
	});

	function resetForm(): void {
		clearRevealTimers();
		titulo = '';
		// Pré-seleciona quando há um único órgão disponível (paridade Jinja).
		const opts = options?.orgaos_options ?? [];
		orgaoId = opts.length === 1 ? opts[0].value : '';
		prioridade = 'baixa';
		shortDescription = '';
		orgaoTexto = '';
		deliveryType = '';
		specialProject = '';
		objetivoId = '';
		resultados = [];
		resultadoId = '';
		indicadores = [];
		selectedIndicadores = [];
		revealedIndicadores = new Set();
		abepValue = '';
		abepLabel = '';
		abepOpen = false;
		abepActiveIndex = -1;
		lastSelectedAbepLabel = '';
		seiProcess = '';
		githubLink = '';
		documentationLink = '';
		productLink = '';
		observacao = '';
		templateId = '';
		templateStages = [];
		startDate = '';
		openSections = new Set(['principal']);
		triedSubmit = false;
	}

	async function loadCatalogs(): Promise<void> {
		if (catalogsLoaded) return;
		try {
			const [objetivosData, templatesData] = await Promise.all([
				fetchObjetivosCatalogo(),
				fetchTemplates()
			]);
			objetivos = objetivosData;
			templates = templatesData;
			catalogsLoaded = true;
		} catch (err) {
			if (err instanceof ApiClientError && err.code === 'unauthenticated') return;
			// Catálogos são auxiliares: falha não bloqueia o título/área.
			objetivos = objetivos.length ? objetivos : [];
		}
	}

	// --- Cascata objetivo → resultado → indicadores ------------------------

	async function onObjetivoChange(): Promise<void> {
		clearRevealTimers();
		resultadoId = '';
		resultados = [];
		indicadores = [];
		selectedIndicadores = [];
		revealedIndicadores = new Set();
		if (!objetivoId) return;
		resultadosLoading = true;
		try {
			resultados = await fetchResultados(objetivoId);
		} catch {
			resultados = [];
		} finally {
			resultadosLoading = false;
		}
	}

	async function onResultadoChange(): Promise<void> {
		clearRevealTimers();
		indicadores = [];
		selectedIndicadores = [];
		revealedIndicadores = new Set();
		if (!resultadoId) return;
		indicadoresLoading = true;
		try {
			const data = await fetchIndicadores(resultadoId);
			indicadores = data;
			if (reduceMotion) {
				// prefers-reduced-motion: revela todos de uma vez (sem stagger).
				revealedIndicadores = new Set(data.map((ind) => ind.id));
			} else {
				// Animação escalonada (animate-in): revela cada item a cada 100ms.
				revealedIndicadores = new Set();
				data.forEach((ind, index) => {
					revealTimers.push(
						setTimeout(() => {
							revealedIndicadores = new Set([...revealedIndicadores, ind.id]);
						}, index * 100)
					);
				});
			}
		} catch {
			indicadores = [];
		} finally {
			indicadoresLoading = false;
		}
	}

	function toggleIndicador(id: number): void {
		if (selectedIndicadores.includes(id)) {
			selectedIndicadores = selectedIndicadores.filter((x) => x !== id);
			return;
		}
		// Limite de 4 (paridade: alerta de flash e não marca).
		if (selectedIndicadores.length >= MAX_INDICADORES) {
			flash.warning('Você pode selecionar no máximo 4 indicadores');
			return;
		}
		selectedIndicadores = [...selectedIndicadores, id];
	}

	// --- Máscara SEI (on-input) -------------------------------------------

	function onSeiInput(event: Event): void {
		const raw = (event.currentTarget as HTMLInputElement).value.replace(/[^0-9]/g, '');
		if (!raw) {
			seiProcess = '';
			return;
		}
		let formatted = 'SEI-';
		if (raw.length <= 6) {
			formatted += raw;
		} else if (raw.length <= 12) {
			formatted += `${raw.substring(0, 6)}/${raw.substring(6)}`;
		} else {
			formatted += `${raw.substring(0, 6)}/${raw.substring(6, 12)}/${raw.substring(12, 16)}`;
		}
		seiProcess = formatted;
	}

	// --- ABEP combobox -----------------------------------------------------

	function openAbep(): void {
		abepOpen = true;
		abepActiveIndex = -1;
	}

	function closeAbep(): void {
		abepOpen = false;
		abepActiveIndex = -1;
	}

	function onAbepInput(): void {
		abepValue = '';
		lastSelectedAbepLabel = '';
		openAbep();
	}

	function selectAbep(value: string, label: string): void {
		abepValue = value;
		abepLabel = label;
		lastSelectedAbepLabel = label;
		closeAbep();
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

	// --- Modelo de etapas: preview com cálculo de datas no client ----------

	async function onTemplateChange(): Promise<void> {
		templateStages = [];
		if (!templateId) return;
		templateLoading = true;
		try {
			const stages = await fetchTemplateStages(templateId);
			templateStages = [...stages].sort((a, b) => (a.order || 0) - (b.order || 0));
		} catch {
			templateStages = [];
		} finally {
			templateLoading = false;
		}
	}

	/** Parse ISO (YYYY-MM-DD) em Date UTC — espelha `parseIsoDate` legado. */
	function parseIsoDate(iso: string): Date | null {
		if (!iso) return null;
		const parts = iso.split('-').map(Number);
		if (parts.length !== 3 || parts.some(Number.isNaN)) return null;
		return new Date(Date.UTC(parts[0], parts[1] - 1, parts[2]));
	}

	function addDaysUtc(date: Date, days: number): Date {
		const copy = new Date(date.getTime());
		copy.setUTCDate(copy.getUTCDate() + days);
		return copy;
	}

	function formatBrDate(date: Date): string {
		const d = String(date.getUTCDate()).padStart(2, '0');
		const m = String(date.getUTCMonth() + 1).padStart(2, '0');
		const y = date.getUTCFullYear();
		return `${d}/${m}/${y}`;
	}

	/** Preview das etapas com datas/duração calculadas no client (read-only). */
	interface PreviewStage {
		name: string;
		rangeText: string;
		duration: number;
	}

	const previewStages = $derived.by<PreviewStage[]>(() => {
		if (!templateStages.length) return [];
		const start = parseIsoDate(startDate);
		let cursor = start ? new Date(start.getTime()) : null;
		return templateStages.map((etapa) => {
			const duration = Math.max(1, Number.parseInt(String(etapa.duration), 10) || 1);
			let rangeText = `${duration}d`;
			if (cursor) {
				const stageStart = new Date(cursor.getTime());
				const stageEnd = addDaysUtc(stageStart, duration - 1);
				rangeText = `${formatBrDate(stageStart)} → ${formatBrDate(stageEnd)} · ${duration}d`;
				cursor = addDaysUtc(stageEnd, 1);
			}
			return { name: etapa.name, rangeText, duration };
		});
	});

	const previewTotalDuration = $derived(
		previewStages.reduce((sum, s) => sum + s.duration, 0)
	);
	const previewStart = $derived.by(() => {
		const start = parseIsoDate(startDate);
		return start ? formatBrDate(start) : null;
	});
	const previewEnd = $derived.by(() => {
		const start = parseIsoDate(startDate);
		if (!start || !templateStages.length) return null;
		let cursor = new Date(start.getTime());
		let lastEnd = cursor;
		for (const etapa of templateStages) {
			const duration = Math.max(1, Number.parseInt(String(etapa.duration), 10) || 1);
			lastEnd = addDaysUtc(cursor, duration - 1);
			cursor = addDaysUtc(lastEnd, 1);
		}
		return formatBrDate(lastEnd);
	});

	// --- Status das seções (pills) -----------------------------------------

	type SectionStatus = 'incompleto' | 'progresso' | 'completo';

	// Erro só na seção Principal (título/órgão) e só após tentar salvar inválido.
	const step1HasError = $derived(triedSubmit && (!titulo.trim() || !orgaoId.trim()));

	// "Preenchido" (status completo): heurística leve por seção.
	function sectionFilled(index: number): boolean {
		if (index === 0) return titulo.trim().length > 0 && orgaoId.trim().length > 0;
		if (index === 1) return Boolean(deliveryType || specialProject);
		if (index === 2)
			return Boolean(objetivoId || resultadoId || selectedIndicadores.length || abepValue);
		if (index === 3)
			return Boolean(
				seiProcess || githubLink || documentationLink || productLink || observacao.trim()
			);
		return Boolean(templateId || startDate);
	}

	function sectionStatus(index: number): SectionStatus {
		if (index === 0) {
			const hasTitulo = titulo.trim().length > 0;
			const hasArea = orgaoId.trim().length > 0;
			if (hasTitulo && hasArea) return 'completo';
			if (hasTitulo || hasArea) return 'progresso';
			return 'incompleto';
		}
		// Seções opcionais: vazio => incompleto; algum campo => completo.
		return sectionFilled(index) ? 'completo' : 'incompleto';
	}

	function pillLabel(s: SectionStatus, errored: boolean): string {
		if (errored) return 'Revisar';
		return s === 'completo' ? 'Completo' : s === 'progresso' ? 'Em progresso' : 'Pendente';
	}
	function pillClass(s: SectionStatus, errored: boolean): string {
		// Pills da referência são TEXTO PURO (sem ícone, sem chip no estado neutro).
		const base =
			'inline-flex flex-shrink-0 items-center rounded-full px-2.5 py-1 text-2xs font-semibold uppercase tracking-wide';
		if (errored) return `${base} text-danger bg-danger/15`;
		if (s === 'completo') return `${base} text-success bg-success/15`;
		if (s === 'progresso') return `${base} text-warning bg-warning/15`;
		// "Pendente"/Incomplete: só texto cinza, sem background (espelha o mockup).
		return `${base} text-text-muted`;
	}

	// --- Submit ------------------------------------------------------------

	// Wrapper do submit: se inválido, abre a seção Principal e foca o campo faltante.
	async function trySubmit(): Promise<void> {
		if (!canSubmit) {
			triedSubmit = true;
			openSection('principal');
			await tick();
			const target = !titulo.trim()
				? titleInputEl
				: (document.getElementById('cp-orgao-id') as HTMLElement | null);
			target?.scrollIntoView({ block: 'center', behavior: 'smooth' });
			target?.focus();
			return;
		}
		await submit();
	}

	// Esc fecha; Ctrl/Cmd+Enter salva de qualquer seção.
	function onModalKeydown(event: KeyboardEvent): void {
		if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') {
			event.preventDefault();
			void trySubmit();
			return;
		}
		trapFocus(event);
		onBackdropKeydown(event);
	}

	async function submit(): Promise<void> {
		if (!canSubmit) return;
		submitting = true;
		const input: CreateProjectInput = {
			titulo: titulo.trim(),
			orgao_id: orgaoId,
			orgao: orgaoTexto.trim() || undefined,
			prioridade,
			objetivo: objetivoId || undefined,
			resultado: resultadoId || undefined,
			indicadores: selectedIndicadores,
			observacao: observacao.trim() || undefined,
			special_project: specialProject || undefined,
			sei_process: seiProcess.trim() || undefined,
			short_description: shortDescription.trim() || undefined,
			delivery_type: deliveryType || undefined,
			abep_indicator: abepValue || undefined,
			github_link: githubLink.trim() || undefined,
			documentation_link: documentationLink.trim() || undefined,
			product_link: productLink.trim() || undefined,
			etapas: templateStages.map((s) => ({
				descricao: s.name,
				duration: Math.max(1, Number.parseInt(String(s.duration), 10) || 1)
			})),
			start_date: startDate || undefined,
			template_id: templateId ? Number(templateId) : undefined
		};
		try {
			const result = await createProject(input);
			onCreated(result);
		} catch (err) {
			if (err instanceof ApiClientError) {
				if (err.code === 'unauthenticated') return; // já redirecionou
				// 403 forbidden -> danger; 422 validation -> warning (paridade).
				const tone = err.code === 'forbidden' ? 'danger' : 'warning';
				flash.show(err.message, err.status >= 500 ? 'danger' : tone);
			} else {
				flash.danger('Ocorreu um erro ao adicionar o projeto.');
			}
		} finally {
			submitting = false;
		}
	}

	function onBackdropKeydown(event: KeyboardEvent): void {
		if (event.key === 'Escape' && !submitting) {
			event.preventDefault();
			requestClose();
		}
	}

	// Fecha o modal restaurando o foco ao elemento que o abriu (APG dialog).
	function requestClose(): void {
		const opener = openerEl;
		onClose();
		void tick().then(() => opener?.focus?.());
	}

	onDestroy(clearRevealTimers);

	/** Focáveis dentro do dialog, em ordem de tabulação. */
	function focusableElements(): HTMLElement[] {
		if (!dialogEl) return [];
		const nodes = dialogEl.querySelectorAll<HTMLElement>(
			'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
		);
		// Ignora os que estão em painéis colapsados (inert) ou ocultos.
		return Array.from(nodes).filter(
			(el) => !el.closest('[inert]') && el.offsetParent !== null
		);
	}

	// Focus trap: Tab/Shift+Tab fazem wrap entre o primeiro e o último focável,
	// contendo o foco físico do teclado dentro do dialog (aria-modal sozinho só
	// informa o leitor de tela, não contém o foco).
	function trapFocus(event: KeyboardEvent): void {
		if (event.key !== 'Tab') return;
		const focusables = focusableElements();
		if (focusables.length === 0) return;
		const first = focusables[0];
		const last = focusables[focusables.length - 1];
		const active = document.activeElement as HTMLElement | null;
		if (event.shiftKey) {
			if (active === first || !dialogEl?.contains(active)) {
				event.preventDefault();
				last.focus();
			}
		} else if (active === last) {
			event.preventDefault();
			first.focus();
		}
	}
</script>

{#if open}
	<div
		class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
		role="presentation"
		onclick={() => !submitting && requestClose()}
	>
		<div
			bind:this={dialogEl}
			role="dialog"
			aria-modal="true"
			aria-labelledby="criar-projeto-title"
			class="flex max-h-[calc(100dvh-5rem)] w-full max-w-2xl flex-col overflow-hidden rounded-xl border border-border-subtle bg-surface shadow-lg"
			onclick={(e) => e.stopPropagation()}
			onkeydown={onModalKeydown}
			tabindex="-1"
			transition:fly={{ y: 16, duration: reduceMotion ? 0 : 220 }}
		>
			<!-- HEADER fixo: ícone circular + título/subtítulo + fechar -->
			<header
				class="flex flex-shrink-0 items-center gap-4 border-b border-border-subtle px-6 py-5"
			>
				<span
					class="flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-full border border-border-subtle bg-surface text-text-secondary"
				>
					<i class="fas fa-diagram-project" aria-hidden="true"></i>
				</span>
				<div class="min-w-0 flex-1">
					<h2
						id="criar-projeto-title"
						class="font-heading text-lg font-semibold text-text-primary"
					>
						Criar Novo Projeto
					</h2>
					<p class="text-sm text-text-secondary">Preencha as seções para criar seu projeto.</p>
				</div>
				<button
					type="button"
					onclick={requestClose}
					disabled={submitting}
					aria-label="Fechar"
					class="rounded-md p-2 text-text-secondary transition-colors duration-fast hover:bg-surface-muted disabled:opacity-60 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
				>
					<i class="fas fa-xmark" aria-hidden="true"></i>
				</button>
			</header>

			<form
				onsubmit={(e) => {
					e.preventDefault();
					void trySubmit();
				}}
				class="flex min-h-0 flex-1 flex-col"
			>
				<!-- LISTA de seções: única região que rola -->
				<div class="flex-1 overflow-y-auto">
					{#each SECTIONS as section, i (section.id)}
						{@const expanded = isOpen(section.id)}
						{@const status = sectionStatus(i)}
						{@const errored = i === 0 && step1HasError}
						<section class="border-b border-border-subtle last:border-b-0">
							<!-- HEADER da seção. A área de toque é o <button> de expandir, que
							     cobre a linha inteira (absolute inset-0). O ícone (i) é um BOTÃO
							     próprio, irmão do toggle (não filho — botão aninhado é HTML
							     inválido), com aria-label próprio e foco por teclado: a dica fica
							     acessível sem mouse e sem inflar o nome acessível do toggle. -->
							<h3 id={`cp-panel-${section.id}-h`} class="relative">
								<button
									type="button"
									onclick={() => toggleSection(section.id)}
									aria-expanded={expanded}
									aria-controls={`cp-panel-${section.id}`}
									class="absolute inset-0 z-0 w-full transition-colors duration-fast hover:bg-surface-muted/50 focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary-500"
								>
									<span class="sr-only">{section.title}</span>
								</button>
								<!-- Conteúdo visível por cima do botão; pointer-events-none para que
								     o clique caia no toggle, exceto no botão (i). -->
								<div class="pointer-events-none relative z-10 flex items-center gap-4 px-6 py-4">
									<span
										class="flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-full border border-border-subtle bg-surface text-text-secondary"
									>
										<i class={`fas ${section.icon}`} aria-hidden="true"></i>
									</span>
									<span class="min-w-0 flex-1">
										<span class="flex items-center gap-1.5">
											<span class="font-heading text-base font-semibold text-text-primary"
												>{section.title}</span
											>
											<button
												type="button"
												aria-label={`Sobre "${section.title}": ${section.tooltip}`}
												title={section.tooltip}
												class="pointer-events-auto inline-flex items-center justify-center rounded-full text-sm text-text-muted transition-colors duration-fast hover:text-text-secondary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
											>
												<i class="fas fa-circle-info" aria-hidden="true"></i>
											</button>
										</span>
										<span class="block truncate text-sm text-text-secondary"
											>{section.description}</span
										>
									</span>
									<span class={pillClass(status, errored)}>{pillLabel(status, errored)}</span>
									<span
										class={`cp-chevron-circle flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full transition-all duration-base ${expanded ? 'bg-text-primary text-surface' : 'bg-surface-muted text-text-secondary'}`}
									>
										<i
											class={`cp-chevron-icon fas fa-chevron-down text-xs transition-transform duration-base ${expanded ? 'rotate-180' : ''}`}
											aria-hidden="true"
										></i>
									</span>
								</div>
							</h3>

							<!-- PANEL colapsável (task-collapse: grid-rows 1fr↔0fr) -->
							<div
								id={`cp-panel-${section.id}`}
								role="region"
								aria-labelledby={`cp-panel-${section.id}-h`}
								class="task-collapse px-6"
								data-collapsed={!expanded}
								inert={!expanded}
								aria-hidden={!expanded}
							>
								<!-- overflow-visible só quando objetivos está EXPANDIDA: libera o
								     dropdown ABEP (top-full) do overflow:hidden imposto pela regra
								     global `.task-collapse > *`. Gate por `expanded` evita vazar
								     conteúdo durante a animação de colapso (grid-rows → 0fr). -->
								<div class={section.id === 'objetivos' && expanded ? 'overflow-visible' : ''}>
									<!-- CARTÃO de formulário interno -->
									<div
										class="mb-4 rounded-lg border border-border-subtle bg-surface px-2 py-1"
									>
										{#if section.id === 'principal'}
											<!-- Título -->
											<div
												class="grid grid-cols-1 items-center gap-2 rounded-md px-3 py-2.5 transition-colors duration-fast hover:bg-surface-muted/60 focus-within:bg-surface-muted/60 not-last:border-b not-last:border-border-subtle/60 sm:grid-cols-[minmax(0,40%)_1fr] sm:gap-3"
											>
												<label
													for="cp-titulo"
													class="flex items-center gap-2 text-sm font-medium text-text-primary"
												>
													<i
														class="fas fa-tag w-4 text-center text-text-secondary"
														aria-hidden="true"
													></i>
													Título do Projeto <span class="text-danger">*</span>
												</label>
												<input
													id="cp-titulo"
													bind:this={titleInputEl}
													bind:value={titulo}
													type="text"
													required
													placeholder="Digite o título do projeto"
													class="w-full rounded-md border border-transparent bg-transparent px-2 py-1.5 text-sm text-text-primary placeholder:text-text-muted focus:border-border-subtle focus:bg-surface focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
												/>
											</div>
											<!-- Área Responsável -->
											<div
												class="grid grid-cols-1 items-center gap-2 rounded-md px-3 py-2.5 transition-colors duration-fast hover:bg-surface-muted/60 focus-within:bg-surface-muted/60 not-last:border-b not-last:border-border-subtle/60 sm:grid-cols-[minmax(0,40%)_1fr] sm:gap-3"
											>
												<label
													for="cp-orgao-id"
													class="flex items-center gap-2 text-sm font-medium text-text-primary"
												>
													<i
														class="fas fa-users w-4 text-center text-text-secondary"
														aria-hidden="true"
													></i>
													Área Responsável <span class="text-danger">*</span>
												</label>
												{#if orgaoOptions.length === 0}
													<select
														id="cp-orgao-id"
														disabled
														class="w-full rounded-md border border-transparent bg-transparent px-2 py-1.5 text-sm text-text-muted"
													>
														<option value="">Nenhum órgão atribuído</option>
													</select>
												{:else if orgaoOptions.length === 1}
													<input
														type="text"
														value={orgaoOptions[0].label}
														disabled
														class="w-full rounded-md border border-transparent bg-transparent px-2 py-1.5 text-sm text-text-muted"
													/>
												{:else}
													<select
														id="cp-orgao-id"
														bind:value={orgaoId}
														required
														class="w-full rounded-md border border-transparent bg-transparent px-2 py-1.5 text-sm text-text-primary focus:border-border-subtle focus:bg-surface focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
													>
														<option value="" disabled>Selecione um órgão</option>
														{#each orgaoOptions as opt (opt.value)}
															<option value={opt.value}>{opt.label}</option>
														{/each}
													</select>
												{/if}
											</div>
											<!-- Prioridade -->
											<div
												class="grid grid-cols-1 items-center gap-2 rounded-md px-3 py-2.5 transition-colors duration-fast hover:bg-surface-muted/60 focus-within:bg-surface-muted/60 not-last:border-b not-last:border-border-subtle/60 sm:grid-cols-[minmax(0,40%)_1fr] sm:gap-3"
											>
												<label
													for="cp-prioridade"
													class="flex items-center gap-2 text-sm font-medium text-text-primary"
												>
													<i
														class="fas fa-flag w-4 text-center text-text-secondary"
														aria-hidden="true"
													></i>
													Prioridade
												</label>
												<select
													id="cp-prioridade"
													bind:value={prioridade}
													class="w-full rounded-md border border-transparent bg-transparent px-2 py-1.5 text-sm text-text-primary focus:border-border-subtle focus:bg-surface focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
												>
													{#each PRIORITIES as p (p.value)}
														<option value={p.value}>{p.label}</option>
													{/each}
												</select>
											</div>
											<!-- Órgão (texto) -->
											<div
												class="grid grid-cols-1 items-center gap-2 rounded-md px-3 py-2.5 transition-colors duration-fast hover:bg-surface-muted/60 focus-within:bg-surface-muted/60 not-last:border-b not-last:border-border-subtle/60 sm:grid-cols-[minmax(0,40%)_1fr] sm:gap-3"
											>
												<label
													for="cp-orgao-texto"
													class="flex items-center gap-2 text-sm font-medium text-text-primary"
												>
													<i
														class="fas fa-building w-4 text-center text-text-secondary"
														aria-hidden="true"
													></i>
													Órgão
												</label>
												<input
													id="cp-orgao-texto"
													bind:value={orgaoTexto}
													type="text"
													placeholder="Digite o órgão responsável"
													class="w-full rounded-md border border-transparent bg-transparent px-2 py-1.5 text-sm text-text-primary placeholder:text-text-muted focus:border-border-subtle focus:bg-surface focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
												/>
											</div>
											<!-- Descrição -->
											<div
												class="grid grid-cols-1 items-start gap-2 rounded-md px-3 py-2.5 transition-colors duration-fast hover:bg-surface-muted/60 focus-within:bg-surface-muted/60 sm:grid-cols-[minmax(0,40%)_1fr] sm:gap-3"
											>
												<label
													for="cp-short-desc"
													class="flex items-center gap-2 pt-1.5 text-sm font-medium text-text-primary"
												>
													<i
														class="fas fa-align-left w-4 text-center text-text-secondary"
														aria-hidden="true"
													></i>
													Descrição
												</label>
												<textarea
													id="cp-short-desc"
													bind:value={shortDescription}
													rows="2"
													placeholder="Breve descrição do projeto"
													class="w-full rounded-md border border-transparent bg-transparent px-2 py-1.5 text-sm text-text-primary placeholder:text-text-muted focus:border-border-subtle focus:bg-surface focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
												></textarea>
											</div>
										{:else if section.id === 'classificacao'}
											<!-- Tipo de Entrega -->
											<div
												class="grid grid-cols-1 items-center gap-2 rounded-md px-3 py-2.5 transition-colors duration-fast hover:bg-surface-muted/60 focus-within:bg-surface-muted/60 not-last:border-b not-last:border-border-subtle/60 sm:grid-cols-[minmax(0,40%)_1fr] sm:gap-3"
											>
												<label
													for="cp-delivery"
													class="flex items-center gap-2 text-sm font-medium text-text-primary"
												>
													<i
														class="fas fa-truck w-4 text-center text-text-secondary"
														aria-hidden="true"
													></i>
													Tipo de Entrega
												</label>
												<select
													id="cp-delivery"
													bind:value={deliveryType}
													class="w-full rounded-md border border-transparent bg-transparent px-2 py-1.5 text-sm text-text-primary focus:border-border-subtle focus:bg-surface focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
												>
													<option value="">Selecione o tipo</option>
													{#each deliveryTypes as dt (dt)}
														<option value={dt}>{dt}</option>
													{/each}
												</select>
											</div>
											<!-- Projetos Especiais -->
											<div
												class="grid grid-cols-1 items-center gap-2 rounded-md px-3 py-2.5 transition-colors duration-fast hover:bg-surface-muted/60 focus-within:bg-surface-muted/60 sm:grid-cols-[minmax(0,40%)_1fr] sm:gap-3"
											>
												<label
													for="cp-special"
													class="flex items-center gap-2 text-sm font-medium text-text-primary"
												>
													<i
														class="fas fa-star w-4 text-center text-text-secondary"
														aria-hidden="true"
													></i>
													Projetos Especiais
												</label>
												<select
													id="cp-special"
													bind:value={specialProject}
													class="w-full rounded-md border border-transparent bg-transparent px-2 py-1.5 text-sm text-text-primary focus:border-border-subtle focus:bg-surface focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
												>
													<option value="">Nenhum</option>
													{#each specialOptions as sp (sp)}
														<option value={sp}>{sp}</option>
													{/each}
												</select>
											</div>
										{:else if section.id === 'objetivos'}
											<!-- Objetivo EEGD -->
											<div
												class="grid grid-cols-1 items-center gap-2 rounded-md px-3 py-2.5 transition-colors duration-fast hover:bg-surface-muted/60 focus-within:bg-surface-muted/60 not-last:border-b not-last:border-border-subtle/60 sm:grid-cols-[minmax(0,40%)_1fr] sm:gap-3"
											>
												<label
													for="cp-objetivo"
													class="flex items-center gap-2 text-sm font-medium text-text-primary"
												>
													<i
														class="fas fa-bullseye w-4 text-center text-text-secondary"
														aria-hidden="true"
													></i>
													Objetivo EEGD
												</label>
												<select
													id="cp-objetivo"
													bind:value={objetivoId}
													onchange={onObjetivoChange}
													class="w-full rounded-md border border-transparent bg-transparent px-2 py-1.5 text-sm text-text-primary focus:border-border-subtle focus:bg-surface focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
												>
													<option value="">Selecione um objetivo</option>
													{#each objetivos as obj (obj.id)}
														<option value={String(obj.id)}>{obj.descricao}</option>
													{/each}
												</select>
											</div>
											<!-- Resultado Esperado EEGD -->
											<div
												class="grid grid-cols-1 items-center gap-2 rounded-md px-3 py-2.5 transition-colors duration-fast hover:bg-surface-muted/60 focus-within:bg-surface-muted/60 not-last:border-b not-last:border-border-subtle/60 sm:grid-cols-[minmax(0,40%)_1fr] sm:gap-3"
											>
												<label
													for="cp-resultado"
													class="flex items-center gap-2 text-sm font-medium text-text-primary"
												>
													<i
														class="fas fa-chart-line w-4 text-center text-text-secondary"
														aria-hidden="true"
													></i>
													Resultado Esperado EEGD
												</label>
												<select
													id="cp-resultado"
													bind:value={resultadoId}
													onchange={onResultadoChange}
													disabled={!objetivoId || resultadosLoading}
													class="w-full rounded-md border border-transparent bg-transparent px-2 py-1.5 text-sm text-text-primary disabled:opacity-60 focus:border-border-subtle focus:bg-surface focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
												>
													<option value="">
														{resultadosLoading
															? 'Carregando resultados...'
															: 'Selecione um resultado esperado'}
													</option>
													{#each resultados as r (r.id)}
														<option value={String(r.id)}>{r.descricao}</option>
													{/each}
												</select>
											</div>
											<!-- Indicadores EEGD (linha full-width) -->
											<div
												class="flex flex-col gap-2 rounded-md px-3 py-2.5 not-last:border-b not-last:border-border-subtle/60"
											>
												<span
													class="flex items-center gap-2 text-sm font-medium text-text-primary"
												>
													<i
														class="fas fa-list-check w-4 text-center text-text-secondary"
														aria-hidden="true"
													></i>
													Indicadores EEGD
												</span>
												{#if indicadoresLoading}
													<p role="status" aria-live="polite" class="text-sm text-text-secondary">
														<i class="fas fa-spinner fa-spin mr-1"></i>Carregando indicadores...
													</p>
												{:else if !resultadoId}
													<p class="text-sm text-text-muted">
														<i class="fas fa-info-circle mr-1"></i>Selecione um resultado esperado
														para ver os indicadores disponíveis
													</p>
												{:else if indicadores.length === 0}
													<p class="text-sm text-text-muted">
														<i class="fas fa-exclamation-circle mr-1"></i>Nenhum indicador
														disponível para este resultado esperado
													</p>
												{:else}
													<div class="flex flex-col gap-2">
														{#each indicadores as ind (ind.id)}
															<!-- div (não label) p/ que SÓ o clique na caixa marque; a11y via aria-label. -->
															<div
																class="cp-indicador-row flex items-center gap-2 text-sm text-text-primary transition-[opacity,transform] duration-300 {revealedIndicadores.has(
																	ind.id
																)
																	? 'translate-y-0 opacity-100'
																	: 'translate-y-1 opacity-0'}"
															>
																<input
																	type="checkbox"
																	aria-label={ind.descricao}
																	checked={selectedIndicadores.includes(ind.id)}
																	onchange={() => toggleIndicador(ind.id)}
																	class="h-4 w-4 shrink-0 rounded border-border-subtle text-primary-600 focus:ring-primary-500"
																/>
																<span>{ind.descricao}</span>
															</div>
														{/each}
													</div>
												{/if}
											</div>
											<!-- Indicadores ABEP (combobox, linha full-width) -->
											<div class="relative flex flex-col gap-2 rounded-md px-3 py-2.5">
												<label
													for="cp-abep"
													class="flex items-center gap-2 text-sm font-medium text-text-primary"
												>
													<i
														class="fas fa-chart-simple w-4 text-center text-text-secondary"
														aria-hidden="true"
													></i>
													Indicadores ABEP
												</label>
												<input
													id="cp-abep"
													type="text"
													autocomplete="off"
													role="combobox"
													aria-expanded={abepOpen}
													aria-controls="cp-abep-listbox"
													aria-autocomplete="list"
													aria-activedescendant={abepActiveIndex >= 0
														? `cp-abep-option-${abepActiveIndex}`
														: undefined}
													bind:value={abepLabel}
													oninput={onAbepInput}
													onfocus={openAbep}
													onkeydown={onAbepKeydown}
													onblur={() => setTimeout(closeAbep, 120)}
													placeholder="Busque por número ou título do indicador ABEP"
													class="h-10 rounded-md border border-border-subtle bg-surface px-3 text-sm leading-tight text-text-primary placeholder:text-text-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
												/>
												{#if abepOpen}
													<ul
														id="cp-abep-listbox"
														role="listbox"
														aria-label="Indicadores ABEP"
														class="absolute left-3 right-3 top-full z-10 mt-1 max-h-64 overflow-auto rounded-md border border-border-subtle bg-surface py-1 shadow-md"
													>
														{#if abepVisible.length === 0}
															<li class="px-3 py-2 text-sm text-text-muted">
																Nenhum indicador encontrado
															</li>
														{:else}
															{#each abepVisible as option, index (option.value)}
																<li class="contents">
																	<button
																		type="button"
																		id={`cp-abep-option-${index}`}
																		role="option"
																		aria-selected={option.value === abepValue}
																		class="block w-full cursor-pointer px-3 py-2 text-left text-sm text-text-primary hover:bg-surface-muted {index ===
																		abepActiveIndex
																			? 'bg-surface-muted'
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
										{:else if section.id === 'links'}
											<!-- Processo SEI -->
											<div
												class="grid grid-cols-1 items-center gap-2 rounded-md px-3 py-2.5 transition-colors duration-fast hover:bg-surface-muted/60 focus-within:bg-surface-muted/60 not-last:border-b not-last:border-border-subtle/60 sm:grid-cols-[minmax(0,40%)_1fr] sm:gap-3"
											>
												<label
													for="cp-sei"
													class="flex items-center gap-2 text-sm font-medium text-text-primary"
												>
													<i
														class="fas fa-file-lines w-4 text-center text-text-secondary"
														aria-hidden="true"
													></i>
													Processo SEI-RJ
												</label>
												<input
													id="cp-sei"
													value={seiProcess}
													oninput={onSeiInput}
													type="text"
													maxlength="25"
													placeholder="SEI-000000/000000/0000"
													class="w-full rounded-md border border-transparent bg-transparent px-2 py-1.5 text-sm text-text-primary placeholder:text-text-muted focus:border-border-subtle focus:bg-surface focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
												/>
											</div>
											<!-- Link Github -->
											<div
												class="grid grid-cols-1 items-center gap-2 rounded-md px-3 py-2.5 transition-colors duration-fast hover:bg-surface-muted/60 focus-within:bg-surface-muted/60 not-last:border-b not-last:border-border-subtle/60 sm:grid-cols-[minmax(0,40%)_1fr] sm:gap-3"
											>
												<label
													for="cp-github"
													class="flex items-center gap-2 text-sm font-medium text-text-primary"
												>
													<i
														class="fas fa-code-branch w-4 text-center text-text-secondary"
														aria-hidden="true"
													></i>
													Link Github
												</label>
												<input
													id="cp-github"
													bind:value={githubLink}
													type="text"
													placeholder="https://github.com/..."
													class="w-full rounded-md border border-transparent bg-transparent px-2 py-1.5 text-sm text-text-primary placeholder:text-text-muted focus:border-border-subtle focus:bg-surface focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
												/>
											</div>
											<!-- Link Documentação -->
											<div
												class="grid grid-cols-1 items-center gap-2 rounded-md px-3 py-2.5 transition-colors duration-fast hover:bg-surface-muted/60 focus-within:bg-surface-muted/60 not-last:border-b not-last:border-border-subtle/60 sm:grid-cols-[minmax(0,40%)_1fr] sm:gap-3"
											>
												<label
													for="cp-doc"
													class="flex items-center gap-2 text-sm font-medium text-text-primary"
												>
													<i
														class="fas fa-book w-4 text-center text-text-secondary"
														aria-hidden="true"
													></i>
													Link Documentação
												</label>
												<input
													id="cp-doc"
													bind:value={documentationLink}
													type="text"
													placeholder="https://..."
													class="w-full rounded-md border border-transparent bg-transparent px-2 py-1.5 text-sm text-text-primary placeholder:text-text-muted focus:border-border-subtle focus:bg-surface focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
												/>
											</div>
											<!-- Link para o Produto -->
											<div
												class="grid grid-cols-1 items-center gap-2 rounded-md px-3 py-2.5 transition-colors duration-fast hover:bg-surface-muted/60 focus-within:bg-surface-muted/60 not-last:border-b not-last:border-border-subtle/60 sm:grid-cols-[minmax(0,40%)_1fr] sm:gap-3"
											>
												<label
													for="cp-product"
													class="flex items-center gap-2 text-sm font-medium text-text-primary"
												>
													<i
														class="fas fa-box w-4 text-center text-text-secondary"
														aria-hidden="true"
													></i>
													Link para o Produto
												</label>
												<input
													id="cp-product"
													bind:value={productLink}
													type="text"
													placeholder="https://..."
													class="w-full rounded-md border border-transparent bg-transparent px-2 py-1.5 text-sm text-text-primary placeholder:text-text-muted focus:border-border-subtle focus:bg-surface focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
												/>
											</div>
											<!-- Observações -->
											<div
												class="grid grid-cols-1 items-start gap-2 rounded-md px-3 py-2.5 transition-colors duration-fast hover:bg-surface-muted/60 focus-within:bg-surface-muted/60 sm:grid-cols-[minmax(0,40%)_1fr] sm:gap-3"
											>
												<label
													for="cp-obs"
													class="flex items-center gap-2 pt-1.5 text-sm font-medium text-text-primary"
												>
													<i
														class="fas fa-comment w-4 text-center text-text-secondary"
														aria-hidden="true"
													></i>
													Observações / Descrição Detalhada
												</label>
												<textarea
													id="cp-obs"
													bind:value={observacao}
													rows="3"
													placeholder="Digite observações detalhadas sobre o projeto..."
													class="w-full rounded-md border border-transparent bg-transparent px-2 py-1.5 text-sm text-text-primary placeholder:text-text-muted focus:border-border-subtle focus:bg-surface focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
												></textarea>
											</div>
										{:else}
											<!-- Importar Modelo -->
											<div
												class="grid grid-cols-1 items-center gap-2 rounded-md px-3 py-2.5 transition-colors duration-fast hover:bg-surface-muted/60 focus-within:bg-surface-muted/60 not-last:border-b not-last:border-border-subtle/60 sm:grid-cols-[minmax(0,40%)_1fr] sm:gap-3"
											>
												<label
													for="cp-template"
													class="flex items-center gap-2 text-sm font-medium text-text-primary"
												>
													<i
														class="fas fa-layer-group w-4 text-center text-text-secondary"
														aria-hidden="true"
													></i>
													Importar Modelo
												</label>
												<select
													id="cp-template"
													bind:value={templateId}
													onchange={onTemplateChange}
													class="w-full rounded-md border border-transparent bg-transparent px-2 py-1.5 text-sm text-text-primary focus:border-border-subtle focus:bg-surface focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
												>
													<option value="">Não importar / Limpar etapas</option>
													{#each templates as tpl (tpl.id)}
														<option value={String(tpl.id)}>{tpl.name}</option>
													{/each}
												</select>
											</div>
											<!-- Data de Início -->
											<div
												class="grid grid-cols-1 items-center gap-2 rounded-md px-3 py-2.5 transition-colors duration-fast hover:bg-surface-muted/60 focus-within:bg-surface-muted/60 not-last:border-b not-last:border-border-subtle/60 sm:grid-cols-[minmax(0,40%)_1fr] sm:gap-3"
											>
												<label
													for="cp-start"
													class="flex items-center gap-2 text-sm font-medium text-text-primary"
												>
													<i
														class="fas fa-calendar w-4 text-center text-text-secondary"
														aria-hidden="true"
													></i>
													Data de Início (opcional)
												</label>
												<input
													id="cp-start"
													bind:value={startDate}
													type="date"
													title="Sem data, o preview mostra só a duração de cada etapa."
													class="w-full rounded-md border border-transparent bg-transparent px-2 py-1.5 text-sm text-text-primary focus:border-border-subtle focus:bg-surface focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
												/>
											</div>
											<!-- Preview de etapas (read-only, linha full-width) -->
											<div class="px-3 py-2.5">
												{#if templateLoading}
													<p role="status" aria-live="polite" class="text-sm text-text-secondary">
														<i class="fas fa-spinner fa-spin mr-1"></i>Carregando etapas…
													</p>
												{:else if previewStages.length > 0}
													<div
														class="flex flex-col gap-2 rounded-md border border-border-subtle bg-surface-muted/30 p-3"
													>
														<div
															class="flex items-center justify-between text-xs font-semibold uppercase tracking-wide text-text-muted"
														>
															<span>Etapas importadas</span>
															<span
																>{previewStages.length} etapas · total {previewTotalDuration} dias</span
															>
														</div>
														<ol class="flex flex-col gap-1.5">
															{#each previewStages as stage, index (index)}
																<li class="flex items-start gap-2 text-sm text-text-primary">
																	<span
																		class="inline-flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full bg-primary-100 text-xs font-medium text-primary-700"
																	>
																		{index + 1}
																	</span>
																	<span class="flex flex-col">
																		<span>{stage.name}</span>
																		<span class="text-xs text-text-muted">{stage.rangeText}</span>
																	</span>
																</li>
															{/each}
														</ol>
														{#if previewStart && previewEnd}
															<p class="text-xs text-text-muted">
																Previsão de término com início em <strong>{previewStart}</strong> →
																<strong>{previewEnd}</strong>.
															</p>
														{/if}
													</div>
												{:else}
													<p class="text-sm text-text-muted">
														<i class="fas fa-layer-group mr-1"></i>Selecione um modelo para
														visualizar as etapas importadas.
													</p>
												{/if}
											</div>
										{/if}
									</div>
								</div>
							</div>
						</section>
					{/each}
				</div>

				<!-- RODAPÉ fixo: Cancelar (ghost) | Criar projeto (primário) -->
				<footer
					class="flex flex-shrink-0 items-center gap-3 border-t border-border-subtle px-6 py-4"
				>
					<button
						type="button"
						onclick={requestClose}
						disabled={submitting}
						class="flex-1 rounded-lg border border-border-subtle bg-surface px-4 py-2.5 text-sm font-semibold text-text-secondary transition-colors duration-fast hover:bg-surface-muted disabled:opacity-60 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
					>
						Cancelar
					</button>
					<button
						type="submit"
						disabled={!canSubmit}
						class="flex flex-1 items-center justify-center gap-2 rounded-lg border border-primary-700 bg-topnav-gradient px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition-all duration-fast hover:-translate-y-0.5 hover:shadow-md active:translate-y-0 disabled:translate-y-0 disabled:cursor-not-allowed disabled:border-border-subtle disabled:bg-surface-muted disabled:bg-none disabled:text-text-muted disabled:shadow-none focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
					>
						{#if submitting}
							<i class="fas fa-spinner fa-spin" aria-hidden="true"></i>Criando…
						{:else}
							<i class="fas fa-plus-circle" aria-hidden="true"></i>Criar projeto
						{/if}
					</button>
				</footer>
			</form>
		</div>
	</div>
{/if}

<style>
	/* Neutraliza a transição do chevron quando o usuário prefere menos movimento;
	   o .task-collapse já é tratado em app.css, e o fly é condicionado via reduceMotion. */
	@media (prefers-reduced-motion: reduce) {
		:global(.cp-chevron-icon),
		:global(.cp-chevron-circle) {
			transition: none !important;
		}
		/* Reveal escalonado dos indicadores: o JS já revela tudo de uma vez quando
		   reduceMotion é true; aqui zeramos a transição como rede de segurança. */
		:global(.cp-indicador-row) {
			transition: none !important;
		}
	}
</style>
