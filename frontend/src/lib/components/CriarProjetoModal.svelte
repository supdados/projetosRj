<script lang="ts">
	/**
	 * Modal "Criar novo projeto" — assistente em 5 fases internas. Nada é criado
	 * até uma ação explícita de criação; o `POST /api/projetos` é ÚNICO e leva
	 * tudo que estiver preenchido:
	 *   1. `assist1` — título (card compacto, sem header; "Cancelar"/"Continuar");
	 *   2. `assist2` — prioridade + área; "Próximo" só avança à ficha;
	 *   3. `ficha` — revisão: sidebar (título, prioridade, área, % do cadastro) e
	 *      lista das 4 seções. "Concluir" cria o projeto (mínimo) → sucesso;
	 *      "Continuar preenchendo" abre o wizard SEM criar nem festejar;
	 *   4. `form` — wizard 4-seções (Detalhes · Objetivos e Indicadores ·
	 *      Links · Etapas); "Criar projeto" faz o POST com tudo,
	 *      dispara confete e vai para a tela de sucesso;
	 *   5. `success` — "Projeto criado!" com "Criar outro projeto" (reseta) e
	 *      "Ver o projeto" (`onCreated(result)` → a página navega).
	 *
	 * Mantém (paridade funcional):
	 *   - combobox ABEP filtrável (LEGADO, oculto via SHOW_ABEP);
	 *   - cascata objetivo→resultado→indicadores via `/api/resultados`/
	 *     `indicadores` legados, com revelação escalonada (índice·100ms) e LIMITE
	 *     de 4 indicadores (flash 'Você pode selecionar no máximo 4 indicadores');
	 *   - MÚLTIPLOS processos SEI via `SeiProcessField`;
	 *   - import de modelo com preview read-only e cálculo de datas no client;
	 *   - Esc: fecha nas fases assist (com confirmação de descarte se sujo);
	 *     no form volta à ficha; na ficha fecha · Ctrl/Cmd+Enter dispara a ação
	 *     primária da fase (Continuar / Próximo / Continuar preenchendo / Salvar).
	 *
	 * `onCreated` permanece nas props (as páginas passam), sem uso interno no
	 * fluxo atual; `onCreatedDismissed(result)` dispara ao fechar após criar.
	 */
	import { tick, untrack } from 'svelte';
	import { fade, fly, slide } from 'svelte/transition';
	import { cubicOut } from 'svelte/easing';
	import { focusTrap } from '$lib/actions/focusTrap';
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
	import { triggerTaskFinalizeConfetti } from '$lib/celebration/confettiEpic';
	import '$lib/celebration/confetti.css';
	import SeiProcessField from '$lib/components/SeiProcessField.svelte';
	import LinkFieldRow from '$lib/components/LinkFieldRow.svelte';
	import ObjetivoPicker from '$lib/components/ObjetivoPicker.svelte';
	import OrgaoTreeSelect from '$lib/components/OrgaoTreeSelect.svelte';
	import SelectMenu from '$lib/components/SelectMenu.svelte';
	import DatePickerPanel from '$lib/components/DatePickerPanel.svelte';
	import type { OrgaoSelectOption } from '$lib/types/orgaoTreeSelect';
	import type { SelectMenuOption } from '$lib/types/selectMenu';
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
		/** Modal dispensado (✕/Esc/backdrop) após criar sem "Ver o projeto". */
		onCreatedDismissed?: (result: CreateProjectResult) => void;
	}

	let { open, options, onClose, onCreated, onCreatedDismissed }: Props = $props();

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

	// --- Fases do assistente -------------------------------------------------
	let phase = $state<'assist1' | 'assist2' | 'ficha' | 'form' | 'success'>('assist1');

	// --- Campos definidos na criação (assist1/assist2) -----------------------
	let titulo = $state('');
	let orgaoId = $state('');
	let prioridade = $state('baixa');

	// --- Seção "Detalhes" ----------------------------------------------------
	let shortDescription = $state('');
	let orgaoTexto = $state('');
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
	// Denominador do contador: o teto de 4 só vale quando há mais de 4 disponíveis.
	const maxIndicadoresSelecionaveis = $derived(
		Math.min(MAX_INDICADORES, indicadores.length)
	);

	// --- ABEP combobox -----------------------------------------------------
	// LEGADO (jun/2026): o campo sai da UI mas o código fica intacto para
	// reativação futura — basta alternar SHOW_ABEP para `true`. O backend segue
	// aceitando `abep_indicator` no payload de criação.
	const SHOW_ABEP = false;
	let abepValue = $state(''); // value canônico (hidden)
	let abepLabel = $state(''); // texto exibido
	let abepOpen = $state(false);
	let abepActiveIndex = $state(-1);
	let lastSelectedAbepLabel = $state('');

	// --- Links e Observação ------------------------------------------------
	// Números SEI canônicos (com "SEI-") já adicionados via SeiProcessField.
	let seiList = $state<string[]>([]);
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
	let startDateAnchorEl = $state<HTMLElement | null>(null);
	let startDatePickerOpen = $state(false);

	// --- Estado geral ------------------------------------------------------
	let submitting = $state(false);
	let catalogsLoaded = $state(false);
	let titleInputEl = $state<HTMLInputElement | null>(null);
	let dialogEl = $state<HTMLDivElement | null>(null);
	let continuarFichaBtn = $state<HTMLButtonElement | null>(null);
	let verProjetoBtn = $state<HTMLButtonElement | null>(null);
	// Descrição do passo 2 cresce com o conteúdo (underline sempre colado ao texto).
	let assistDescEl = $state<HTMLTextAreaElement | null>(null);
	let triedAssist1 = $state(false);
	let triedAssist2 = $state(false);
	// Projeto criado nesta abertura: habilita as fases ficha/form.
	let createdResult = $state<CreateProjectResult | null>(null);
	// Garante onCreatedDismissed em qualquer caminho de fechamento pós-criação.
	let lastCreatedThisOpen: CreateProjectResult | null = null;

	// --- Wizard: uma seção visível por vez ----------------------------------
	const NAV_SECTIONS = [
		'Informações essenciais',
		'Objetivos e indicadores',
		'Detalhes',
		'Links',
		'Etapas'
	];
	const FICHA_SECTIONS = [
		{ title: 'Objetivos e indicadores', subtitle: 'Resultados esperados e medição' },
		{ title: 'Detalhes', subtitle: 'Órgão, tipo de entrega e observações' },
		{ title: 'Links', subtitle: 'Processos SEI e documentos' },
		{ title: 'Etapas', subtitle: 'Marcos e prazos' }
	];
	let activeSection = $state(0);

	function goToSection(index: number): void {
		startDatePickerOpen = false;
		activeSection = Math.min(NAV_SECTIONS.length - 1, Math.max(0, index));
	}

	function onNavKeydown(event: KeyboardEvent): void {
		const delta =
			event.key === 'ArrowDown' || event.key === 'ArrowRight'
				? 1
				: event.key === 'ArrowUp' || event.key === 'ArrowLeft'
					? -1
					: 0;
		if (!delta) return;
		event.preventDefault();
		goToSection(activeSection + delta);
		void tick().then(() => document.getElementById(`cp-nav-${activeSection}`)?.focus());
	}

	const orgaoOptions = $derived<OrgaoOption[]>(options?.orgaos_options ?? []);
	// Adapta a lista plana ao shape numérico do OrgaoTreeSelect.
	const orgaoTreeOptions = $derived<OrgaoSelectOption[]>(
		orgaoOptions.map((o) => ({
			value: Number(o.value),
			label: o.label,
			sigla: o.sigla,
			nome: o.nome,
			pai_id: o.pai_id,
			is_inactive: o.is_inactive
		}))
	);
	const abepOptions = $derived<AbepIndicadorOption[]>(
		options?.abep_indicadores_options ?? []
	);
	const deliveryTypes = $derived(options?.delivery_types_options ?? DELIVERY_TYPES);

	// --- Opções dos SelectMenu (derivadas das constantes/catálogos acima) --
	const deliveryTypeMenuOptions = $derived<SelectMenuOption[]>(
		deliveryTypes.map((dt) => ({ value: dt, label: dt }))
	);
	const templateMenuOptions = $derived<SelectMenuOption[]>(
		templates.map((t) => ({ value: String(t.id), label: t.name }))
	);

	const assistTituloError = $derived(triedAssist1 && !titulo.trim());
	const assistOrgaoError = $derived(triedAssist2 && !orgaoId.trim());

	const orgaoSelecionadoLabel = $derived.by(() => {
		if (orgaoOptions.length === 1) return orgaoOptions[0].label;
		return orgaoOptions.find((o) => o.value === orgaoId)?.label ?? '';
	});
	const createdTitulo = $derived(createdResult?.project?.titulo ?? titulo.trim());
	const prioridadeLabel = $derived(
		PRIORITIES.find((p) => p.value === prioridade)?.label ?? 'Baixa'
	);

	// Critérios de seção "preenchida" (✓ na navegação/ficha + % do cadastro).
	// Índice 0 = "Informações essenciais" (título/prioridade/área), já feito ao
	// chegar aqui; os demais são as 4 seções do detalhamento.
	const sectionDone = $derived<boolean[]>([
		titulo.trim().length > 0 && orgaoId.trim().length > 0,
		objetivoId !== '' && resultadoId !== '',
		[orgaoTexto, deliveryType, specialProject, observacao].some((v) => v.trim().length > 0),
		seiList.length > 0 ||
			[githubLink, documentationLink, productLink].some((v) => v.trim().length > 0),
		templateId !== ''
	]);
	// % do cadastro: 20% pela criação + 20% por seção de detalhamento (1..4).
	const detailDoneCount = $derived(sectionDone.slice(1).filter(Boolean).length);
	const cadastroPct = $derived(Math.min(100, 20 + detailDoneCount * 20));

	const headerTitle = $derived(
		phase === 'form'
			? 'Preencher cadastro'
			: phase === 'ficha'
				? 'Projeto criado'
				: 'Criar novo projeto'
	);
	const dialogWidthClass = $derived(
		phase === 'form' ? 'max-w-[870px]' : phase === 'ficha' ? 'max-w-[680px]' : 'max-w-[560px]'
	);
	// Todas as fases ancoram o topo no mesmo ponto (não centralizam), para o card
	// não subir/descer conforme a altura do conteúdo.
	const outerAlignClass = 'items-start justify-center pt-[14vh]';
	// Passos compactos (assist) e sucesso deixam o dropdown de área escapar do
	// card (overflow visível) em vez de ser cortado.
	const isCompactPhase = $derived(phase === 'assist1' || phase === 'assist2');
	const dialogOverflowClass = $derived(
		isCompactPhase || phase === 'success' ? 'overflow-visible' : 'overflow-hidden'
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
	// untrack: resetForm lê `options` e loadCatalogs lê `catalogsLoaded` de forma
	// síncrona — sem untrack o efeito re-rodaria quando o fetch de catálogos
	// resolvesse (ou `options` mudasse), apagando o que o usuário digitou.
	// O efeito deve depender SÓ de `open`.
	$effect(() => {
		if (!open) return;
		untrack(() => {
			lastCreatedThisOpen = null;
			resetForm();
			void loadCatalogs();
		});
		void tick().then(() => titleInputEl?.focus());
	});

	// Pré-seleção tardia de órgão único: `options` pode resolver DEPOIS do open
	// (ex.: /projetos?new=1 abre o modal antes do fetch da lista), quando o
	// resetForm já rodou com a lista vazia. Sem isto a UI de órgão único fica
	// read-only com orgaoId vazio — beco sem saída no "Próximo"/"Concluir".
	$effect(() => {
		if (open && orgaoOptions.length === 1 && orgaoId === '') {
			orgaoId = orgaoOptions[0].value;
		}
	});

	function resizeTextarea(el: HTMLTextAreaElement | null): void {
		if (!el) return;
		el.style.height = 'auto';
		el.style.height = `${el.scrollHeight}px`;
	}

	function autoGrowDesc(event: Event): void {
		resizeTextarea(event.currentTarget as HTMLTextAreaElement);
	}

	// Reajusta a altura ao (re)montar no passo 2 — ex.: voltar do passo 1 com
	// descrição já digitada — sem depender de um novo input.
	$effect(() => {
		if (phase === 'assist2' && assistDescEl) {
			void shortDescription;
			void tick().then(() => resizeTextarea(assistDescEl));
		}
	});

	function resetForm(): void {
		phase = 'assist1';
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
		seiList = [];
		githubLink = '';
		documentationLink = '';
		productLink = '';
		observacao = '';
		templateId = '';
		templateStages = [];
		startDate = '';
		startDatePickerOpen = false;
		resultadosLoading = false;
		indicadoresLoading = false;
		templateLoading = false;
		activeSection = 0;
		triedAssist1 = false;
		triedAssist2 = false;
		createdResult = null;
		confirmDiscardOpen = false;
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
		resultadoId = '';
		resultados = [];
		indicadores = [];
		selectedIndicadores = [];
		revealedIndicadores = new Set();
		// Fetch de indicadores pendente ficou órfão (resultadoId mudou): o finally
		// guardado dele NÃO vai limpar o loading — limpamos aqui.
		indicadoresLoading = false;
		if (!objetivoId) {
			resultadosLoading = false; // idem para fetch de resultados pendente
			return;
		}
		// Guarda de corrida: respostas fora de ordem (ou após resetForm) são
		// descartadas — só a resposta do objetivo ATUAL pode popular o estado.
		const requested = objetivoId;
		resultadosLoading = true;
		try {
			const data = await fetchResultados(requested);
			if (requested !== objetivoId) return;
			resultados = data;
		} catch {
			if (requested === objetivoId) resultados = [];
		} finally {
			if (requested === objetivoId) resultadosLoading = false;
		}
	}

	async function onResultadoChange(): Promise<void> {
		indicadores = [];
		selectedIndicadores = [];
		revealedIndicadores = new Set();
		if (!resultadoId) {
			// Limpou a seleção com fetch em voo: o finally guardado não limpa.
			indicadoresLoading = false;
			return;
		}
		// Guarda de corrida: idem onObjetivoChange — resposta de um resultado
		// antigo nunca pode popular os indicadores do resultado atual.
		const requested = resultadoId;
		indicadoresLoading = true;
		try {
			const data = await fetchIndicadores(requested);
			if (requested !== resultadoId) return;
			indicadores = data;
			// Animação escalonada (animate-in): revela cada item a cada 100ms.
			revealedIndicadores = new Set();
			data.forEach((ind, index) => {
				setTimeout(() => {
					if (requested !== resultadoId) return; // lista trocou no meio
					revealedIndicadores = new Set([...revealedIndicadores, ind.id]);
				}, index * 100);
			});
		} catch {
			if (requested === resultadoId) indicadores = [];
		} finally {
			if (requested === resultadoId) indicadoresLoading = false;
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

	// Números SEI: o SeiProcessField (compartilhado com o Detalhe) gerencia
	// máscara/adição/remoção; aqui a lista é estado local até o "Salvar".
	// Snapshot da lista ao abrir a linha SEI: o onSave grava direto em seiList,
	// então "cancelar" restaura e "confirmar" só decide a celebração.
	let seiListSnapshot: string[] = [];

	function onSeiRowOpen(): void {
		seiListSnapshot = [...seiList];
	}

	function onSeiRowConfirm(): boolean {
		return seiList.length > 0 && JSON.stringify(seiList) !== JSON.stringify(seiListSnapshot);
	}

	function onSeiRowCancel(): void {
		seiList = [...seiListSnapshot];
	}

	const seiRowPreview = $derived(seiList.join(' · '));
	const linkRowsFilled = $derived(
		(seiList.length > 0 ? 1 : 0) +
			[githubLink, documentationLink, productLink].filter((v) => v.trim().length > 0).length
	);
	const linkRowsSummary = $derived(
		linkRowsFilled === 0 ? '' : `${linkRowsFilled} de 4 itens preenchidos.`
	);

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
			// Consome o Esc só com o dropdown aberto (padrão APG combobox):
			// 1º Esc fecha o popup, 2º Esc borbulha para o modal.
			if (abepOpen) {
				event.preventDefault();
				event.stopPropagation();
				closeAbep();
			}
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
		if (!templateId) {
			// Limpou a seleção com fetch em voo: o finally guardado não limpa.
			templateLoading = false;
			return;
		}
		// Guarda de corrida: sem ela, um fetch lento sobrevivia ao resetForm e
		// repopulava templateStages com templateId já vazio — o "Salvar" enviava
		// etapas de um modelo nunca escolhido nesta sessão.
		const requested = templateId;
		templateLoading = true;
		try {
			const stages = await fetchTemplateStages(requested);
			if (requested !== templateId) return;
			templateStages = [...stages].sort((a, b) => (a.order || 0) - (b.order || 0));
		} catch {
			if (requested === templateId) templateStages = [];
		} finally {
			if (requested === templateId) templateLoading = false;
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

	/** dd/mm/aaaa para exibição no trigger; startDate continua ISO. */
	function startDateLabel(iso: string): string {
		if (!iso) return '';
		const [y, m, d] = iso.split('-');
		return `${d}/${m}/${y}`;
	}

	const MONTHS_PT_ABBR = [
		'jan', 'fev', 'mar', 'abr', 'mai', 'jun',
		'jul', 'ago', 'set', 'out', 'nov', 'dez'
	];

	function formatBrShort(date: Date): string {
		return `${String(date.getUTCDate()).padStart(2, '0')} ${MONTHS_PT_ABBR[date.getUTCMonth()]}`;
	}

	/** Preview das etapas com datas/duração calculadas no client (read-only). */
	interface PreviewStage {
		name: string;
		/** "início DD mmm" cumulativo; vazio sem data de início. */
		startText: string;
		duration: number;
	}

	const previewStages = $derived.by<PreviewStage[]>(() => {
		if (!templateStages.length) return [];
		const start = parseIsoDate(startDate);
		let cursor = start ? new Date(start.getTime()) : null;
		return templateStages.map((etapa) => {
			const duration = Math.max(1, Number.parseInt(String(etapa.duration), 10) || 1);
			let startText = '';
			if (cursor) {
				const stageStart = new Date(cursor.getTime());
				const stageEnd = addDaysUtc(stageStart, duration - 1);
				startText = `início ${formatBrShort(stageStart)}`;
				cursor = addDaysUtc(stageEnd, 1);
			}
			return { name: etapa.name, startText, duration };
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

	// --- Confirmação de descarte (só nas fases assist*) ----------------------

	let confirmDiscardOpen = $state(false);
	let discardCancelBtn = $state<HTMLButtonElement | null>(null);
	// Foco a restaurar quando a confirmação fecha em "Continuar editando"
	// (o botão dela desmonta; sem isso o foco cairia no body, fora do trap).
	let focusedBeforeDiscard: HTMLElement | null = null;

	/** Escolha do usuário que seria perdida ao fechar antes de criar. */
	const formIsDirty = $derived(
		titulo.trim().length > 0 ||
			shortDescription.trim().length > 0 ||
			prioridade !== 'baixa' ||
			// Órgão único é pré-selecionado na abertura; só conta escolha do usuário.
			(orgaoOptions.length > 1 && orgaoId.trim().length > 0)
	);

	/** Fecha avisando a página se houve criação nesta abertura. */
	function closeAndNotify(): void {
		if (lastCreatedThisOpen) onCreatedDismissed?.(lastCreatedThisOpen);
		onClose();
	}

	/** Fecha o modal; com dados preenchidos antes de criar, pede confirmação. */
	function requestClose(): void {
		if (submitting) return;
		// Pós-criação: nada a perder — fecha direto.
		if (createdResult || !formIsDirty) {
			closeAndNotify();
			return;
		}
		focusedBeforeDiscard = document.activeElement as HTMLElement | null;
		confirmDiscardOpen = true;
		void tick().then(() => discardCancelBtn?.focus());
	}

	/** Fecha só a confirmação, devolvendo o foco a quem o tinha no formulário. */
	function closeDiscardConfirm(): void {
		confirmDiscardOpen = false;
		void tick().then(() => {
			if (focusedBeforeDiscard && document.contains(focusedBeforeDiscard)) {
				focusedBeforeDiscard.focus();
			}
		});
	}

	function discardAndClose(): void {
		confirmDiscardOpen = false;
		closeAndNotify();
	}

	// --- Navegação entre fases ----------------------------------------------

	// Trocar de fase desmonta quem tinha o foco; sem re-focar, Esc/focusTrap morrem.
	// offsetParent null = elemento com display:none (ex.: nav desktop no mobile):
	// .focus() seria no-op e o foco cairia no body, fora do trap.
	function focusAfterTick(getEl: () => HTMLElement | null | undefined): void {
		void tick().then(() => {
			const el = getEl();
			const visible = el && el.offsetParent !== null ? el : dialogEl;
			visible?.focus();
		});
	}

	function goToAssist2(): void {
		triedAssist1 = true;
		if (!titulo.trim()) {
			titleInputEl?.focus();
			return;
		}
		phase = 'assist2';
		focusAfterTick(() => assistDescEl);
	}

	function backToAssist1(): void {
		phase = 'assist1';
		focusAfterTick(() => titleInputEl);
	}

	function enterForm(index: number): void {
		phase = 'form';
		activeSection = index;
		focusAfterTick(() => document.getElementById(`cp-nav-${activeSection}`));
	}

	function backToFicha(): void {
		phase = 'ficha';
		startDatePickerOpen = false;
		focusAfterTick(() => continuarFichaBtn);
	}

	function flashApiError(err: unknown, fallback: string): void {
		if (err instanceof ApiClientError) {
			if (err.code === 'unauthenticated') return; // já redirecionou
			// 403 forbidden -> danger; 422 validation -> warning (paridade).
			const tone = err.code === 'forbidden' ? 'danger' : 'warning';
			flash.show(err.message, err.status >= 500 ? 'danger' : tone);
			return;
		}
		flash.danger(fallback);
	}

	// --- Ficha (revisão) → criação (única) -----------------------------------

	// "Próximo" só avança à ficha de revisão — nada é criado ainda.
	function goToFicha(): void {
		triedAssist2 = true;
		if (!titulo.trim()) {
			triedAssist1 = true;
			backToAssist1();
			return;
		}
		if (!orgaoId.trim()) return; // erro inline via assistOrgaoError
		phase = 'ficha';
		focusAfterTick(() => continuarFichaBtn);
	}

	// "Continuar preenchendo": abre o wizard SEM criar nem festejar — a criação
	// (com tudo que for preenchido) só acontece no botão "Criar projeto".
	function continuarPreenchendo(): void {
		// Cai direto em "Detalhes" (1); "Informações essenciais" (0) fica atrás
		// para revisão, já que o usuário acabou de preenchê-las.
		enterForm(1);
	}

	/**
	 * Criação ÚNICA do projeto com tudo que estiver preenchido (ficha mínima ou
	 * wizard completo). Dispara confete e vai para a tela de sucesso. Chamada por
	 * "Concluir" (ficha) e "Criar projeto" (form).
	 */
	async function createProjectNow(): Promise<void> {
		if (submitting || createdResult) return;
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
			sei_processes: seiList.length ? seiList : undefined,
			short_description: shortDescription.trim() || undefined,
			delivery_type: deliveryType || undefined,
			abep_indicator: abepValue || undefined,
			github_link: githubLink.trim() || undefined,
			documentation_link: documentationLink.trim() || undefined,
			product_link: productLink.trim() || undefined,
			// Defesa extra: etapas só valem com modelo escolhido.
			etapas: (templateId ? templateStages : []).map((s) => ({
				descricao: s.name,
				duration: Math.max(1, Number.parseInt(String(s.duration), 10) || 1)
			})),
			start_date: startDate || undefined,
			template_id: templateId ? Number(templateId) : undefined
		};
		try {
			const result = await createProject(input);
			createdResult = result;
			lastCreatedThisOpen = result;
			// Sem origem o helper usa fallback no canto superior direito; centro da tela.
			triggerTaskFinalizeConfetti({
				x: window.innerWidth / 2,
				y: window.innerHeight / 2
			});
			phase = 'success';
			void tick().then(() => verProjetoBtn?.focus());
		} catch (err) {
			flashApiError(err, 'Ocorreu um erro ao adicionar o projeto.');
		} finally {
			submitting = false;
		}
	}

	/** "Criar outro projeto" na tela de sucesso: limpa e volta ao passo 1. */
	function startAnotherProject(): void {
		resetForm();
		void tick().then(() => titleInputEl?.focus());
	}

	/** Ação primária da fase atual (botão principal e Ctrl/Cmd+Enter). */
	function phasePrimaryAction(): void {
		if (phase === 'assist1') {
			goToAssist2();
			return;
		}
		if (phase === 'assist2') {
			goToFicha();
			return;
		}
		if (phase === 'ficha') {
			continuarPreenchendo();
			return;
		}
		if (phase === 'success') {
			if (createdResult) onCreated(createdResult);
			return;
		}
		void createProjectNow();
	}

	// Ctrl/Cmd+Enter dispara a ação primária de qualquer lugar do modal.
	function onModalKeydown(event: KeyboardEvent): void {
		if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') {
			event.preventDefault();
			event.stopPropagation(); // evita repetição ao borbulhar para o backdrop
			phasePrimaryAction();
			return;
		}
		onBackdropKeydown(event);
	}

	function onBackdropKeydown(event: KeyboardEvent): void {
		// Esc já consumido por um popover filho (SelectMenu/OrgaoTreeSelect/SEI):
		// não empilhar a ação de fase no mesmo keystroke.
		if (event.defaultPrevented) return;
		if (event.key === 'Escape' && !submitting) {
			event.preventDefault();
			// stopPropagation: dialog e backdrop compartilham este handler; sem
			// consumir aqui, o mesmo Esc seria tratado DUAS vezes.
			event.stopPropagation();
			// Primeiro Esc fecha só a confirmação de descarte; o próximo, o modal.
			if (confirmDiscardOpen) {
				closeDiscardConfirm();
				return;
			}
			// No form o Esc volta à ficha; na ficha, requestClose decide entre
			// fechar direto (já criado) ou confirmar descarte (ainda não criado).
			if (phase === 'form') {
				backToFicha();
				return;
			}
			requestClose();
		}
	}

	// --- Classes utilitárias (campos com visual unificado) -------------------
	const labelClass = 'text-xs font-medium uppercase tracking-wide text-text-muted';
	const microLabelClass =
		'text-[10px] font-bold uppercase tracking-[.16em] text-text-muted';
	const fieldClass =
		'h-10 w-full rounded-md border border-border-subtle bg-surface px-3 text-sm leading-tight text-text-primary placeholder:text-text-muted transition-colors duration-fast focus:border-primary-500 focus:outline-none disabled:opacity-60';
	const areaClass =
		'w-full rounded-md border border-border-subtle bg-surface px-3 py-2 text-sm text-text-primary placeholder:text-text-muted transition-colors duration-fast focus:border-primary-500 focus:outline-none';
	const sectionTitleClass = 'font-heading text-base font-semibold text-text-primary';
	const emptyBoxClass =
		'rounded-lg border border-dashed border-border-subtle bg-surface-muted px-4 py-3.5 text-sm text-text-muted';
	const btnPrimaryClass =
		'inline-flex h-9 items-center justify-center gap-2 rounded-md bg-primary-600 px-4 text-sm font-semibold text-primary-fg shadow-sm transition-colors duration-fast hover:bg-primary-700 hover:shadow-md focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-1 disabled:cursor-not-allowed disabled:opacity-60';
	const btnSecondaryClass =
		'inline-flex h-9 items-center gap-1.5 rounded-md border border-border-subtle bg-surface px-3.5 text-sm font-medium text-text-secondary transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-60';
</script>

{#snippet spinner()}
	<svg class="h-3.5 w-3.5 animate-spin" viewBox="0 0 24 24" fill="none" aria-hidden="true">
		<circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="3" class="opacity-25" />
		<path
			d="M22 12a10 10 0 0 0-10-10"
			stroke="currentColor"
			stroke-width="3"
			stroke-linecap="round"
		/>
	</svg>
{/snippet}

{#snippet stepBars(step: number)}
	<div class="flex items-center gap-1.5" aria-hidden="true">
		<div class="h-[5px] w-9 rounded-[3px] bg-primary-600"></div>
		<div class="h-[5px] w-9 rounded-[3px] {step >= 2 ? 'bg-primary-600' : 'bg-border-subtle'}"></div>
	</div>
{/snippet}

{#snippet navItems(orientation: 'vertical' | 'horizontal')}
	{#each NAV_SECTIONS as label, index (index)}
		{@const isActive = activeSection === index}
		{@const isDone = sectionDone[index]}
		<button
			type="button"
			id={orientation === 'vertical' ? `cp-nav-${index}` : undefined}
			onclick={() => goToSection(index)}
			onkeydown={orientation === 'vertical' ? onNavKeydown : undefined}
			aria-current={isActive ? 'step' : undefined}
			class="flex shrink-0 items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-sm transition-colors duration-fast focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary-500 {isActive
				? 'bg-surface font-semibold text-primary-600 shadow-sm'
				: 'text-text-secondary hover:bg-surface/60'}"
		>
			<span
				class="grid h-6 w-6 flex-none place-items-center rounded-md text-xs font-semibold {isActive
					? 'bg-primary-600 text-primary-fg'
					: isDone
						? 'bg-[color-mix(in_srgb,var(--ds-color-primary-600)_10%,transparent)] text-primary-600'
						: 'bg-border-subtle/60 text-text-muted'}"
			>
				{#if isDone && !isActive}
					<svg viewBox="0 0 20 20" class="h-3 w-3" fill="none" stroke="currentColor" stroke-width="2.2" aria-hidden="true">
						<path d="m4.5 10.5 3.5 3.5 7.5-8" stroke-linecap="round" stroke-linejoin="round" />
					</svg>
				{:else}
					{index + 1}
				{/if}
			</span>
			<span class="min-w-0 {orientation === 'vertical' ? 'leading-snug' : 'whitespace-nowrap'}">{label}</span>
		</button>
	{/each}
{/snippet}

{#if open}
	<div
		class="fixed inset-0 z-50 flex {outerAlignClass} bg-black/40 p-4 backdrop-blur-[1.5px]"
		role="presentation"
		onclick={requestClose}
		onkeydown={onModalKeydown}
		transition:fade={{ duration: 200 }}
	>
		<div
			role="dialog"
			aria-modal="true"
			aria-labelledby={phase === 'assist1' ? 'cp-assist1-title' : 'criar-projeto-title'}
			bind:this={dialogEl}
			class="relative flex max-h-[92vh] w-full flex-col {dialogOverflowClass} rounded-xl border border-border-subtle bg-surface shadow-lg transition-[max-width] duration-base {dialogWidthClass}"
			style="--cp-grid-w: calc(min(870px, 100vw - 2rem) - 206px - 4rem);"
			onclick={(e) => e.stopPropagation()}
			onkeydown={onModalKeydown}
			tabindex="-1"
			use:focusTrap
			transition:fly={{ y: 18, duration: 320, easing: cubicOut }}
		>
			<!-- Cabeçalho fixo só na fase de preenchimento; as demais têm o título
			     no próprio corpo. inert: descarte aberto tira o fundo do Tab. -->
			{#if phase === 'form'}
				<header
					inert={confirmDiscardOpen}
					class="flex h-14 flex-shrink-0 items-center justify-between gap-4 border-b border-border-subtle px-6"
				>
					<h2
						id="criar-projeto-title"
						class="truncate font-heading text-base font-semibold text-text-primary"
					>
						{headerTitle}
					</h2>
					<button
						type="button"
						onclick={requestClose}
						disabled={submitting}
						aria-label="Fechar"
						class="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-md text-text-muted transition-colors duration-fast hover:bg-surface-muted hover:text-text-primary disabled:opacity-60 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
					>
						<svg viewBox="0 0 20 20" class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true">
							<path d="m5 5 10 10M15 5 5 15" stroke-linecap="round" />
						</svg>
					</button>
				</header>
			{/if}

			{#if phase === 'assist1'}
				<form
					inert={confirmDiscardOpen}
					onsubmit={(e) => {
						e.preventDefault();
						goToAssist2();
					}}
					class="flex animate-panel-in flex-col gap-6 overflow-visible p-8"
				>
					{@render stepBars(1)}
					<h3 id="cp-assist1-title" class="font-heading text-2xl font-semibold text-text-primary">
						Como vai se chamar o projeto?
					</h3>
					<div class="flex flex-col gap-1.5">
						<input
							id="cp-titulo"
							bind:this={titleInputEl}
							bind:value={titulo}
							type="text"
							aria-labelledby="cp-assist1-title"
							aria-invalid={assistTituloError}
							placeholder="Digite o nome do projeto…"
							class="w-full border-0 border-b-2 bg-transparent px-0 py-2 text-lg text-text-primary placeholder:text-text-muted focus:outline-none {assistTituloError
								? 'border-danger'
								: 'border-primary-600'}"
						/>
						{#if assistTituloError}
							<p class="text-xs text-danger" transition:slide={{ duration: 160, easing: cubicOut }}>
								Informe o título do projeto.
							</p>
						{/if}
					</div>
					<div class="mt-2 flex items-center justify-between">
						<span class="text-xs text-text-muted">Passo 1 de 2</span>
						<div class="flex items-center gap-2">
							<button type="button" onclick={requestClose} class={btnSecondaryClass}>
								Cancelar
							</button>
							<button type="submit" class={btnPrimaryClass}>
								Próximo <span aria-hidden="true">→</span>
							</button>
						</div>
					</div>
				</form>
			{:else if phase === 'assist2'}
				<form
					inert={confirmDiscardOpen}
					onsubmit={(e) => {
						e.preventDefault();
						goToFicha();
					}}
					class="flex animate-panel-in flex-col gap-6 overflow-visible p-8"
				>
					{@render stepBars(2)}
					<h3 class="font-heading text-2xl font-semibold text-text-primary">Descrição breve</h3>
					<div class="flex flex-col gap-2">
						<textarea
							id="cp-assist-desc"
							aria-label="Descrição breve"
							bind:this={assistDescEl}
							bind:value={shortDescription}
							rows="1"
							placeholder="Breve descrição do projeto"
							oninput={autoGrowDesc}
							class="w-full resize-none overflow-hidden border-0 border-b-2 border-border-subtle bg-transparent px-0 py-1.5 text-lg leading-snug text-text-primary placeholder:text-text-muted transition-colors duration-fast focus:border-primary-600 focus:outline-none"
						></textarea>
					</div>
					<div class="flex flex-col gap-6 sm:flex-row">
						<div class="flex flex-1 flex-col gap-1.5">
							<span class={labelClass} id="cp-prioridade-label">Prioridade</span>
							<div
								id="cp-prioridade"
								role="group"
								aria-labelledby="cp-prioridade-label"
								class="flex h-10 flex-wrap items-center gap-1.5"
							>
								{#each PRIORITIES as p (p.value)}
									{@const selected = prioridade === p.value}
									<button
										type="button"
										aria-pressed={selected}
										onclick={() => (prioridade = p.value)}
										style={selected
											? `background: var(--ds-color-priority-${p.value}); border-color: var(--ds-color-priority-${p.value});`
											: ''}
										class="inline-flex h-9 flex-1 items-center justify-center whitespace-nowrap rounded-lg border px-2 text-xs transition-colors duration-fast focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 {selected
											? 'font-semibold text-primary-fg'
											: 'border-border-subtle bg-surface font-medium text-text-secondary hover:bg-surface-muted'}"
									>
										{p.label}
									</button>
								{/each}
							</div>
						</div>
						<div class="flex w-full flex-col gap-1.5 sm:w-[220px]">
							<span class={labelClass} id="cp-orgao-label">Área responsável</span>
							{#if orgaoOptions.length === 0}
								<div
									class="flex items-center justify-between gap-2 rounded-md border border-border-subtle bg-surface-muted px-3 py-2 text-sm text-text-muted opacity-60"
								>
									<span class="truncate">Nenhum órgão atribuído</span>
								</div>
							{:else if orgaoOptions.length === 1}
								<div
									class="flex items-center justify-between gap-2 rounded-md border border-border-subtle bg-surface-muted px-3 py-2 text-sm text-text-primary"
								>
									<span class="truncate">{orgaoOptions[0].label}</span>
									<svg viewBox="0 0 20 20" class="h-3.5 w-3.5 flex-none text-text-muted" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true">
										<rect x="4.5" y="9" width="11" height="7.5" rx="1.5" />
										<path d="M7 9V6.5a3 3 0 0 1 6 0V9" />
									</svg>
								</div>
								<p class="text-[11px] text-text-muted">Definida pelo seu perfil</p>
							{:else}
								<OrgaoTreeSelect
									id="cp-orgao-id"
									options={orgaoTreeOptions}
									value={orgaoId ? Number(orgaoId) : null}
									onSelect={(v) => (orgaoId = v == null ? '' : String(v))}
									placeholder="Selecionar área"
								/>
							{/if}
							{#if assistOrgaoError}
								<p class="text-xs text-danger" transition:slide={{ duration: 160, easing: cubicOut }}>
									{orgaoOptions.length === 0
										? 'Nenhum órgão atribuído ao seu perfil.'
										: 'Selecione a área responsável.'}
								</p>
							{/if}
						</div>
					</div>
					<div class="mt-2 flex items-center justify-between gap-2">
						<span class="text-xs text-text-muted">Passo 2 de 2</span>
						<div class="flex items-center gap-2">
							<button type="button" onclick={backToAssist1} class={btnSecondaryClass}>
								Voltar
							</button>
							<button type="submit" class={btnPrimaryClass}>
								Próximo <span aria-hidden="true">→</span>
							</button>
						</div>
					</div>
				</form>
			{:else if phase === 'ficha'}
				<div
					inert={confirmDiscardOpen}
					class="flex max-h-[calc(92vh-3.5rem)] min-h-[420px] animate-panel-in overflow-hidden"
				>
					<aside
						class="hidden w-[236px] flex-none flex-col gap-6 border-r border-border-subtle bg-surface-muted p-7 sm:flex"
					>
						<p class={microLabelClass}>Título do projeto</p>
						<p class="text-lg font-extrabold leading-snug text-text-primary">{createdTitulo}</p>
						<div class="flex flex-col gap-1">
							<p class={microLabelClass}>Prioridade</p>
							<p class="text-sm font-bold" style="color: var(--ds-color-priority-{prioridade});">
								{prioridadeLabel}
							</p>
						</div>
						<div class="flex flex-col gap-1">
							<p class={microLabelClass}>Área responsável</p>
							<p class="text-sm font-semibold text-text-primary">{orgaoSelecionadoLabel}</p>
						</div>
						{#if shortDescription.trim()}
							<div class="flex flex-col gap-1">
								<p class={microLabelClass}>Descrição breve</p>
								<p class="text-sm leading-snug text-text-secondary">{shortDescription.trim()}</p>
							</div>
						{/if}
						<div class="mt-auto flex flex-col gap-1.5">
							<div class="flex items-center justify-between text-xs">
								<span class="text-text-muted">Cadastro</span>
								<span class="font-semibold tabular-nums text-text-primary">{cadastroPct}%</span>
							</div>
							<div class="h-[3px] overflow-hidden rounded-full bg-border-subtle">
								<div
									class="h-full rounded-full bg-primary-600 transition-[width] duration-base"
									style="width: {cadastroPct}%"
								></div>
							</div>
						</div>
					</aside>
					<div class="flex min-w-0 flex-1 flex-col overflow-y-auto p-7">
						<p class={microLabelClass}>Próximas seções</p>
						<div class="mt-2 flex flex-col">
							{#each FICHA_SECTIONS as section, index (index)}
								<button
									type="button"
									onclick={() => enterForm(index + 1)}
									class="flex w-full items-center gap-3.5 py-3.5 text-left transition-colors duration-fast hover:bg-surface-muted/60 focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary-500 {index <
									FICHA_SECTIONS.length - 1
										? 'border-b border-border-subtle/60'
										: ''}"
								>
									{#if sectionDone[index + 1]}
										<span class="w-5 flex-none text-success" aria-label="Seção preenchida">
											<svg viewBox="0 0 20 20" class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="2.2" aria-hidden="true">
												<path d="m4.5 10.5 3.5 3.5 7.5-8" stroke-linecap="round" stroke-linejoin="round" />
											</svg>
										</span>
									{:else}
										<span class="w-5 flex-none text-xs font-semibold tabular-nums text-text-muted">
											{String(index + 1).padStart(2, '0')}
										</span>
									{/if}
									<span class="flex min-w-0 flex-1 flex-col">
										<span class="text-sm font-bold text-text-primary">{section.title}</span>
										<span class="text-xs text-text-muted">{section.subtitle}</span>
									</span>
									<span class="flex-none text-lg leading-none text-text-muted" aria-hidden="true">›</span>
								</button>
							{/each}
						</div>
						<div class="mt-auto flex items-center justify-end gap-4 pt-6">
							<button
								type="button"
								onclick={() => void createProjectNow()}
								disabled={submitting}
								class="inline-flex items-center gap-2 text-sm font-semibold text-text-muted transition-colors duration-fast hover:text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-60"
							>
								{#if submitting}
									{@render spinner()}Criando…
								{:else}
									Concluir
								{/if}
							</button>
							<button
								type="button"
								bind:this={continuarFichaBtn}
								onclick={continuarPreenchendo}
								disabled={submitting}
								class={btnPrimaryClass}
							>
								Continuar preenchendo
							</button>
						</div>
					</div>
				</div>
			{:else if phase === 'form'}
				<form
					inert={confirmDiscardOpen}
					onsubmit={(e) => {
						e.preventDefault();
						void createProjectNow();
					}}
					class="flex h-[560px] max-h-[calc(92vh-3.5rem)] min-h-0 animate-panel-in flex-col"
				>
					<!-- Stepper compacto (mobile): mesma navegação da sidebar -->
					<nav
						aria-label="Seções do formulário"
						class="flex shrink-0 items-center gap-1 overflow-x-auto border-b border-border-subtle bg-surface-muted px-3 py-2 md:hidden"
					>
						{@render navItems('horizontal')}
					</nav>

					<div class="flex min-h-0 flex-1 overflow-hidden">
						<!-- Sidebar de navegação entre seções -->
						<nav
							aria-label="Seções do formulário"
							class="hidden w-[206px] flex-none flex-col gap-0.5 overflow-y-auto border-r border-border-subtle bg-surface-muted p-3.5 md:flex"
						>
							{@render navItems('vertical')}
							<div class="flex-1"></div>
							<div class="mx-0.5 mt-2.5 flex flex-col gap-2 border-t border-border-subtle px-2 pt-3.5">
								<p class="truncate text-sm font-medium text-text-primary">{createdTitulo}</p>
								{#if orgaoSelecionadoLabel}
									<p class="truncate text-xs text-text-secondary">{orgaoSelecionadoLabel}</p>
								{/if}
								<div class="flex items-center justify-between">
									<span class="text-[11px] font-medium leading-none text-text-muted">Cadastro</span>
									<span class="text-[11px] font-semibold leading-none tabular-nums text-text-primary">
										{cadastroPct}%
									</span>
								</div>
								<div class="h-1 overflow-hidden rounded-full bg-border-subtle">
									<div
										class="h-full rounded-full bg-primary-600 transition-[width] duration-base"
										style="width: {cadastroPct}%"
									></div>
								</div>
							</div>
						</nav>

						<!-- Conteúdo da seção ativa -->
						<div class="flex min-w-0 flex-1 flex-col">
							<div class="min-h-0 flex-1 overflow-y-auto overflow-x-clip px-6 py-6 md:px-8">
								{#key activeSection}
									<div class="flex animate-panel-in flex-col gap-5">
										{#if activeSection === 0}
											<h3 class={sectionTitleClass}>Informações essenciais</h3>
											<div class="flex flex-col gap-1.5">
												<label for="cp-form-titulo" class={labelClass}>Título do projeto</label>
												<input
													id="cp-form-titulo"
													bind:value={titulo}
													type="text"
													placeholder="Nome do projeto"
													class={fieldClass}
												/>
											</div>
											<div class="flex flex-col gap-1.5">
												<label for="cp-form-desc" class={labelClass}>Descrição breve</label>
												<textarea
													id="cp-form-desc"
													bind:value={shortDescription}
													rows="3"
													placeholder="Breve descrição do projeto"
													class={areaClass}
												></textarea>
											</div>
											<div class="grid grid-cols-1 gap-x-4 gap-y-5 md:grid-cols-2">
												<div class="flex flex-col gap-1.5">
													<span class={labelClass} id="cp-form-area-label">Área responsável</span>
													{#if orgaoOptions.length <= 1}
														<div
															class="flex items-center justify-between gap-2 rounded-md border border-border-subtle bg-surface-muted px-3 py-2 text-sm {orgaoOptions.length ===
															1
																? 'text-text-primary'
																: 'text-text-muted opacity-60'}"
														>
															<span class="truncate">
																{orgaoSelecionadoLabel || 'Nenhum órgão atribuído'}
															</span>
															{#if orgaoOptions.length === 1}
																<svg viewBox="0 0 20 20" class="h-3.5 w-3.5 flex-none text-text-muted" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true">
																	<rect x="4.5" y="9" width="11" height="7.5" rx="1.5" />
																	<path d="M7 9V6.5a3 3 0 0 1 6 0V9" />
																</svg>
															{/if}
														</div>
													{:else}
														<OrgaoTreeSelect
															id="cp-form-orgao"
															options={orgaoTreeOptions}
															value={orgaoId ? Number(orgaoId) : null}
															onSelect={(v) => (orgaoId = v == null ? '' : String(v))}
															placeholder="Selecionar área"
														/>
													{/if}
												</div>
												<div class="flex flex-col gap-1.5">
													<span class={labelClass} id="cp-form-prioridade-label">Prioridade</span>
													<div
														role="group"
														aria-labelledby="cp-form-prioridade-label"
														class="flex flex-wrap items-center gap-1.5"
													>
														{#each PRIORITIES as p (p.value)}
															{@const selected = prioridade === p.value}
															<button
																type="button"
																aria-pressed={selected}
																onclick={() => (prioridade = p.value)}
																style={selected
																	? `background: var(--ds-color-priority-${p.value}); border-color: var(--ds-color-priority-${p.value});`
																	: ''}
																class="inline-flex h-9 flex-1 items-center justify-center rounded-lg border px-3 text-xs transition-colors duration-fast focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 {selected
																	? 'font-semibold text-primary-fg'
																	: 'border-border-subtle bg-surface font-medium text-text-secondary hover:bg-surface-muted'}"
															>
																{p.label}
															</button>
														{/each}
													</div>
												</div>
											</div>
										{:else if activeSection === 2}
											<h3 class={sectionTitleClass}>Detalhes</h3>
											<div class="grid grid-cols-1 gap-x-4 gap-y-5 md:grid-cols-12">
												<div class="flex flex-col gap-1.5 md:col-span-4">
													<label for="cp-orgao-texto" class={labelClass}>Órgão</label>
													<input
														id="cp-orgao-texto"
														bind:value={orgaoTexto}
														type="text"
														placeholder="Órgão responsável"
														class={fieldClass}
													/>
												</div>
												<div class="flex flex-col gap-1.5 md:col-span-5">
													<label for="cp-delivery" class={labelClass}>Tipo de entrega</label>
													<SelectMenu
														id="cp-delivery"
														options={deliveryTypeMenuOptions}
														value={deliveryType || null}
														onSelect={(v) => (deliveryType = v ?? '')}
														allowAll
														allLabel="Selecione o tipo"
														ariaLabel="Tipo de entrega"
													/>
												</div>
												<div class="flex flex-col gap-1.5 md:col-span-3">
													<span id="cp-special-label" class={labelClass}>Projetos especiais</span>
													<div
														id="cp-special"
														role="group"
														aria-labelledby="cp-special-label"
														class="flex h-10 items-center gap-2"
													>
														{#each SPECIAL_PROJECTS as sp (sp)}
															{@const selected = specialProject === sp}
															<button
																type="button"
																aria-pressed={selected}
																onclick={() => (specialProject = selected ? '' : sp)}
																class="inline-flex h-10 flex-1 items-center justify-center rounded-lg border px-3 text-sm font-semibold transition-colors duration-fast active:scale-[0.97] focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 {selected
																	? 'border-primary-600 bg-primary-600 text-primary-fg'
																	: 'border-border-subtle bg-surface text-text-secondary hover:border-primary-500'}"
															>
																{sp}
															</button>
														{/each}
													</div>
												</div>
											</div>
											<div class="flex flex-col gap-1.5">
												<label for="cp-obs" class={labelClass}>Observações</label>
												<textarea
													id="cp-obs"
													bind:value={observacao}
													rows="3"
													placeholder="Digite observações detalhadas sobre o projeto…"
													class={areaClass}
												></textarea>
											</div>
										{:else if activeSection === 1}
											<h3 class={sectionTitleClass}>Objetivos e indicadores</h3>
											<ObjetivoPicker
												{objetivos}
												{objetivoId}
												{resultados}
												{resultadoId}
												{resultadosLoading}
												{indicadores}
												{indicadoresLoading}
												{selectedIndicadores}
												{revealedIndicadores}
												onObjetivoSelect={(id) => {
													objetivoId = id;
													void onObjetivoChange();
												}}
												onResultadoSelect={(id) => {
													resultadoId = id;
													void onResultadoChange();
												}}
												onToggleIndicador={toggleIndicador}
											/>

											<!-- Indicadores ABEP (combobox) — LEGADO, oculto via SHOW_ABEP.
												 Código mantido para reativação futura. -->
											{#if SHOW_ABEP}
											<div class="relative flex flex-col gap-1.5">
												<label for="cp-abep" class={labelClass}>Indicadores ABEP</label>
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
													class={fieldClass}
												/>
												{#if abepOpen}
													<ul
														id="cp-abep-listbox"
														role="listbox"
														aria-label="Indicadores ABEP"
														transition:fly={{ y: -4, duration: 160, easing: cubicOut }}
														class="absolute left-0 right-0 top-full z-10 mt-1 max-h-64 overflow-auto rounded-md border border-border-subtle bg-surface py-1 shadow-md"
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
																		class="block w-full cursor-pointer px-3 py-2 text-left text-sm text-text-primary transition-colors duration-fast hover:bg-surface-muted {index ===
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
											{/if}
										{:else if activeSection === 3}
											<div class="flex flex-col gap-5">
												<h3 class={sectionTitleClass}>Links</h3>
												<div class="rounded-lg border border-border-subtle">
													<LinkFieldRow
														id="cp-sei"
														label="Processo SEI-RJ"
														first
														startOpen
														filled={seiList.length > 0}
														preview={seiRowPreview}
														onEditorOpen={onSeiRowOpen}
														onEditorConfirm={onSeiRowConfirm}
														onEditorCancel={onSeiRowCancel}
													>
														{#snippet editor()}
															<SeiProcessField
																fieldId="cp-sei"
																processes={seiList}
																onSave={(list) => (seiList = list)}
															/>
														{/snippet}
													</LinkFieldRow>
													<LinkFieldRow
														id="cp-github"
														label="Link GitHub"
														startOpen
														placeholder="https://github.com/..."
														value={githubLink}
														onCommit={(v) => (githubLink = v)}
													/>
													<LinkFieldRow
														id="cp-doc"
														label="Link documentação"
														startOpen
														placeholder="https://..."
														value={documentationLink}
														onCommit={(v) => (documentationLink = v)}
													/>
													<LinkFieldRow
														id="cp-product"
														label="Link para o produto"
														startOpen
														placeholder="https://..."
														last
														value={productLink}
														onCommit={(v) => (productLink = v)}
													/>
												</div>
												{#if linkRowsSummary}
													<p class="-mt-2 text-xs text-text-muted">{linkRowsSummary}</p>
												{/if}
											</div>
										{:else}
											<h3 class={sectionTitleClass}>Modelo de etapas</h3>
											<div class="grid grid-cols-1 gap-x-4 gap-y-5 md:grid-cols-5">
												<div class="flex flex-col gap-1.5 md:col-span-3">
													<label for="cp-template" class={labelClass}>Importar modelo</label>
													<SelectMenu
														id="cp-template"
														options={templateMenuOptions}
														value={templateId || null}
														onSelect={(v) => {
															templateId = v ?? '';
															void onTemplateChange();
														}}
														allowAll
														allLabel="Não importar / limpar etapas"
														searchable
														ariaLabel="Importar modelo"
													/>
												</div>
												<div class="flex flex-col gap-1.5 md:col-span-2">
													<label for="cp-start" class={labelClass}>Data de início</label>
													<button
														id="cp-start"
														type="button"
														bind:this={startDateAnchorEl}
														aria-haspopup="dialog"
														aria-expanded={startDatePickerOpen}
														title="Sem data, o preview mostra só a duração de cada etapa."
														onclick={() => (startDatePickerOpen = !startDatePickerOpen)}
														class="{fieldClass} flex items-center text-left"
													>
														<span class={startDate ? '' : 'text-text-muted'}>
															{startDateLabel(startDate) || 'Selecionar data'}
														</span>
													</button>
													{#if startDatePickerOpen && startDateAnchorEl}
														<DatePickerPanel
															anchor={startDateAnchorEl}
															value={startDate || null}
															allowClear
															ariaLabel="Data de início"
															onPick={(iso) => {
																startDate = iso;
																startDatePickerOpen = false;
															}}
															onClear={() => {
																startDate = '';
																startDatePickerOpen = false;
															}}
															onClose={() => (startDatePickerOpen = false)}
														/>
													{/if}
												</div>
											</div>

											{#if templateLoading}
												<p
													role="status"
													aria-live="polite"
													class="flex items-center gap-2 text-sm text-text-secondary"
												>
													{@render spinner()}Carregando etapas…
												</p>
											{:else if previewStages.length > 0}
												<div class="flex flex-col gap-2" transition:slide={{ duration: 240, easing: cubicOut }}>
													<ol
														class="flex flex-col divide-y divide-border-subtle overflow-hidden rounded-lg border border-border-subtle"
													>
														{#each previewStages as stage, index (index)}
															<li class="flex items-center gap-3 px-3.5 py-2.5">
																<span class="flex-none text-sm font-semibold tabular-nums text-primary-600">
																	{index + 1} <span aria-hidden="true" class="text-text-muted">-</span>
																</span>
																<span class="min-w-0 flex-1 truncate text-sm font-medium text-text-primary">
																	{stage.name}
																</span>
																{#if stage.startText}
																	<span class="shrink-0 text-xs tabular-nums text-text-muted">
																		{stage.startText}
																	</span>
																{/if}
																<span
																	class="shrink-0 rounded-full bg-surface-muted px-2.5 py-1 text-xs font-medium tabular-nums text-text-secondary"
																>
																	{stage.duration}
																	{stage.duration === 1 ? 'dia' : 'dias'}
																</span>
															</li>
														{/each}
													</ol>
													<p class="text-xs text-text-muted">
														{previewStages.length}
														{previewStages.length === 1 ? 'etapa' : 'etapas'} ·
														{previewTotalDuration} dias
														{#if previewStart && previewEnd}
															· início em
															<span class="font-medium text-text-secondary">{previewStart}</span>
															· término previsto em
															<span class="font-medium text-text-secondary">{previewEnd}</span>
														{/if}
													</p>
												</div>
											{:else}
												<p class={emptyBoxClass}>
													Selecione um modelo para visualizar as etapas importadas.
												</p>
											{/if}
										{/if}
									</div>
								{/key}
							</div>

							<!-- Rodapé fixo -->
							<footer
								class="flex h-14 flex-shrink-0 items-center gap-2 border-t border-border-subtle px-5"
							>
								{#if activeSection === 0}
									<button type="button" onclick={backToFicha} class={btnSecondaryClass}>
										<svg viewBox="0 0 20 20" class="h-3.5 w-3.5" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
											<path d="M12.5 5 7.5 10l5 5" stroke-linecap="round" stroke-linejoin="round" />
										</svg>
										Voltar à ficha
									</button>
								{/if}
								<div class="flex-1"></div>
								{#if activeSection > 0}
									<button
										type="button"
										onclick={() => goToSection(activeSection - 1)}
										class={btnSecondaryClass}
									>
										<svg viewBox="0 0 20 20" class="h-3.5 w-3.5" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
											<path d="M12.5 5 7.5 10l5 5" stroke-linecap="round" stroke-linejoin="round" />
										</svg>
										Voltar
									</button>
								{/if}
								{#if activeSection < NAV_SECTIONS.length - 1}
									<button
										type="button"
										onclick={() => goToSection(activeSection + 1)}
										class="inline-flex h-9 items-center gap-1.5 rounded-md bg-primary-100 px-3.5 text-sm font-semibold text-primary-700 transition-colors duration-fast hover:bg-primary-100/70 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
									>
										Próximo
										<svg viewBox="0 0 20 20" class="h-3.5 w-3.5" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
											<path d="m7.5 5 5 5-5 5" stroke-linecap="round" stroke-linejoin="round" />
										</svg>
									</button>
								{/if}
								<div aria-hidden="true" class="mx-1 h-6 w-px bg-border-subtle"></div>
								<button type="submit" disabled={submitting} class={btnPrimaryClass}>
									{#if submitting}
										{@render spinner()}Criando…
									{:else}
										Criar projeto
									{/if}
								</button>
							</footer>
						</div>
					</div>
				</form>
			{:else}
				<!-- Tela de sucesso: "Criar outro projeto" reseta · "Ver o projeto"
				     dispara onCreated (a página faz flash + navegação). -->
				<div
					class="flex h-[560px] max-h-[calc(92vh-3.5rem)] min-h-0 animate-panel-in flex-col items-center justify-center gap-3.5 overflow-y-auto px-10 py-16"
				>
					<img
						src="/static/img/confete-popper.png"
						alt=""
						class="cp-success-icon h-32 w-32"
						aria-hidden="true"
					/>
					<p class="font-heading text-xl font-semibold text-text-primary">Projeto criado!</p>
					<p class="max-w-md text-center text-sm text-text-secondary">
						{createdTitulo}{orgaoSelecionadoLabel ? ` · ${orgaoSelecionadoLabel}` : ''}
					</p>
					<div class="mt-2 flex items-center gap-2.5">
						<button
							type="button"
							onclick={startAnotherProject}
							class="inline-flex h-10 items-center rounded-md border border-border-subtle bg-surface px-4 text-sm font-semibold text-text-primary transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
						>
							Criar outro projeto
						</button>
						<button
							type="button"
							bind:this={verProjetoBtn}
							onclick={() => createdResult && onCreated(createdResult)}
							class="inline-flex h-10 items-center rounded-md bg-primary-600 px-4 text-sm font-semibold text-primary-fg shadow-sm transition-colors duration-fast hover:bg-primary-700 hover:shadow-md focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-1"
						>
							Ver o projeto
						</button>
					</div>
				</div>
			{/if}

			<!-- Confirmação de descarte: cobre o modal ao fechar com dados preenchidos -->
			{#if confirmDiscardOpen}
				<div
					class="absolute inset-0 z-10 flex items-center justify-center bg-black/30 p-6 backdrop-blur-[1px]"
					role="alertdialog"
					aria-modal="true"
					aria-labelledby="cp-discard-title"
					aria-describedby="cp-discard-desc"
					transition:fade={{ duration: 160 }}
				>
					<div
						class="w-full max-w-sm rounded-lg border border-border-subtle bg-surface p-4 shadow-md"
						transition:fly={{ y: 8, duration: 200, easing: cubicOut }}
					>
						<p id="cp-discard-title" class="text-sm font-semibold text-text-primary">
							Descartar projeto?
						</p>
						<p id="cp-discard-desc" class="mt-1 text-xs text-text-muted">
							As informações preenchidas serão perdidas.
						</p>
						<div class="mt-4 flex items-center justify-end gap-2">
							<button
								type="button"
								bind:this={discardCancelBtn}
								onclick={closeDiscardConfirm}
								class="inline-flex h-8 items-center rounded-md px-3 text-xs font-medium text-text-secondary transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
							>
								Continuar editando
							</button>
							<button
								type="button"
								onclick={discardAndClose}
								class="inline-flex h-8 items-center rounded-md bg-danger px-3 text-xs font-semibold text-danger-fg transition-opacity duration-fast hover:opacity-90 focus:outline-none focus-visible:ring-2 focus-visible:ring-danger focus-visible:ring-offset-1"
							>
								Descartar
							</button>
						</div>
					</div>
				</div>
			{/if}
		</div>
	</div>
{/if}

<style>
	/* Ícone de celebração: pop + tremida UMA vez ao montar, depois fica parado. */
	.cp-success-icon {
		display: inline-block;
		transform-origin: 35% 75%;
		animation: cp-si-pop-shake 0.9s cubic-bezier(0.34, 1.4, 0.64, 1) both;
	}
	@keyframes cp-si-pop-shake {
		0% {
			opacity: 0;
			transform: scale(0.5) rotate(0deg);
		}
		35% {
			opacity: 1;
			transform: scale(1.06) rotate(-9deg);
		}
		55% {
			transform: scale(1) rotate(7deg);
		}
		75% {
			transform: rotate(-4deg);
		}
		100% {
			opacity: 1;
			transform: scale(1) rotate(0deg);
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.cp-success-icon {
			animation: none;
		}
	}
</style>
