<script lang="ts">
	/**
	 * Modal "Criar novo projeto" (Quick Create) — paridade de LÓGICA com o modal
	 * Bootstrap `templates/projects/add_form.html` + `add_form_js.html`.
	 *
	 * Layout: seção principal (título*, área responsável*, prioridade, órgão,
	 * descrição) + acordeão EXCLUSIVO de 4 seções opcionais (Classificação,
	 * Objetivos/resultados/indicadores, Links e observações, Modelo de etapas).
	 * Expandir uma seção retrai a anterior; o cabeçalho de cada seção resume o
	 * que já foi preenchido quando fechada. A seção principal participa do
	 * acordeão: abrir uma seção opcional a colapsa num cabeçalho compacto
	 * (título — ou "Sem título" — + resumo do que foi/não foi respondido);
	 * clicar nesse cabeçalho a reexpande e fecha a seção opcional aberta.
	 * Fechar o modal com dados preenchidos pede confirmação de descarte.
	 *
	 * Mantém (paridade funcional):
	 *   - combobox ABEP filtrável com navegação por teclado (Arrow/Enter/Escape);
	 *   - cascata objetivo→resultado→indicadores via `/api/resultados`/
	 *     `indicadores` legados, com revelação escalonada (índice·100ms) e LIMITE
	 *     de 4 indicadores (flash 'Você pode selecionar no máximo 4 indicadores');
	 *   - máscara SEI on-input ('SEI-000000/000000/0000');
	 *   - import de modelo com preview read-only e cálculo de datas no client
	 *     (dias corridos, mesmo algoritmo de `renderTemplateImportPreview`);
	 *   - criação só com título + área válidos (validação ao tentar salvar, com
	 *     foco no campo faltante);
	 *   - Esc fecha · Ctrl/Cmd+Enter salva.
	 *
	 * Submit: `POST /api/projetos` (via `createProject`). Em sucesso o COMPONENTE
	 * NÃO navega nem mostra flash — emite `onCreated(result)` e a página decide
	 * (showFlash + goto), replicando o flash success + redirect do Jinja. Em erro,
	 * exibe a mensagem do envelope como flash danger/warning (sem fechar o modal).
	 *
	 * NÃO há som/confete (o fluxo Jinja não tem).
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

	// --- Campos da seção principal ------------------------------------------
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
	let triedSubmit = $state(false); // marca erro de título/área só após tentativa

	// --- Acordeão exclusivo: no máximo UMA seção opcional aberta -------------
	type SectionId = 'classificacao' | 'objetivos' | 'links' | 'etapas';
	const SECTIONS: { id: SectionId; label: string }[] = [
		{ id: 'classificacao', label: 'Classificação' },
		{ id: 'objetivos', label: 'Objetivos e indicadores' },
		{ id: 'links', label: 'Links e observações' },
		{ id: 'etapas', label: 'Modelo de etapas' }
	];
	let openSection = $state<SectionId | null>(null);

	// Colapso da principal é ORIENTADO A EVENTO (nunca derivado da digitação):
	// só muda ao abrir/fechar uma seção opcional ou ao clicar no cabeçalho.
	let mainCollapsed = $state(false);

	function toggleSection(id: SectionId): void {
		const opening = openSection !== id;
		openSection = opening ? id : null;
		// Principal retrai ao abrir qualquer opcional — mesmo sem título (o header
		// colapsado mostra "Sem título") — e restaura ao fechar a última seção.
		// Digitar no título nunca altera mainCollapsed (colapso só por evento).
		mainCollapsed = opening;
	}

	function expandMainSection(): void {
		mainCollapsed = false;
		openSection = null; // acordeão exclusivo: reexpandir a principal fecha a opcional
	}

	const orgaoOptions = $derived<OrgaoOption[]>(options?.orgaos_options ?? []);
	const abepOptions = $derived<AbepIndicadorOption[]>(
		options?.abep_indicadores_options ?? []
	);
	const deliveryTypes = $derived(options?.delivery_types_options ?? DELIVERY_TYPES);
	const specialOptions = $derived(options?.special_projects_options ?? SPECIAL_PROJECTS);

	// Criação só com título + área (paridade com updateSubmitState).
	const canSubmit = $derived(
		!submitting && titulo.trim().length > 0 && orgaoId.trim().length > 0
	);
	const tituloError = $derived(triedSubmit && !titulo.trim());
	const orgaoError = $derived(triedSubmit && !orgaoId.trim());

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
	// resolvesse (ou `options` mudasse), apagando o que o usuário digitou e
	// fechando a seção aberta "do nada". O efeito deve depender SÓ de `open`.
	$effect(() => {
		if (!open) return;
		untrack(() => {
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
		seiProcess = '';
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
		openSection = null;
		mainCollapsed = false;
		triedSubmit = false;
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

	/** Preview das etapas com datas/duração calculadas no client (read-only). */
	interface PreviewStage {
		name: string;
		/** Intervalo "dd/mm/aaaa → dd/mm/aaaa"; vazio sem data de início. */
		rangeText: string;
		duration: number;
	}

	const previewStages = $derived.by<PreviewStage[]>(() => {
		if (!templateStages.length) return [];
		const start = parseIsoDate(startDate);
		let cursor = start ? new Date(start.getTime()) : null;
		return templateStages.map((etapa) => {
			const duration = Math.max(1, Number.parseInt(String(etapa.duration), 10) || 1);
			let rangeText = '';
			if (cursor) {
				const stageStart = new Date(cursor.getTime());
				const stageEnd = addDaysUtc(stageStart, duration - 1);
				rangeText = `${formatBrDate(stageStart)} → ${formatBrDate(stageEnd)}`;
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

	// --- Resumos das seções (exibidos no cabeçalho quando fechadas) ----------

	const orgaoSelecionadoLabel = $derived.by(() => {
		if (orgaoOptions.length === 1) return orgaoOptions[0].label;
		return orgaoOptions.find((o) => o.value === orgaoId)?.label ?? '';
	});
	const prioridadeLabel = $derived(
		PRIORITIES.find((p) => p.value === prioridade)?.label ?? prioridade
	);

	const classificacaoSummary = $derived(
		[deliveryType, specialProject].filter(Boolean).join(' · ')
	);
	const objetivosSummary = $derived.by(() => {
		const parts: string[] = [];
		const objetivoNome = objetivos.find((o) => String(o.id) === objetivoId)?.descricao;
		if (objetivoNome) parts.push(objetivoNome);
		const resultadoNome = resultados.find((r) => String(r.id) === resultadoId)?.descricao;
		if (resultadoNome) parts.push(resultadoNome);
		if (selectedIndicadores.length)
			parts.push(
				`${selectedIndicadores.length} ${selectedIndicadores.length === 1 ? 'indicador' : 'indicadores'}`
			);
		if (abepValue) parts.push('ABEP');
		return parts.join(' · ');
	});
	const linksSummary = $derived.by(() => {
		const filled = [seiProcess, githubLink, documentationLink, productLink, observacao]
			.map((v) => v.trim())
			.filter(Boolean).length;
		if (!filled) return '';
		return filled === 1 ? '1 campo preenchido' : `${filled} campos preenchidos`;
	});
	const etapasSummary = $derived.by(() => {
		if (!templateId) return '';
		const name = templates.find((t) => String(t.id) === templateId)?.name ?? 'Modelo';
		return previewStages.length
			? `${name} · ${previewStages.length} ${previewStages.length === 1 ? 'etapa' : 'etapas'}`
			: name;
	});
	const sectionSummaries = $derived<Record<SectionId, string>>({
		classificacao: classificacaoSummary,
		objetivos: objetivosSummary,
		links: linksSummary,
		etapas: etapasSummary
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
			seiProcess,
			githubLink,
			documentationLink,
			productLink,
			observacao,
			abepValue
		].some((v) => v.trim().length > 0) ||
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

	/** Fecha o modal; com dados preenchidos, pede confirmação de descarte antes. */
	function requestClose(): void {
		if (submitting) return;
		if (formIsDirty) {
			focusedBeforeDiscard = document.activeElement as HTMLElement | null;
			confirmDiscardOpen = true;
			void tick().then(() => discardCancelBtn?.focus());
			return;
		}
		onClose();
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
		onClose();
	}

	// Wrapper do submit: se inválido, marca os campos faltantes e foca o primeiro.
	async function trySubmit(): Promise<void> {
		if (!canSubmit) {
			if (submitting) return;
			triedSubmit = true;
			// Reexpande a seção principal: o campo faltante pode estar oculto
			// pelo colapso e precisa existir no DOM para receber foco.
			expandMainSection();
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
		'h-10 w-full rounded-md border border-border-subtle bg-surface px-3 text-sm leading-tight text-text-primary placeholder:text-text-muted transition-colors duration-fast focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-60';
	const areaClass =
		'w-full rounded-md border border-border-subtle bg-surface px-3 py-2 text-sm text-text-primary placeholder:text-text-muted transition-colors duration-fast focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500';
	const fieldErrorClass = 'border-danger focus-visible:ring-danger';
</script>

{#snippet mainSummary()}
	<!-- Metadados da principal colapsada: só positivos (nunca anuncia ausência
	     de campo opcional); o único negativo permitido é o obrigatório pendente.
	     A descrição breve é renderizada à parte, antes deste snippet. -->
	{#if orgaoSelecionadoLabel}
		<span class="text-text-secondary">{orgaoSelecionadoLabel}</span>
	{:else}
		<span class="font-medium text-danger">Área pendente</span>
	{/if}
	{#if prioridade !== 'baixa'}
		· {prioridadeLabel}
	{/if}
	{#if orgaoTexto.trim()}
		· {orgaoTexto.trim()}
	{/if}
{/snippet}

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
			class="relative flex max-h-[calc(100dvh-7rem)] w-full max-w-3xl flex-col overflow-hidden rounded-xl border border-border-subtle bg-surface shadow-lg"
			onclick={(e) => e.stopPropagation()}
			onkeydown={onModalKeydown}
			tabindex="-1"
			use:focusTrap
			transition:fly={{ y: 18, duration: 320, easing: cubicOut }}
		>
			<!-- Cabeçalho fixo (mesma altura do rodapé: h-14). inert: com a
			     confirmação de descarte aberta, o fundo sai do Tab e da interação. -->
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

			<form
				inert={confirmDiscardOpen}
				onsubmit={(e) => {
					e.preventDefault();
					void trySubmit();
				}}
				class="flex min-h-0 flex-1 flex-col"
			>
				<!-- Corpo: única região que rola -->
				<div class="min-h-0 flex-1 overflow-y-auto px-6 py-5">
					<!-- Acordeão: a seção principal é o item 0, com header sempre montado
					     (anatomia idêntica às opcionais — sem card avulso, sem swap de
					     dois elementos com transições simultâneas). -->
					<div
						class="divide-y divide-border-subtle overflow-hidden rounded-lg border border-border-subtle"
					>
						<!-- Seção 0: informações principais -->
						<section>
							<h3 class="contents">
								<!-- Expandida: o header vira informativo — sai da ordem de Tab
								     (tabindex=-1) e anuncia aria-disabled, pois ativá-lo seria
								     no-op (disclosure só atua no sentido colapsada→expandida). -->
								<button
									type="button"
									onclick={() => {
										if (mainCollapsed) expandMainSection();
									}}
									tabindex={mainCollapsed ? 0 : -1}
									aria-disabled={!mainCollapsed}
									aria-expanded={!mainCollapsed}
									aria-controls={mainCollapsed ? undefined : 'cp-section-principal'}
									class="flex w-full items-center justify-between gap-3 px-4 py-3 text-left transition-colors duration-fast focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary-500 {mainCollapsed
										? 'hover:bg-surface-muted/60'
										: 'cursor-default'}"
								>
									<span class="flex min-w-0 flex-col gap-0.5">
										{#if mainCollapsed}
											{#if titulo.trim()}
												<span class="truncate text-sm font-medium text-text-primary">
													{titulo.trim()}
												</span>
											{:else}
												<span class="truncate text-sm font-medium text-text-muted">
													Sem título
												</span>
											{/if}
											<span class="flex min-w-0 items-baseline gap-1.5 text-xs text-text-muted">
												{#if shortDescription.trim()}
													<span class="min-w-0 truncate">{shortDescription.trim()}</span>
													<span aria-hidden="true" class="shrink-0">·</span>
												{/if}
												<span class="shrink-0 whitespace-nowrap">{@render mainSummary()}</span>
											</span>
										{:else}
											<span class="text-sm font-medium text-text-primary">
												Informações principais
											</span>
											<span class="text-xs text-text-muted">
												Título e área responsável são obrigatórios
											</span>
										{/if}
									</span>
									<svg
										viewBox="0 0 20 20"
										fill="none"
										stroke="currentColor"
										stroke-width="1.6"
										aria-hidden="true"
										class="h-4 w-4 flex-shrink-0 text-text-muted transition-transform duration-base {mainCollapsed
											? ''
											: 'rotate-180'}"
									>
										<path d="m5 7.5 5 5 5-5" stroke-linecap="round" stroke-linejoin="round" />
									</svg>
								</button>
							</h3>
							{#if !mainCollapsed}
								<div
									id="cp-section-principal"
									transition:slide={{ duration: 280, easing: cubicOut }}
								>
									<!-- Linhas: 1) título · 2) área → prioridade → órgão · 3) descrição -->
									<div class="grid grid-cols-1 gap-x-4 gap-y-4 px-4 pb-5 pt-1 md:grid-cols-12">
										<div class="flex flex-col gap-1.5 md:col-span-12">
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
										<div class="flex flex-col gap-1.5 md:col-span-5">
											<label for="cp-orgao-id" class={labelClass}>
												Área responsável <span class="text-danger" aria-hidden="true">*</span>
											</label>
											{#if orgaoOptions.length === 0}
												<select id="cp-orgao-id" disabled class={fieldClass}>
													<option value="">Nenhum órgão atribuído</option>
												</select>
											{:else if orgaoOptions.length === 1}
												<input
													type="text"
													value={orgaoOptions[0].label}
													disabled
													class={fieldClass}
												/>
											{:else}
												<select
													id="cp-orgao-id"
													bind:value={orgaoId}
													required
													aria-invalid={orgaoError}
													class="{fieldClass} {orgaoError ? fieldErrorClass : ''}"
												>
													<option value="" disabled>Selecione um órgão</option>
													{#each orgaoOptions as opt (opt.value)}
														<option value={opt.value}>{opt.label}</option>
													{/each}
												</select>
											{/if}
											{#if orgaoError}
												<p class="text-xs text-danger" transition:slide={{ duration: 160, easing: cubicOut }}>
													Selecione a área responsável.
												</p>
											{/if}
										</div>
										<div class="flex flex-col gap-1.5 md:col-span-3">
											<label for="cp-prioridade" class={labelClass}>Prioridade</label>
											<select id="cp-prioridade" bind:value={prioridade} class={fieldClass}>
												{#each PRIORITIES as p (p.value)}
													<option value={p.value}>{p.label}</option>
												{/each}
											</select>
										</div>
										<div class="flex flex-col gap-1.5 md:col-span-4">
											<label for="cp-orgao-texto" class={labelClass}>Órgão</label>
											<input
												id="cp-orgao-texto"
												bind:value={orgaoTexto}
												type="text"
												placeholder="Digite o órgão responsável"
												class={fieldClass}
											/>
										</div>
										<div class="flex flex-col gap-1.5 md:col-span-12">
											<label for="cp-short-desc" class={labelClass}>Descrição breve</label>
											<textarea
												id="cp-short-desc"
												bind:value={shortDescription}
												rows="2"
												placeholder="Breve descrição do projeto"
												class={areaClass}
											></textarea>
										</div>
									</div>
								</div>
							{/if}
						</section>

						{#each SECTIONS as section (section.id)}
							{@const isOpen = openSection === section.id}
							{@const summary = sectionSummaries[section.id]}
							<section>
								<h3 class="contents">
									<button
										type="button"
										onclick={() => toggleSection(section.id)}
										aria-expanded={isOpen}
										aria-controls={isOpen ? `cp-section-${section.id}` : undefined}
										class="flex w-full items-center justify-between gap-3 px-4 py-3 text-left transition-colors duration-fast hover:bg-surface-muted/60 focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary-500"
									>
										<span class="flex min-w-0 flex-col">
											<span class="text-sm font-medium text-text-primary">{section.label}</span>
											{#if summary && !isOpen}
												<span class="truncate text-xs text-primary-600">{summary}</span>
											{/if}
										</span>
										<svg
											viewBox="0 0 20 20"
											fill="none"
											stroke="currentColor"
											stroke-width="1.6"
											aria-hidden="true"
											class="h-4 w-4 flex-shrink-0 text-text-muted transition-transform duration-base {isOpen
												? 'rotate-180'
												: ''}"
										>
											<path d="m5 7.5 5 5 5-5" stroke-linecap="round" stroke-linejoin="round" />
										</svg>
									</button>
								</h3>
								{#if isOpen}
									<div
										id={`cp-section-${section.id}`}
										transition:slide={{ duration: 280, easing: cubicOut }}
									>
										<div class="px-4 pb-5 pt-1">
											{#if section.id === 'classificacao'}
												<div class="grid grid-cols-1 gap-x-4 gap-y-4 md:grid-cols-2">
													<div class="flex flex-col gap-1.5">
														<label for="cp-delivery" class={labelClass}>Tipo de entrega</label>
														<select id="cp-delivery" bind:value={deliveryType} class={fieldClass}>
															<option value="">Selecione o tipo</option>
															{#each deliveryTypes as dt (dt)}
																<option value={dt}>{dt}</option>
															{/each}
														</select>
													</div>
													<div class="flex flex-col gap-1.5">
														<label for="cp-special" class={labelClass}>Projetos especiais</label>
														<select id="cp-special" bind:value={specialProject} class={fieldClass}>
															<option value="">Nenhum</option>
															{#each specialOptions as sp (sp)}
																<option value={sp}>{sp}</option>
															{/each}
														</select>
													</div>
												</div>
											{:else if section.id === 'objetivos'}
												<div class="flex flex-col gap-4">
													<div class="grid grid-cols-1 gap-x-4 gap-y-4 md:grid-cols-2">
														<div class="flex flex-col gap-1.5">
															<label for="cp-objetivo" class={labelClass}>Objetivo EEGD</label>
															<select
																id="cp-objetivo"
																bind:value={objetivoId}
																onchange={onObjetivoChange}
																class={fieldClass}
															>
																<option value="">Selecione um objetivo</option>
																{#each objetivos as obj (obj.id)}
																	<option value={String(obj.id)}>{obj.descricao}</option>
																{/each}
															</select>
														</div>
														<div class="flex flex-col gap-1.5">
															<label for="cp-resultado" class={labelClass}>Resultado esperado EEGD</label>
															<select
																id="cp-resultado"
																bind:value={resultadoId}
																onchange={onResultadoChange}
																disabled={!objetivoId || resultadosLoading}
																class={fieldClass}
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
													</div>

													<div class="flex flex-col gap-2">
														<span class="flex items-baseline justify-between gap-2">
															<span class={labelClass}>Indicadores EEGD</span>
															{#if selectedIndicadores.length > 0}
																<span class="text-xs text-text-muted">
																	{selectedIndicadores.length}/{maxIndicadoresSelecionaveis} selecionados
																</span>
															{/if}
														</span>
														{#if indicadoresLoading}
															<p
																role="status"
																aria-live="polite"
																class="flex items-center gap-2 text-sm text-text-secondary"
															>
																{@render spinner()}Carregando indicadores...
															</p>
														{:else if !resultadoId}
															<p class="text-sm text-text-muted">
																Selecione um resultado esperado para ver os indicadores disponíveis.
															</p>
														{:else if indicadores.length === 0}
															<p class="text-sm text-text-muted">
																Nenhum indicador disponível para este resultado esperado.
															</p>
														{:else}
															<div class="flex flex-col gap-1">
																{#each indicadores as ind (ind.id)}
																	<!-- div (não label) p/ que SÓ o clique na caixa marque; a11y via aria-label. -->
																	<div
																		class="flex items-start gap-2.5 py-1 text-sm text-text-primary transition-[opacity,transform] duration-300 {revealedIndicadores.has(
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
																			class="mt-0.5 h-4 w-4 shrink-0 rounded border-border-subtle text-primary-600 focus:ring-primary-500"
																		/>
																		<span>{ind.descricao}</span>
																	</div>
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
											{:else if section.id === 'links'}
												<div class="flex flex-col gap-4">
													<div class="grid grid-cols-1 gap-x-4 gap-y-4 md:grid-cols-2">
														<div class="flex flex-col gap-1.5">
															<label for="cp-sei" class={labelClass}>Processo SEI-RJ</label>
															<input
																id="cp-sei"
																value={seiProcess}
																oninput={onSeiInput}
																type="text"
																maxlength="25"
																placeholder="SEI-000000/000000/0000"
																class={fieldClass}
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
														<label for="cp-obs" class={labelClass}>
															Observações
														</label>
														<textarea
															id="cp-obs"
															bind:value={observacao}
															rows="3"
															placeholder="Digite observações detalhadas sobre o projeto..."
															class={areaClass}
														></textarea>
													</div>
												</div>
											{:else}
												<div class="flex flex-col gap-4">
													<div class="grid grid-cols-1 gap-x-4 gap-y-4 md:grid-cols-3">
														<div class="flex flex-col gap-1.5 md:col-span-2">
															<label for="cp-template" class={labelClass}>Importar modelo</label>
															<select
																id="cp-template"
																bind:value={templateId}
																onchange={onTemplateChange}
																class={fieldClass}
															>
																<option value="">Não importar / limpar etapas</option>
																{#each templates as tpl (tpl.id)}
																	<option value={String(tpl.id)}>{tpl.name}</option>
																{/each}
															</select>
														</div>
														<div class="flex flex-col gap-1.5">
															<label for="cp-start" class={labelClass}>Data de início</label>
															<input
																id="cp-start"
																bind:value={startDate}
																type="date"
																title="Sem data, o preview mostra só a duração de cada etapa."
																class={fieldClass}
															/>
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
														<!-- Timeline minimalista: fio vertical + pontos vazados; nome à
														     esquerda, datas tabulares à direita — sem caixa nem badges. -->
														<div
															transition:slide={{ duration: 240, easing: cubicOut }}
															class="flex flex-col"
														>
															<div
																class="flex items-baseline justify-between gap-3 border-b border-border-subtle pb-2"
															>
																<span
																	class="text-xs font-medium uppercase tracking-wide text-text-muted"
																>
																	Etapas importadas
																</span>
																<span class="text-xs tabular-nums text-text-muted">
																	{previewStages.length}
																	{previewStages.length === 1 ? 'etapa' : 'etapas'} ·
																	{previewTotalDuration} dias
																</span>
															</div>
															<ol class="relative flex flex-col py-1.5">
																<span
																	aria-hidden="true"
																	class="absolute bottom-[1.1rem] left-[3px] top-[1.1rem] w-px bg-border-subtle"
																></span>
																{#each previewStages as stage, index (index)}
																	<li
																		class="relative flex items-baseline justify-between gap-4 py-2 pl-5"
																	>
																		<span
																			aria-hidden="true"
																			class="absolute left-0 top-1/2 h-[7px] w-[7px] -translate-y-1/2 rounded-full border-[1.5px] border-text-muted bg-surface"
																		></span>
																		<span class="flex min-w-0 items-baseline gap-2">
																			<span class="shrink-0 text-xs tabular-nums text-text-muted">
																				{String(index + 1).padStart(2, '0')}
																			</span>
																			<span class="min-w-0 truncate text-sm text-text-primary">
																				{stage.name}
																			</span>
																		</span>
																		<!-- Colunas fixas: intervalo (largura constante em tabular-nums)
																		     e duração alinhada à direita — sem serrilhado entre linhas. -->
																		<span
																			class="flex shrink-0 items-baseline gap-1.5 text-xs tabular-nums text-text-muted"
																		>
																			{#if stage.rangeText}
																				<span>{stage.rangeText}</span>
																				<span aria-hidden="true">·</span>
																			{/if}
																			<span class="w-14 text-right">
																				{stage.duration}
																				{stage.duration === 1 ? 'dia' : 'dias'}
																			</span>
																		</span>
																	</li>
																{/each}
															</ol>
															{#if previewStart && previewEnd}
																<p
																	class="border-t border-border-subtle pt-2 text-xs text-text-muted"
																>
																	Início em
																	<span class="font-medium text-text-secondary">{previewStart}</span>
																	· término previsto em
																	<span class="font-medium text-text-secondary">{previewEnd}</span>
																</p>
															{/if}
														</div>
													{:else}
														<p class="text-sm text-text-muted">
															Selecione um modelo para visualizar as etapas importadas.
														</p>
													{/if}
												</div>
											{/if}
										</div>
									</div>
								{/if}
							</section>
						{/each}
					</div>
				</div>

				<!-- Rodapé fixo (mesma altura do cabeçalho: h-14) -->
				<footer
					class="flex h-14 flex-shrink-0 items-center justify-between gap-3 border-t border-border-subtle px-6"
				>
					<p class="hidden items-center gap-1 text-xs text-text-muted sm:flex">
						<kbd
							class="rounded border border-border-subtle bg-surface-muted px-1.5 py-0.5 font-mono text-2xs text-text-secondary"
						>
							Ctrl
						</kbd>
						<span aria-hidden="true">+</span>
						<kbd
							class="rounded border border-border-subtle bg-surface-muted px-1.5 py-0.5 font-mono text-2xs text-text-secondary"
						>
							Enter
						</kbd>
						<span class="ml-1">para criar</span>
					</p>
					<div class="flex items-center gap-2">
						<button
							type="button"
							onclick={requestClose}
							disabled={submitting}
							class="inline-flex h-9 items-center rounded-md px-3.5 text-sm font-medium text-text-secondary transition-colors duration-fast hover:bg-surface-muted disabled:opacity-60 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
						>
							Cancelar
						</button>
						<button
							type="submit"
							disabled={submitting}
							class="inline-flex h-9 items-center justify-center gap-2 rounded-md bg-brand-gradient px-4 text-sm font-medium text-white transition-[filter,opacity] duration-fast hover:brightness-110 active:brightness-95 disabled:cursor-not-allowed disabled:opacity-60 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-1"
						>
							{#if submitting}
								{@render spinner()}Criando…
							{:else}
								Criar projeto
							{/if}
						</button>
					</div>
				</footer>
			</form>

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
								class="inline-flex h-8 items-center rounded-md bg-danger px-3 text-xs font-semibold text-white transition-opacity duration-fast hover:opacity-90 focus:outline-none focus-visible:ring-2 focus-visible:ring-danger focus-visible:ring-offset-1"
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
