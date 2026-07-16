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
	import { onMount, onDestroy, tick } from 'svelte';
	import {
		fetchTemplateList,
		peekTemplateList,
		fetchTemplateDetail,
		createTemplate,
		updateTemplate,
		duplicateTemplate,
		deleteTemplate
	} from '$lib/api/adminTemplates';
	import { ApiClientError } from '$lib/api/client';
	import { flash } from '$lib/stores/flash';
	import type {
		TemplateListResult,
		TemplateListQuery,
		TemplateOrder,
		TemplateRow,
		TemplateStageInput
	} from '$lib/types/adminTemplates';
	import Card from '$lib/components/Card.svelte';
	import Badge from '$lib/components/Badge.svelte';
	import Modal from '$lib/components/Modal.svelte';
	import PageHeader from '$lib/components/PageHeader.svelte';
	import Button from '$lib/components/Button.svelte';
	import CountBadge from '$lib/components/CountBadge.svelte';
	import AdminTemplatesSkeleton from '$lib/components/skeletons/AdminTemplatesSkeleton.svelte';
	import SelectMenu from '$lib/components/SelectMenu.svelte';
	import type { SelectMenuOption } from '$lib/types/selectMenu';

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
		/**
		 * Marca etapas recém-adicionadas pelo botão "Adicionar"/Enter. Espelha
		 * `dataset.draftStage` do template_form.js: ao perder o foco com nome em
		 * branco, a etapa rascunho é removida automaticamente.
		 */
		_draft?: boolean;
		/** Sinaliza animação de saída antes do `remove()` (classe is-removing). */
		_removing?: boolean;
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

	// SWR: reabre com a ultima listagem boa dos filtros correntes (cache de
	// modulo em $lib/api/adminTemplates) e revalida em silencio — sem flash de
	// "Carregando…" ao voltar para a tela. So sem cache mostra o skeleton.
	const initialData = peekTemplateList({ q: undefined, order: DEFAULT_ORDER, page: 1 });
	let loadState = $state<LoadState>(initialData ? 'ready' : 'loading');
	let data = $state<TemplateListResult | null>(initialData);
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
	const orderSelectOptions = $derived<SelectMenuOption[]>(
		orderOptions.map((opt) => ({ value: opt, label: ORDER_LABELS[opt] }))
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
		inFlight?.abort();
		const controller = new AbortController();
		inFlight = controller;

		// SWR: com cache dos filtros correntes mostra o dado antigo ja (sem
		// skeleton) e a revalidacao abaixo troca em silencio; sem cache, skeleton.
		const query: TemplateListQuery = { q: search.trim() || undefined, order, page };
		const cached = peekTemplateList(query);
		if (cached) {
			data = cached;
			loadState = 'ready';
		} else {
			data = null;
			loadState = 'loading';
		}
		errorMessage = '';

		try {
			const next = await fetchTemplateList(query, controller.signal);
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
			const message =
				err instanceof Error ? err.message : 'Falha ao carregar os modelos.';
			// Revalidacao falhou com dado stale na tela: mantem o dado e avisa via
			// flash, em vez de trocar a lista inteira pelo painel de erro.
			if (data) {
				flash.danger(message);
				return;
			}
			errorMessage = message;
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

	function onOrderChange(next: TemplateOrder): void {
		order = next;
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

	function blankStage(options?: { draft?: boolean }): FormStage {
		return { _key: nextStageKey(), name: '', duration_days: 1, _draft: options?.draft };
	}

	/**
	 * Foca (e seleciona) o input de nome da etapa de índice `index` no próximo
	 * frame, espelhando o `requestAnimationFrame` + `focus()/select()` do
	 * template_form.js ao adicionar uma etapa.
	 */
	async function focusStageName(index: number): Promise<void> {
		await tick();
		const input = stageListEl?.querySelectorAll<HTMLInputElement>(
			'input[data-stage-name]'
		)[index];
		if (input) {
			input.focus();
			input.select();
		}
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

	/**
	 * Adiciona uma etapa ao fim e foca seu nome. `draft` marca a etapa como
	 * rascunho (auto-removida ao perder foco vazia), espelhando o
	 * template_form.js — usado pelo botão "Adicionar" e pelo Enter.
	 */
	function addStage(options?: { draft?: boolean }): void {
		formStages = [...formStages, blankStage(options)];
		void focusStageName(formStages.length - 1);
	}

	/**
	 * Remove a etapa com animação de saída (classe is-removing por ~140ms),
	 * espelhando o `removeStage` do template_form.js. Garante ao menos uma linha
	 * em branco quando a lista esvazia.
	 */
	function removeStage(index: number): void {
		const target = formStages[index];
		if (!target) return;
		target._removing = true;
		formStages = [...formStages];
		setTimeout(() => {
			formStages = formStages.filter((s) => s._key !== target._key);
			if (formStages.length === 0) formStages = [blankStage()];
		}, 140);
	}

	/** "Limpar tudo": confirma antes de remover, como o `clearAll` do original. */
	function clearStages(): void {
		if (formStages.length === 0) return;
		const ok = window.confirm(
			'Remover todas as etapas deste modelo? Esta ação só é aplicada quando você salvar.'
		);
		if (!ok) return;
		formStages = [blankStage()];
	}

	/**
	 * Ao perder o foco de uma etapa rascunho deixada em branco, remove-a — igual
	 * ao handler `focusout` do template_form.js. O `setTimeout(0)` espera o foco
	 * assentar (pode ter ido para outro campo da mesma linha).
	 */
	function onStageFocusOut(index: number): void {
		const stage = formStages[index];
		if (!stage || !stage._draft) return;
		setTimeout(() => {
			const current = formStages.find((s) => s._key === stage._key);
			if (!current || !current._draft) return;
			const row = stageListEl?.querySelectorAll<HTMLElement>('[data-stage-row]')[
				formStages.indexOf(current)
			];
			if (row && row.contains(document.activeElement)) return;
			if (current.name.trim() === '') {
				removeStage(formStages.indexOf(current));
			}
		}, 0);
	}

	/**
	 * Enter no nome da ÚLTIMA etapa adiciona uma nova (rascunho), igual ao
	 * `keydown` do template_form.js. Em etapas intermediárias, Enter não faz nada
	 * especial (deixa o submit/required do browser cuidar).
	 */
	function onStageNameKeydown(event: KeyboardEvent, index: number): void {
		if (event.key !== 'Enter') return;
		if (index !== formStages.length - 1) return;
		event.preventDefault();
		addStage({ draft: true });
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
	//
	// Espelha o template_form.js: o arraste só começa pela alça (grip) e a
	// posição de soltura é mostrada por uma linha indicadora flutuante entre
	// as etapas (em vez de mover itens "ao vivo"). `dropBeforeIndex` é o índice
	// ANTES do qual a etapa arrastada cairá; `formStages.length` significa "no
	// fim". Isso evita o salto visual e reproduz a UX do original.
	let stageListEl: HTMLElement | null = $state(null);
	let dragStageIndex = $state<number | null>(null);
	let dropBeforeIndex = $state<number | null>(null);

	function handleStageDragStart(event: DragEvent, index: number): void {
		dragStageIndex = index;
		if (event.dataTransfer) {
			event.dataTransfer.effectAllowed = 'move';
			// Firefox/Safari exigem um payload para iniciar o arraste.
			try {
				event.dataTransfer.setData('text/plain', String(index));
			} catch {
				/* Safari pode lançar com payload vazio — ignorar. */
			}
		}
	}

	/**
	 * Calcula, a partir do Y do cursor, o índice ANTES do qual o item cairia —
	 * usando o ponto médio de cada linha (exceto a própria que está sendo
	 * arrastada), igual ao `getInsertionSlot` do template_form.js.
	 */
	function computeDropBefore(clientY: number): number {
		if (!stageListEl) return formStages.length;
		const rows = Array.from(
			stageListEl.querySelectorAll<HTMLElement>('[data-stage-row]')
		);
		for (let i = 0; i < rows.length; i += 1) {
			if (i === dragStageIndex) continue;
			const rect = rows[i].getBoundingClientRect();
			if (clientY < rect.top + rect.height / 2) return i;
		}
		return formStages.length;
	}

	function handleStageListDragOver(event: DragEvent): void {
		if (dragStageIndex === null) return;
		event.preventDefault();
		if (event.dataTransfer) event.dataTransfer.dropEffect = 'move';
		dropBeforeIndex = computeDropBefore(event.clientY);
	}

	function handleStageListDragLeave(event: DragEvent): void {
		if (dragStageIndex === null) return;
		const related = event.relatedTarget as Node | null;
		if (!related || !stageListEl?.contains(related)) dropBeforeIndex = null;
	}

	function handleStageListDrop(event: DragEvent): void {
		if (dragStageIndex === null) return;
		event.preventDefault();
		const before = dropBeforeIndex ?? computeDropBefore(event.clientY);
		// Converte o "índice antes do qual cair" para o índice de destino do array
		// após a remoção do item arrastado.
		let to = before;
		if (before > dragStageIndex) to = before - 1;
		if (to > formStages.length - 1) to = formStages.length - 1;
		reorderStage(dragStageIndex, to);
		resetStageDrag();
	}

	function resetStageDrag(): void {
		dragStageIndex = null;
		dropBeforeIndex = null;
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

	// --- Navegação da linha (linha inteira clicável -> editar) ------------
	//
	// Espelha o `navigateToTemplate` do template_list.html: clicar/Enter/Espaço
	// em qualquer ponto da linha abre a edição, EXCETO em elementos interativos
	// (botões de ação) marcados com [data-stop-row-click].

	function isInteractiveTarget(event: Event): boolean {
		const el = event.target as HTMLElement | null;
		if (!el) return false;
		return !!el.closest(
			'[data-stop-row-click], button, a, input, select, textarea, [role="button"]'
		);
	}

	function onRowActivate(event: MouseEvent, row: TemplateRow): void {
		if (isInteractiveTarget(event)) return;
		void openEdit(row);
	}

	function onRowKeydown(event: KeyboardEvent, row: TemplateRow): void {
		if (event.key !== 'Enter' && event.key !== ' ') return;
		if (isInteractiveTarget(event)) return;
		event.preventDefault();
		void openEdit(row);
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

<section aria-labelledby="tpl-title" class="flex flex-col gap-4">
	<!-- CARD ÚNICO header + filtros (padrão de Projetos/Tarefas/Pendentes): chrome
		 de card no wrapper, PageHeader compacto `embedded` e a linha de filtros
		 embutida abaixo de um divisor fino. -->
	<div class="rounded-xl border border-border-subtle bg-surface shadow-sm">
	<PageHeader compact embedded class="min-h-[3.5rem]" labelId="tpl-title">
		{#snippet titleContent()}
			<span class="align-middle">Modelos de Etapas</span>
			{#if data}
				<CountBadge class="ml-2">{totalTemplates} modelo{totalTemplates === 1 ? '' : 's'}</CountBadge>
			{/if}
		{/snippet}
		{#snippet actions()}
			{#if view === 'list'}
				<Button size="sm" onclick={openCreate}>
					{#snippet icon()}<i class="fas fa-plus" aria-hidden="true"></i>{/snippet}
					Novo modelo
				</Button>
			{/if}
		{/snippet}
	</PageHeader>

	{#if view === 'list'}
		<!-- Linha de filtros embutida no card, mesmos controles h-9 das demais telas. -->
		<form
			class="flex flex-wrap items-center gap-2 border-t border-border-subtle px-4 py-2.5"
			role="search"
			aria-label="Filtros de modelos"
			onsubmit={onSearchSubmit}
		>
			<div class="relative min-w-[15rem] flex-1">
				<label for="tplSearch" class="sr-only">Busca livre</label>
				<i
					class="fas fa-search pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-sm text-text-muted"
					aria-hidden="true"
				></i>
				<input
					id="tplSearch"
					name="q"
					type="search"
					autocomplete="off"
					bind:value={search}
					oninput={onSearchInput}
					placeholder="Buscar modelo por nome ou descrição…"
					class="h-9 w-full rounded-lg border border-border-subtle bg-surface pl-8 pr-2.5 text-sm text-text-primary placeholder:text-text-muted transition-colors duration-fast focus:border-primary-500 focus:outline-none"
				/>
			</div>

			<div class="ml-auto flex items-center gap-2">
				<div
					class="inline-flex h-9 items-center gap-2 rounded-lg border border-border-subtle bg-surface px-2.5 text-sm text-text-secondary transition-colors duration-fast hover:border-border-strong hover:bg-surface-muted"
				>
					<i class="fas fa-sliders-h text-text-muted" aria-hidden="true"></i>
					<span class="text-text-muted">Ordenar por:</span>
					<SelectMenu
						id="tplOrder"
						unstyled
						options={orderSelectOptions}
						value={order}
						onSelect={(v) => onOrderChange((v as TemplateOrder) ?? DEFAULT_ORDER)}
						ariaLabel="Ordenar por"
					>
						{#snippet trigger({ label })}
							<span class="cursor-pointer text-sm font-semibold text-text-primary">{label}</span>
						{/snippet}
					</SelectMenu>
				</div>

				{#if hasActiveFilters}
					<button
						type="button"
						onclick={clearFilters}
						title="Limpar filtros"
						aria-label="Limpar filtros"
						class="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-border-subtle bg-surface text-text-secondary transition-all duration-fast ease-out hover:border-border-strong hover:bg-surface-muted hover:text-primary-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
					>
						<i class="fas fa-filter-circle-xmark" aria-hidden="true"></i>
					</button>
				{/if}
			</div>
			<button type="submit" class="sr-only">Filtrar</button>
		</form>
	{/if}
	</div>

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
							class="w-full rounded-md border border-border-subtle bg-surface-muted px-3 py-2 text-base font-semibold text-text-primary transition-all duration-fast placeholder:font-normal placeholder:text-text-muted hover:border-border-strong hover:bg-surface focus:border-primary-500 focus:bg-surface focus:outline-none"
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
							class="w-full resize-y rounded-md border border-border-subtle bg-surface-muted px-3 py-2 text-sm text-text-primary transition-all duration-fast placeholder:text-text-muted hover:border-border-strong hover:bg-surface focus:border-primary-500 focus:bg-surface focus:outline-none"
						></textarea>
					</div>

					<div class="flex flex-col gap-3">
						<div class="flex flex-wrap items-center justify-between gap-2">
							<div class="flex items-baseline gap-2">
								<span class="text-xs font-bold uppercase tracking-caps text-text-primary">
									Etapas
								</span>
								<span class="text-xs text-text-muted" aria-live="polite">
									{formStages.length} etapa{formStages.length === 1 ? '' : 's'}
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

						<ul
							bind:this={stageListEl}
							ondragover={handleStageListDragOver}
							ondragleave={handleStageListDragLeave}
							ondrop={handleStageListDrop}
							class="relative flex flex-col gap-1.5"
							role="list"
						>
							{#each formStages as stage, index (stage._key)}
								<li
									data-stage-row
									class="group relative grid grid-cols-[1fr_24px] items-center gap-2 transition-all duration-fast {stage._removing
										? 'translate-x-4 opacity-0'
										: ''}"
								>
									<!-- Indicador de soltura ANTES desta etapa (linha azul flutuante) -->
									{#if dragStageIndex !== null && dropBeforeIndex === index}
										<span
											class="drop-indicator pointer-events-none absolute left-0 right-0 -mt-1 h-[3px] -translate-y-1/2 rounded-full bg-primary-600"
											style="top: 0"
											aria-hidden="true"
										></span>
									{/if}
									<div
										ondragstart={(e) => handleStageDragStart(e, index)}
										ondragend={resetStageDrag}
										role="presentation"
										class="grid grid-cols-[22px_30px_1fr] items-center gap-2 rounded-lg border bg-surface px-2.5 py-2 transition-all duration-fast hover:border-primary-500/40 hover:bg-surface-muted/40 group-focus-within:border-primary-500/40 group-focus-within:bg-surface-muted/40 {dragStageIndex ===
										index
											? 'scale-[0.99] border-dashed border-border-strong bg-surface-muted opacity-45'
											: 'border-border-subtle'}"
									>
										<button
											type="button"
											draggable={formStages.length > 1}
											aria-label={`Arraste para reordenar a etapa ${index + 1}`}
											title="Arraste para reordenar"
											class="flex h-7 w-[22px] shrink-0 cursor-grab items-center justify-center rounded-md border-none bg-transparent text-border-strong transition-colors duration-fast hover:bg-surface-muted hover:text-primary-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 active:cursor-grabbing {formStages.length >
											1
												? ''
												: 'pointer-events-none opacity-40'}"
										>
											<i class="fas fa-grip-vertical" aria-hidden="true"></i>
										</button>
										<span
											class="flex h-7 w-[30px] shrink-0 items-center justify-center text-sm font-semibold text-text-muted"
											data-stage-number
											aria-hidden="true"
										>
											{index + 1}
										</span>
										<div class="grid grid-cols-[1fr_68px] items-center gap-2">
											<input
												type="text"
												data-stage-name
												bind:value={stage.name}
												placeholder="Nome da etapa"
												aria-label={`Nome da etapa ${index + 1}`}
												onkeydown={(e) => onStageNameKeydown(e, index)}
												onfocusout={() => onStageFocusOut(index)}
												class="h-[34px] w-full rounded-md border border-border-subtle bg-surface px-2.5 text-sm text-text-primary transition-all duration-fast placeholder:text-text-muted focus:border-primary-500 focus:outline-none"
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
													onfocusout={() => onStageFocusOut(index)}
													aria-label={`Duração em dias da etapa ${index + 1}`}
													class="h-full w-full [appearance:textfield] border-none bg-transparent px-1 text-center text-sm font-semibold text-text-primary focus:outline-none [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
												/>
											</div>
										</div>
									</div>
									<!-- Remover (X) revelado no hover/foco, como o original; setas ↑/↓
									     ficam disponíveis por teclado como fallback acessível ao DnD. -->
									<div class="flex flex-col items-center justify-center">
										<button
											type="button"
											onclick={() => moveStage(index, -1)}
											disabled={index === 0}
											aria-label={`Mover etapa ${index + 1} para cima`}
											class="inline-flex h-4 w-5 items-center justify-center rounded text-2xs text-text-muted opacity-0 transition-all duration-fast hover:text-text-primary focus:opacity-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:invisible group-focus-within:opacity-100"
										>
											<i class="fas fa-chevron-up" aria-hidden="true"></i>
										</button>
										<button
											type="button"
											onclick={() => removeStage(index)}
											aria-label={`Remover etapa ${index + 1}`}
											title="Remover etapa"
											class="inline-flex h-[22px] w-[22px] items-center justify-center rounded-md text-xs font-bold text-text-muted opacity-0 transition-all duration-fast hover:bg-surface-muted hover:text-danger focus:opacity-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 group-hover:opacity-100 group-focus-within:opacity-100"
										>
											<i class="fas fa-times" aria-hidden="true"></i>
										</button>
										<button
											type="button"
											onclick={() => moveStage(index, 1)}
											disabled={index === formStages.length - 1}
											aria-label={`Mover etapa ${index + 1} para baixo`}
											class="inline-flex h-4 w-5 items-center justify-center rounded text-2xs text-text-muted opacity-0 transition-all duration-fast hover:text-text-primary focus:opacity-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:invisible group-focus-within:opacity-100"
										>
											<i class="fas fa-chevron-down" aria-hidden="true"></i>
										</button>
									</div>
								</li>
							{/each}
							<!-- Indicador de soltura AO FINAL da lista -->
							{#if dragStageIndex !== null && dropBeforeIndex === formStages.length}
								<span
									class="drop-indicator pointer-events-none -mt-1 h-[3px] rounded-full bg-primary-600"
									aria-hidden="true"
								></span>
							{/if}
						</ul>

						<div>
							<button
								type="button"
								onclick={() => addStage({ draft: true })}
								class="flex min-h-[44px] w-full items-center justify-center gap-2 rounded-md border border-dashed border-border-strong bg-surface-muted px-4 py-2.5 text-sm font-semibold text-primary-500 transition-all duration-fast hover:border-primary-500 hover:bg-surface-elevated focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
							>
								<i class="fas fa-plus-circle" aria-hidden="true"></i>
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
							class="inline-flex h-9 items-center rounded-md bg-primary-600 px-3.5 text-sm font-semibold text-primary-fg shadow-sm transition-all duration-fast hover:bg-primary-700 hover:shadow-md focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 disabled:opacity-50 disabled:shadow-none"
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
		{#if loadState === 'loading'}
			<p role="status" aria-live="polite" class="sr-only">Carregando modelos…</p>
			<AdminTemplatesSkeleton />
		{:else if loadState === 'error'}
			<div
				role="alert"
				class="flex flex-col items-start gap-3 rounded-xl border border-danger bg-danger/5 px-5 py-4"
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
					class="flex flex-col items-center gap-2 rounded-xl border border-border-subtle bg-surface px-6 py-12 text-center shadow-sm"
				>
					<span class="mb-1 text-4xl text-text-muted/60" aria-hidden="true">
						{#if search.trim()}
							<i class="fas fa-search"></i>
						{:else}
							<i class="fas fa-clipboard-list"></i>
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
							<i class="fas fa-plus" aria-hidden="true"></i>
							<span>{search.trim() ? 'Novo modelo' : 'Criar primeiro modelo'}</span>
						</button>
					</div>
				</div>
			{:else}
				<div
					class="overflow-hidden rounded-xl border border-border-subtle bg-surface shadow-sm"
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
										class="hidden px-4 py-3 text-2xs font-semibold uppercase tracking-caps text-text-muted lg:table-cell"
									>
										Silhueta
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
										role="link"
										tabindex="0"
										aria-label="Editar modelo {row.name}"
										onclick={(e) => onRowActivate(e, row)}
										onkeydown={(e) => onRowKeydown(e, row)}
										class="group cursor-pointer border-b border-border-subtle transition-colors duration-fast last:border-0 hover:bg-surface-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:-ring-offset-2 focus-visible:ring-primary-500"
									>
										<td class="min-w-[280px] px-4 py-3 align-middle">
											<div class="flex items-center gap-3">
												<span
													class="flex h-[38px] w-[38px] shrink-0 items-center justify-center rounded-lg bg-surface-elevated text-xs font-bold tracking-wide text-primary-500"
													aria-hidden="true"
												>
													{row.initials}
												</span>
												<div class="flex min-w-0 flex-col gap-0.5">
													<div class="flex items-center gap-2">
														<span class="text-sm font-semibold text-primary-700">
															{row.name}
														</span>
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
										<td class="hidden px-4 py-3 align-middle lg:table-cell">
											{#if row.silhouette.length > 0}
												<!-- Mini bar-chart das durações por etapa (silhueta), fiel ao
												     v4.5: barras de 4px com passo 6px, altura já calculada no
												     backend (par [altura_px, duração_dias]). As barras usam o
												     primary-500 com opacidade que sobe no hover da linha. -->
												<svg
													viewBox="0 0 {row.silhouette.length * 6 - 2} 28"
													class="block h-7 w-auto text-primary-500 [&_rect]:fill-current [&_rect]:opacity-70 group-hover:[&_rect]:opacity-95"
													role="img"
													aria-label="Distribuição de duração das etapas"
												>
													{#each row.silhouette as [height, dur], i (i)}
														<rect
															x={i * 6}
															y={28 - height}
															width="4"
															height={height}
															rx="1.2"
															ry="1.2"
														>
															<title>{dur} dia{dur === 1 ? '' : 's'}</title>
														</rect>
													{/each}
												</svg>
											{:else}
												<span class="text-border-strong" aria-hidden="true">—</span>
											{/if}
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
										<td class="whitespace-nowrap px-4 py-3 pr-5 align-middle" data-stop-row-click>
											<div class="flex items-center justify-end gap-1">
												<button
													type="button"
													onclick={() => onDuplicate(row)}
													disabled={busyRowId === row.id}
													title="Duplicar modelo"
													aria-label="Duplicar modelo {row.name}"
													class="inline-flex h-8 w-8 items-center justify-center rounded-md border border-transparent text-text-muted transition-colors duration-fast hover:border-border-subtle hover:bg-surface-muted hover:text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-50"
												>
													{#if busyRowId === row.id}
														<i class="fas fa-spinner fa-spin" aria-hidden="true"></i>
													{:else}
														<i class="far fa-copy" aria-hidden="true"></i>
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
													<i class="far fa-trash-alt" aria-hidden="true"></i>
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
								<i class="fas fa-chevron-left" aria-hidden="true"></i>
							</button>
							{#each Array.from({ length: meta.total_pages }, (_, i) => i + 1) as p (p)}
								<button
									type="button"
									onclick={() => goToPage(p)}
									aria-current={p === meta.page ? 'page' : undefined}
									class="inline-flex h-8 min-w-[2rem] items-center justify-center rounded-md border px-2 text-sm transition-colors duration-fast focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 {p ===
									meta.page
										? 'border-primary-600 bg-primary-600 font-semibold text-primary-fg'
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
								<i class="fas fa-chevron-right" aria-hidden="true"></i>
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
	<Modal labelId="tpl-delete-title">
			<div class="flex items-center gap-3">
				<span
					class="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-danger/10 text-danger"
					aria-hidden="true"
				>
					<i class="far fa-trash-alt"></i>
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
				class="mt-4 block text-2xs font-bold uppercase tracking-caps text-text-muted"
			>
				Digite <strong>{DELETE_PHRASE}</strong> para confirmar
			</label>
			<input
				id="tplDeleteConfirm"
				type="text"
				bind:value={confirmPhrase}
				autocomplete="off"
				class="mt-1 w-full rounded-md border border-border-subtle bg-surface px-3 py-2 text-sm text-text-primary focus:border-primary-500 focus:outline-none"
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
					class="rounded-md border border-danger bg-danger px-4 py-2 text-sm font-medium text-danger-fg transition-colors duration-fast hover:opacity-90 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-50"
				>
					{busyRowId === confirmDeleteRow.id ? 'Apagando…' : 'Apagar modelo'}
				</button>
			</div>
	</Modal>
{/if}

<style>
	:global(.drop-indicator) {
		box-shadow: 0 2px 8px color-mix(in srgb, var(--ds-color-primary-600) 35%, transparent);
	}
</style>
