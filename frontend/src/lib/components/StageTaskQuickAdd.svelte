<script lang="ts">
	/**
	 * DRAWER "Tarefas da etapa" — usado no Detalhe do Projeto e em Projetos
	 * Pendentes. As tarefas usam o MESMO template da página /tarefas (modo
	 * lista): grade `.task-hub-grid` com as colunas Descrição | Prioridade |
	 * Tipo | Status | Responsável | Ações, linhas `TaskHubTaskRow` (edição
	 * inline de descrição, chips-select, AssigneePicker, comentários inline,
	 * anexos, exclusão com confirm) e o form "+ Adicionar nova tarefa" idêntico
	 * ao do hub (descrição + prioridade + tipo + status + responsáveis).
	 *
	 * Diferenças deliberadas em relação ao hub (são a identidade deste drawer):
	 *  - o form de adição abre JÁ ABERTO e permanece aberto após salvar
	 *    (Enter salva e abre nova linha — espírito quick-add preservado);
	 *  - header fixo com pílula done/total e barra de progresso; a pílula da
	 *    etapa na página hospedeira sincroniza via `onProgressChange`;
	 *  - fechar com rascunho digitado pede confirmação inline no rodapé;
	 *  - etapa concluída bloqueia criação (aviso no lugar do form).
	 *
	 * Toda mutação re-busca a lista (server-autoritativo, paridade com o hub).
	 * O TaskDrawer (store injetada por prop; NÃO recriar aqui) abre por cima ao
	 * clicar na descrição e, ao fechar, a lista é re-buscada. O confete de
	 * finalização é fornecido às linhas via contexto `celebrateFinalize`
	 * (mesmo motor da página de tarefas).
	 */
	import { onMount, setContext, tick } from 'svelte';
	import { fly, fade } from 'svelte/transition';
	import { cubicOut } from 'svelte/easing';
	import { ApiClientError } from '$lib/api/client';
	import { fetchStageTasks } from '$lib/api/pendentesMutations';
	import { createTarefa, deleteTarefa } from '$lib/api/tasks';
	import { focusTrap } from '$lib/actions/focusTrap';
	import type { StageTaskCard } from '$lib/types/pendentes';
	import type { TaskAssignee, TaskCard } from '$lib/types/tasks';
	import type { TaskDrawerStore } from '$lib/stores/taskDrawer';
	import { normalizeStatus } from '$lib/utils/taskStatus';
	import TaskHubTaskRow from '$lib/components/TaskHubTaskRow.svelte';
	import AssigneePicker from '$lib/components/AssigneePicker.svelte';
	import SelectMenu from '$lib/components/SelectMenu.svelte';
	import type { SelectMenuOption } from '$lib/types/selectMenu';
	import {
		triggerTaskFinalizeConfetti,
		type CelebrationOriginLike
	} from '$lib/celebration/confettiEpic';
	import '$lib/celebration/confetti.css';

	interface Props {
		projectId: number;
		projectTitulo: string;
		etapaId: number;
		etapaDescricao: string;
		/** Datas formuladas pelo card ("dd/mm/yyyy — dd/mm/yyyy" etc.). */
		etapaDatas?: string;
		/** Etapa concluída? Bloqueia criação (aviso no rodapé), igual ao legado. */
		stageDone: boolean;
		/** Store do drawer (reusada da página; NÃO recriar aqui). */
		drawer: TaskDrawerStore;
		/** Fecha o drawer. */
		onClose: () => void;
		/** Notifica a página do novo done/total para sincronizar a pílula. */
		onProgressChange: (etapaId: number, done: number, total: number) => void;
	}

	let {
		projectId,
		projectTitulo,
		etapaId,
		etapaDescricao,
		etapaDatas = '',
		stageDone,
		drawer,
		onProgressChange,
		onClose
	}: Props = $props();

	// Confete ao finalizar via chip de status — MESMO motor e contexto da página
	// de tarefas (TaskHubTaskRow lê `celebrateFinalize` do contexto).
	setContext('celebrateFinalize', (origin?: unknown) =>
		triggerTaskFinalizeConfetti(origin as CelebrationOriginLike)
	);

	type LoadState = 'loading' | 'ready' | 'error';

	let loadState = $state<LoadState>('loading');
	let loadError = $state<string>('');
	let tarefas = $state<StageTaskCard[]>([]);

	let panelEl = $state<HTMLDivElement | null>(null);

	const total = $derived(tarefas.length);
	const done = $derived(tarefas.filter((t) => normalizeStatus(t.status) === 'finalizada').length);
	const progressPct = $derived(total === 0 ? 0 : Math.round((done / total) * 100));

	const eyebrow = $derived(`Tarefas da etapa · ${projectTitulo}`);

	/** Card da etapa -> card do hub (a linha não usa os extras de agrupamento). */
	function toHubCard(task: StageTaskCard): TaskCard {
		return {
			...task,
			etapa_titulo: etapaDescricao,
			etapa_display_id: null,
			is_first_of_stage: false
		};
	}
	const hubTasks = $derived(tarefas.map(toHubCard));

	async function loadTasks(): Promise<void> {
		loadState = tarefas.length ? loadState : 'loading';
		loadError = '';
		try {
			const result = await fetchStageTasks(projectId, etapaId);
			tarefas = result.tarefas;
			loadState = 'ready';
			onProgressChange(etapaId, result.done, result.total);
		} catch (err) {
			if (err instanceof ApiClientError && err.code === 'unauthenticated') return;
			loadError = err instanceof Error ? err.message : 'Falha ao carregar as tarefas.';
			loadState = 'error';
		}
	}

	onMount(() => {
		void loadTasks();
		// O form de adição nasce FECHADO: o painel abre mostrando "+ Adicionar
		// nova tarefa" e só expande o form ao clicar (paridade com o hub).
	});

	// Re-lista ao FECHAR o TaskDrawer (edição inline pode mudar status/contador).
	let drawerWasOpen = false;
	$effect(() => {
		const open = $drawer.status !== 'closed';
		if (drawerWasOpen && !open) void loadTasks();
		drawerWasOpen = open;
	});

	/** Exclui via linha do hub (mesmo contrato `onDelete` da página de tarefas). */
	async function deleteCard(taskId: number): Promise<boolean> {
		try {
			await deleteTarefa(taskId);
		} catch {
			return false;
		}
		await loadTasks();
		return true;
	}

	function openDrawer(taskId: number): void {
		void drawer.open(taskId, { mode: 'etapa' });
	}

	// --- Form "+ Adicionar nova tarefa" (template idêntico ao hub) -------------

	type AddDraft = {
		descricao: string;
		prioridade: string;
		tipo: string;
		status: string;
		assignees: TaskAssignee[];
		saving: boolean;
		error: string | null;
	};

	const ADD_STATUS_OPTIONS: { value: string; label: string }[] = [
		{ value: 'nao_iniciada', label: 'Não iniciada' },
		{ value: 'em_andamento', label: 'Em andamento' },
		{ value: 'para_validacao', label: 'Para validação' },
		{ value: 'para_ajustes', label: 'Para ajustes' },
		{ value: 'finalizada', label: 'Finalizada' }
	];
	const ADD_PRIORIDADE_OPTIONS: { value: string; label: string }[] = [
		{ value: '', label: 'Prioridade' },
		{ value: 'baixa', label: 'Baixa' },
		{ value: 'media', label: 'Média' },
		{ value: 'alta', label: 'Alta' },
		{ value: 'urgente', label: 'Urgente' }
	];
	// Sem "implementacao": é tipo LEGADO (`LEGACY_TIPOS`) — a criação via
	// /api/tarefas só aceita VALID_TIPOS e descartaria o valor silenciosamente.
	const ADD_TIPO_OPTIONS: { value: string; label: string }[] = [
		{ value: '', label: 'Tipo' },
		{ value: 'bug', label: 'Bug' },
		{ value: 'melhoria', label: 'Melhoria' },
		{ value: 'duvida', label: 'Dúvida' },
		{ value: 'outros', label: 'Outros' }
	];

	// Dots dos chips: mesmas cores dos tons já usados no hub (taskLabels.ts —
	// STATUS_TONE/STATUS_BAR_CLASS e priority-* tokens), não inventadas aqui.
	const PRIORIDADE_DOT: Record<string, string> = {
		baixa: 'var(--ds-color-priority-baixa)',
		media: 'var(--ds-color-priority-media)',
		alta: 'var(--ds-color-priority-alta)',
		urgente: 'var(--ds-color-priority-urgente)'
	};
	const STATUS_DOT: Record<string, string> = {
		nao_iniciada: 'var(--color-text-muted)',
		em_andamento: 'var(--ds-color-info-600)',
		para_validacao: 'var(--ds-color-primary-500)',
		para_ajustes: 'var(--ds-color-warning-600)',
		finalizada: 'var(--ds-color-success-600)'
	};

	// Placeholder "" vira `SelectMenu` sem opção (value null = mostra o placeholder).
	const PRIORIDADE_MENU_OPTIONS: SelectMenuOption[] = ADD_PRIORIDADE_OPTIONS.filter(
		(opt) => opt.value
	).map((opt) => ({ value: opt.value, label: opt.label, dot: PRIORIDADE_DOT[opt.value] }));
	const TIPO_MENU_OPTIONS: SelectMenuOption[] = ADD_TIPO_OPTIONS.filter((opt) => opt.value).map(
		(opt) => ({ value: opt.value, label: opt.label })
	);
	const STATUS_MENU_OPTIONS: SelectMenuOption[] = ADD_STATUS_OPTIONS.map((opt) => ({
		value: opt.value,
		label: opt.label,
		dot: STATUS_DOT[opt.value]
	}));

	let addOpen = $state(false);
	let addDraft = $state<AddDraft>(emptyAddDraft());
	let addTextareaEl = $state<HTMLTextAreaElement | null>(null);

	function emptyAddDraft(): AddDraft {
		return {
			descricao: '',
			prioridade: '',
			tipo: '',
			status: 'nao_iniciada',
			assignees: [],
			saving: false,
			error: null
		};
	}

	function openAddForm(): void {
		addOpen = true;
		addDraft = emptyAddDraft();
	}

	function cancelAddForm(): void {
		addOpen = false;
		addDraft = emptyAddDraft();
	}

	/**
	 * Action (paridade com o hub): fecha o form ao clicar FORA dele — só se nada
	 * foi digitado (não descarta texto em andamento). Captura no `pointerdown`.
	 */
	function closeOnClickOutside(node: HTMLElement) {
		function handle(event: PointerEvent): void {
			if (node.contains(event.target as Node)) return;
			if (!addDraft.descricao.trim()) cancelAddForm();
		}
		document.addEventListener('pointerdown', handle, true);
		return {
			destroy() {
				document.removeEventListener('pointerdown', handle, true);
			}
		};
	}

	/** Auto-resize da textarea de descrição (piso 34px; teto via max-h CSS). */
	function autoResizeAdd(event: Event): void {
		const el = event.currentTarget as HTMLTextAreaElement;
		el.style.height = 'auto';
		el.style.height = `${Math.max(34, el.scrollHeight)}px`;
	}

	function onAddTextareaKeydown(event: KeyboardEvent): void {
		if (event.key === 'Escape') {
			// stopPropagation: o Esc aqui só fecha o FORM (não o drawer inteiro).
			event.preventDefault();
			event.stopPropagation();
			cancelAddForm();
			return;
		}
		if (event.key === 'Enter' && !event.shiftKey) {
			event.preventDefault();
			void submitAddForm();
		}
	}

	async function submitAddForm(): Promise<void> {
		if (addDraft.saving || stageDone) return;
		addDraft.error = null;
		// Descrição vazia: paridade com o hub — apenas não submete.
		if (!addDraft.descricao.trim()) return;

		addDraft.saving = true;
		try {
			await createTarefa({
				project_id: projectId,
				etapa_id: etapaId,
				descricao: addDraft.descricao.trim(),
				status: addDraft.status,
				assignee_ids: addDraft.assignees.map((a) => a.id),
				prioridade: addDraft.prioridade || null,
				tipo_pedido: addDraft.tipo || null
			});
			// Form permanece aberto e focado (Enter salva e abre nova linha); a
			// lista re-busca e a tarefa entra JÁ ordenada (status, prioridade) —
			// regra do hub aplicada pelo endpoint, por isso sem scroll automático.
			addDraft = emptyAddDraft();
			await loadTasks();
			await tick();
			addTextareaEl?.focus();
		} catch (err) {
			addDraft.error =
				err instanceof ApiClientError ? err.message : 'Erro ao adicionar tarefa.';
			addDraft.saving = false;
		}
	}

	// --- Fechamento do drawer ---------------------------------------------------

	// Descarte de rascunho ao fechar (confirm inline no rodapé, sem window.confirm).
	let confirmingDiscard = $state(false);

	/** Fecha o drawer; com rascunho não salvo no form, pede confirmação inline. */
	function attemptClose(): void {
		if (addDraft.descricao.trim() && !confirmingDiscard) {
			confirmingDiscard = true;
			return;
		}
		onClose();
	}

	function keepEditing(): void {
		confirmingDiscard = false;
		addTextareaEl?.focus();
	}

	/**
	 * Escape global do drawer — só fecha quando nenhum filho tratou a tecla:
	 *  - TaskDrawer aberto por cima trata o Esc dele (e faz stopPropagation);
	 *  - `defaultPrevented`: edição inline de descrição, popover do
	 *    AssigneePicker e o form de adição cancelam com preventDefault;
	 *  - painel de comentários da linha fecha a si mesmo (região identificável);
	 *  - lightbox de anexos (aria-modal aninhado) fecha a si mesmo.
	 */
	function onWindowKeydown(event: KeyboardEvent): void {
		if (event.key !== 'Escape') return;
		if ($drawer.status !== 'closed') return;
		if (event.defaultPrevented) return;
		const target = event.target instanceof HTMLElement ? event.target : null;
		if (target?.closest('[id$="-comments-region"]')) return;
		if (panelEl?.querySelector('[aria-modal="true"]')) return;
		if (confirmingDiscard) {
			keepEditing();
			return;
		}
		attemptClose();
	}

	// Rótulos de coluna (mesmo token visual do StageGroupHeader do hub, um
	// degrau menor — acompanha a variante compacta da grade).
	const COL_LABEL =
		'self-center text-center text-2xs font-bold uppercase tracking-[0.08em] text-text-secondary';
</script>

<svelte:window onkeydown={onWindowKeydown} />

<!-- Backdrop: mesma tinta/blur do TaskDrawer, fade 200ms. -->
<div
	class="fixed inset-0 z-modal bg-overlay backdrop-blur-[1.2px]"
	role="presentation"
	transition:fade={{ duration: 200 }}
	onclick={attemptClose}
></div>

<!-- Painel lateral: 880px fixo (fullscreen abaixo disso via min()); a grade
     interna usa larguras próprias (.stq-compact, min 800px + scroll-x).
     O TaskDrawer (645px) abre por cima ao clicar numa tarefa. -->
<div
	bind:this={panelEl}
	role="dialog"
	aria-modal="true"
	aria-labelledby="stage-quick-add-title"
	tabindex="-1"
	use:focusTrap
	transition:fly={{ x: 880, duration: 240, easing: cubicOut, opacity: 1 }}
	class="stq-panel fixed right-0 top-0 z-modal flex h-full w-[min(880px,100vw)] flex-col border-l border-border-subtle bg-surface shadow-[-18px_0_44px_rgba(12,44,74,0.18)]"
>
	<header
		class="flex shrink-0 flex-col gap-3 border-b border-border-subtle bg-surface-elevated/70 px-5 pb-3.5 pt-4"
	>
		<div class="flex items-start justify-between gap-3">
			<div class="flex min-w-0 flex-1 flex-col gap-1">
				<p class="m-0 truncate text-2xs font-bold uppercase tracking-[0.08em] text-text-muted">
					{eyebrow}
				</p>
				<h2
					id="stage-quick-add-title"
					class="m-0 line-clamp-2 break-words font-heading text-lg font-bold leading-snug text-text-primary"
				>
					{etapaDescricao}
				</h2>
				{#if etapaDatas}
					<span class="text-xs text-text-muted">{etapaDatas}</span>
				{/if}
			</div>
			<div class="flex shrink-0 items-center gap-2">
				<span
					class="inline-flex items-center rounded-full border border-border-subtle bg-surface px-2 py-0.5 text-xs font-semibold text-text-secondary"
					aria-label={`${done} de ${total} tarefas concluídas`}
				>
					{done}/{total}
				</span>
				<button
					type="button"
					onclick={attemptClose}
					aria-label="Fechar"
					class="inline-flex h-8 w-8 items-center justify-center rounded-md text-text-secondary transition-colors duration-fast hover:bg-surface-muted hover:text-primary-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
				>
					<svg viewBox="0 0 24 24" class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
						<path d="M18 6 6 18M6 6l12 12" />
					</svg>
				</button>
			</div>
		</div>
		<!-- Progresso done/total (espelha a pílula; some quando não há tarefas). -->
		{#if total > 0}
			<div
				class="h-1 w-full overflow-hidden rounded-full bg-border-subtle"
				role="progressbar"
				aria-valuemin={0}
				aria-valuemax={total}
				aria-valuenow={done}
				aria-label="Progresso das tarefas da etapa"
			>
				<div
					class="h-full rounded-full bg-primary-500 transition-[width] duration-300 ease-out"
					style:width={`${progressPct}%`}
				></div>
			</div>
		{/if}
	</header>

	<!-- Corpo rolável: bloco de tarefas no MESMO template do hub. -->
	<div class="thin-scroll flex-1 overflow-y-auto px-4 py-4">
		{#if loadState === 'loading'}
			<div role="status" aria-live="polite" class="flex items-center gap-2 py-2 text-sm text-text-secondary">
				<span
					class="h-4 w-4 animate-spin rounded-full border-2 border-border-subtle border-t-primary-600"
					aria-hidden="true"
				></span>
				Carregando tarefas…
			</div>
		{:else if loadState === 'error'}
			<div role="alert" class="flex flex-col items-start gap-2 rounded-lg border border-danger bg-surface px-4 py-3 text-sm text-text-primary">
				<p class="m-0">{loadError}</p>
				<button
					type="button"
					onclick={() => void loadTasks()}
					class="rounded-md border border-border-subtle bg-surface px-3 py-1.5 text-sm font-medium text-text-primary transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
				>
					Tentar novamente
				</button>
			</div>
		{:else}
			<div class="stq-compact overflow-hidden rounded-lg border border-border-subtle">
				<!-- Scroller horizontal ÚNICO (header de colunas + linhas + form),
				     como no hub — colunas sempre alinhadas. -->
				<div class="overflow-x-auto overflow-y-hidden">
					<div class="task-hub-grid bg-primary-100 px-3 py-2">
						<span class="text-2xs font-bold uppercase tracking-[0.08em] text-text-secondary">
							Tarefa
						</span>
						<span class={COL_LABEL}>Prioridade</span>
						<span class={COL_LABEL}>Tipo</span>
						<span class={COL_LABEL}>Status</span>
						<span class={COL_LABEL}>Responsável</span>
						<span class={COL_LABEL}>Ações</span>
					</div>

					<div class="border-t border-border-subtle">
						{#if tarefas.length === 0}
							<p class="m-0 px-3 py-6 text-center text-sm text-text-muted">
								Nenhuma tarefa nesta etapa ainda.
							</p>
						{:else}
							{#each hubTasks as task (task.id)}
								<TaskHubTaskRow
									{task}
									onOpen={openDrawer}
									onDelete={deleteCard}
									onChanged={() => void loadTasks()}
								/>
							{/each}
						{/if}

						{#if stageDone}
							<p
								role="status"
								class="m-0 border-t border-border-subtle bg-surface-muted px-3 py-2.5 text-sm text-text-secondary"
							>
								Etapa concluída — desfaça a conclusão para criar tarefas.
							</p>
						{:else if addOpen}
							<!-- Form de adição: MESMO template do hub (grade + campos). -->
							<form
								use:closeOnClickOutside
								class="border-t border-border-subtle bg-surface {addDraft.saving
									? 'pointer-events-none opacity-[0.72]'
									: ''}"
								aria-label="Nova tarefa em {etapaDescricao}"
								onsubmit={(e) => {
									e.preventDefault();
									void submitAddForm();
								}}
							>
								<div class="task-hub-grid min-h-[44px] items-center px-3">
									<textarea
										bind:this={addTextareaEl}
										bind:value={addDraft.descricao}
										onkeydown={onAddTextareaKeydown}
										oninput={autoResizeAdd}
										disabled={addDraft.saving}
										rows="1"
										placeholder="Descreva a tarefa…"
										aria-label="Descrição da tarefa"
										class="max-h-[120px] min-h-[34px] w-full min-w-0 resize-y rounded-sm border border-border-subtle bg-surface px-2 py-1.5 text-sm leading-normal text-text-primary transition-colors duration-fast focus:border-primary-500 focus:outline-none disabled:opacity-60"
									></textarea>
									<SelectMenu
										options={PRIORIDADE_MENU_OPTIONS}
										value={addDraft.prioridade || null}
										onSelect={(v) => (addDraft.prioridade = v ?? '')}
										placeholder="Prioridade"
										disabled={addDraft.saving}
										ariaLabel="Prioridade"
										size="sm"
									/>
									<SelectMenu
										options={TIPO_MENU_OPTIONS}
										value={addDraft.tipo || null}
										onSelect={(v) => (addDraft.tipo = v ?? '')}
										placeholder="Tipo"
										disabled={addDraft.saving}
										ariaLabel="Tipo de pedido"
										size="sm"
									/>
									<SelectMenu
										options={STATUS_MENU_OPTIONS}
										value={addDraft.status}
										onSelect={(v) => (addDraft.status = v ?? 'nao_iniciada')}
										disabled={addDraft.saving}
										ariaLabel="Status"
										size="sm"
									/>
									<AssigneePicker
										projectValue={String(projectId)}
										bind:assignees={addDraft.assignees}
										disabled={addDraft.saving}
									/>
									<div class="flex items-center justify-center gap-1">
										<button
											type="submit"
											disabled={addDraft.saving}
											title="Salvar"
											aria-label="Salvar tarefa"
											class="inline-flex h-[30px] w-[30px] items-center justify-center rounded-sm border border-primary-500 bg-primary-100 text-primary-700 transition-colors duration-fast hover:bg-primary-100/80 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-50"
										>
											<i class="fas fa-check text-xs" aria-hidden="true"></i>
										</button>
										<button
											type="button"
											onclick={cancelAddForm}
											disabled={addDraft.saving}
											title="Cancelar"
											aria-label="Cancelar"
											class="inline-flex h-[30px] w-[30px] items-center justify-center rounded-sm border border-border-subtle text-text-secondary transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-50"
										>
											<i class="fas fa-xmark text-xs" aria-hidden="true"></i>
										</button>
									</div>
								</div>
								{#if addDraft.error}
									<p role="alert" class="px-3 pb-2 text-xs text-danger">{addDraft.error}</p>
								{/if}
							</form>
						{:else}
							<button
								type="button"
								onclick={openAddForm}
								class="flex min-h-[44px] w-full items-center gap-2 border-t border-border-subtle px-3 text-left text-sm font-medium text-text-secondary transition-colors duration-fast hover:bg-primary-100/30 hover:text-primary-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary-500"
							>
								<i class="fas fa-plus text-2xs text-primary-500" aria-hidden="true"></i>
								Adicionar nova tarefa
							</button>
						{/if}
					</div>
				</div>
			</div>
		{/if}
	</div>

	{#if confirmingDiscard}
		<!-- Rodapé transiente: confirma o descarte do rascunho antes de fechar. -->
		<footer class="shrink-0 border-t border-border-subtle bg-surface-elevated/70 px-5 py-3.5">
			<div
				role="alertdialog"
				aria-label="Confirmar descarte do rascunho"
				class="stq-discard-confirm flex flex-col gap-2 rounded-lg border px-3 py-2.5"
				transition:fade={{ duration: 100 }}
			>
				<p class="m-0 text-sm font-semibold text-text-primary">Descartar o que foi digitado?</p>
				<div class="flex justify-end gap-2">
					<button
						type="button"
						onclick={keepEditing}
						class="rounded-md border border-border-subtle bg-surface px-3 py-1.5 text-xs font-semibold text-text-secondary transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
					>
						Continuar editando
					</button>
					<button
						type="button"
						onclick={onClose}
						class="stq-discard-btn rounded-md border px-3 py-1.5 text-xs font-semibold text-danger transition-colors duration-fast focus:outline-none focus-visible:ring-2 focus-visible:ring-danger"
					>
						Descartar
					</button>
				</div>
			</div>
		</footer>
	{/if}
</div>

<style>
	/* VARIANTE da grade do hub, só neste drawer — a página /tarefas segue com os
	 * defaults de `.task-hub-grid` (fallbacks `var(--th-col-*, ...)` do app.css).
	 * Larguras dimensionadas pelo PIOR rótulo de cada SelectMenu (dot + label +
	 * chevron sem truncar): "Urgente"/"Prioridade" 120px, "Melhoria" 108px,
	 * "Para validação" 160px. */
	.stq-compact {
		--th-col-prio: 120px;
		--th-col-tipo: 108px;
		--th-col-status: 160px;
		--th-col-owner: 128px;
		--th-col-actions: 84px;
	}
	.stq-compact :global(.task-hub-grid) {
		/* 600px de colunas fixas + gaps + mínimo legível da descrição; abaixo
		   disso o overflow-x-auto do card assume o scroll. */
		min-width: 800px;
		column-gap: 0.45rem;
	}

	/* Tintas via color-mix sobre tokens DS (o Tailwind 3 não gera `bg-x/10`
	 * para cores definidas como var() sem alpha-value). */
	:global([data-theme='dark']) .stq-panel {
		box-shadow: -18px 0 44px rgba(0, 0, 0, 0.5);
	}
	.stq-discard-confirm {
		border-color: color-mix(in srgb, var(--ds-color-warning-600) 40%, transparent);
		background-color: color-mix(in srgb, var(--ds-color-warning-600) 8%, transparent);
	}
	.stq-discard-btn {
		border-color: color-mix(in srgb, var(--ds-color-danger-600) 48%, transparent);
		background-color: color-mix(in srgb, var(--ds-color-danger-600) 10%, transparent);
	}
	.stq-discard-btn:hover:not(:disabled) {
		background-color: color-mix(in srgb, var(--ds-color-danger-600) 18%, transparent);
	}
</style>
