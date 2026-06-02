<script lang="ts">
	/**
	 * Modal "Criar Novo Projeto" (Quick Create) — paridade fiel com o modal
	 * Bootstrap `templates/projects/add_form.html` + `add_form_js.html`.
	 *
	 * Replica:
	 *   - modal grande com seção rápida (título*, área responsável, prioridade,
	 *     descrição, órgão) + accordion de 4 seções colapsáveis (Classificação,
	 *     Objetivos/resultados/indicadores, Links e Observação, Modelo de Etapas);
	 *   - combobox ABEP filtrável com navegação por teclado (Arrow/Enter/Escape);
	 *   - cascata objetivo→resultado→indicadores via `/api/resultados`/`indicadores`
	 *     legados, com animação escalonada (índice·100ms) e LIMITE de 4 indicadores
	 *     (alerta de flash 'Você pode selecionar no máximo 4 indicadores');
	 *   - máscara SEI on-input ('SEI-000000/000000/0000');
	 *   - import de modelo com preview read-only e cálculo de datas no client
	 *     (dias corridos, mesmo algoritmo de `renderTemplateImportPreview`);
	 *   - botão "Criar Projeto" desabilitado até título + área válidos.
	 *
	 * Submit: `POST /api/projetos` (via `createProject`). Em sucesso o COMPONENTE
	 * NÃO navega nem mostra flash — emite `onCreated(result)` e a página decide
	 * (showFlash + goto), replicando o flash success + redirect do Jinja. Em erro,
	 * exibe a mensagem do envelope como flash danger/warning (sem fechar o modal).
	 *
	 * NÃO há som/confete (o fluxo Jinja não tem).
	 */
	import { tick } from 'svelte';
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

	// --- Campos da seção rápida -------------------------------------------
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
	let openSection = $state<string>(''); // accordion: só uma seção aberta
	let catalogsLoaded = $state(false);
	let titleInputEl = $state<HTMLInputElement | null>(null);

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
	$effect(() => {
		if (open) {
			resetForm();
			void loadCatalogs();
			void tick().then(() => titleInputEl?.focus());
		}
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
		openSection = '';
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
		indicadores = [];
		selectedIndicadores = [];
		revealedIndicadores = new Set();
		if (!resultadoId) return;
		indicadoresLoading = true;
		try {
			const data = await fetchIndicadores(resultadoId);
			indicadores = data;
			// Animação escalonada (animate-in): revela cada item a cada 100ms.
			revealedIndicadores = new Set();
			data.forEach((ind, index) => {
				setTimeout(() => {
					revealedIndicadores = new Set([...revealedIndicadores, ind.id]);
				}, index * 100);
			});
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

	// --- Accordion ---------------------------------------------------------

	function toggleSection(id: string): void {
		openSection = openSection === id ? '' : id;
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
			onClose();
		}
	}
</script>

{#if open}
	<div
		class="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/50 p-4 py-10"
		role="presentation"
		onclick={() => !submitting && onClose()}
		onkeydown={onBackdropKeydown}
	>
		<div
			role="dialog"
			aria-modal="true"
			aria-labelledby="criar-projeto-title"
			class="flex w-full max-w-4xl flex-col gap-4 rounded-lg border border-border-subtle bg-surface p-6 shadow-lg"
			onclick={(e) => e.stopPropagation()}
			onkeydown={onBackdropKeydown}
			tabindex="-1"
			transition:fly={{ y: 16, duration: 200 }}
		>
			<!-- Cabeçalho -->
			<header class="flex items-center justify-between gap-3">
				<h2
					id="criar-projeto-title"
					class="font-heading text-lg font-semibold text-text-primary"
				>
					Criar Novo Projeto
				</h2>
				<button
					type="button"
					onclick={onClose}
					disabled={submitting}
					aria-label="Fechar"
					class="rounded-md border border-border-subtle bg-surface px-2 py-1 text-sm text-text-secondary transition-colors duration-fast hover:bg-surface-muted disabled:opacity-60 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
				>
					✕
				</button>
			</header>

			<form
				onsubmit={(e) => {
					e.preventDefault();
					void submit();
				}}
				class="flex flex-col gap-5"
			>
				<!-- Seção rápida -->
				<section
					class="flex flex-col gap-4 rounded-md border border-border-subtle bg-surface-muted/30 p-4"
				>
					<span
						class="inline-flex w-fit items-center rounded-full bg-primary-100 px-2.5 py-1 text-xs font-bold uppercase tracking-wide text-primary-700"
					>
						Criação rápida
					</span>

					<div class="grid grid-cols-1 gap-4 md:grid-cols-2">
						<div class="flex flex-col gap-1 md:col-span-1">
							<label
								for="cp-titulo"
								class="text-xs font-semibold uppercase tracking-wide text-text-muted"
							>
								Título do Projeto <span class="text-danger">*</span>
							</label>
							<input
								id="cp-titulo"
								bind:this={titleInputEl}
								bind:value={titulo}
								type="text"
								required
								placeholder="Digite o título do projeto"
								class="rounded-md border border-border-subtle bg-surface px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
							/>
						</div>

						<div class="flex flex-col gap-1">
							<label
								for="cp-orgao-id"
								class="text-xs font-semibold uppercase tracking-wide text-text-muted"
							>
								Área Responsável <span class="text-danger">*</span>
							</label>
							{#if orgaoOptions.length === 0}
								<select
									id="cp-orgao-id"
									disabled
									class="rounded-md border border-border-subtle bg-surface px-3 py-2 text-sm text-text-muted"
								>
									<option value="">Nenhum órgão atribuído</option>
								</select>
							{:else if orgaoOptions.length === 1}
								<input
									type="text"
									value={orgaoOptions[0].label}
									disabled
									class="rounded-md border border-border-subtle bg-surface px-3 py-2 text-sm text-text-muted"
								/>
							{:else}
								<select
									id="cp-orgao-id"
									bind:value={orgaoId}
									required
									class="rounded-md border border-border-subtle bg-surface px-3 py-2 text-sm text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
								>
									<option value="" disabled>Selecione um órgão</option>
									{#each orgaoOptions as opt (opt.value)}
										<option value={opt.value}>{opt.label}</option>
									{/each}
								</select>
							{/if}
						</div>

						<div class="flex flex-col gap-1">
							<label
								for="cp-prioridade"
								class="text-xs font-semibold uppercase tracking-wide text-text-muted"
							>
								Prioridade
							</label>
							<select
								id="cp-prioridade"
								bind:value={prioridade}
								class="rounded-md border border-border-subtle bg-surface px-3 py-2 text-sm text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
							>
								{#each PRIORITIES as p (p.value)}
									<option value={p.value}>{p.label}</option>
								{/each}
							</select>
						</div>

						<div class="flex flex-col gap-1 md:col-span-1">
							<label
								for="cp-short-desc"
								class="text-xs font-semibold uppercase tracking-wide text-text-muted"
							>
								Descrição
							</label>
							<textarea
								id="cp-short-desc"
								bind:value={shortDescription}
								rows="2"
								placeholder="Breve descrição do projeto"
								class="rounded-md border border-border-subtle bg-surface px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
							></textarea>
						</div>

						<div class="flex flex-col gap-1">
							<label
								for="cp-orgao-texto"
								class="text-xs font-semibold uppercase tracking-wide text-text-muted"
							>
								Órgão
							</label>
							<input
								id="cp-orgao-texto"
								bind:value={orgaoTexto}
								type="text"
								placeholder="Digite o órgão responsável"
								class="rounded-md border border-border-subtle bg-surface px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
							/>
						</div>
					</div>
				</section>

				<!-- Configurações adicionais (accordion) -->
				<section class="flex flex-col gap-2">
					<h3 class="text-sm font-semibold text-text-primary">Configurações adicionais</h3>

					<!-- Classificação -->
					<div class="rounded-md border border-border-subtle">
						<button
							type="button"
							onclick={() => toggleSection('planning')}
							aria-expanded={openSection === 'planning'}
							class="flex w-full items-center justify-between px-4 py-3 text-left text-sm font-semibold transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 {openSection === 'planning' ? 'bg-primary-100 text-primary-700' : 'text-text-primary'}"
						>
							<span><i class="fas fa-sliders-h mr-2"></i>Classificação</span>
							<i class="fas {openSection === 'planning' ? 'fa-chevron-up' : 'fa-chevron-down'}"></i>
						</button>
						{#if openSection === 'planning'}
							<div class="grid grid-cols-1 gap-4 border-t border-border-subtle p-4 md:grid-cols-2">
								<div class="flex flex-col gap-1">
									<label for="cp-delivery" class="text-xs font-semibold uppercase tracking-wide text-text-muted">
										Tipo de Entrega
									</label>
									<select
										id="cp-delivery"
										bind:value={deliveryType}
										class="rounded-md border border-border-subtle bg-surface px-3 py-2 text-sm text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
									>
										<option value="">Selecione o tipo</option>
										{#each deliveryTypes as dt (dt)}
											<option value={dt}>{dt}</option>
										{/each}
									</select>
								</div>
								<div class="flex flex-col gap-1">
									<label for="cp-special" class="text-xs font-semibold uppercase tracking-wide text-text-muted">
										Projetos Especiais
									</label>
									<select
										id="cp-special"
										bind:value={specialProject}
										class="rounded-md border border-border-subtle bg-surface px-3 py-2 text-sm text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
									>
										<option value="">Nenhum</option>
										{#each specialOptions as sp (sp)}
											<option value={sp}>{sp}</option>
										{/each}
									</select>
								</div>
							</div>
						{/if}
					</div>

					<!-- Objetivos, resultados e indicadores -->
					<div class="rounded-md border border-border-subtle">
						<button
							type="button"
							onclick={() => toggleSection('goals')}
							aria-expanded={openSection === 'goals'}
							class="flex w-full items-center justify-between px-4 py-3 text-left text-sm font-semibold transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 {openSection === 'goals' ? 'bg-primary-100 text-primary-700' : 'text-text-primary'}"
						>
							<span><i class="fas fa-bullseye mr-2"></i>Objetivos, resultados e indicadores</span>
							<i class="fas {openSection === 'goals' ? 'fa-chevron-up' : 'fa-chevron-down'}"></i>
						</button>
						{#if openSection === 'goals'}
							<div class="flex flex-col gap-4 border-t border-border-subtle p-4">
								<div class="grid grid-cols-1 gap-4 md:grid-cols-2">
									<div class="flex flex-col gap-1">
										<label for="cp-objetivo" class="text-xs font-semibold uppercase tracking-wide text-text-muted">
											Objetivo EEGD
										</label>
										<select
											id="cp-objetivo"
											bind:value={objetivoId}
											onchange={onObjetivoChange}
											class="rounded-md border border-border-subtle bg-surface px-3 py-2 text-sm text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
										>
											<option value="">Selecione um objetivo</option>
											{#each objetivos as obj (obj.id)}
												<option value={String(obj.id)}>{obj.descricao}</option>
											{/each}
										</select>
									</div>
									<div class="flex flex-col gap-1">
										<label for="cp-resultado" class="text-xs font-semibold uppercase tracking-wide text-text-muted">
											Resultado Esperado EEGD
										</label>
										<select
											id="cp-resultado"
											bind:value={resultadoId}
											onchange={onResultadoChange}
											disabled={!objetivoId || resultadosLoading}
											class="rounded-md border border-border-subtle bg-surface px-3 py-2 text-sm text-text-primary disabled:opacity-60 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
										>
											<option value="">
												{resultadosLoading ? 'Carregando resultados...' : 'Selecione um resultado esperado'}
											</option>
											{#each resultados as r (r.id)}
												<option value={String(r.id)}>{r.descricao}</option>
											{/each}
										</select>
									</div>
								</div>

								<div class="flex flex-col gap-2">
									<span class="text-xs font-semibold uppercase tracking-wide text-text-muted">
										Indicadores EEGD
									</span>
									{#if indicadoresLoading}
										<p role="status" aria-live="polite" class="text-sm text-text-secondary">
											<i class="fas fa-spinner fa-spin mr-1"></i>Carregando indicadores...
										</p>
									{:else if !resultadoId}
										<p class="text-sm text-text-muted">
											<i class="fas fa-info-circle mr-1"></i>Selecione um resultado esperado para ver os indicadores disponíveis
										</p>
									{:else if indicadores.length === 0}
										<p class="text-sm text-text-muted">
											<i class="fas fa-exclamation-circle mr-1"></i>Nenhum indicador disponível para este resultado esperado
										</p>
									{:else}
										<div class="flex flex-col gap-2">
											{#each indicadores as ind (ind.id)}
												<label
													class="flex items-center gap-2 text-sm text-text-primary transition-all duration-300 {revealedIndicadores.has(
														ind.id
													)
														? 'translate-y-0 opacity-100'
														: 'translate-y-1 opacity-0'}"
												>
													<input
														type="checkbox"
														checked={selectedIndicadores.includes(ind.id)}
														onchange={() => toggleIndicador(ind.id)}
														class="h-4 w-4 rounded border-border-subtle text-primary-600 focus:ring-primary-500"
													/>
													<span>{ind.descricao}</span>
												</label>
											{/each}
										</div>
									{/if}
								</div>

								<!-- Indicadores ABEP (combobox) -->
								<div class="relative flex flex-col gap-1">
									<label for="cp-abep" class="text-xs font-semibold uppercase tracking-wide text-text-muted">
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
										class="rounded-md border border-border-subtle bg-surface px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
									/>
									{#if abepOpen}
										<ul
											id="cp-abep-listbox"
											role="listbox"
											aria-label="Indicadores ABEP"
											class="absolute left-0 right-0 top-full z-10 mt-1 max-h-64 overflow-auto rounded-md border border-border-subtle bg-surface py-1 shadow-md"
										>
											{#if abepVisible.length === 0}
												<li class="px-3 py-2 text-sm text-text-muted">Nenhum indicador encontrado</li>
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
							</div>
						{/if}
					</div>

					<!-- Links e Observação -->
					<div class="rounded-md border border-border-subtle">
						<button
							type="button"
							onclick={() => toggleSection('details')}
							aria-expanded={openSection === 'details'}
							class="flex w-full items-center justify-between px-4 py-3 text-left text-sm font-semibold transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 {openSection === 'details' ? 'bg-primary-100 text-primary-700' : 'text-text-primary'}"
						>
							<span><i class="fas fa-link mr-2"></i>Links e Observação</span>
							<i class="fas {openSection === 'details' ? 'fa-chevron-up' : 'fa-chevron-down'}"></i>
						</button>
						{#if openSection === 'details'}
							<div class="flex flex-col gap-4 border-t border-border-subtle p-4">
								<div class="grid grid-cols-1 gap-4 md:grid-cols-2">
									<div class="flex flex-col gap-1">
										<label for="cp-sei" class="text-xs font-semibold uppercase tracking-wide text-text-muted">
											Processo SEI-RJ
										</label>
										<input
											id="cp-sei"
											value={seiProcess}
											oninput={onSeiInput}
											type="text"
											maxlength="25"
											placeholder="SEI-000000/000000/0000"
											class="rounded-md border border-border-subtle bg-surface px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
										/>
									</div>
									<div class="flex flex-col gap-1">
										<label for="cp-github" class="text-xs font-semibold uppercase tracking-wide text-text-muted">
											Link Github
										</label>
										<input
											id="cp-github"
											bind:value={githubLink}
											type="text"
											placeholder="https://github.com/..."
											class="rounded-md border border-border-subtle bg-surface px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
										/>
									</div>
									<div class="flex flex-col gap-1">
										<label for="cp-doc" class="text-xs font-semibold uppercase tracking-wide text-text-muted">
											Link Documentação
										</label>
										<input
											id="cp-doc"
											bind:value={documentationLink}
											type="text"
											placeholder="https://..."
											class="rounded-md border border-border-subtle bg-surface px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
										/>
									</div>
									<div class="flex flex-col gap-1">
										<label for="cp-product" class="text-xs font-semibold uppercase tracking-wide text-text-muted">
											Link para o Produto
										</label>
										<input
											id="cp-product"
											bind:value={productLink}
											type="text"
											placeholder="https://..."
											class="rounded-md border border-border-subtle bg-surface px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
										/>
									</div>
								</div>
								<div class="flex flex-col gap-1">
									<label for="cp-obs" class="text-xs font-semibold uppercase tracking-wide text-text-muted">
										Observações / Descrição Detalhada
									</label>
									<textarea
										id="cp-obs"
										bind:value={observacao}
										rows="3"
										placeholder="Digite observações detalhadas sobre o projeto..."
										class="rounded-md border border-border-subtle bg-surface px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
									></textarea>
								</div>
							</div>
						{/if}
					</div>

					<!-- Modelo de Etapas -->
					<div class="rounded-md border border-border-subtle">
						<button
							type="button"
							onclick={() => toggleSection('template')}
							aria-expanded={openSection === 'template'}
							class="flex w-full items-center justify-between px-4 py-3 text-left text-sm font-semibold transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 {openSection === 'template' ? 'bg-primary-100 text-primary-700' : 'text-text-primary'}"
						>
							<span><i class="fas fa-layer-group mr-2"></i>Modelo de Etapas</span>
							<i class="fas {openSection === 'template' ? 'fa-chevron-up' : 'fa-chevron-down'}"></i>
						</button>
						{#if openSection === 'template'}
							<div class="flex flex-col gap-4 border-t border-border-subtle p-4">
								<div class="grid grid-cols-1 gap-4 md:grid-cols-3">
									<div class="flex flex-col gap-1 md:col-span-2">
										<label for="cp-template" class="text-xs font-semibold uppercase tracking-wide text-text-muted">
											Importar Modelo
										</label>
										<select
											id="cp-template"
											bind:value={templateId}
											onchange={onTemplateChange}
											class="rounded-md border border-border-subtle bg-surface px-3 py-2 text-sm text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
										>
											<option value="">Não importar / Limpar etapas</option>
											{#each templates as tpl (tpl.id)}
												<option value={String(tpl.id)}>{tpl.name}</option>
											{/each}
										</select>
									</div>
									<div class="flex flex-col gap-1">
										<label for="cp-start" class="text-xs font-semibold uppercase tracking-wide text-text-muted">
											Data de Início (opcional)
										</label>
										<input
											id="cp-start"
											bind:value={startDate}
											type="date"
											title="Sem data, o preview mostra só a duração de cada etapa."
											class="rounded-md border border-border-subtle bg-surface px-3 py-2 text-sm text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
										/>
									</div>
								</div>

								{#if templateLoading}
									<p role="status" aria-live="polite" class="text-sm text-text-secondary">
										<i class="fas fa-spinner fa-spin mr-1"></i>Carregando etapas…
									</p>
								{:else if previewStages.length > 0}
									<div class="flex flex-col gap-2 rounded-md border border-border-subtle bg-surface-muted/30 p-3">
										<div class="flex items-center justify-between text-xs font-semibold uppercase tracking-wide text-text-muted">
											<span>Etapas importadas</span>
											<span>{previewStages.length} etapas · total {previewTotalDuration} dias</span>
										</div>
										<ol class="flex flex-col gap-1">
											{#each previewStages as stage, index (index)}
												<li class="flex items-start gap-2 text-sm text-text-primary">
													<span class="inline-flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full bg-primary-100 text-xs font-medium text-primary-700">
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
										<i class="fas fa-layer-group mr-1"></i>Selecione um modelo para visualizar as etapas importadas.
									</p>
								{/if}
							</div>
						{/if}
					</div>
				</section>

				<!-- Rodapé -->
				<footer class="flex items-center justify-end gap-2 border-t border-border-subtle pt-4">
					<button
						type="button"
						onclick={onClose}
						disabled={submitting}
						class="min-w-[126px] rounded-md border border-primary-500 bg-surface px-4 py-2 text-sm font-semibold text-primary-700 transition-colors duration-fast hover:bg-primary-100 disabled:opacity-60 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
					>
						Cancelar
					</button>
					<button
						type="submit"
						disabled={!canSubmit}
						class="inline-flex min-w-[126px] items-center justify-center gap-2 rounded-md border border-primary-700 bg-topnav-gradient px-4 py-2 text-sm font-semibold text-white shadow-sm transition-all duration-fast hover:-translate-y-0.5 hover:shadow-md active:translate-y-0 disabled:translate-y-0 disabled:cursor-not-allowed disabled:border-border-subtle disabled:bg-surface-muted disabled:bg-none disabled:text-text-muted disabled:shadow-none focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
					>
						{#if submitting}
							<i class="fas fa-spinner fa-spin" aria-hidden="true"></i>Criando…
						{:else}
							<i class="fas fa-plus-circle" aria-hidden="true"></i>Criar Projeto
						{/if}
					</button>
				</footer>
			</form>
		</div>
	</div>
{/if}
