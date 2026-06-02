<script lang="ts">
	/**
	 * Tela "Admin > Modelos de Etapas" (FASE 4). CRUD completo de modelos de
	 * etapas (`StageTemplate`) consumindo `/api/admin/templates*` via
	 * `$lib/api/adminTemplates`. Espelha visualmente
	 * `templates/admin/template_list.html` (lista + métricas + ordenação) e
	 * `template_form.html` (criar/editar com etapas nome/duração).
	 *
	 * A tela alterna entre dois modos sem trocar de rota:
	 *   - `list`: tabela com busca (debounce), ordenação, métricas
	 *     (usage/stage/duration), duplicar e excluir (com confirmação).
	 *   - `form`: criar/editar — nome, descrição e a sequência de etapas
	 *     (adicionar/remover/reordenar por DRAG-AND-DROP, com setas ↑/↓ como
	 *     alternativa acessível por teclado). A reordenação é local (estado do
	 *     formulário); a ordem só é persistida ao salvar o modelo. DnD nativo
	 *     HTML5, espelhando StageList.svelte/OrgaoTreeNode.svelte (sem libs).
	 *
	 * Padrões reusados das telas de leitura (FASE 2/3): AbortController +
	 * debounce, estados loading/erro/vazio anunciados via aria-live, componentes
	 * compartilhados Card/Badge (NÃO editados), dark via vars semânticas. As
	 * mutações usam `client.post` (X-CSRFToken automático). 401 já redireciona
	 * em `client.ts`.
	 */
	import { onMount, onDestroy } from 'svelte';
	import {
		fetchTemplateList,
		fetchTemplateDetail,
		createTemplate,
		updateTemplate,
		duplicateTemplate,
		deleteTemplate
	} from '$lib/api/adminTemplates';
	import { ApiClientError } from '$lib/api/client';
	import type {
		TemplateListResult,
		TemplateOrder,
		TemplateRow,
		TemplateStageInput
	} from '$lib/types/adminTemplates';
	import Card from '$lib/components/Card.svelte';
	import Badge from '$lib/components/Badge.svelte';

	type LoadState = 'loading' | 'ready' | 'error';
	type ViewMode = 'list' | 'form';

	/**
	 * Etapa no estado do formulário. Acrescenta `_key` (id estável só-cliente) ao
	 * payload `TemplateStageInput` para o `{#each}` keyed sobreviver à
	 * reordenação por drag-and-drop sem reusar nós errados. O `_key` é removido
	 * ao montar o payload enviado à API.
	 */
	interface FormStage extends TemplateStageInput {
		_key: number;
	}

	let stageKeySeq = 0;
	function nextStageKey(): number {
		stageKeySeq += 1;
		return stageKeySeq;
	}

	/** Janela de debounce da busca textual (ms). Espelha o list.html (350ms). */
	const DEBOUNCE_MS = 350;
	const DEFAULT_ORDER: TemplateOrder = 'mais_usados';

	/** Rótulos em pt-BR das chaves de ordenação (espelham `order_labels`). */
	const ORDER_LABELS: Record<TemplateOrder, string> = {
		mais_usados: 'mais usados',
		nome: 'nome (A-Z)',
		mais_etapas: 'mais etapas',
		maior_duracao: 'maior duração',
		edicao_recente: 'edição recente'
	};

	let loadState = $state<LoadState>('loading');
	let data = $state<TemplateListResult | null>(null);
	let errorMessage = $state<string>('');

	let view = $state<ViewMode>('list');

	// Filtros controlados pela UI; a busca acontece server-side.
	let search = $state<string>('');
	let order = $state<TemplateOrder>(DEFAULT_ORDER);
	let page = $state<number>(1);

	let debounceTimer: ReturnType<typeof setTimeout> | null = null;
	let inFlight: AbortController | null = null;

	// --- Estado do formulário (criar/editar) ------------------------------
	let formMode = $state<'create' | 'edit'>('create');
	let editingId = $state<number | null>(null);
	let formName = $state<string>('');
	let formDescription = $state<string>('');
	let formStages = $state<FormStage[]>([]);
	let formError = $state<string>('');
	let formSaving = $state<boolean>(false);
	let formLoading = $state<boolean>(false);

	// --- Estado de ações de linha (duplicar/excluir) ----------------------
	let busyRowId = $state<number | null>(null);
	let confirmDeleteRow = $state<TemplateRow | null>(null);
	let confirmPhrase = $state<string>('');
	let deleteError = $state<string>('');

	const DELETE_PHRASE = 'APAGAR MODELO';

	const orderOptions = $derived<TemplateOrder[]>(
		data?.order_options ?? [
			'mais_usados',
			'nome',
			'mais_etapas',
			'maior_duracao',
			'edicao_recente'
		]
	);
	const meta = $derived(data?.meta ?? null);
	const totalTemplates = $derived(data?.meta.total ?? 0);
	const hasActiveFilters = $derived(search.trim() !== '' || order !== DEFAULT_ORDER);

	const stageTotalDuration = $derived(
		formStages.reduce((sum, s) => sum + (Number(s.duration_days) || 0), 0)
	);
	const formValid = $derived(
		formName.trim() !== '' && formStages.some((s) => s.name.trim() !== '')
	);

	async function load(): Promise<void> {
		loadState = data ? loadState : 'loading';
		errorMessage = '';
		inFlight?.abort();
		const controller = new AbortController();
		inFlight = controller;

		try {
			const next = await fetchTemplateList(
				{ q: search.trim() || undefined, order, page },
				controller.signal
			);
			if (controller.signal.aborted) return;
			data = next;
			// Reconcilia os filtros com o que o backend efetivamente aplicou.
			order = next.meta.order;
			search = next.meta.q;
			page = next.meta.page;
			loadState = 'ready';
		} catch (err) {
			if (controller.signal.aborted) return;
			if (err instanceof ApiClientError && err.code === 'unauthenticated') return;
			errorMessage =
				err instanceof Error ? err.message : 'Falha ao carregar os modelos.';
			loadState = 'error';
		}
	}

	function onSearchInput(): void {
		if (debounceTimer) clearTimeout(debounceTimer);
		debounceTimer = setTimeout(() => {
			page = 1;
			void load();
		}, DEBOUNCE_MS);
	}

	function onSearchSubmit(event: SubmitEvent): void {
		event.preventDefault();
		if (debounceTimer) clearTimeout(debounceTimer);
		page = 1;
		void load();
	}

	function onOrderChange(event: Event): void {
		order = (event.currentTarget as HTMLSelectElement).value as TemplateOrder;
		page = 1;
		void load();
	}

	function clearFilters(): void {
		if (debounceTimer) clearTimeout(debounceTimer);
		search = '';
		order = DEFAULT_ORDER;
		page = 1;
		void load();
	}

	function goToPage(target: number): void {
		page = target;
		void load();
	}

	// --- Formulário -------------------------------------------------------

	function blankStage(): FormStage {
		return { _key: nextStageKey(), name: '', duration_days: 1 };
	}

	function openCreate(): void {
		formMode = 'create';
		editingId = null;
		formName = '';
		formDescription = '';
		formStages = [blankStage()];
		formError = '';
		formLoading = false;
		view = 'form';
	}

	async function openEdit(row: TemplateRow): Promise<void> {
		formMode = 'edit';
		editingId = row.id;
		formName = row.name;
		formDescription = row.description ?? '';
		formStages = [];
		formError = '';
		formLoading = true;
		view = 'form';
		try {
			const detail = await fetchTemplateDetail(row.id);
			formName = detail.template.name;
			formDescription = detail.template.description ?? '';
			formStages = detail.template.stages.map((s) => ({
				_key: nextStageKey(),
				name: s.name,
				duration_days: s.duration_days
			}));
			if (formStages.length === 0) formStages = [blankStage()];
		} catch (err) {
			if (err instanceof ApiClientError && err.code === 'unauthenticated') return;
			formError =
				err instanceof Error ? err.message : 'Falha ao carregar o modelo.';
		} finally {
			formLoading = false;
		}
	}

	function cancelForm(): void {
		view = 'list';
		formError = '';
	}

	function addStage(): void {
		formStages = [...formStages, blankStage()];
	}

	function removeStage(index: number): void {
		formStages = formStages.filter((_, i) => i !== index);
		if (formStages.length === 0) formStages = [blankStage()];
	}

	function clearStages(): void {
		formStages = [blankStage()];
	}

	function moveStage(index: number, delta: number): void {
		reorderStage(index, index + delta);
	}

	/** Move a etapa de `from` para `to` no estado do formulário (compartilhado por setas e DnD). */
	function reorderStage(from: number, to: number): void {
		if (to < 0 || to >= formStages.length || from === to) return;
		const next = [...formStages];
		const [moved] = next.splice(from, 1);
		next.splice(to, 0, moved);
		formStages = next;
	}

	// --- Drag-and-drop das etapas (estado do formulário, sem API) ---------
	let dragStageIndex = $state<number | null>(null);
	let dropStageIndex = $state<number | null>(null);

	function handleStageDragStart(event: DragEvent, index: number): void {
		dragStageIndex = index;
		if (event.dataTransfer) {
			event.dataTransfer.effectAllowed = 'move';
			// Firefox exige um payload para iniciar o arraste.
			event.dataTransfer.setData('text/plain', String(index));
		}
	}

	function handleStageDragOver(event: DragEvent, index: number): void {
		if (dragStageIndex === null) return;
		event.preventDefault();
		if (event.dataTransfer) event.dataTransfer.dropEffect = 'move';
		dropStageIndex = index;
	}

	function handleStageDrop(event: DragEvent, index: number): void {
		event.preventDefault();
		if (dragStageIndex !== null) reorderStage(dragStageIndex, index);
		resetStageDrag();
	}

	function resetStageDrag(): void {
		dragStageIndex = null;
		dropStageIndex = null;
	}

	async function saveForm(event: SubmitEvent): Promise<void> {
		event.preventDefault();
		formError = '';
		const cleanedStages = formStages
			.map((s) => ({
				name: s.name.trim(),
				duration_days: Math.max(1, Number(s.duration_days) || 1)
			}))
			.filter((s) => s.name !== '');

		if (formName.trim() === '') {
			formError = 'O nome do modelo é obrigatório.';
			return;
		}
		if (cleanedStages.length === 0) {
			formError = 'Informe pelo menos uma etapa.';
			return;
		}

		formSaving = true;
		const payload = {
			name: formName.trim(),
			description: formDescription.trim() || null,
			stages: cleanedStages
		};
		try {
			if (formMode === 'edit' && editingId !== null) {
				await updateTemplate(editingId, payload);
			} else {
				await createTemplate(payload);
			}
			view = 'list';
			page = 1;
			await load();
		} catch (err) {
			if (err instanceof ApiClientError && err.code === 'unauthenticated') return;
			formError = err instanceof Error ? err.message : 'Falha ao salvar o modelo.';
		} finally {
			formSaving = false;
		}
	}

	// --- Duplicar / Excluir ----------------------------------------------

	async function onDuplicate(row: TemplateRow): Promise<void> {
		busyRowId = row.id;
		errorMessage = '';
		try {
			await duplicateTemplate(row.id);
			await load();
		} catch (err) {
			if (err instanceof ApiClientError && err.code === 'unauthenticated') return;
			errorMessage =
				err instanceof Error ? err.message : 'Falha ao duplicar o modelo.';
		} finally {
			busyRowId = null;
		}
	}

	function askDelete(row: TemplateRow): void {
		confirmDeleteRow = row;
		confirmPhrase = '';
		deleteError = '';
	}

	function cancelDelete(): void {
		confirmDeleteRow = null;
		confirmPhrase = '';
		deleteError = '';
	}

	async function confirmDelete(): Promise<void> {
		if (!confirmDeleteRow) return;
		if (confirmPhrase.trim().toUpperCase() !== DELETE_PHRASE) {
			deleteError = `Digite "${DELETE_PHRASE}" para confirmar.`;
			return;
		}
		const target = confirmDeleteRow;
		busyRowId = target.id;
		deleteError = '';
		try {
			await deleteTemplate(target.id);
			confirmDeleteRow = null;
			confirmPhrase = '';
			// Se a página ficou vazia após excluir, recua uma página.
			if (data && data.templates.length === 1 && page > 1) page -= 1;
			await load();
		} catch (err) {
			if (err instanceof ApiClientError && err.code === 'unauthenticated') return;
			deleteError = err instanceof Error ? err.message : 'Falha ao excluir o modelo.';
		} finally {
			busyRowId = null;
		}
	}

	onMount(() => {
		void load();
		return () => inFlight?.abort();
	});

	onDestroy(() => {
		if (debounceTimer) clearTimeout(debounceTimer);
		inFlight?.abort();
	});
</script>

<svelte:head>
	<title>Modelos de Etapas — Administração — ProjetosRJ</title>
</svelte:head>

<section aria-labelledby="tpl-title" class="flex flex-col gap-6">
	<nav aria-label="Trilha" class="flex items-center gap-2 text-sm text-text-muted">
		<span>Administração</span>
		<span aria-hidden="true" class="text-text-muted">/</span>
		<span class="font-medium text-text-secondary">Modelos de Etapas</span>
	</nav>

	<header
		class="flex flex-col items-start gap-4 rounded-xl border border-border-subtle bg-surface p-5 shadow-lg sm:flex-row sm:items-start"
	>
		<div
			class="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-primary-100 text-primary-700"
			aria-hidden="true"
		>
			<svg viewBox="0 0 20 20" fill="currentColor" class="h-5 w-5">
				<path d="M10 2 2 6l8 4 8-4-8-4Z" />
				<path d="m3.5 9-1.5.75 8 4 8-4L16.5 9 10 12.25 3.5 9Z" opacity="0.85" />
				<path d="m3.5 12.5-1.5.75 8 4 8-4-1.5-.75L10 15.75 3.5 12.5Z" opacity="0.7" />
			</svg>
		</div>
		<div class="flex min-w-0 flex-1 flex-col gap-1">
			<div class="flex flex-wrap items-center gap-3">
				<h1 id="tpl-title" class="font-heading text-2xl font-bold tracking-tight text-primary-700">
					Modelos de Etapas
				</h1>
				{#if data}
					<span
						class="inline-flex items-center rounded-full border border-primary-500 bg-primary-100 px-3 py-1 text-sm font-semibold text-primary-700"
					>
						{totalTemplates} modelo{totalTemplates === 1 ? '' : 's'}
					</span>
				{/if}
			</div>
			<p class="text-sm text-text-secondary">
				Padronize os ciclos dos projetos — use, duplique ou edite conforme a necessidade da
				secretaria.
			</p>
		</div>
		{#if view === 'list'}
			<button
				type="button"
				onclick={openCreate}
				class="inline-flex shrink-0 items-center gap-2 rounded-lg bg-primary-600 px-4 py-2.5 text-sm font-semibold text-white shadow-md transition-all duration-base hover:-translate-y-px hover:bg-primary-700 hover:shadow-lg focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2"
			>
				<svg viewBox="0 0 20 20" fill="currentColor" class="h-4 w-4" aria-hidden="true">
					<path d="M10 4a1 1 0 0 1 1 1v4h4a1 1 0 1 1 0 2h-4v4a1 1 0 1 1-2 0v-4H5a1 1 0 1 1 0-2h4V5a1 1 0 0 1 1-1Z" />
				</svg>
				<span>Novo modelo</span>
			</button>
		{/if}
	</header>

	{#if view === 'form'}
		<!-- =================== FORMULÁRIO CRIAR/EDITAR =================== -->
		<Card>
			<form class="flex flex-col gap-5" onsubmit={saveForm} novalidate>
				<div class="flex flex-col gap-1">
					<h2 class="font-heading text-lg font-bold text-text-primary">
						{formMode === 'edit' ? 'Editar modelo' : 'Novo modelo'}
					</h2>
					<p class="text-sm text-text-muted">
						Defina o nome e organize as etapas na ordem em que devem acontecer.
					</p>
				</div>

				{#if formError}
					<p
						role="alert"
						class="rounded-md border border-danger bg-danger/10 px-3 py-2 text-sm font-medium text-danger"
					>
						{formError}
					</p>
				{/if}

				{#if formLoading}
					<p role="status" aria-live="polite" class="text-text-secondary">
						Carregando modelo…
					</p>
				{:else}
					<div class="flex flex-col gap-2 border-b border-dashed border-border-subtle pb-4">
						<label
							for="tplName"
							class="text-2xs font-bold uppercase tracking-caps text-text-muted"
						>
							Nome do modelo
						</label>
						<input
							id="tplName"
							type="text"
							bind:value={formName}
							required
							placeholder="Ex.: Aquisição simples"
							class="w-full rounded-md border border-border-subtle bg-surface-muted px-3 py-2 text-base font-semibold text-text-primary transition-all duration-fast placeholder:font-normal placeholder:text-text-muted hover:border-border-strong hover:bg-surface focus:border-primary-500 focus:bg-surface focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/40"
						/>

						<label
							for="tplDesc"
							class="mt-2 text-2xs font-bold uppercase tracking-caps text-text-muted"
						>
							Descrição (opcional)
						</label>
						<textarea
							id="tplDesc"
							bind:value={formDescription}
							rows="2"
							placeholder="Para que serve este modelo?"
							class="w-full resize-y rounded-md border border-border-subtle bg-surface-muted px-3 py-2 text-sm text-text-primary transition-all duration-fast placeholder:text-text-muted hover:border-border-strong hover:bg-surface focus:border-primary-500 focus:bg-surface focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/40"
						></textarea>
					</div>

					<div class="flex flex-col gap-3">
						<div class="flex flex-wrap items-center justify-between gap-2">
							<div class="flex items-baseline gap-2">
								<span class="text-xs font-bold uppercase tracking-caps text-text-primary">
									Etapas
								</span>
								<span class="text-xs text-text-muted" aria-live="polite">
									{formStages.filter((s) => s.name.trim() !== '').length} etapa{formStages.filter(
										(s) => s.name.trim() !== ''
									).length === 1
										? ''
										: 's'}
									<span class="px-1 text-border-strong" aria-hidden="true">·</span>
									{stageTotalDuration} dia{stageTotalDuration === 1 ? '' : 's'} no total
								</span>
							</div>
							<button
								type="button"
								onclick={clearStages}
								class="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-semibold text-text-muted transition-colors duration-fast hover:bg-surface-muted hover:text-danger focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
							>
								Limpar tudo
							</button>
						</div>

						<ul class="flex flex-col gap-2">
							{#each formStages as stage, index (stage._key)}
								<li
									draggable={formStages.length > 1}
									ondragstart={(e) => handleStageDragStart(e, index)}
									ondragover={(e) => handleStageDragOver(e, index)}
									ondrop={(e) => handleStageDrop(e, index)}
									ondragend={resetStageDrag}
									class="group grid grid-cols-[22px_30px_1fr_auto] items-center gap-2 rounded-md border bg-surface px-2.5 py-2 transition-all duration-fast hover:border-primary-500/40 hover:bg-surface-muted/40 focus-within:border-primary-500/40 focus-within:bg-surface-muted/40 {dragStageIndex ===
									index
										? 'scale-[0.99] border-dashed border-border-strong bg-surface-muted opacity-45'
										: 'border-border-subtle'} {dropStageIndex === index &&
									dragStageIndex !== null &&
									dragStageIndex !== index
										? 'ring-2 ring-primary-500'
										: ''}"
								>
									<span
										class="flex h-7 w-[22px] shrink-0 items-center justify-center rounded-md text-border-strong transition-colors duration-fast {formStages.length >
										1
											? 'cursor-grab group-hover:text-primary-700 active:cursor-grabbing'
											: 'opacity-0'}"
										title="Arraste para reordenar"
										aria-hidden="true"
									>
										<svg viewBox="0 0 20 20" fill="currentColor" class="h-4 w-4">
											<path d="M7 4a1 1 0 11-2 0 1 1 0 012 0zm0 6a1 1 0 11-2 0 1 1 0 012 0zm-1 7a1 1 0 100-2 1 1 0 000 2zm9-13a1 1 0 11-2 0 1 1 0 012 0zm-1 7a1 1 0 100-2 1 1 0 000 2zm1 5a1 1 0 11-2 0 1 1 0 012 0z" />
										</svg>
									</span>
									<span
										class="flex h-7 w-[30px] shrink-0 items-center justify-center text-sm font-semibold text-text-muted"
										aria-hidden="true"
									>
										{index + 1}
									</span>
									<div class="grid grid-cols-[1fr_68px] items-center gap-2">
										<input
											type="text"
											bind:value={stage.name}
											placeholder="Nome da etapa"
											aria-label={`Nome da etapa ${index + 1}`}
											class="h-[34px] w-full rounded-md border border-border-subtle bg-surface px-2.5 text-sm text-text-primary transition-all duration-fast placeholder:text-text-muted focus:border-primary-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/40"
										/>
										<div
											class="flex h-[34px] items-center justify-center rounded-md border border-border-subtle bg-surface-muted"
											title="Duração em dias"
										>
											<input
												type="number"
												min="1"
												inputmode="numeric"
												bind:value={stage.duration_days}
												aria-label={`Duração em dias da etapa ${index + 1}`}
												class="h-full w-full [appearance:textfield] border-none bg-transparent px-1 text-center text-sm font-semibold text-text-primary focus:outline-none [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
											/>
										</div>
									</div>
									<div class="flex items-center gap-0.5">
										<button
											type="button"
											onclick={() => moveStage(index, -1)}
											disabled={index === 0}
											aria-label={`Mover etapa ${index + 1} para cima`}
											class="inline-flex h-6 w-6 items-center justify-center rounded-md text-text-muted opacity-0 transition-all duration-fast hover:bg-surface-muted hover:text-text-primary focus:opacity-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-0 group-hover:opacity-100 group-focus-within:opacity-100"
										>
											<svg viewBox="0 0 20 20" fill="currentColor" class="h-3.5 w-3.5" aria-hidden="true">
												<path d="M10 5a1 1 0 0 1 .7.3l4 4a1 1 0 0 1-1.4 1.4L10 7.42l-3.3 3.3a1 1 0 1 1-1.4-1.42l4-4A1 1 0 0 1 10 5Z" />
											</svg>
										</button>
										<button
											type="button"
											onclick={() => moveStage(index, 1)}
											disabled={index === formStages.length - 1}
											aria-label={`Mover etapa ${index + 1} para baixo`}
											class="inline-flex h-6 w-6 items-center justify-center rounded-md text-text-muted opacity-0 transition-all duration-fast hover:bg-surface-muted hover:text-text-primary focus:opacity-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-0 group-hover:opacity-100 group-focus-within:opacity-100"
										>
											<svg viewBox="0 0 20 20" fill="currentColor" class="h-3.5 w-3.5" aria-hidden="true">
												<path d="M10 15a1 1 0 0 1-.7-.3l-4-4a1 1 0 1 1 1.4-1.4L10 12.58l3.3-3.3a1 1 0 0 1 1.4 1.42l-4 4A1 1 0 0 1 10 15Z" />
											</svg>
										</button>
										<button
											type="button"
											onclick={() => removeStage(index)}
											aria-label={`Remover etapa ${index + 1}`}
											title="Remover etapa"
											class="inline-flex h-6 w-6 items-center justify-center rounded-md text-text-muted opacity-0 transition-all duration-fast hover:bg-danger/10 hover:text-danger focus:opacity-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 group-hover:opacity-100 group-focus-within:opacity-100"
										>
											<svg viewBox="0 0 20 20" fill="currentColor" class="h-4 w-4" aria-hidden="true">
												<path d="M6.28 5.22a.75.75 0 0 0-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 1 0 1.06 1.06L10 11.06l3.72 3.72a.75.75 0 1 0 1.06-1.06L11.06 10l3.72-3.72a.75.75 0 0 0-1.06-1.06L10 8.94 6.28 5.22Z" />
											</svg>
										</button>
									</div>
								</li>
							{/each}
						</ul>

						<div>
							<button
								type="button"
								onclick={addStage}
								class="flex min-h-[44px] w-full items-center justify-center gap-2 rounded-md border border-dashed border-border-strong bg-primary-100/40 px-4 py-2.5 text-sm font-semibold text-primary-700 transition-all duration-fast hover:border-primary-500 hover:bg-primary-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
							>
								<svg viewBox="0 0 20 20" fill="currentColor" class="h-4 w-4" aria-hidden="true">
									<path d="M10 4a1 1 0 0 1 1 1v4h4a1 1 0 1 1 0 2h-4v4a1 1 0 1 1-2 0v-4H5a1 1 0 1 1 0-2h4V5a1 1 0 0 1 1-1Z" />
								</svg>
								<span>Adicionar nova etapa</span>
							</button>
						</div>
					</div>

					<div class="flex items-center justify-end gap-2 border-t border-border-subtle pt-4">
						<button
							type="button"
							onclick={cancelForm}
							class="inline-flex h-9 items-center rounded-md border border-border-strong bg-surface px-3.5 text-sm font-semibold text-text-secondary transition-all duration-fast hover:border-border-strong hover:bg-surface-muted hover:text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
						>
							Cancelar
						</button>
						<button
							type="submit"
							disabled={formSaving || !formValid}
							class="inline-flex h-9 items-center rounded-md bg-primary-600 px-3.5 text-sm font-semibold text-white shadow-sm transition-all duration-fast hover:bg-primary-700 hover:shadow-md focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 disabled:opacity-50 disabled:shadow-none"
						>
							{#if formSaving}
								Salvando…
							{:else if formMode === 'edit'}
								Salvar alterações
							{:else}
								Criar modelo
							{/if}
						</button>
					</div>
				{/if}
			</form>
		</Card>
	{:else}
		<!-- ======================= LISTA ======================= -->
		<form
			class="flex flex-wrap items-center gap-3 rounded-xl border border-border-subtle bg-surface px-4 py-3 shadow-md"
			role="search"
			aria-label="Filtros de modelos"
			onsubmit={onSearchSubmit}
		>
			<div class="relative min-w-[15rem] flex-1">
				<label for="tplSearch" class="sr-only">Busca livre</label>
				<span class="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" aria-hidden="true">
					<svg viewBox="0 0 20 20" fill="currentColor" class="h-4 w-4">
						<path fill-rule="evenodd" d="M9 3.5a5.5 5.5 0 1 0 3.4 9.83l3.13 3.14a1 1 0 0 0 1.42-1.42l-3.14-3.13A5.5 5.5 0 0 0 9 3.5Zm-3.5 5.5a3.5 3.5 0 1 1 7 0 3.5 3.5 0 0 1-7 0Z" clip-rule="evenodd" />
					</svg>
				</span>
				<input
					id="tplSearch"
					name="q"
					type="search"
					autocomplete="off"
					bind:value={search}
					oninput={onSearchInput}
					placeholder="Buscar modelo por nome ou descrição…"
					class="w-full rounded-lg border border-border-subtle bg-surface-muted py-2.5 pl-9 pr-3 text-sm text-text-primary transition-all duration-base placeholder:text-text-muted focus:border-primary-500 focus:bg-surface focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/40"
				/>
			</div>

			<label
				class="inline-flex items-center gap-2 rounded-lg border border-border-subtle bg-surface-muted px-3 py-2 text-sm text-text-secondary transition-colors duration-base hover:border-border-strong hover:bg-surface"
			>
				<svg viewBox="0 0 20 20" fill="currentColor" class="h-4 w-4 text-text-muted" aria-hidden="true">
					<path d="M3 6h10a1 1 0 0 0 0-2H3a1 1 0 0 0 0 2Zm0 5h7a1 1 0 1 0 0-2H3a1 1 0 1 0 0 2Zm0 5h4a1 1 0 1 0 0-2H3a1 1 0 1 0 0 2ZM17 4a1 1 0 0 0-2 0v3.59l-.3-.3a1 1 0 0 0-1.4 1.42l2 2a1 1 0 0 0 1.4 0l2-2a1 1 0 0 0-1.4-1.42l-.3.3V4Z" />
				</svg>
				<span class="text-text-muted">Ordenar por:</span>
				<select
					id="tplOrder"
					value={order}
					onchange={onOrderChange}
					class="cursor-pointer border-none bg-transparent text-sm font-semibold text-text-primary focus:outline-none"
				>
					{#each orderOptions as opt (opt)}
						<option value={opt}>{ORDER_LABELS[opt]}</option>
					{/each}
				</select>
			</label>

			{#if hasActiveFilters}
				<button
					type="button"
					onclick={clearFilters}
					class="rounded-lg border border-border-subtle bg-surface px-4 py-2 text-sm font-medium text-text-primary transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
				>
					Limpar filtros
				</button>
			{/if}
			<button type="submit" class="sr-only">Filtrar</button>
		</form>

		{#if loadState === 'loading'}
			<p role="status" aria-live="polite" class="text-text-secondary">
				Carregando modelos…
			</p>
		{:else if loadState === 'error'}
			<div
				role="alert"
				class="flex flex-col items-start gap-3 rounded-xl border border-danger bg-danger/5 px-5 py-4 shadow-md"
			>
				<p class="font-medium text-text-primary">{errorMessage}</p>
				<button
					type="button"
					onclick={() => load()}
					class="rounded-md border border-border-subtle bg-surface px-4 py-2 text-sm font-medium text-text-primary transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
				>
					Tentar novamente
				</button>
			</div>
		{:else if data}
			{#if errorMessage}
				<p
					role="alert"
					class="rounded-md border border-danger bg-danger/10 px-3 py-2 text-sm font-medium text-danger"
				>
					{errorMessage}
				</p>
			{/if}

			<div role="status" aria-live="polite" class="sr-only">
				{totalTemplates} modelo{totalTemplates === 1 ? '' : 's'} encontrado{totalTemplates ===
				1
					? ''
					: 's'}.
			</div>

			{#if data.templates.length === 0}
				<div
					class="flex flex-col items-center gap-2 rounded-xl border border-border-subtle bg-surface px-6 py-12 text-center shadow-md"
				>
					<span class="mb-1 text-text-muted/60" aria-hidden="true">
						{#if search.trim()}
							<svg viewBox="0 0 24 24" fill="currentColor" class="h-10 w-10">
								<path fill-rule="evenodd" d="M10.5 3a7.5 7.5 0 1 0 4.55 13.46l4.24 4.25a1 1 0 0 0 1.42-1.42l-4.25-4.24A7.5 7.5 0 0 0 10.5 3ZM5 10.5a5.5 5.5 0 1 1 11 0 5.5 5.5 0 0 1-11 0Z" clip-rule="evenodd" />
							</svg>
						{:else}
							<svg viewBox="0 0 24 24" fill="currentColor" class="h-10 w-10">
								<path d="M7 2a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8.83a2 2 0 0 0-.59-1.42l-4.82-4.82A2 2 0 0 0 12.17 2H7Zm2 9h6a1 1 0 1 1 0 2H9a1 1 0 1 1 0-2Zm0 4h6a1 1 0 1 1 0 2H9a1 1 0 1 1 0-2Zm0-8h3a1 1 0 1 1 0 2H9a1 1 0 0 1 0-2Z" />
							</svg>
						{/if}
					</span>
					<h2 class="font-heading text-lg font-semibold text-text-primary">
						{search.trim()
							? `Nenhum modelo encontrado para "${search.trim()}"`
							: 'Nenhum modelo cadastrado'}
					</h2>
					<p class="text-sm text-text-muted">
						{search.trim()
							? 'Tente outra busca ou limpe os filtros.'
							: 'Crie seu primeiro modelo de etapas.'}
					</p>
					<div class="mt-3 flex justify-center gap-2">
						{#if search.trim()}
							<button
								type="button"
								onclick={clearFilters}
								class="rounded-lg border border-border-subtle bg-surface px-4 py-2 text-sm font-medium text-text-primary transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
							>
								Limpar filtros
							</button>
						{/if}
						<button
							type="button"
							onclick={openCreate}
							class="inline-flex items-center gap-2 rounded-lg bg-primary-600 px-4 py-2.5 text-sm font-semibold text-white shadow-md transition-all duration-base hover:-translate-y-px hover:bg-primary-700 hover:shadow-lg focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2"
						>
							<svg viewBox="0 0 20 20" fill="currentColor" class="h-4 w-4" aria-hidden="true">
								<path d="M10 4a1 1 0 0 1 1 1v4h4a1 1 0 1 1 0 2h-4v4a1 1 0 1 1-2 0v-4H5a1 1 0 1 1 0-2h4V5a1 1 0 0 1 1-1Z" />
							</svg>
							<span>{search.trim() ? 'Novo modelo' : 'Criar primeiro modelo'}</span>
						</button>
					</div>
				</div>
			{:else}
				<div
					class="overflow-hidden rounded-xl border border-border-subtle bg-surface shadow-md"
				>
					<div class="overflow-x-auto" aria-busy={loadState !== 'ready'}>
						<table class="w-full border-collapse text-sm">
							<caption class="sr-only">Lista de modelos de etapas</caption>
							<thead>
								<tr class="border-b border-border-subtle bg-surface-muted text-left">
									<th
										scope="col"
										class="px-4 py-3 text-2xs font-semibold uppercase tracking-caps text-text-muted"
									>
										Modelo
									</th>
									<th
										scope="col"
										class="whitespace-nowrap px-4 py-3 text-2xs font-semibold uppercase tracking-caps text-text-muted"
									>
										Etapas
									</th>
									<th
										scope="col"
										class="whitespace-nowrap px-4 py-3 text-2xs font-semibold uppercase tracking-caps text-text-muted"
									>
										Duração
									</th>
									<th
										scope="col"
										class="whitespace-nowrap px-4 py-3 text-2xs font-semibold uppercase tracking-caps text-text-muted"
									>
										Usado em
									</th>
									<th
										scope="col"
										class="px-4 py-3 text-2xs font-semibold uppercase tracking-caps text-text-muted"
									>
										Última edição
									</th>
									<th
										scope="col"
										class="px-4 py-3 pr-5 text-right text-2xs font-semibold uppercase tracking-caps text-text-muted"
									>
										<span class="sr-only">Ações</span>
									</th>
								</tr>
							</thead>
							<tbody>
								{#each data.templates as row (row.id)}
									<tr
										class="border-b border-border-subtle transition-colors duration-fast last:border-0 hover:bg-surface-muted/60"
									>
										<td class="min-w-[280px] px-4 py-3 align-middle">
											<div class="flex items-center gap-3">
												<span
													class="flex h-[38px] w-[38px] shrink-0 items-center justify-center rounded-lg bg-primary-100 text-xs font-bold tracking-wide text-primary-700"
													aria-hidden="true"
												>
													{row.initials}
												</span>
												<div class="flex min-w-0 flex-col gap-0.5">
													<div class="flex items-center gap-2">
														<button
															type="button"
															onclick={() => openEdit(row)}
															class="text-left text-sm font-semibold text-primary-700 hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
														>
															{row.name}
														</button>
														{#if row.is_new}
															<Badge tone="success">novo</Badge>
														{/if}
													</div>
													{#if row.description}
														<p class="truncate text-xs text-text-muted">{row.description}</p>
													{/if}
												</div>
											</div>
										</td>
										<td class="whitespace-nowrap px-4 py-3 align-middle font-medium text-text-primary">
											{row.stage_count}
										</td>
										<td class="whitespace-nowrap px-4 py-3 align-middle font-medium">
											<span class="font-semibold text-text-primary">{row.total_duration}</span><span
												class="ml-0.5 text-xs text-text-muted">d</span
											>
										</td>
										<td class="whitespace-nowrap px-4 py-3 align-middle font-medium">
											<span class="font-semibold text-text-primary">{row.usage_count}</span>
											<span class="ml-1 text-xs text-text-muted"
												>projeto{row.usage_count === 1 ? '' : 's'}</span
											>
										</td>
										<td class="min-w-[160px] px-4 py-3 align-middle">
											{#if row.updated_relative}
												<span class="block font-medium text-text-primary">{row.updated_relative}</span>
												{#if row.editor_name}
													<span class="block text-xs text-text-muted">
														por {row.editor_name}
													</span>
												{/if}
											{:else}
												<span class="text-text-muted">—</span>
											{/if}
										</td>
										<td class="whitespace-nowrap px-4 py-3 pr-5 align-middle">
											<div class="flex items-center justify-end gap-1">
												<button
													type="button"
													onclick={() => openEdit(row)}
													title="Editar modelo"
													aria-label="Editar modelo {row.name}"
													class="inline-flex h-8 w-8 items-center justify-center rounded-md border border-transparent text-text-muted transition-colors duration-fast hover:border-border-subtle hover:bg-surface-muted hover:text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
												>
													<svg viewBox="0 0 20 20" fill="currentColor" class="h-4 w-4" aria-hidden="true">
														<path d="M13.59 2.59a2 2 0 0 1 2.83 2.83l-8.3 8.3a1 1 0 0 1-.42.25l-3 .9a.5.5 0 0 1-.62-.62l.9-3a1 1 0 0 1 .25-.42l8.36-8.24Z" />
													</svg>
												</button>
												<button
													type="button"
													onclick={() => onDuplicate(row)}
													disabled={busyRowId === row.id}
													title="Duplicar modelo"
													aria-label="Duplicar modelo {row.name}"
													class="inline-flex h-8 w-8 items-center justify-center rounded-md border border-transparent text-text-muted transition-colors duration-fast hover:border-border-subtle hover:bg-surface-muted hover:text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-50"
												>
													{#if busyRowId === row.id}
														<span class="text-xs" aria-hidden="true">…</span>
													{:else}
														<svg viewBox="0 0 20 20" fill="currentColor" class="h-4 w-4" aria-hidden="true">
															<path d="M7 3a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2V5a2 2 0 0 0-2-2H7Zm0 2h6v8H7V5Z" />
															<path d="M3 7a2 2 0 0 1 1-1.73V15a2 2 0 0 0 2 2h7.73A2 2 0 0 1 12 18H6a3 3 0 0 1-3-3V7Z" />
														</svg>
													{/if}
												</button>
												<button
													type="button"
													onclick={() => askDelete(row)}
													disabled={busyRowId === row.id}
													title="Excluir modelo"
													aria-label="Excluir modelo {row.name}"
													class="inline-flex h-8 w-8 items-center justify-center rounded-md border border-transparent text-text-muted transition-colors duration-fast hover:border-danger/40 hover:bg-danger/10 hover:text-danger focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-50"
												>
													<svg viewBox="0 0 20 20" fill="currentColor" class="h-4 w-4" aria-hidden="true">
														<path d="M8 3a1 1 0 0 0-1 1v1H4a1 1 0 0 0 0 2h.08l.84 8.4A2 2 0 0 0 6.9 17h6.2a2 2 0 0 0 1.98-1.6L15.92 7H16a1 1 0 1 0 0-2h-3V4a1 1 0 0 0-1-1H8Zm1 4a1 1 0 0 1 1 1v5a1 1 0 1 1-2 0V8a1 1 0 0 1 1-1Zm-3 0a1 1 0 0 1 1 1v5a1 1 0 1 1-2 0V8a1 1 0 0 1 1-1Zm7 0a1 1 0 0 0-1 1v5a1 1 0 1 0 2 0V8a1 1 0 0 0-1-1Z" />
													</svg>
												</button>
											</div>
										</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
				</div>

				<footer class="flex flex-wrap items-center justify-between gap-3 px-1">
					<span class="text-sm text-text-secondary">
						Mostrando <strong class="font-semibold text-text-primary">{data.templates.length}</strong> de
						<strong class="font-semibold text-text-primary">{totalTemplates}</strong> modelo{totalTemplates ===
						1
							? ''
							: 's'}
					</span>
					{#if meta && meta.total_pages > 1}
						<nav class="flex items-center gap-1" aria-label="Paginação de modelos">
							<button
								type="button"
								onclick={() => goToPage(meta.page - 1)}
								disabled={meta.page <= 1}
								aria-label="Página anterior"
								class="inline-flex h-8 min-w-[2rem] items-center justify-center rounded-md border border-border-subtle bg-surface px-2 text-sm text-text-secondary transition-colors duration-fast hover:border-border-strong hover:bg-surface-muted hover:text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:pointer-events-none disabled:opacity-40"
							>
								<svg viewBox="0 0 20 20" fill="currentColor" class="h-4 w-4" aria-hidden="true">
									<path d="M12.7 5.3a1 1 0 0 1 0 1.4L9.42 10l3.3 3.3a1 1 0 0 1-1.42 1.4l-4-4a1 1 0 0 1 0-1.4l4-4a1 1 0 0 1 1.4 0Z" />
								</svg>
							</button>
							{#each Array.from({ length: meta.total_pages }, (_, i) => i + 1) as p (p)}
								<button
									type="button"
									onclick={() => goToPage(p)}
									aria-current={p === meta.page ? 'page' : undefined}
									class="inline-flex h-8 min-w-[2rem] items-center justify-center rounded-md border px-2 text-sm transition-colors duration-fast focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 {p ===
									meta.page
										? 'border-primary-600 bg-primary-600 font-semibold text-white'
										: 'border-border-subtle bg-surface text-text-secondary hover:border-border-strong hover:bg-surface-muted hover:text-text-primary'}"
								>
									{p}
								</button>
							{/each}
							<button
								type="button"
								onclick={() => goToPage(meta.page + 1)}
								disabled={meta.page >= meta.total_pages}
								aria-label="Próxima página"
								class="inline-flex h-8 min-w-[2rem] items-center justify-center rounded-md border border-border-subtle bg-surface px-2 text-sm text-text-secondary transition-colors duration-fast hover:border-border-strong hover:bg-surface-muted hover:text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:pointer-events-none disabled:opacity-40"
							>
								<svg viewBox="0 0 20 20" fill="currentColor" class="h-4 w-4" aria-hidden="true">
									<path d="M7.3 5.3a1 1 0 0 0 0 1.4L10.58 10l-3.3 3.3a1 1 0 1 0 1.42 1.4l4-4a1 1 0 0 0 0-1.4l-4-4a1 1 0 0 0-1.4 0Z" />
								</svg>
							</button>
						</nav>
					{/if}
				</footer>
			{/if}
		{/if}
	{/if}
</section>

<!-- ================= MODAL DE CONFIRMAÇÃO DE EXCLUSÃO ================= -->
{#if confirmDeleteRow}
	<div
		class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
		role="dialog"
		aria-modal="true"
		aria-labelledby="tpl-delete-title"
	>
		<div
			class="w-full max-w-md animate-modal-slide-in rounded-xl border border-border-subtle bg-surface p-6 shadow-lg"
		>
			<div class="flex items-center gap-3">
				<span
					class="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-danger/10 text-danger"
					aria-hidden="true"
				>
					<svg viewBox="0 0 20 20" fill="currentColor" class="h-5 w-5">
						<path d="M8 3a1 1 0 0 0-1 1v1H4a1 1 0 0 0 0 2h.08l.84 8.4A2 2 0 0 0 6.9 17h6.2a2 2 0 0 0 1.98-1.6L15.92 7H16a1 1 0 1 0 0-2h-3V4a1 1 0 0 0-1-1H8Zm1 4a1 1 0 0 1 1 1v5a1 1 0 1 1-2 0V8a1 1 0 0 1 1-1Zm-3 0a1 1 0 0 1 1 1v5a1 1 0 1 1-2 0V8a1 1 0 0 1 1-1Zm7 0a1 1 0 0 0-1 1v5a1 1 0 1 0 2 0V8a1 1 0 0 0-1-1Z" />
					</svg>
				</span>
				<h2 id="tpl-delete-title" class="font-heading text-lg font-bold text-text-primary">
					Apagar modelo?
				</h2>
			</div>
			<p class="mt-2 text-sm text-text-secondary">
				Você está prestes a apagar <strong>{confirmDeleteRow.name}</strong> e todas as suas
				etapas. Esta ação não pode ser desfeita.
			</p>
			<label
				for="tplDeleteConfirm"
				class="mt-4 block text-xs font-semibold uppercase tracking-wide text-text-muted"
			>
				Digite <strong>{DELETE_PHRASE}</strong> para confirmar
			</label>
			<input
				id="tplDeleteConfirm"
				type="text"
				bind:value={confirmPhrase}
				autocomplete="off"
				class="mt-1 w-full rounded-md border border-border-subtle bg-surface px-3 py-2 text-sm text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
			/>
			{#if deleteError}
				<p role="alert" class="mt-2 text-sm text-danger">{deleteError}</p>
			{/if}
			<div class="mt-5 flex items-center justify-end gap-2">
				<button
					type="button"
					onclick={cancelDelete}
					class="rounded-md border border-border-subtle bg-surface px-4 py-2 text-sm font-medium text-text-primary transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
				>
					Cancelar
				</button>
				<button
					type="button"
					onclick={confirmDelete}
					disabled={busyRowId === confirmDeleteRow.id ||
						confirmPhrase.trim().toUpperCase() !== DELETE_PHRASE}
					class="rounded-md border border-danger bg-danger px-4 py-2 text-sm font-medium text-white transition-colors duration-fast hover:opacity-90 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-50"
				>
					{busyRowId === confirmDeleteRow.id ? 'Apagando…' : 'Apagar modelo'}
				</button>
			</div>
		</div>
	</div>
{/if}
