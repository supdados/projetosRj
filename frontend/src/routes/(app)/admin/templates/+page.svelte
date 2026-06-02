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
	 *     (adicionar/remover/reordenar com setas).
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
	let formStages = $state<TemplateStageInput[]>([]);
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

	function blankStage(): TemplateStageInput {
		return { name: '', duration_days: 1 };
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
		const target = index + delta;
		if (target < 0 || target >= formStages.length) return;
		const next = [...formStages];
		const [moved] = next.splice(index, 1);
		next.splice(target, 0, moved);
		formStages = next;
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
	<header class="flex flex-col gap-2">
		<nav aria-label="Trilha" class="text-xs text-text-muted">
			<span>Administração</span>
			<span aria-hidden="true" class="px-1">/</span>
			<span class="text-text-secondary">Modelos de Etapas</span>
		</nav>
		<div class="flex flex-wrap items-center justify-between gap-3">
			<div class="flex flex-wrap items-center gap-3">
				<h1 id="tpl-title" class="font-heading text-2xl font-bold text-text-primary">
					Modelos de Etapas
				</h1>
				{#if data}
					<span
						class="inline-flex items-center gap-1 rounded-sm border border-primary-500 bg-primary-100 px-2 py-1 text-xs font-medium text-primary-700"
					>
						{totalTemplates} modelo{totalTemplates === 1 ? '' : 's'}
					</span>
				{/if}
			</div>
			{#if view === 'list'}
				<button
					type="button"
					onclick={openCreate}
					class="rounded-md border border-primary-500 bg-primary-100 px-4 py-2 text-sm font-medium text-primary-700 transition-colors duration-fast hover:bg-primary-100/80 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
				>
					Novo modelo
				</button>
			{/if}
		</div>
		<p class="text-sm text-text-secondary">
			Padronize os ciclos dos projetos — use, duplique ou edite conforme a necessidade da
			secretaria.
		</p>
	</header>

	{#if view === 'form'}
		<!-- =================== FORMULÁRIO CRIAR/EDITAR =================== -->
		<Card>
			<form class="flex flex-col gap-5" onsubmit={saveForm} novalidate>
				<div class="flex items-center justify-between">
					<h2 class="font-heading text-lg font-semibold text-text-primary">
						{formMode === 'edit' ? 'Editar modelo' : 'Novo modelo'}
					</h2>
				</div>

				{#if formError}
					<p
						role="alert"
						class="rounded-md border border-danger bg-surface px-3 py-2 text-sm text-text-primary"
					>
						{formError}
					</p>
				{/if}

				{#if formLoading}
					<p role="status" aria-live="polite" class="text-text-secondary">
						Carregando modelo…
					</p>
				{:else}
					<div class="flex flex-col gap-1">
						<label
							for="tplName"
							class="text-xs font-semibold uppercase tracking-wide text-text-muted"
						>
							Nome do modelo
						</label>
						<input
							id="tplName"
							type="text"
							bind:value={formName}
							required
							placeholder="Ex.: Aquisição simples"
							class="rounded-md border border-border-subtle bg-surface px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
						/>
					</div>

					<div class="flex flex-col gap-1">
						<label
							for="tplDesc"
							class="text-xs font-semibold uppercase tracking-wide text-text-muted"
						>
							Descrição (opcional)
						</label>
						<textarea
							id="tplDesc"
							bind:value={formDescription}
							rows="2"
							placeholder="Para que serve este modelo?"
							class="rounded-md border border-border-subtle bg-surface px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
						></textarea>
					</div>

					<div class="flex flex-col gap-3">
						<div class="flex flex-wrap items-center justify-between gap-2">
							<div class="flex items-baseline gap-2">
								<span
									class="text-xs font-semibold uppercase tracking-wide text-text-muted"
								>
									Etapas
								</span>
								<span class="text-xs text-text-secondary" aria-live="polite">
									{formStages.filter((s) => s.name.trim() !== '').length} etapa{formStages.filter(
										(s) => s.name.trim() !== ''
									).length === 1
										? ''
										: 's'}
									· {stageTotalDuration} dia{stageTotalDuration === 1 ? '' : 's'} no total
								</span>
							</div>
							<button
								type="button"
								onclick={clearStages}
								class="text-xs font-medium text-text-secondary underline-offset-2 hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
							>
								Limpar tudo
							</button>
						</div>

						<ul class="flex flex-col gap-2">
							{#each formStages as stage, index (index)}
								<li
									class="flex items-center gap-2 rounded-md border border-border-subtle bg-surface px-3 py-2"
								>
									<span
										class="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-surface-muted text-xs font-semibold text-text-secondary"
										aria-hidden="true"
									>
										{index + 1}
									</span>
									<div class="flex flex-1 flex-wrap items-center gap-2">
										<input
											type="text"
											bind:value={stage.name}
											placeholder="Nome da etapa"
											aria-label={`Nome da etapa ${index + 1}`}
											class="min-w-[10rem] flex-1 rounded-md border border-border-subtle bg-surface px-3 py-1.5 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
										/>
										<div class="flex items-center gap-1">
											<input
												type="number"
												min="1"
												inputmode="numeric"
												bind:value={stage.duration_days}
												aria-label={`Duração em dias da etapa ${index + 1}`}
												class="w-20 rounded-md border border-border-subtle bg-surface px-2 py-1.5 text-sm text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
											/>
											<span class="text-xs text-text-muted">dias</span>
										</div>
									</div>
									<div class="flex items-center gap-1">
										<button
											type="button"
											onclick={() => moveStage(index, -1)}
											disabled={index === 0}
											aria-label={`Mover etapa ${index + 1} para cima`}
											class="rounded-md border border-border-subtle bg-surface px-2 py-1 text-xs text-text-secondary transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-40"
										>
											↑
										</button>
										<button
											type="button"
											onclick={() => moveStage(index, 1)}
											disabled={index === formStages.length - 1}
											aria-label={`Mover etapa ${index + 1} para baixo`}
											class="rounded-md border border-border-subtle bg-surface px-2 py-1 text-xs text-text-secondary transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-40"
										>
											↓
										</button>
										<button
											type="button"
											onclick={() => removeStage(index)}
											aria-label={`Remover etapa ${index + 1}`}
											class="rounded-md border border-border-subtle bg-surface px-2 py-1 text-xs text-danger transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
										>
											Remover
										</button>
									</div>
								</li>
							{/each}
						</ul>

						<div>
							<button
								type="button"
								onclick={addStage}
								class="rounded-md border border-border-subtle bg-surface px-3 py-2 text-sm font-medium text-primary-700 transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
							>
								+ Adicionar nova etapa
							</button>
						</div>
					</div>

					<div class="flex items-center justify-end gap-2 border-t border-border-subtle pt-4">
						<button
							type="button"
							onclick={cancelForm}
							class="rounded-md border border-border-subtle bg-surface px-4 py-2 text-sm font-medium text-text-primary transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
						>
							Cancelar
						</button>
						<button
							type="submit"
							disabled={formSaving || !formValid}
							class="rounded-md border border-primary-500 bg-primary-100 px-4 py-2 text-sm font-medium text-primary-700 transition-colors duration-fast hover:bg-primary-100/80 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-50"
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
			class="flex flex-wrap items-end gap-4 rounded-lg border border-border-subtle bg-surface px-5 py-4 shadow-sm"
			role="search"
			aria-label="Filtros de modelos"
			onsubmit={onSearchSubmit}
		>
			<div class="flex min-w-[16rem] flex-1 flex-col gap-1">
				<label
					for="tplSearch"
					class="text-xs font-semibold uppercase tracking-wide text-text-muted"
				>
					Busca livre
				</label>
				<input
					id="tplSearch"
					name="q"
					type="search"
					autocomplete="off"
					bind:value={search}
					oninput={onSearchInput}
					placeholder="Buscar por nome ou descrição…"
					class="rounded-md border border-border-subtle bg-surface px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
				/>
			</div>

			<div class="flex min-w-[12rem] flex-col gap-1">
				<label
					for="tplOrder"
					class="text-xs font-semibold uppercase tracking-wide text-text-muted"
				>
					Ordenar por
				</label>
				<select
					id="tplOrder"
					value={order}
					onchange={onOrderChange}
					class="rounded-md border border-border-subtle bg-surface px-3 py-2 text-sm text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
				>
					{#each orderOptions as opt (opt)}
						<option value={opt}>{ORDER_LABELS[opt]}</option>
					{/each}
				</select>
			</div>

			<div class="flex items-end gap-2">
				<button
					type="submit"
					class="rounded-md border border-primary-500 bg-primary-100 px-4 py-2 text-sm font-medium text-primary-700 transition-colors duration-fast hover:bg-primary-100/80 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
				>
					Filtrar
				</button>
				{#if hasActiveFilters}
					<button
						type="button"
						onclick={clearFilters}
						class="rounded-md border border-border-subtle bg-surface px-4 py-2 text-sm font-medium text-text-primary transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
					>
						Limpar filtros
					</button>
				{/if}
			</div>
		</form>

		{#if loadState === 'loading'}
			<p role="status" aria-live="polite" class="text-text-secondary">
				Carregando modelos…
			</p>
		{:else if loadState === 'error'}
			<div
				role="alert"
				class="flex flex-col items-start gap-3 rounded-lg border border-danger bg-surface px-5 py-4"
			>
				<p class="text-text-primary">{errorMessage}</p>
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
					class="rounded-md border border-danger bg-surface px-3 py-2 text-sm text-text-primary"
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
				<div class="rounded-lg border border-border-subtle bg-surface px-5 py-12 text-center">
					<h2 class="font-heading text-lg font-semibold text-text-primary">
						{search.trim() ? `Nenhum modelo encontrado para "${search.trim()}"` : 'Nenhum modelo cadastrado'}
					</h2>
					<p class="mt-2 text-sm text-text-muted">
						{search.trim()
							? 'Tente outra busca ou limpe os filtros.'
							: 'Crie seu primeiro modelo de etapas.'}
					</p>
					<div class="mt-4 flex justify-center gap-2">
						{#if search.trim()}
							<button
								type="button"
								onclick={clearFilters}
								class="rounded-md border border-border-subtle bg-surface px-4 py-2 text-sm font-medium text-text-primary transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
							>
								Limpar filtros
							</button>
						{/if}
						<button
							type="button"
							onclick={openCreate}
							class="rounded-md border border-primary-500 bg-primary-100 px-4 py-2 text-sm font-medium text-primary-700 transition-colors duration-fast hover:bg-primary-100/80 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
						>
							Novo modelo
						</button>
					</div>
				</div>
			{:else}
				<Card>
					<div class="overflow-x-auto" aria-busy={loadState !== 'ready'}>
						<table class="w-full border-collapse text-sm">
							<caption class="sr-only">Lista de modelos de etapas</caption>
							<thead>
								<tr class="border-b border-border-subtle text-left text-text-muted">
									<th scope="col" class="px-3 py-2 font-semibold">Modelo</th>
									<th scope="col" class="px-3 py-2 font-semibold">Etapas</th>
									<th scope="col" class="px-3 py-2 font-semibold">Duração</th>
									<th scope="col" class="px-3 py-2 font-semibold">Usado em</th>
									<th scope="col" class="px-3 py-2 font-semibold">Última edição</th>
									<th scope="col" class="px-3 py-2 font-semibold text-right">
										<span class="sr-only">Ações</span>
									</th>
								</tr>
							</thead>
							<tbody>
								{#each data.templates as row (row.id)}
									<tr class="border-b border-border-subtle last:border-0">
										<td class="px-3 py-2">
											<div class="flex items-center gap-3">
												<span
													class="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-surface-muted text-xs font-semibold text-text-secondary"
													aria-hidden="true"
												>
													{row.initials}
												</span>
												<div class="flex flex-col">
													<div class="flex items-center gap-2">
														<button
															type="button"
															onclick={() => openEdit(row)}
															class="text-left font-medium text-primary-700 hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
														>
															{row.name}
														</button>
														{#if row.is_new}
															<Badge tone="info">novo</Badge>
														{/if}
													</div>
													{#if row.description}
														<p class="text-xs text-text-muted">{row.description}</p>
													{/if}
												</div>
											</div>
										</td>
										<td class="px-3 py-2 text-text-secondary">{row.stage_count}</td>
										<td class="px-3 py-2 text-text-secondary">
											{row.total_duration}d
										</td>
										<td class="px-3 py-2 text-text-secondary">
											{row.usage_count} projeto{row.usage_count === 1 ? '' : 's'}
										</td>
										<td class="px-3 py-2 text-text-secondary">
											{#if row.updated_relative}
												<span>{row.updated_relative}</span>
												{#if row.editor_name}
													<span class="block text-xs text-text-muted">
														por {row.editor_name}
													</span>
												{/if}
											{:else}
												<span class="text-text-muted">—</span>
											{/if}
										</td>
										<td class="px-3 py-2">
											<div class="flex items-center justify-end gap-2">
												<button
													type="button"
													onclick={() => openEdit(row)}
													class="rounded-md border border-border-subtle bg-surface px-3 py-1.5 text-xs font-medium text-text-primary transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
												>
													Editar
												</button>
												<button
													type="button"
													onclick={() => onDuplicate(row)}
													disabled={busyRowId === row.id}
													class="rounded-md border border-border-subtle bg-surface px-3 py-1.5 text-xs font-medium text-text-primary transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-50"
												>
													{busyRowId === row.id ? '…' : 'Duplicar'}
												</button>
												<button
													type="button"
													onclick={() => askDelete(row)}
													disabled={busyRowId === row.id}
													class="rounded-md border border-border-subtle bg-surface px-3 py-1.5 text-xs font-medium text-danger transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-50"
												>
													Excluir
												</button>
											</div>
										</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
				</Card>

				<footer class="flex flex-wrap items-center justify-between gap-3">
					<span class="text-sm text-text-secondary">
						Mostrando <strong>{data.templates.length}</strong> de
						<strong>{totalTemplates}</strong> modelo{totalTemplates === 1 ? '' : 's'}
					</span>
					{#if meta && meta.total_pages > 1}
						<nav class="flex items-center gap-3" aria-label="Paginação de modelos">
							<button
								type="button"
								onclick={() => goToPage(meta.page - 1)}
								disabled={meta.page <= 1}
								class="rounded-md border border-border-subtle bg-surface px-4 py-2 text-sm font-medium text-text-primary transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-50"
							>
								Anterior
							</button>
							<span class="text-sm text-text-secondary" aria-live="polite">
								Página {meta.page} de {meta.total_pages}
							</span>
							<button
								type="button"
								onclick={() => goToPage(meta.page + 1)}
								disabled={meta.page >= meta.total_pages}
								class="rounded-md border border-border-subtle bg-surface px-4 py-2 text-sm font-medium text-text-primary transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-50"
							>
								Próxima
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
		<div class="w-full max-w-md rounded-lg border border-border-subtle bg-surface p-6 shadow-lg">
			<h2 id="tpl-delete-title" class="font-heading text-lg font-semibold text-text-primary">
				Apagar modelo?
			</h2>
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
