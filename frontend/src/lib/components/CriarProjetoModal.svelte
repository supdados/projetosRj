<script lang="ts">
	/**
	 * Modal "Criar novo projeto" (v2). A fase ESSENCIAL tem 3 passos (nome →
	 * descrição → prioridade + área) e TERMINA CRIANDO o projeto; daí em diante o
	 * hub "Resumo do cadastro" salva cada seção complementar por update no projeto
	 * que já existe:
	 *   1. `passo1..3` — essencial; o último dispara o `POST /api/projetos` ÚNICO
	 *      (título, órgão, prioridade, descrição), o confete e leva ao hub;
	 *   2. `hub` — "Projeto criado!" na 1ª visita; lista das 4 seções (Objetivos e
	 *      indicadores · Detalhes · Links · Etapas) + lápis para reeditar os
	 *      essenciais via `/inline`;
	 *   3. `secao` — uma seção por vez; salva via `/inline` (ou
	 *      `/importar-modelo` nas Etapas) e pula para a próxima pendente;
	 *   4. `done` — "Cadastro concluído": "Criar novo projeto" (reseta) e
	 *      "Ver o projeto" (`onCreated(result)` → a página navega).
	 *
	 * Mantém (paridade funcional):
	 *   - combobox ABEP filtrável (LEGADO, oculto via SHOW_ABEP);
	 *   - cascata objetivo→resultado→indicadores via `/api/resultados`/
	 *     `indicadores` legados, com revelação escalonada (índice·100ms) e LIMITE
	 *     de 4 indicadores (flash 'Você pode selecionar no máximo 4 indicadores');
	 *   - MÚLTIPLOS processos SEI via `SeiProcessField`;
	 *   - modelo de etapas com preview read-only (datas em dias ÚTEIS, iguais às
	 *     que o servidor grava);
	 *   - Esc: na seção volta ao hub; nas demais fases fecha (com confirmação de
	 *     descarte só antes de criar) · Ctrl/Cmd+Enter dispara a ação primária.
	 *
	 * `onCreatedDismissed(result)` dispara em QUALQUER fechamento posterior à
	 * criação (✕, Esc, backdrop, "Salvar e fechar"), para a página listar o
	 * projeto novo mesmo sem "Ver o projeto".
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
		type CreateProjectResult,
		type ObjetivoCatalogo,
		type ResultadoCatalogo,
		type IndicadorCatalogo,
		type TemplateOption,
		type TemplateStage
	} from '$lib/api/projects';
	import {
		applyStageTemplate,
		saveDetailsSection,
		saveEssentials,
		saveGoalsSection,
		saveLinksSection
	} from '$lib/api/projectSections';
	import { addBusinessDays, nextBusinessDay } from '$lib/utils/businessDays';
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
	import type { AbepIndicadorOption, ProjectsListOptions } from '$lib/types/projects';
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
	const CUSTOM_LINK_MAX = 3;

	/** Seções complementares do hub, na ordem em que são numeradas (01..04). */
	const HUB_SECTIONS = [
		{ title: 'Objetivos e indicadores', subtitle: 'Resultados esperados e medição' },
		{ title: 'Detalhes', subtitle: 'Órgão, tipo de entrega, processo SEI e observações' },
		{ title: 'Links', subtitle: 'Documentos e links do projeto' },
		{ title: 'Etapas', subtitle: 'Marcos e prazos' }
	];

	type Fase = 'passo1' | 'passo2' | 'passo3' | 'hub' | 'secao' | 'done';

	// --- Máquina de estados --------------------------------------------------
	let fase = $state<Fase>('passo1');
	let secaoAtiva = $state(0);
	let secaoSalva = $state<boolean[]>([false, false, false, false]);
	let projetoCriado = $state<CreateProjectResult | null>(null);
	let justCreated = $state(false);
	let editandoEssenciais = $state(false);
	let salvandoSecao = $state(false);
	// Trava anti-duplicação: importar-modelo ACRESCENTA etapas a cada chamada.
	let etapasImportadas = $state<number | null>(null);
	let modeloImportadoLabel = $state('');

	// --- Campos essenciais (passos 1-3) --------------------------------------
	let titulo = $state('');
	let orgaoId = $state('');
	let prioridade = $state('baixa');
	let shortDescription = $state('');

	// --- Seção "Detalhes" ----------------------------------------------------
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

	// --- ABEP combobox -----------------------------------------------------
	// LEGADO (jun/2026): o campo sai da UI mas o código fica intacto para
	// reativação futura — basta alternar SHOW_ABEP para `true`. O backend segue
	// aceitando `abep_indicator` no payload.
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
	// Links personalizados (até 3): pares {nome, url} livres. Snapshot restaura no
	// Escape; carrega o índice p/ não restaurar valores de OUTRA linha aberta.
	let customLinks = $state<{ label: string; url: string }[]>([]);
	let customLinkSnapshot = $state<{ index: number; label: string; url: string } | null>(null);
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
	let hubPrimaryBtn = $state<HTMLButtonElement | null>(null);
	// Origem do confete: a própria arte do popper na tela de sucesso.
	let successIconEl = $state<HTMLElement | null>(null);
	let verProjetoBtn = $state<HTMLButtonElement | null>(null);
	let secaoHeadingEl = $state<HTMLHeadingElement | null>(null);
	// Descrição do passo 2 cresce com o conteúdo (underline sempre colado ao texto).
	let assistDescEl = $state<HTMLTextAreaElement | null>(null);
	let triedAssist1 = $state(false);
	let triedAssist2 = $state(false);
	// Garante onCreatedDismissed em qualquer caminho de fechamento pós-criação.
	let lastCreatedThisOpen: CreateProjectResult | null = null;
	// Valores dos essenciais ao entrar em edição: "Cancelar" desfaz o rascunho.
	let essenciaisSnapshot: {
		titulo: string;
		shortDescription: string;
		prioridade: string;
		orgaoId: string;
	} | null = null;

	// Picker de ESCRITA (§5.4): só órgãos com rank >= editor
	// (orgaos_assignable_options); o filtro da lista continua em orgaos_options.
	const orgaoOptions = $derived(
		(options?.orgaos_assignable_options ?? []).map((o) => ({
			value: String(o.id),
			label: o.sigla || o.nome,
			sigla: o.sigla,
			nome: o.nome,
			pai_id: o.pai_id
		}))
	);
	// Adapta a lista plana ao shape numérico do OrgaoTreeSelect.
	const orgaoTreeOptions = $derived<OrgaoSelectOption[]>(
		orgaoOptions.map((o) => ({
			value: Number(o.value),
			label: o.label,
			sigla: o.sigla,
			nome: o.nome,
			pai_id: o.pai_id
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
	// O que o usuário digitou manda: depois de reeditar os essenciais o título do
	// hub precisa refletir o rascunho, não o `project` devolvido na criação.
	const createdTitulo = $derived(titulo.trim() || projetoCriado?.project?.titulo || '');
	const prioridadeLabel = $derived(
		PRIORITIES.find((p) => p.value === prioridade)?.label ?? 'Baixa'
	);
	const secoesSalvas = $derived(secaoSalva.filter(Boolean).length);
	const isFaseEssencial = $derived(
		fase === 'passo1' || fase === 'passo2' || fase === 'passo3'
	);
	const modeloSelecionadoLabel = $derived(
		templates.find((t) => String(t.id) === templateId)?.name ?? ''
	);

	const dialogWidthClass = $derived.by(() => {
		if (fase === 'hub') return 'max-w-[560px]';
		if (fase === 'secao' && secaoAtiva === 0) return 'max-w-[980px]';
		return 'max-w-[620px]';
	});
	// Todas as fases ancoram o topo no mesmo ponto (não centralizam), para o card
	// não subir/descer conforme a altura do conteúdo.
	const outerAlignClass = 'items-start justify-center pt-[14vh]';
	// Passos compactos e "done" deixam o dropdown de área escapar do card
	// (overflow visível) em vez de ser cortado.
	const dialogOverflowClass = $derived(
		isFaseEssencial || fase === 'done' ? 'overflow-visible' : 'overflow-hidden'
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
	// read-only com orgaoId vazio — beco sem saída no "Criar projeto".
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
		if (fase === 'passo2' && assistDescEl) {
			void shortDescription;
			void tick().then(() => resizeTextarea(assistDescEl));
		}
	});

	function resetForm(): void {
		fase = 'passo1';
		secaoAtiva = 0;
		secaoSalva = [false, false, false, false];
		projetoCriado = null;
		justCreated = false;
		editandoEssenciais = false;
		essenciaisSnapshot = null;
		salvandoSecao = false;
		etapasImportadas = null;
		modeloImportadoLabel = '';
		titulo = '';
		// Pré-seleciona quando há um único órgão ATRIBUÍVEL (paridade Jinja).
		const opts = options?.orgaos_assignable_options ?? [];
		orgaoId = opts.length === 1 ? String(opts[0].id) : '';
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
		customLinks = [];
		customLinkSnapshot = null;
		observacao = '';
		templateId = '';
		templateStages = [];
		startDate = '';
		startDatePickerOpen = false;
		resultadosLoading = false;
		indicadoresLoading = false;
		templateLoading = false;
		triedAssist1 = false;
		triedAssist2 = false;
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
	const customLinksFilled = $derived(
		customLinks.filter((cl) => cl.label.trim().length > 0 && cl.url.trim().length > 0).length
	);
	const linkRowsFilled = $derived(
		[githubLink, documentationLink, productLink].filter((v) => v.trim().length > 0).length +
			customLinksFilled
	);
	const totalLinkSlots = $derived(3 + customLinks.length);
	const linkRowsSummary = $derived.by(() => {
		if (linkRowsFilled === 0) return '';
		const base = `${linkRowsFilled} de ${totalLinkSlots} itens preenchidos.`;
		if (customLinks.length >= CUSTOM_LINK_MAX) {
			return `${base} Limite de ${CUSTOM_LINK_MAX} links personalizados atingido.`;
		}
		return base;
	});

	function addCustomLink(): void {
		if (customLinks.length >= CUSTOM_LINK_MAX) return;
		customLinks = [...customLinks, { label: '', url: '' }];
		// Adicionar ja declara intencao de digitar: foca o Nome da linha nova.
		void tick().then(() => {
			const cards = document.querySelectorAll('.cp-custom-link-card');
			cards[cards.length - 1]?.querySelector<HTMLInputElement>('input')?.focus();
		});
	}

	function removeCustomLink(index: number): void {
		customLinks = customLinks.filter((_, i) => i !== index);
		customLinkSnapshot = null;
	}

	function snapshotCustomLink(index: number): void {
		const cl = customLinks[index];
		customLinkSnapshot = cl ? { index, label: cl.label, url: cl.url } : null;
	}

	// Confirma a edição (descarta o snapshot); retorna se houve mudança.
	function confirmCustomLink(index: number): boolean {
		const snap = customLinkSnapshot;
		if (!snap || snap.index !== index) return false;
		customLinkSnapshot = null;
		const cl = customLinks[index];
		if (!cl) return false;
		return cl.label.trim() !== snap.label.trim() || cl.url.trim() !== snap.url.trim();
	}

	function cancelCustomLink(index: number): void {
		const snap = customLinkSnapshot;
		if (!snap || snap.index !== index) return;
		customLinkSnapshot = null;
		const cl = customLinks[index];
		if (!cl) return;
		cl.label = snap.label;
		cl.url = snap.url;
	}

	let customRowRefs = $state<LinkFieldRow[]>([]);

	function focusCustomUrl(event: KeyboardEvent): void {
		const card = (event.currentTarget as HTMLElement).closest('.cp-custom-link-card');
		card?.querySelector<HTMLElement>('[data-cp-custom-url]')?.focus();
	}

	// Blur para fora do editor confirma a linha (paridade com o editor default);
	// linha ainda totalmente vazia e descartada em vez de ficar aberta.
	function onCustomEditorFocusOut(event: FocusEvent, index: number): void {
		const wrapper = event.currentTarget as HTMLElement;
		if (event.relatedTarget instanceof Node && wrapper.contains(event.relatedTarget)) return;
		const cl = customLinks[index];
		if (cl && cl.label.trim() === '' && cl.url.trim() === '') {
			removeCustomLink(index);
			return;
		}
		customRowRefs[index]?.confirmFromEditor();
	}

	function onCustomLabelKeydown(event: KeyboardEvent, index: number): void {
		if (event.key === 'Enter') {
			event.preventDefault();
			focusCustomUrl(event);
			return;
		}
		if (event.key === 'Escape') {
			event.preventDefault();
			event.stopPropagation();
			customRowRefs[index]?.cancelFromEditor();
		}
	}

	function onCustomUrlKeydown(event: KeyboardEvent, index: number): void {
		if (event.key === 'Enter') {
			event.preventDefault();
			customRowRefs[index]?.confirmFromEditor();
			return;
		}
		if (event.key === 'Escape') {
			event.preventDefault();
			event.stopPropagation();
			customRowRefs[index]?.cancelFromEditor();
		}
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
		// `importar-modelo` devolve 422 sem `start_date`: escolher o modelo já
		// garante uma data válida.
		if (!startDate) startDate = new Date().toLocaleDateString('sv-SE');
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

	// Dias ÚTEIS: `import_template_stages` pula fim de semana; com dias corridos o
	// preview mostrava datas que o servidor nunca grava.
	const previewStages = $derived.by<PreviewStage[]>(() => {
		if (!templateStages.length) return [];
		const start = parseIsoDate(startDate);
		let cursor = start ? nextBusinessDay(start) : null;
		return templateStages.map((etapa) => {
			const duration = Math.max(1, Number.parseInt(String(etapa.duration), 10) || 1);
			let startText = '';
			if (cursor) {
				const stageEnd = addBusinessDays(cursor, duration - 1);
				startText = `início ${formatBrShort(cursor)}`;
				cursor = addBusinessDays(stageEnd, 1);
			}
			return { name: etapa.name, startText, duration };
		});
	});

	const previewTotalDuration = $derived(
		previewStages.reduce((sum, s) => sum + s.duration, 0)
	);
	const previewStart = $derived.by(() => {
		const start = parseIsoDate(startDate);
		return start ? formatBrDate(nextBusinessDay(start)) : null;
	});
	const previewEnd = $derived.by(() => {
		const start = parseIsoDate(startDate);
		if (!start || !templateStages.length) return null;
		let cursor = nextBusinessDay(start);
		let lastEnd = cursor;
		for (const etapa of templateStages) {
			const duration = Math.max(1, Number.parseInt(String(etapa.duration), 10) || 1);
			lastEnd = addBusinessDays(cursor, duration - 1);
			cursor = addBusinessDays(lastEnd, 1);
		}
		return formatBrDate(lastEnd);
	});

	// --- Confirmação de descarte (só antes da criação) ----------------------

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
		if (submitting || salvandoSecao) return;
		// Pós-criação: o projeto já existe — nada a descartar.
		if (projetoCriado || !formIsDirty) {
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
	// offsetParent null = elemento com display:none: .focus() seria no-op e o foco
	// cairia no body, fora do trap.
	function focusAfterTick(getEl: () => HTMLElement | null | undefined): void {
		void tick().then(() => {
			const el = getEl();
			const visible = el && el.offsetParent !== null ? el : dialogEl;
			visible?.focus();
		});
	}

	function irParaPasso1(): void {
		fase = 'passo1';
		focusAfterTick(() => titleInputEl);
	}

	function irParaPasso2(): void {
		triedAssist1 = true;
		if (!titulo.trim()) {
			titleInputEl?.focus();
			return;
		}
		fase = 'passo2';
		focusAfterTick(() => assistDescEl);
	}

	function irParaPasso3(): void {
		fase = 'passo3';
		focusAfterTick(() => document.querySelector<HTMLElement>('#cp-prioridade button'));
	}

	function primeiraPendente(): number {
		return secaoSalva.findIndex((s) => !s);
	}

	function abrirSecao(index: number): void {
		startDatePickerOpen = false;
		if (index < 0) {
			fase = 'done';
			focusAfterTick(() => verProjetoBtn);
			return;
		}
		justCreated = false;
		secaoAtiva = index;
		fase = 'secao';
		focusAfterTick(() => secaoHeadingEl);
	}

	function voltarAoHub(): void {
		fase = 'hub';
		startDatePickerOpen = false;
		focusAfterTick(() => hubPrimaryBtn);
	}

	function editarEssenciais(): void {
		essenciaisSnapshot = { titulo, shortDescription, prioridade, orgaoId };
		editandoEssenciais = true;
		justCreated = false;
		irParaPasso1();
	}

	function cancelarEdicaoEssenciais(): void {
		if (essenciaisSnapshot) {
			({ titulo, shortDescription, prioridade, orgaoId } = essenciaisSnapshot);
			essenciaisSnapshot = null;
		}
		editandoEssenciais = false;
		voltarAoHub();
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

	// --- Criação (fim da fase essencial) e saves das seções ------------------

	/**
	 * Cria o projeto com os 4 campos essenciais, festeja e abre o hub. Chamada
	 * só pelo primário do passo 3 fora do modo de edição.
	 */
	async function criarProjeto(): Promise<void> {
		triedAssist2 = true;
		if (!titulo.trim()) {
			triedAssist1 = true;
			irParaPasso1();
			return;
		}
		if (!orgaoId.trim()) return; // erro inline via assistOrgaoError
		if (submitting || projetoCriado) return;
		submitting = true;
		try {
			const result = await createProject({
				titulo: titulo.trim(),
				orgao_id: orgaoId,
				prioridade,
				short_description: shortDescription.trim() || undefined
			});
			projetoCriado = result;
			lastCreatedThisOpen = result;
			// Confete só depois da tela de sucesso pintar (animate-panel-in ~320ms),
			// com origem medida na arte do popper — nunca no centro do viewport.
			setTimeout(() => {
				if (!open || fase !== 'hub' || !justCreated || !successIconEl) return;
				const rect = successIconEl.getBoundingClientRect();
				triggerTaskFinalizeConfetti({
					x: rect.left + rect.width / 2,
					y: rect.top + rect.height / 2
				});
			}, 420);
			justCreated = true;
			fase = 'hub';
			focusAfterTick(() => hubPrimaryBtn);
		} catch (err) {
			flashApiError(err, 'Ocorreu um erro ao adicionar o projeto.');
		} finally {
			submitting = false;
		}
	}

	/** Reedição dos essenciais depois da criação (lápis do hub). */
	async function salvarEssenciais(): Promise<void> {
		const pid = projetoCriado?.id;
		if (!pid || submitting) return;
		triedAssist1 = true;
		triedAssist2 = true;
		if (!titulo.trim()) {
			irParaPasso1();
			return;
		}
		if (!orgaoId.trim()) return;
		submitting = true;
		try {
			await saveEssentials(pid, {
				titulo: titulo.trim(),
				short_description: shortDescription.trim(),
				prioridade,
				orgao_id: Number(orgaoId)
			});
			editandoEssenciais = false;
			essenciaisSnapshot = null;
			voltarAoHub();
		} catch (err) {
			flashApiError(err, 'Não foi possível salvar as informações do projeto.');
		} finally {
			submitting = false;
		}
	}

	/** Persiste a seção ativa. Só marca `secaoSalva` em caso de sucesso. */
	async function salvarSecao(): Promise<boolean> {
		const pid = projetoCriado?.id;
		if (!pid || salvandoSecao) return false;
		salvandoSecao = true;
		try {
			if (secaoAtiva === 0) {
				await saveGoalsSection(pid, {
					objetivo_id: objetivoId ? Number(objetivoId) : null,
					resultado_esperado_id: resultadoId ? Number(resultadoId) : null,
					indicadores_ids: selectedIndicadores,
					abep_indicator: abepValue
				});
			} else if (secaoAtiva === 1) {
				await saveDetailsSection(pid, {
					orgao: orgaoTexto.trim(),
					delivery_type: deliveryType,
					special_project: specialProject,
					sei_processes: seiList,
					observacao: observacao.trim()
				});
			} else if (secaoAtiva === 2) {
				await saveLinksSection(pid, {
					github_link: githubLink.trim(),
					documentation_link: documentationLink.trim(),
					product_link: productLink.trim(),
					custom_links: customLinks
						.filter((cl) => cl.label.trim() && cl.url.trim())
						.map((cl) => ({ label: cl.label.trim(), url: cl.url.trim() }))
				});
			} else if (templateId && startDate && etapasImportadas === null) {
				const res = await applyStageTemplate(pid, Number(templateId), startDate);
				etapasImportadas = res.etapas_criadas;
				modeloImportadoLabel = modeloSelecionadoLabel;
			}
			secaoSalva = secaoSalva.map((v, i) => (i === secaoAtiva ? true : v));
			return true;
		} catch (err) {
			flashApiError(err, 'Não foi possível salvar esta seção.');
			return false;
		} finally {
			salvandoSecao = false;
		}
	}

	async function salvarEContinuar(): Promise<void> {
		if (!(await salvarSecao())) return;
		abrirSecao(primeiraPendente());
	}

	function salvarEFechar(): void {
		if (fase !== 'secao') {
			closeAndNotify();
			return;
		}
		void salvarSecao().then((ok) => {
			if (ok) closeAndNotify();
		});
	}

	/** "Criar outro projeto" na tela final: limpa e volta ao passo 1. */
	function startAnotherProject(): void {
		resetForm();
		void tick().then(() => titleInputEl?.focus());
	}

	/** Ação primária da fase atual (botão principal e Ctrl/Cmd+Enter). */
	function phasePrimaryAction(): void {
		if (fase === 'passo1') {
			irParaPasso2();
			return;
		}
		if (fase === 'passo2') {
			irParaPasso3();
			return;
		}
		if (fase === 'passo3') {
			void (editandoEssenciais ? salvarEssenciais() : criarProjeto());
			return;
		}
		if (fase === 'hub') {
			abrirSecao(primeiraPendente());
			return;
		}
		if (fase === 'secao') {
			void salvarEContinuar();
			return;
		}
		if (projetoCriado) onCreated(projetoCriado);
	}

	// --- Rótulos/ações do rodapé (espelham a máquina de estados) -------------

	const primaryLabel = $derived.by(() => {
		if (fase === 'passo1' || fase === 'passo2') return 'Continuar';
		if (fase === 'passo3') return editandoEssenciais ? 'Salvar' : 'Criar projeto';
		if (fase === 'hub') return primeiraPendente() < 0 ? 'Concluir cadastro' : 'Continuar cadastro';
		if (fase === 'secao') return 'Salvar e continuar';
		return 'Ver o projeto';
	});
	const secondaryLabel = $derived.by(() => {
		if (fase === 'passo2' || fase === 'passo3' || fase === 'secao') return 'Voltar';
		// Único atalho de navegação para o projeto recém-criado sem ter de
		// percorrer as 4 seções opcionais até a tela final.
		if (fase === 'hub' && projetoCriado) return 'Ver o projeto';
		return '';
	});
	const ghostLabel = $derived(editandoEssenciais ? 'Cancelar edição' : 'Cancelar');

	function secondaryAction(): void {
		if (fase === 'passo2') {
			irParaPasso1();
			return;
		}
		if (fase === 'passo3') {
			fase = 'passo2';
			focusAfterTick(() => assistDescEl);
			return;
		}
		if (fase === 'hub') {
			if (projetoCriado) onCreated(projetoCriado);
			return;
		}
		// "Voltar" não persiste: salvar é só do primário e do "Salvar e fechar".
		voltarAoHub();
	}

	function ghostAction(): void {
		if (editandoEssenciais) {
			cancelarEdicaoEssenciais();
			return;
		}
		requestClose();
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
			// Na seção o Esc volta ao hub SEM salvar (o estado local sobrevive
			// enquanto o modal estiver aberto).
			if (fase === 'secao') {
				voltarAoHub();
				return;
			}
			requestClose();
		}
	}

	// --- Classes utilitárias (campos com visual unificado) -------------------
	const labelClass = 'text-2xs font-bold uppercase tracking-[.08em] text-text-label';
	const microLabelClass = 'text-2xs font-bold uppercase tracking-[.07em] text-text-faint';
	const fieldBaseClass =
		'w-full rounded-control border border-border-strong bg-surface px-3.5 leading-tight text-text-primary placeholder:text-text-faint transition-colors duration-fast focus:border-primary-600 focus:outline-none disabled:opacity-60';
	const fieldClass = `h-11 text-base ${fieldBaseClass}`;
	// Altura dos controles compostos (SelectMenu/SEI/OrgaoTreeSelect) — usada onde
	// campos nativos dividem linha com eles.
	const fieldMdClass = `h-[var(--control-h-md)] text-sm ${fieldBaseClass}`;
	const areaClass =
		'w-full rounded-control border border-border-strong bg-surface px-3.5 py-3 text-base text-text-primary placeholder:text-text-faint transition-colors duration-fast focus:border-primary-600 focus:outline-none';
	const sectionTitleClass = 'font-heading text-2xl font-semibold text-text-primary';
	const emptyBoxClass =
		'rounded-control border border-dashed border-icon-faint bg-surface-muted px-4 py-3.5 text-sm text-text-faint';
	// whitespace-nowrap: o rodapé tem 3 ações e o card do hub é estreito — sem
	// isso os rótulos quebram em duas linhas.
	const btnPrimaryClass =
		'inline-flex h-11 items-center justify-center gap-2 whitespace-nowrap rounded-control bg-brand px-5 text-[15px] font-semibold text-on-brand transition-colors duration-fast hover:bg-brand-hover focus:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-1 disabled:cursor-not-allowed disabled:opacity-60';
	const btnSecondaryClass =
		'inline-flex h-11 items-center gap-1.5 whitespace-nowrap rounded-control border border-border-subtle bg-surface px-4 text-[15px] font-semibold text-text-secondary transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:opacity-60';
	const btnGhostClass =
		'inline-flex h-10 items-center whitespace-nowrap rounded-md px-2.5 text-[15px] font-semibold text-text-muted transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:opacity-60';
	const dashedAddClass =
		'inline-flex h-10 w-fit items-center gap-1.5 rounded-control border border-dashed border-icon-faint bg-surface px-4 text-sm font-semibold text-primary-600 transition-colors duration-fast hover:bg-wash-neutral focus:outline-none focus-visible:ring-2 focus-visible:ring-brand';
	const bodyClass = 'max-h-[70vh] min-h-0 flex-1 overflow-y-auto px-10 pb-8 pt-9';
	// Passos essenciais não rolam: o dropdown de área precisa escapar do card.
	const bodyOpenClass = 'px-8 pb-6 pt-7';
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

{#snippet segmentProgress(total: number, done: number, label: string)}
	<div class="mb-5 flex flex-col gap-2">
		<div
			class="flex max-w-[220px] gap-1.5"
			role="progressbar"
			aria-valuemin={0}
			aria-valuemax={total}
			aria-valuenow={done}
			aria-label={label}
		>
			{#each Array.from({ length: total }) as _, i (i)}
				<div
					class="h-1.5 flex-1 rounded-full transition-colors duration-base {i < done
						? 'bg-brand'
						: 'bg-progress-track'}"
				></div>
			{/each}
		</div>
		{#if label}
			<span class={microLabelClass}>{label}</span>
		{/if}
	</div>
{/snippet}

{#snippet editarEssenciaisBtn()}
	<button
		type="button"
		onclick={editarEssenciais}
		aria-label="Editar informações essenciais"
		class="grid h-9 w-9 flex-none place-items-center rounded-md text-icon-faint transition-colors duration-fast hover:bg-surface-muted hover:text-primary-600 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
	>
		<svg
			viewBox="0 0 24 24"
			class="h-4 w-4"
			fill="none"
			stroke="currentColor"
			stroke-width="2"
			stroke-linecap="round"
			stroke-linejoin="round"
			aria-hidden="true"
		>
			<path d="M12 20h9" />
			<path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z" />
		</svg>
	</button>
{/snippet}

{#snippet checkIcon(size: string)}
	<svg viewBox="0 0 20 20" class={size} fill="none" stroke="currentColor" stroke-width="2.4" aria-hidden="true">
		<path d="m4.5 10.5 3.5 3.5 7.5-8" stroke-linecap="round" stroke-linejoin="round" />
	</svg>
{/snippet}

{#snippet footer()}
	<footer
		class="flex flex-none items-center justify-between gap-3 border-t border-border-faint px-6 py-3.5"
	>
		<div>
			{#if isFaseEssencial}
				<button type="button" onclick={ghostAction} class={btnGhostClass} disabled={submitting}>
					{ghostLabel}
				</button>
			{:else if fase === 'hub'}
				<button type="button" onclick={startAnotherProject} class={btnGhostClass}>
					Criar novo projeto
				</button>
			{:else if fase === 'secao'}
				<button
					type="button"
					onclick={salvarEFechar}
					class={btnGhostClass}
					disabled={salvandoSecao}
				>
					Salvar e fechar
				</button>
			{:else}
				<button type="button" onclick={startAnotherProject} class={btnGhostClass}>
					Criar novo projeto
				</button>
			{/if}
		</div>
		<div class="flex items-center gap-2.5">
			{#if secondaryLabel}
				<button
					type="button"
					onclick={secondaryAction}
					class={btnSecondaryClass}
					disabled={submitting || salvandoSecao}
				>
					{secondaryLabel}
				</button>
			{/if}
			{#if fase === 'hub'}
				<button
					type="button"
					bind:this={hubPrimaryBtn}
					onclick={phasePrimaryAction}
					class={btnPrimaryClass}
				>
					{primaryLabel}
				</button>
			{:else if fase === 'done'}
				<button
					type="button"
					bind:this={verProjetoBtn}
					onclick={phasePrimaryAction}
					class={btnPrimaryClass}
				>
					{primaryLabel}
				</button>
			{:else}
				<button
					type="button"
					onclick={phasePrimaryAction}
					disabled={submitting || salvandoSecao}
					class={btnPrimaryClass}
				>
					{#if submitting || salvandoSecao}
						{@render spinner()}{submitting && !editandoEssenciais ? 'Criando…' : 'Salvando…'}
					{:else}
						{primaryLabel}
					{/if}
				</button>
			{/if}
		</div>
	</footer>
{/snippet}

{#if open}
	<div
		class="fixed inset-0 z-50 flex {outerAlignClass} bg-[rgba(7,20,33,0.34)] p-4 backdrop-blur-[1.5px]"
		role="presentation"
		onclick={requestClose}
		onkeydown={onModalKeydown}
		transition:fade={{ duration: 200 }}
	>
		<div
			role="dialog"
			aria-modal="true"
			aria-labelledby="criar-projeto-title"
			bind:this={dialogEl}
			class="relative flex max-h-[92vh] w-full flex-col {dialogOverflowClass} rounded-xl border border-border-subtle bg-surface shadow-modal transition-[max-width] duration-base {dialogWidthClass}"
			style="--cp-grid-w: calc(min(980px, 100vw - 2rem) - 5rem);"
			onclick={(e) => e.stopPropagation()}
			onkeydown={onModalKeydown}
			tabindex="-1"
			use:focusTrap
			transition:fly={{ y: 18, duration: 320, easing: cubicOut }}
		>
			<button
				type="button"
				inert={confirmDiscardOpen}
				onclick={requestClose}
				disabled={submitting || salvandoSecao}
				aria-label="Fechar"
				class="absolute right-3 top-3 z-10 grid h-8 w-8 place-items-center rounded-md text-icon-faint transition-colors duration-fast hover:bg-surface-muted hover:text-text-primary disabled:opacity-60 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
			>
				<svg viewBox="0 0 20 20" class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true">
					<path d="m5 5 10 10M15 5 5 15" stroke-linecap="round" />
				</svg>
			</button>

			{#if fase === 'passo1'}
				<form
					inert={confirmDiscardOpen}
					onsubmit={(e) => {
						e.preventDefault();
						irParaPasso2();
					}}
					class="flex animate-panel-in flex-col"
				>
					<div class={bodyOpenClass}>
						{@render segmentProgress(3, 1, 'Passo 1 de 3')}
						<h3 id="criar-projeto-title" class={sectionTitleClass}>
							Como vai se chamar o projeto?
						</h3>
						<div class="mt-6 flex flex-col gap-1.5">
							<input
								id="cp-titulo"
								bind:this={titleInputEl}
								bind:value={titulo}
								type="text"
								aria-labelledby="criar-projeto-title"
								aria-invalid={assistTituloError}
								placeholder="Digite o nome do projeto…"
								class="w-full border-0 border-b-2 bg-transparent px-0 py-1.5 text-xl text-text-primary placeholder:text-text-faint focus:outline-none {assistTituloError
									? 'border-danger'
									: 'border-primary-600'}"
							/>
							{#if assistTituloError}
								<p class="text-xs text-danger" transition:slide={{ duration: 160, easing: cubicOut }}>
									Informe o título do projeto.
								</p>
							{/if}
						</div>
					</div>
					{@render footer()}
				</form>
			{:else if fase === 'passo2'}
				<form
					inert={confirmDiscardOpen}
					onsubmit={(e) => {
						e.preventDefault();
						irParaPasso3();
					}}
					class="flex animate-panel-in flex-col"
				>
					<div class={bodyOpenClass}>
						{@render segmentProgress(3, 2, 'Passo 2 de 3')}
						<h3 id="criar-projeto-title" class={sectionTitleClass}>Descrição breve</h3>
						<div class="mt-6 flex flex-col gap-1.5">
							<textarea
								id="cp-assist-desc"
								aria-label="Descrição breve do projeto (opcional)"
								bind:this={assistDescEl}
								bind:value={shortDescription}
								rows="1"
								placeholder="Breve descrição do projeto"
								oninput={autoGrowDesc}
								onkeydown={(e) => {
									if (e.key === 'Enter') {
										e.preventDefault();
										irParaPasso3();
									}
								}}
								class="w-full resize-none overflow-hidden border-0 border-b-2 border-border-strong bg-transparent px-0 py-1.5 text-lg text-text-primary placeholder:text-text-faint focus:border-primary-600 focus:outline-none"
							></textarea>
						</div>
					</div>
					{@render footer()}
				</form>
			{:else if fase === 'passo3'}
				<form
					inert={confirmDiscardOpen}
					onsubmit={(e) => {
						e.preventDefault();
						phasePrimaryAction();
					}}
					class="flex animate-panel-in flex-col"
				>
					<div class={bodyOpenClass}>
						{@render segmentProgress(3, 3, 'Passo 3 de 3')}
						<h3 id="criar-projeto-title" class={sectionTitleClass}>Prioridade e responsável</h3>
						<div class="mt-6 flex flex-col gap-6 sm:flex-row sm:items-start sm:gap-9">
							<div class="flex flex-col gap-2">
								<span class={labelClass} id="cp-prioridade-label">Prioridade</span>
								<div
									id="cp-prioridade"
									role="group"
									aria-labelledby="cp-prioridade-label"
									class="flex flex-wrap items-center gap-2"
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
											class="inline-flex h-10 items-center justify-center whitespace-nowrap rounded-md border px-5 text-sm transition-colors duration-fast focus:outline-none focus-visible:ring-2 focus-visible:ring-brand {selected
												? 'font-bold text-on-brand'
												: 'border-border-subtle bg-surface font-semibold text-text-secondary hover:bg-surface-muted'}"
										>
											{p.label}
										</button>
									{/each}
								</div>
							</div>
							<div class="flex w-full min-w-0 flex-col gap-2 sm:max-w-[300px] sm:flex-1">
								<span class={labelClass} id="cp-orgao-label">Área responsável</span>
								{#if orgaoOptions.length === 0}
									<div
										class="flex h-11 items-center justify-between gap-2 rounded-control border border-border-strong bg-surface-muted px-3.5 text-base text-text-faint opacity-60"
									>
										<span class="truncate">Nenhum órgão atribuído</span>
									</div>
								{:else if orgaoOptions.length === 1}
									<div
										class="flex h-11 items-center justify-between gap-2 rounded-control border border-border-strong bg-surface-muted px-3.5 text-base text-text-primary"
									>
										<span class="truncate">{orgaoOptions[0].label}</span>
										<svg viewBox="0 0 20 20" class="h-3.5 w-3.5 flex-none text-icon-faint" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true">
											<rect x="4.5" y="9" width="11" height="7.5" rx="1.5" />
											<path d="M7 9V6.5a3 3 0 0 1 6 0V9" />
										</svg>
									</div>
									<p class="text-xs text-text-faint">Definida pelo seu perfil</p>
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
					</div>
					{@render footer()}
				</form>
			{:else if fase === 'hub'}
				<div inert={confirmDiscardOpen} class="flex animate-panel-in flex-col">
					<div class={bodyClass}>
						{#if justCreated}
							<div class="relative flex flex-col items-center gap-2.5 pb-7 pt-2">
								<!-- Wrapper sem transform: rect estável para a origem do confete. -->
								<span bind:this={successIconEl} class="block h-28 w-28">
									<img
										src="/static/img/confete-popper.png"
										alt=""
										class="cp-success-icon h-28 w-28"
										aria-hidden="true"
									/>
								</span>
								<h2
									id="criar-projeto-title"
									class="font-heading text-[24px] font-bold text-text-primary"
								>
									Projeto criado!
								</h2>
								<p class="text-center text-sm text-text-faint">
									{createdTitulo}{orgaoSelecionadoLabel ? ` · ${orgaoSelecionadoLabel}` : ''}
								</p>
								<div class="absolute right-0 top-0">{@render editarEssenciaisBtn()}</div>
							</div>
						{:else}
							<div class="flex items-start gap-2 pb-5">
								<div class="min-w-0 flex-1">
									<h2
										id="criar-projeto-title"
										class="font-heading text-[24px] font-bold text-text-primary"
									>
										{createdTitulo}
									</h2>
									<p class="mt-1 text-sm text-text-faint">
										{orgaoSelecionadoLabel ? `${orgaoSelecionadoLabel} · ` : ''}prioridade
										{prioridadeLabel.toLowerCase()}
									</p>
								</div>
								{@render editarEssenciaisBtn()}
							</div>
						{/if}

						<p class="pb-3 text-sm text-text-faint">
							{secoesSalvas === HUB_SECTIONS.length
								? 'Todas as informações complementares foram preenchidas.'
								: 'Estas informações ainda não foram preenchidas.'}
						</p>

						<div class="flex flex-col">
							{#each HUB_SECTIONS as section, index (index)}
								{@const feita = secaoSalva[index]}
								<button
									type="button"
									onclick={() => abrirSecao(index)}
									class="flex w-full items-center gap-3 border-t border-border-hairline px-1.5 py-2 text-left transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand"
								>
									<span
										class="grid h-5 w-5 flex-none place-items-center text-[11px] font-bold tabular-nums {feita
											? 'text-success'
											: 'text-text-faint'}"
										aria-hidden="true"
									>
										{#if feita}
											{@render checkIcon('h-3 w-3')}
										{:else}
											{String(index + 1).padStart(2, '0')}
										{/if}
									</span>
									<span class="flex min-w-0 flex-1 flex-col leading-tight">
										<span class="text-sm font-bold text-text-primary">{section.title}</span>
										<span class="text-xs text-text-faint">{section.subtitle}</span>
									</span>
									<span class="flex-none text-base leading-none text-icon-faint" aria-hidden="true">›</span>
									<span class="sr-only">{feita ? 'seção salva' : 'seção pendente'}</span>
								</button>
							{/each}
						</div>
					</div>
					{@render footer()}
				</div>
			{:else if fase === 'secao'}
				<div inert={confirmDiscardOpen} class="flex min-h-0 animate-panel-in flex-col">
					<div class={bodyClass}>
						{@render segmentProgress(
							4,
							Math.max(secoesSalvas, secaoAtiva + 1),
							`Seção ${secaoAtiva + 1} de 4`
						)}
						<h3
							id="criar-projeto-title"
							bind:this={secaoHeadingEl}
							tabindex="-1"
							class="{sectionTitleClass} outline-none"
						>
							{HUB_SECTIONS[secaoAtiva].title}
						</h3>

						<div class="mt-7 flex flex-col gap-5">
							{#if secaoAtiva === 0}
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
												class="absolute left-0 right-0 top-full z-10 mt-1 max-h-64 overflow-auto rounded-control border border-border-strong bg-surface py-1 shadow-md"
											>
												{#if abepVisible.length === 0}
													<li class="px-3 py-2 text-sm text-text-faint">
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
							{:else if secaoAtiva === 1}
								<div class="grid grid-cols-1 gap-x-[22px] gap-y-[18px] md:grid-cols-2">
									<div class="flex flex-col gap-1.5">
										<label for="cp-orgao-texto" class={labelClass}>Órgão</label>
										<input
											id="cp-orgao-texto"
											bind:value={orgaoTexto}
											type="text"
											placeholder="Órgão responsável"
											class={fieldMdClass}
										/>
									</div>
									<div class="flex flex-col gap-1.5">
										<label for="cp-sei" class={labelClass}>Processo SEI-RJ</label>
										<SeiProcessField
											fieldId="cp-sei"
											processes={seiList}
											onSave={(list) => (seiList = list)}
										/>
									</div>
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
										<span id="cp-special-label" class={labelClass}>Projetos especiais</span>
										<div
											id="cp-special"
											role="group"
											aria-labelledby="cp-special-label"
											class="flex items-center gap-2"
										>
											{#each SPECIAL_PROJECTS as sp (sp)}
												{@const selected = specialProject === sp}
												<button
													type="button"
													aria-pressed={selected}
													onclick={() => (specialProject = selected ? '' : sp)}
													class="inline-flex h-[var(--control-h-md)] flex-1 items-center justify-center rounded-control border px-3 text-sm font-semibold transition-colors duration-fast active:scale-[0.97] focus:outline-none focus-visible:ring-2 focus-visible:ring-brand {selected
														? 'border-primary-600 bg-brand text-on-brand'
														: 'border-border-strong bg-surface text-text-secondary hover:border-primary-600'}"
												>
													{sp}
												</button>
											{/each}
										</div>
									</div>
									<div class="flex flex-col gap-1.5 md:col-span-2">
										<label for="cp-obs" class={labelClass}>Observações</label>
										<textarea
											id="cp-obs"
											bind:value={observacao}
											rows="3"
											placeholder="Digite observações detalhadas sobre o projeto…"
											class={areaClass}
										></textarea>
									</div>
								</div>
							{:else if secaoAtiva === 2}
								<div class="flex flex-col gap-3">
									<div class="rounded-control border border-border-subtle">
										<LinkFieldRow
											id="cp-github"
											label="Link GitHub"
											first
											last
											startOpen
											placeholder="https://github.com/..."
											value={githubLink}
											onCommit={(v) => (githubLink = v)}
										/>
									</div>
									<div class="rounded-control border border-border-subtle">
										<LinkFieldRow
											id="cp-doc"
											label="Link documentação"
											first
											last
											startOpen
											placeholder="https://..."
											value={documentationLink}
											onCommit={(v) => (documentationLink = v)}
										/>
									</div>
									<div class="rounded-control border border-border-subtle">
										<LinkFieldRow
											id="cp-product"
											label="Link para o produto"
											first
											last
											startOpen
											placeholder="https://..."
											value={productLink}
											onCommit={(v) => (productLink = v)}
										/>
									</div>
									{#each customLinks as cl, index (cl)}
										<div class="cp-custom-link-card rounded-control border border-border-subtle">
											<LinkFieldRow
												bind:this={customRowRefs[index]}
												id={`cp-custom-${index}`}
												label={cl.label.trim() || 'Link personalizado'}
												first
												last
												startOpen
												filled={cl.label.trim().length > 0 && cl.url.trim().length > 0}
												preview={cl.url}
												onEditorOpen={() => snapshotCustomLink(index)}
												onEditorConfirm={() => confirmCustomLink(index)}
												onEditorCancel={() => cancelCustomLink(index)}
											>
												{#snippet editor()}
													<!-- svelte-ignore a11y_no_static_element_interactions -->
													<div
														class="flex items-start gap-1.5"
														onfocusout={(e) => onCustomEditorFocusOut(e, index)}
													>
														<div class="flex min-w-0 flex-1 flex-col gap-2">
															<input
																bind:value={cl.label}
																type="text"
																maxlength="80"
																placeholder="Nome do link (ex.: Painel de BI)"
																aria-label="Nome do link personalizado"
																onkeydown={(e) => onCustomLabelKeydown(e, index)}
																class="h-10 w-full rounded-control border border-border-strong bg-surface px-3 text-sm leading-tight text-text-primary placeholder:text-text-faint transition-colors duration-fast focus:border-primary-600 focus:outline-none"
															/>
															<input
																data-cp-custom-url
																bind:value={cl.url}
																type="text"
																maxlength="500"
																placeholder="https://..."
																aria-label="URL do link personalizado"
																onkeydown={(e) => onCustomUrlKeydown(e, index)}
																class="h-10 w-full rounded-control border border-border-strong bg-surface px-3 text-sm leading-tight text-text-primary placeholder:text-text-faint transition-colors duration-fast focus:border-primary-600 focus:outline-none"
															/>
														</div>
														<button
															type="button"
															title="Remover link"
															aria-label={`Remover ${cl.label.trim() || 'link personalizado'}`}
															onmousedown={(e) => e.preventDefault()}
															onclick={() => removeCustomLink(index)}
															class="grid h-10 w-9 flex-none place-items-center rounded-md text-icon-faint transition-colors duration-fast hover:bg-surface-muted hover:text-danger active:scale-95 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
														>
															<svg
																viewBox="0 0 24 24"
																class="h-4 w-4"
																fill="none"
																stroke="currentColor"
																stroke-width="2"
																stroke-linecap="round"
																stroke-linejoin="round"
																aria-hidden="true"
															>
																<path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2m2 0v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6" />
																<path d="M10 11v6M14 11v6" />
															</svg>
														</button>
													</div>
												{/snippet}
											</LinkFieldRow>
										</div>
									{/each}
								</div>
								{#if customLinks.length < CUSTOM_LINK_MAX}
									<button type="button" onclick={addCustomLink} class={dashedAddClass}>
										<svg viewBox="0 0 20 20" class="h-3.5 w-3.5" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
											<path d="M10 4.5v11M4.5 10h11" stroke-linecap="round" />
										</svg>
										Adicionar link personalizado
									</button>
								{/if}
								{#if linkRowsSummary}
									<p class="-mt-2 text-sm text-text-faint">{linkRowsSummary}</p>
								{/if}
							{:else if etapasImportadas !== null}
								<!-- importar-modelo ACRESCENTA etapas: depois do primeiro
									 import a seção vira resumo, sem novo POST. -->
								<div
									class="flex items-center gap-3 rounded-control border border-border-subtle bg-surface-muted px-4 py-3.5"
								>
									<span class="grid h-7 w-7 flex-none place-items-center rounded-full bg-success-200 text-success">
										{@render checkIcon('h-3.5 w-3.5')}
									</span>
									<p class="text-sm text-text-secondary">
										{etapasImportadas}
										{etapasImportadas === 1 ? 'etapa criada' : 'etapas criadas'} a partir do modelo
										<span class="font-semibold text-text-primary">{modeloImportadoLabel}</span>.
									</p>
								</div>
							{:else}
								<div class="grid grid-cols-1 gap-x-[22px] gap-y-[18px] md:grid-cols-5">
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
											title="As datas são calculadas em dias úteis a partir daqui."
											onclick={() => (startDatePickerOpen = !startDatePickerOpen)}
											class="{fieldClass} flex items-center text-left"
										>
											<span class={startDate ? '' : 'text-text-faint'}>
												{startDateLabel(startDate) || 'Selecionar data'}
											</span>
										</button>
										{#if startDatePickerOpen && startDateAnchorEl}
											<DatePickerPanel
												anchor={startDateAnchorEl}
												value={startDate || null}
												allowClear={false}
												ariaLabel="Data de início"
												onPick={(iso) => {
													startDate = iso;
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
											class="flex flex-col divide-y divide-border-faint overflow-hidden rounded-control border border-border-subtle"
										>
											{#each previewStages as stage, index (index)}
												<li class="flex items-center gap-3 px-3.5 py-2.5">
													<span class="flex-none text-sm font-semibold tabular-nums text-primary-600">
														{index + 1} <span aria-hidden="true" class="text-icon-faint">-</span>
													</span>
													<span class="min-w-0 flex-1 truncate text-sm font-medium text-text-primary">
														{stage.name}
													</span>
													{#if stage.startText}
														<span class="shrink-0 text-xs tabular-nums text-text-faint">
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
										<p class="text-xs text-text-faint">
											{previewStages.length}
											{previewStages.length === 1 ? 'etapa' : 'etapas'} ·
											{previewTotalDuration} dias úteis
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
					</div>
					{@render footer()}
				</div>
			{:else}
				<div class="flex animate-panel-in flex-col">
					<div class="flex flex-col items-center gap-3 px-10 pb-10 pt-16">
						<img
							src="/static/img/confete-popper.png"
							alt=""
							class="cp-success-icon h-28 w-28"
							aria-hidden="true"
						/>
						<h2 id="criar-projeto-title" class="font-heading text-[24px] font-bold text-text-primary">
							Cadastro concluído
						</h2>
						<p class="max-w-md text-center text-sm text-text-faint">
							{createdTitulo}{orgaoSelecionadoLabel ? ` · ${orgaoSelecionadoLabel}` : ''}
						</p>
					</div>
					{@render footer()}
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
						<p id="cp-discard-desc" class="mt-1 text-xs text-text-faint">
							As informações preenchidas serão perdidas.
						</p>
						<div class="mt-4 flex items-center justify-end gap-2">
							<button
								type="button"
								bind:this={discardCancelBtn}
								onclick={closeDiscardConfirm}
								class="inline-flex h-8 items-center rounded-md px-3 text-xs font-medium text-text-secondary transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
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
