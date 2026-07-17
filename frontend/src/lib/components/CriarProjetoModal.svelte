<script lang="ts">
	/**
	 * Modal "Criar novo projeto" (Quick Create) — wizard com sidebar de 4 seções
	 * ("Informações", "Classificação e Objetivos", "Links e Observações",
	 * "Etapas"), uma seção visível por vez, barra de progresso e tela de sucesso
	 * interna ("Criar outro projeto" / "Ver o projeto").
	 *
	 * Mantém (paridade funcional com a versão acordeão):
	 *   - combobox ABEP filtrável (LEGADO, oculto via SHOW_ABEP);
	 *   - cascata objetivo→resultado→indicadores via `/api/resultados`/
	 *     `indicadores` legados, com revelação escalonada (índice·100ms) e LIMITE
	 *     de 4 indicadores (flash 'Você pode selecionar no máximo 4 indicadores');
	 *   - MÚLTIPLOS processos SEI via `SeiProcessField`;
	 *   - import de modelo com preview read-only e cálculo de datas no client;
	 *   - criação só com título + área válidos (validação ao tentar salvar, com
	 *     foco no campo faltante);
	 *   - Esc fecha · Ctrl/Cmd+Enter salva · confirmação de descarte.
	 *
	 * Submit: `POST /api/projetos` (via `createProject`). Em sucesso o modal
	 * mostra a tela "Projeto criado"; `onCreated(result)` só dispara em
	 * "Ver o projeto" — a página então faz flash + goto(redirect_to), como antes.
	 * "Criar outro projeto" reseta o formulário sem fechar. Em erro, exibe a
	 * mensagem do envelope como flash danger/warning (sem fechar o modal).
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

	// --- Campos da seção "Informações" ---------------------------------------
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
	let triedSubmit = $state(false); // marca erro de título/área só após tentativa
	// Projeto criado nesta abertura: troca o corpo pela tela de sucesso.
	let createdResult = $state<CreateProjectResult | null>(null);
	let verProjetoBtn = $state<HTMLButtonElement | null>(null);
	// Sobrevive ao reset de "Criar outro projeto": garante onCreatedDismissed.
	let lastCreatedThisOpen: CreateProjectResult | null = null;

	// --- Wizard: uma seção visível por vez ----------------------------------
	const NAV_SECTIONS = [
		'Informações',
		'Classificação e Objetivos',
		'Links e Observações',
		'Etapas'
	];
	let activeSection = $state(0);

	function goToSection(index: number): void {
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
	const specialOptions = $derived(options?.special_projects_options ?? SPECIAL_PROJECTS);

	// --- Opções dos SelectMenu (derivadas das constantes/catálogos acima) --
	const deliveryTypeMenuOptions = $derived<SelectMenuOption[]>(
		deliveryTypes.map((dt) => ({ value: dt, label: dt }))
	);
	const specialProjectMenuOptions = $derived<SelectMenuOption[]>(
		specialOptions.map((sp) => ({ value: sp, label: sp }))
	);
	const objetivoMenuOptions = $derived<SelectMenuOption[]>(
		objetivos.map((o) => ({ value: String(o.id), label: o.descricao }))
	);
	const resultadoMenuOptions = $derived<SelectMenuOption[]>(
		resultados.map((r) => ({ value: String(r.id), label: r.descricao }))
	);
	const templateMenuOptions = $derived<SelectMenuOption[]>(
		templates.map((t) => ({ value: String(t.id), label: t.name }))
	);

	// Criação só com título + área (paridade com updateSubmitState).
	const canSubmit = $derived(
		!submitting && titulo.trim().length > 0 && orgaoId.trim().length > 0
	);
	const tituloError = $derived(triedSubmit && !titulo.trim());
	const orgaoError = $derived(triedSubmit && !orgaoId.trim());

	const orgaoSelecionadoLabel = $derived.by(() => {
		if (orgaoOptions.length === 1) return orgaoOptions[0].label;
		return orgaoOptions.find((o) => o.value === orgaoId)?.label ?? '';
	});

	// Critérios de seção "preenchida" (badge ✓ + barra de progresso).
	const sectionDone = $derived<boolean[]>([
		titulo.trim().length > 0 && orgaoId.trim().length > 0,
		deliveryType !== '' && objetivoId !== '' && resultadoId !== '',
		seiList.length > 0 ||
			[githubLink, documentationLink, productLink, observacao].some(
				(v) => v.trim().length > 0
			),
		templateId !== ''
	]);
	const doneCount = $derived(sectionDone.filter(Boolean).length);

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

	function resetForm(): void {
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
		resultadosLoading = false;
		indicadoresLoading = false;
		templateLoading = false;
		activeSection = 0;
		triedSubmit = false;
		createdResult = null;
		confirmDiscardOpen = false;
	}

	/** "Criar outro projeto" na tela de sucesso: limpa e volta ao formulário. */
	function startAnotherProject(): void {
		resetForm();
		void tick().then(() => titleInputEl?.focus());
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
	// máscara/adição/remoção; aqui a lista é estado local até o submit.

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
			// 1º Esc fecha o popup, 2º Esc borbulha e fecha o modal.
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
		// repopulava templateStages com templateId já vazio — o submit enviava
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

	// --- Confirmação de descarte ao fechar com dados preenchidos -------------

	let confirmDiscardOpen = $state(false);
	let discardCancelBtn = $state<HTMLButtonElement | null>(null);
	// Foco a restaurar quando a confirmação fecha em "Continuar editando"
	// (o botão dela desmonta; sem isso o foco cairia no body, fora do trap).
	let focusedBeforeDiscard: HTMLElement | null = null;

	/** Há conteúdo digitado/escolhido que seria perdido ao fechar? */
	const formIsDirty = $derived(
		[
			titulo,
			shortDescription,
			orgaoTexto,
			githubLink,
			documentationLink,
			productLink,
			observacao,
			abepValue
		].some((v) => v.trim().length > 0) ||
			seiList.length > 0 ||
			// Órgão único é pré-selecionado na abertura; só conta escolha do usuário.
			(orgaoOptions.length > 1 && orgaoId.trim().length > 0) ||
			prioridade !== 'baixa' ||
			deliveryType !== '' ||
			specialProject !== '' ||
			objetivoId !== '' ||
			selectedIndicadores.length > 0 ||
			templateId !== '' ||
			startDate !== ''
	);

	/** Fecha avisando a página se houve criação sem "Ver o projeto". */
	function closeAndNotify(): void {
		if (lastCreatedThisOpen) onCreatedDismissed?.(lastCreatedThisOpen);
		onClose();
	}

	/** Fecha o modal; com dados preenchidos, pede confirmação de descarte antes. */
	function requestClose(): void {
		if (submitting) return;
		// Tela de sucesso: nada a perder — fecha direto.
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

	// Wrapper do submit: se inválido, marca os campos faltantes e foca o primeiro.
	async function trySubmit(): Promise<void> {
		if (createdResult) return;
		if (!canSubmit) {
			if (submitting) return;
			triedSubmit = true;
			// Volta à seção "Informações": o campo faltante precisa existir no DOM
			// para receber foco.
			activeSection = 0;
			await tick();
			// Fallback para o título quando o select de órgão está disabled/ausente
			// (ex.: usuário sem órgão atribuído): foco em elemento disabled é no-op
			// e deixaria o foco fora do dialog, quebrando o focusTrap.
			const orgaoEl = document.getElementById('cp-orgao-id') as HTMLSelectElement | null;
			const focusTarget = !titulo.trim()
				? titleInputEl
				: orgaoEl && !orgaoEl.disabled
					? orgaoEl
					: titleInputEl;
			focusTarget?.focus();
			return;
		}
		await submit();
	}

	// Esc fecha; Ctrl/Cmd+Enter salva de qualquer lugar do modal.
	function onModalKeydown(event: KeyboardEvent): void {
		if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') {
			event.preventDefault();
			event.stopPropagation(); // evita repetição ao borbulhar para o backdrop
			void trySubmit();
			return;
		}
		onBackdropKeydown(event);
	}

	// --- Submit ------------------------------------------------------------

	async function submit(): Promise<void> {
		if (!canSubmit || createdResult) return;
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
			// Defesa extra contra estado órfão: etapas só valem com modelo escolhido.
			etapas: (templateId ? templateStages : []).map((s) => ({
				descricao: s.name,
				duration: Math.max(1, Number.parseInt(String(s.duration), 10) || 1)
			})),
			start_date: startDate || undefined,
			template_id: templateId ? Number(templateId) : undefined
		};
		try {
			const result = await createProject(input);
			// Tela de sucesso interna; onCreated dispara em "Ver o projeto".
			createdResult = result;
			lastCreatedThisOpen = result;
			// Sem origem o helper usa fallback no canto superior direito; centro da tela.
			triggerTaskFinalizeConfetti({
				x: window.innerWidth / 2,
				y: window.innerHeight / 2
			});
			// O form desmonta e levaria o foco ao body, matando Esc/focusTrap.
			void tick().then(() => verProjetoBtn?.focus());
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
			// stopPropagation: dialog e backdrop compartilham este handler; sem
			// consumir aqui, o mesmo Esc seria tratado DUAS vezes (abre a
			// confirmação no dialog e fecha no backdrop — efeito líquido nulo).
			event.stopPropagation();
			// Primeiro Esc fecha só a confirmação de descarte; o próximo, o modal.
			if (confirmDiscardOpen) {
				closeDiscardConfirm();
				return;
			}
			requestClose();
		}
	}

	// --- Classes utilitárias (campos com visual unificado) -------------------
	const labelClass = 'text-xs font-medium uppercase tracking-wide text-text-muted';
	const fieldClass =
		'h-10 w-full rounded-md border border-border-subtle bg-surface px-3 text-sm leading-tight text-text-primary placeholder:text-text-muted transition-colors duration-fast focus:border-primary-500 focus:outline-none disabled:opacity-60';
	const areaClass =
		'w-full rounded-md border border-border-subtle bg-surface px-3 py-2 text-sm text-text-primary placeholder:text-text-muted transition-colors duration-fast focus:border-primary-500 focus:outline-none';
	const fieldErrorClass = 'border-danger focus:border-danger';
	const sectionTitleClass = 'font-heading text-base font-semibold text-text-primary';
	const emptyBoxClass =
		'rounded-lg border border-dashed border-border-subtle bg-surface-muted px-4 py-3.5 text-sm text-text-muted';
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
						? 'bg-[var(--ds-color-success-light-bg)] text-success'
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
		class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4 backdrop-blur-[1.5px]"
		role="presentation"
		onclick={requestClose}
		onkeydown={onModalKeydown}
		transition:fade={{ duration: 200 }}
	>
		<div
			role="dialog"
			aria-modal="true"
			aria-labelledby="criar-projeto-title"
			class="relative flex max-h-[92vh] w-full max-w-[870px] flex-col overflow-hidden rounded-xl border border-border-subtle bg-surface shadow-lg"
			onclick={(e) => e.stopPropagation()}
			onkeydown={onModalKeydown}
			tabindex="-1"
			use:focusTrap
			transition:fly={{ y: 18, duration: 320, easing: cubicOut }}
		>
			<!-- Cabeçalho fixo. inert: com a confirmação de descarte aberta, o fundo
			     sai do Tab e da interação. -->
			<header
				inert={confirmDiscardOpen}
				class="flex h-14 flex-shrink-0 items-center justify-between gap-4 border-b border-border-subtle px-6"
			>
				<h2
					id="criar-projeto-title"
					class="truncate font-heading text-base font-semibold text-text-primary"
				>
					Criar novo projeto
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

			{#if createdResult}
				<!-- Tela de sucesso: substitui corpo e rodapé -->
				<div
					class="flex h-[560px] max-h-[calc(92vh-3.5rem)] min-h-0 animate-panel-in flex-col items-center justify-center gap-3.5 overflow-y-auto px-10 py-16"
				>
					<img
						src="/static/img/confete-popper.png"
						alt=""
						class="cp-success-icon h-32 w-32"
						aria-hidden="true"
					/>
					<p class="font-heading text-xl font-bold text-text-primary">Projeto criado!</p>
					<p class="max-w-md text-center text-sm text-text-secondary">
						{createdResult.project?.titulo ?? titulo.trim()}{orgaoSelecionadoLabel
							? ` · ${orgaoSelecionadoLabel}`
							: ''}
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
							onclick={() => onCreated(createdResult!)}
							class="inline-flex h-10 items-center rounded-md bg-primary-600 px-4 text-sm font-semibold text-primary-fg shadow-sm transition-colors duration-fast hover:bg-primary-700 hover:shadow-md focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-1"
						>
							Ver o projeto
						</button>
					</div>
				</div>
			{:else}
				<form
					inert={confirmDiscardOpen}
					onsubmit={(e) => {
						e.preventDefault();
						void trySubmit();
					}}
					class="flex h-[560px] max-h-[calc(92vh-3.5rem)] min-h-0 flex-col"
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
								<p
									class="truncate text-sm font-semibold {titulo.trim()
										? 'text-text-primary'
										: 'text-text-muted'}"
								>
									{titulo.trim() || 'Sem título'}
								</p>
								{#if orgaoSelecionadoLabel}
									<p class="truncate text-xs text-text-secondary">{orgaoSelecionadoLabel}</p>
								{:else}
									<p class="truncate text-xs font-medium text-danger">Área pendente</p>
								{/if}
								<div class="mt-1 h-1 overflow-hidden rounded-full bg-border-subtle">
									<div
										class="h-full rounded-full bg-primary-600 transition-[width] duration-base"
										style="width: {doneCount * 25}%"
									></div>
								</div>
								<p class="text-[11px] font-medium leading-none text-text-muted">
									{doneCount} de 4 seções preenchidas
								</p>
							</div>
						</nav>

						<!-- Conteúdo da seção ativa -->
						<div class="flex min-w-0 flex-1 flex-col">
							<div class="min-h-0 flex-1 overflow-y-auto px-6 py-6 md:px-8">
								{#key activeSection}
									<div class="flex animate-panel-in flex-col gap-5">
										{#if activeSection === 0}
											<h3 class={sectionTitleClass}>Informações principais</h3>
											<div class="flex flex-col gap-1.5">
												<label for="cp-titulo" class={labelClass}>
													Título do projeto <span class="text-danger" aria-hidden="true">*</span>
												</label>
												<input
													id="cp-titulo"
													bind:this={titleInputEl}
													bind:value={titulo}
													type="text"
													required
													aria-invalid={tituloError}
													placeholder="Digite o título do projeto"
													class="{fieldClass} {tituloError ? fieldErrorClass : ''}"
												/>
												{#if tituloError}
													<p class="text-xs text-danger" transition:slide={{ duration: 160, easing: cubicOut }}>
														Informe o título do projeto.
													</p>
												{/if}
											</div>
											<div class="grid grid-cols-1 gap-x-4 gap-y-5 md:grid-cols-5">
												<div class="flex flex-col gap-1.5 md:col-span-2">
													<label for="cp-orgao-id" class={labelClass}>
														Área responsável <span class="text-danger" aria-hidden="true">*</span>
													</label>
													{#if orgaoOptions.length === 0}
														<SelectMenu
															id="cp-orgao-id"
															options={[]}
															value={null}
															onSelect={() => {}}
															disabled
															placeholder="Nenhum órgão atribuído"
															ariaLabel="Área responsável"
														/>
													{:else if orgaoOptions.length === 1}
														<input
															type="text"
															value={orgaoOptions[0].label}
															disabled
															class={fieldClass}
														/>
													{:else}
														<OrgaoTreeSelect
															id="cp-orgao-id"
															options={orgaoTreeOptions}
															value={orgaoId ? Number(orgaoId) : null}
															onSelect={(v) => (orgaoId = v == null ? '' : String(v))}
															placeholder="Selecione um órgão"
														/>
													{/if}
													{#if orgaoError}
														<p class="text-xs text-danger" transition:slide={{ duration: 160, easing: cubicOut }}>
															Selecione a área responsável.
														</p>
													{/if}
												</div>
												<div class="flex flex-col gap-1.5 md:col-span-3">
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
																	? 'font-semibold text-white'
																	: 'border-border-subtle bg-surface font-medium text-text-secondary hover:bg-surface-muted'}"
															>
																{p.label}
															</button>
														{/each}
													</div>
												</div>
											</div>
											<div class="flex flex-col gap-1.5">
												<label for="cp-orgao-texto" class={labelClass}>Órgão</label>
												<input
													id="cp-orgao-texto"
													bind:value={orgaoTexto}
													type="text"
													placeholder="Digite o órgão responsável"
													class={fieldClass}
												/>
											</div>
											<div class="flex flex-col gap-1.5">
												<label for="cp-short-desc" class={labelClass}>Descrição breve</label>
												<textarea
													id="cp-short-desc"
													bind:value={shortDescription}
													rows="3"
													placeholder="Breve descrição do projeto"
													class={areaClass}
												></textarea>
											</div>
										{:else if activeSection === 1}
											<h3 class={sectionTitleClass}>Classificação</h3>
											<div class="grid grid-cols-1 gap-x-4 gap-y-5 md:grid-cols-2">
												<div class="flex flex-col gap-1.5">
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
												<div class="flex flex-col gap-1.5">
													<label for="cp-special" class={labelClass}>Projetos especiais</label>
													<SelectMenu
														id="cp-special"
														options={specialProjectMenuOptions}
														value={specialProject || null}
														onSelect={(v) => (specialProject = v ?? '')}
														allowAll
														allLabel="Nenhum"
														ariaLabel="Projetos especiais"
													/>
												</div>
											</div>

											<div class="flex flex-col gap-5 border-t border-border-subtle pt-5">
												<h3 class={sectionTitleClass}>Objetivos e indicadores</h3>
												<div class="grid grid-cols-1 gap-x-4 gap-y-5 md:grid-cols-2">
													<div class="flex flex-col gap-1.5">
														<label for="cp-objetivo" class={labelClass}>Objetivo EEGD</label>
														<SelectMenu
															id="cp-objetivo"
															options={objetivoMenuOptions}
															value={objetivoId || null}
															onSelect={(v) => {
																objetivoId = v ?? '';
																void onObjetivoChange();
															}}
															allowAll
															allLabel="Selecione um objetivo"
															ariaLabel="Objetivo EEGD"
														/>
													</div>
													<div class="flex flex-col gap-1.5">
														<label for="cp-resultado" class={labelClass}>Resultado esperado EEGD</label>
														<SelectMenu
															id="cp-resultado"
															options={resultadoMenuOptions}
															value={resultadoId || null}
															onSelect={(v) => {
																resultadoId = v ?? '';
																void onResultadoChange();
															}}
															disabled={!objetivoId || resultadosLoading}
															allowAll
															allLabel={resultadosLoading
																? 'Carregando resultados...'
																: 'Selecione um resultado esperado'}
															ariaLabel="Resultado esperado EEGD"
														/>
													</div>
												</div>

												<div class="flex flex-col gap-2">
													<span class={labelClass}>Indicadores EEGD</span>
													{#if indicadoresLoading}
														<p
															role="status"
															aria-live="polite"
															class="flex items-center gap-2 text-sm text-text-secondary"
														>
															{@render spinner()}Carregando indicadores...
														</p>
													{:else if !resultadoId}
														<p class={emptyBoxClass}>
															Selecione um resultado esperado para ver os indicadores disponíveis.
														</p>
													{:else if indicadores.length === 0}
														<p class={emptyBoxClass}>
															Nenhum indicador disponível para este resultado esperado.
														</p>
													{:else}
														<div class="flex flex-wrap gap-2">
															{#each indicadores as ind (ind.id)}
																{@const checked = selectedIndicadores.includes(ind.id)}
																<button
																	type="button"
																	aria-pressed={checked}
																	onclick={() => toggleIndicador(ind.id)}
																	class="inline-flex items-center rounded-lg border px-3 py-2 text-left text-xs transition-[opacity,transform,color,background-color,border-color] duration-300 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 {checked
																		? 'border-primary-500 bg-primary-100 font-medium text-primary-700'
																		: 'border-border-subtle bg-surface text-text-secondary hover:border-border-strong hover:text-text-primary'} {revealedIndicadores.has(
																		ind.id
																	)
																		? 'translate-y-0 opacity-100'
																		: 'translate-y-1 opacity-0'}"
																>
																	{ind.descricao}
																</button>
															{/each}
														</div>
													{/if}
												</div>

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
											</div>
										{:else if activeSection === 2}
											<h3 class={sectionTitleClass}>Links e observações</h3>
											<div class="flex flex-col gap-5">
												<div class="flex flex-col gap-1.5">
													<span class={labelClass}>Processo SEI-RJ</span>
													<SeiProcessField
														fieldId="cp-sei"
														processes={seiList}
														onSave={(list) => (seiList = list)}
													/>
												</div>
												<div class="flex flex-col gap-1.5">
													<label for="cp-github" class={labelClass}>Link GitHub</label>
													<input
														id="cp-github"
														bind:value={githubLink}
														type="text"
														placeholder="https://github.com/..."
														class={fieldClass}
													/>
												</div>
												<div class="flex flex-col gap-1.5">
													<label for="cp-doc" class={labelClass}>Link documentação</label>
													<input
														id="cp-doc"
														bind:value={documentationLink}
														type="text"
														placeholder="https://..."
														class={fieldClass}
													/>
												</div>
												<div class="flex flex-col gap-1.5">
													<label for="cp-product" class={labelClass}>Link para o produto</label>
													<input
														id="cp-product"
														bind:value={productLink}
														type="text"
														placeholder="https://..."
														class={fieldClass}
													/>
												</div>
											</div>
											<div class="flex flex-col gap-1.5">
												<label for="cp-obs" class={labelClass}>Observações</label>
												<textarea
													id="cp-obs"
													bind:value={observacao}
													rows="4"
													placeholder="Digite observações detalhadas sobre o projeto..."
													class={areaClass}
												></textarea>
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
								<div class="flex-1"></div>
								{#if activeSection > 0}
									<button
										type="button"
										onclick={() => goToSection(activeSection - 1)}
										class="inline-flex h-9 items-center gap-1.5 rounded-md border border-border-subtle bg-surface px-3.5 text-sm font-medium text-text-secondary transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
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
								<button
									type="submit"
									disabled={submitting}
									class="inline-flex h-9 items-center justify-center gap-2 rounded-md px-4 text-sm font-semibold transition-colors duration-fast focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-1 disabled:cursor-not-allowed disabled:opacity-60 {canSubmit ||
									submitting
										? 'bg-primary-600 text-primary-fg shadow-sm hover:bg-primary-700 hover:shadow-md'
										: 'border border-border-subtle bg-surface-muted text-text-muted'}"
								>
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
