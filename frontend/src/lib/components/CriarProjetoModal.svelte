<script lang="ts">
	/**
	 * Modal "Criar novo projeto" (Quick Create) — paridade de LÓGICA com o modal
	 * Bootstrap `templates/projects/add_form.html` + `add_form_js.html`.
	 *
	 * Layout: seção principal sempre visível (título*, área responsável*,
	 * prioridade, órgão, descrição) + acordeão EXCLUSIVO de 4 seções opcionais
	 * (Classificação, Objetivos/resultados/indicadores, Links e observações,
	 * Modelo de etapas). Expandir uma seção retrai a anterior; o cabeçalho de
	 * cada seção resume o que já foi preenchido quando fechada.
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
	import { tick } from 'svelte';
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

	function toggleSection(id: SectionId): void {
		openSection = openSection === id ? null : id;
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
		openSection = null;
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

	// --- Resumos das seções (exibidos no cabeçalho quando fechadas) ----------

	const classificacaoSummary = $derived(
		[deliveryType, specialProject].filter(Boolean).join(' · ')
	);
	const objetivosSummary = $derived.by(() => {
		const parts: string[] = [];
		if (objetivoId) parts.push('Objetivo EEGD');
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

	// Wrapper do submit: se inválido, marca os campos faltantes e foca o primeiro.
	async function trySubmit(): Promise<void> {
		if (!canSubmit) {
			if (submitting) return;
			triedSubmit = true;
			await tick();
			(!titulo.trim()
				? titleInputEl
				: (document.getElementById('cp-orgao-id') as HTMLElement | null)
			)?.focus();
			return;
		}
		await submit();
	}

	// Esc fecha; Ctrl/Cmd+Enter salva de qualquer lugar do modal.
	function onModalKeydown(event: KeyboardEvent): void {
		if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') {
			event.preventDefault();
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

	// --- Classes utilitárias (campos com visual unificado) -------------------
	const labelClass = 'text-xs font-medium uppercase tracking-wide text-text-muted';
	const fieldClass =
		'h-10 w-full rounded-md border border-border-subtle bg-surface px-3 text-sm leading-tight text-text-primary placeholder:text-text-muted transition-colors duration-fast focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-60';
	const areaClass =
		'w-full rounded-md border border-border-subtle bg-surface px-3 py-2 text-sm text-text-primary placeholder:text-text-muted transition-colors duration-fast focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500';
	const fieldErrorClass = 'border-danger focus-visible:ring-danger';
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

{#if open}
	<div
		class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4 backdrop-blur-[1.5px]"
		role="presentation"
		onclick={() => !submitting && onClose()}
		onkeydown={onModalKeydown}
		transition:fade={{ duration: 200 }}
	>
		<div
			role="dialog"
			aria-modal="true"
			aria-labelledby="criar-projeto-title"
			class="flex max-h-[calc(100dvh-4rem)] w-full max-w-2xl flex-col overflow-hidden rounded-xl border border-border-subtle bg-surface shadow-lg"
			onclick={(e) => e.stopPropagation()}
			onkeydown={onModalKeydown}
			tabindex="-1"
			use:focusTrap
			transition:fly={{ y: 18, duration: 320, easing: cubicOut }}
		>
			<!-- Cabeçalho fixo -->
			<header
				class="flex flex-shrink-0 items-start justify-between gap-4 border-b border-border-subtle px-6 py-5"
			>
				<div class="flex min-w-0 flex-col gap-0.5">
					<h2
						id="criar-projeto-title"
						class="font-heading text-lg font-semibold text-text-primary"
					>
						Criar novo projeto
					</h2>
					<p class="text-sm text-text-muted">
						Apenas título e área responsável são obrigatórios.
					</p>
				</div>
				<button
					type="button"
					onclick={onClose}
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
				onsubmit={(e) => {
					e.preventDefault();
					void trySubmit();
				}}
				class="flex min-h-0 flex-1 flex-col"
			>
				<!-- Corpo: única região que rola -->
				<div class="min-h-0 flex-1 overflow-y-auto px-6 py-5">
					<!-- Seção principal (sempre visível) -->
					<div class="grid grid-cols-1 gap-x-4 gap-y-4 md:grid-cols-10">
						<div class="flex flex-col gap-1.5 md:col-span-7">
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
						<div class="flex flex-col gap-1.5 md:col-span-3">
							<label for="cp-prioridade" class={labelClass}>Prioridade</label>
							<select id="cp-prioridade" bind:value={prioridade} class={fieldClass}>
								{#each PRIORITIES as p (p.value)}
									<option value={p.value}>{p.label}</option>
								{/each}
							</select>
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
						<div class="flex flex-col gap-1.5 md:col-span-5">
							<label for="cp-orgao-texto" class={labelClass}>Órgão</label>
							<input
								id="cp-orgao-texto"
								bind:value={orgaoTexto}
								type="text"
								placeholder="Digite o órgão responsável"
								class={fieldClass}
							/>
						</div>
						<div class="flex flex-col gap-1.5 md:col-span-10">
							<label for="cp-short-desc" class={labelClass}>Descrição</label>
							<textarea
								id="cp-short-desc"
								bind:value={shortDescription}
								rows="2"
								placeholder="Breve descrição do projeto"
								class={areaClass}
							></textarea>
						</div>
					</div>

					<!-- Acordeão exclusivo de detalhes opcionais -->
					<p class="mb-2 mt-6 text-xs font-medium uppercase tracking-wide text-text-muted">
						Detalhes opcionais
					</p>
					<div class="divide-y divide-border-subtle rounded-lg border border-border-subtle">
						{#each SECTIONS as section (section.id)}
							{@const isOpen = openSection === section.id}
							{@const summary = sectionSummaries[section.id]}
							<section>
								<h3 class="contents">
									<button
										type="button"
										onclick={() => toggleSection(section.id)}
										aria-expanded={isOpen}
										aria-controls={`cp-section-${section.id}`}
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
																	{selectedIndicadores.length}/{MAX_INDICADORES} selecionados
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

													<!-- Indicadores ABEP (combobox) -->
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
															Observações / descrição detalhada
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
														<div
															transition:slide={{ duration: 240, easing: cubicOut }}
															class="flex flex-col gap-2.5 rounded-lg border border-border-subtle bg-surface-muted/40 p-4"
														>
															<div
																class="flex items-center justify-between text-xs font-medium uppercase tracking-wide text-text-muted"
															>
																<span>Etapas importadas</span>
																<span>
																	{previewStages.length}
																	{previewStages.length === 1 ? 'etapa' : 'etapas'} · total
																	{previewTotalDuration} dias
																</span>
															</div>
															<ol class="flex flex-col gap-1.5">
																{#each previewStages as stage, index (index)}
																	<li class="flex items-start gap-2.5 text-sm text-text-primary">
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

				<!-- Rodapé fixo -->
				<footer
					class="flex flex-shrink-0 items-center justify-between gap-3 border-t border-border-subtle px-6 py-4"
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
							onclick={onClose}
							disabled={submitting}
							class="rounded-md px-4 py-2 text-sm font-medium text-text-secondary transition-colors duration-fast hover:bg-surface-muted disabled:opacity-60 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
						>
							Cancelar
						</button>
						<button
							type="submit"
							disabled={submitting}
							class="inline-flex h-10 min-w-[128px] items-center justify-center gap-2 rounded-md bg-brand-gradient px-5 text-sm font-semibold text-white shadow-sm transition-all duration-base hover:-translate-y-px hover:shadow-md active:translate-y-0 disabled:cursor-not-allowed disabled:opacity-60 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-1"
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
		</div>
	</div>
{/if}
