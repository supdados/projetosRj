<script lang="ts">
	/**
	 * Linha de tarefa do hub (modo lista) — nível 3 da hierarquia
	 * Projeto → Etapa → Tarefa. Edição INLINE na própria linha:
	 *   - descrição: caneta ao lado → textarea inline (Enter salva, Esc cancela);
	 *   - prioridade/tipo/status/responsável: chip editável (SelectMenu unstyled,
	 *     clica, abre o dropdown, escolhe) — salva direto via API e revalida a lista;
	 *   - comentários: painel inline expansível sob a linha (CommentsPanel + store
	 *     por linha, lazy); anexos: o ícone abre o seletor de arquivo direto.
	 * O clique na descrição (texto) abre o TaskDrawer (ou edita inline quando
	 * `nestedInDrawer`).
	 */
	import { getContext, onDestroy, tick } from 'svelte';
	import { get } from 'svelte/store';
	import { slide } from 'svelte/transition';
	import { cubicOut } from 'svelte/easing';
	import { prefersReducedMotion } from 'svelte/motion';
	import type { TaskAssignee, TaskCard } from '$lib/types/tasks';
	import type { TaskFieldEdits } from '$lib/types/taskDrawer';
	import { type TaskStatus } from '$lib/utils/taskStatus';
	import {
		statusLabel,
		statusTone,
		priorityDotColor,
		chipClass
	} from '$lib/utils/taskLabels';
	import { saveFields } from '$lib/api/taskDrawer';
	import { updateTaskStatus } from '$lib/api/board';
	import { createTaskDrawerStore } from '$lib/stores/taskDrawer';
	import AssigneePicker from '$lib/components/AssigneePicker.svelte';
	import Modal from '$lib/components/Modal.svelte';
	import InlineCommentsTree from '$lib/components/InlineCommentsTree.svelte';
	import AttachmentLightbox from '$lib/components/AttachmentLightbox.svelte';
	import SelectMenu from '$lib/components/SelectMenu.svelte';
	import type { SelectMenuOption } from '$lib/types/selectMenu';

	interface Props {
		task: TaskCard;
		/** Abre o drawer completo da tarefa (clique na descrição). */
		onOpen: (id: number) => void;
		/** Exclui a tarefa; resolve `true` em sucesso. */
		onDelete: (id: number) => Promise<boolean>;
		/** Revalida a lista após uma edição inline (re-fetch server-autoritativo). */
		onChanged: () => void;
		/** true quando a linha está dentro de outro drawer (StageTaskQuickAdd):
		 *  o clique na descrição edita inline em vez de empilhar o TaskDrawer. */
		nestedInDrawer: boolean;
	}

	let { task, onOpen, onDelete, onChanged, nestedInDrawer }: Props = $props();

	const PRIORIDADE_OPTS = [
		{ value: '', label: '—' },
		{ value: 'baixa', label: 'Baixa' },
		{ value: 'media', label: 'Média' },
		{ value: 'alta', label: 'Alta' },
		{ value: 'urgente', label: 'Urgente' }
	];
	const TIPO_OPTS = [
		{ value: '', label: '—' },
		{ value: 'bug', label: 'Bug' },
		{ value: 'melhoria', label: 'Melhoria' },
		{ value: 'duvida', label: 'Dúvida' },
		{ value: 'outros', label: 'Outros' }
	];
	const STATUS_OPTS = [
		{ value: 'nao_iniciada', label: 'Não iniciada' },
		{ value: 'em_andamento', label: 'Em andamento' },
		{ value: 'para_validacao', label: 'Para validação' },
		{ value: 'para_ajustes', label: 'Para ajustes' },
		{ value: 'finalizada', label: 'Finalizada' }
	];

	// Trigger do SelectMenu unstyled: o próprio chip (chipClass do tom atual).
	const CHIP_TRIGGER = 'w-full cursor-pointer';

	// Dots: prioridade via priorityDotColor (taskLabels.ts); status com os tons
	// de STATUS_TONE/STATUS_BAR_CLASS, não inventados aqui.
	const STATUS_DOT: Record<string, string> = {
		nao_iniciada: 'var(--ds-color-text-muted)',
		em_andamento: 'var(--ds-color-status-andamento)',
		para_validacao: 'var(--ds-color-primary-500)',
		para_ajustes: 'var(--ds-color-fill-warning)',
		finalizada: 'var(--ds-color-fill-success)'
	};

	const prioridadeMenuOptions: SelectMenuOption[] = PRIORIDADE_OPTS.map((opt) => ({
		value: opt.value,
		label: opt.label,
		dot: priorityDotColor(opt.value)
	}));
	const tipoMenuOptions: SelectMenuOption[] = TIPO_OPTS.map((opt) => ({
		value: opt.value,
		label: opt.label
	}));
	const statusMenuOptions: SelectMenuOption[] = STATUS_OPTS.map((opt) => ({
		value: opt.value,
		label: statusLabel(opt.value),
		dot: STATUS_DOT[opt.value]
	}));

	// Referência do chip de status: origem do confete de finalização.
	let statusChipEl = $state<HTMLElement | null>(null);

	let savingField = $state(false);

	// Celebração de finalização (confete), fornecida pela página via contexto — a
	// MESMA do Kanban/drawer. A lista dispara ao transicionar p/ "finalizada".
	const celebrateFinalize =
		getContext<((origin?: unknown) => void) | undefined>('celebrateFinalize');

	/** Salva campos (descricao/prioridade/tipo_pedido/responsavel) e revalida. */
	async function saveField(fields: TaskFieldEdits): Promise<void> {
		savingField = true;
		try {
			await saveFields(task.id, fields);
		} catch {
			// erro fica visível ao revalidar (o valor volta ao do servidor)
		} finally {
			savingField = false;
			onChanged();
		}
	}

	/** Status tem rota própria (respeita can_finalize); revalida sempre. */
	async function changeStatus(value: string, origin?: HTMLElement): Promise<void> {
		const wasFinalized = task.status === 'finalizada';
		savingField = true;
		try {
			await updateTaskStatus(task.id, value as TaskStatus);
			// Confete só na TRANSIÇÃO ativa -> finalizada e após o servidor aceitar
			// (updateTaskStatus lança em 403). Origem = o próprio chip de status.
			if (value === 'finalizada' && !wasFinalized) {
				celebrateFinalize?.(origin);
			}
		} catch {
			// 403 ao finalizar sem permissão etc. — revalida e reverte
		} finally {
			savingField = false;
			onChanged();
		}
	}

	// --- Edição inline da DESCRIÇÃO (caneta) ---
	let editingDesc = $state(false);
	let descDraft = $state('');
	let descEl = $state<HTMLTextAreaElement | null>(null);
	// Auto-grow: sem isso, rows="1" prendia a edição em 1 linha (padrão de StageRow::resizeComment).
	function resizeDesc(): void {
		const el = descEl;
		if (!el) return;
		el.style.height = 'auto';
		el.style.height = `${el.scrollHeight + el.offsetHeight - el.clientHeight}px`;
	}
	async function startEditDesc(): Promise<void> {
		descDraft = task.descricao;
		editingDesc = true;
		await tick();
		resizeDesc();
	}
	function onDescKeydown(event: KeyboardEvent): void {
		if (event.key === 'Enter' && !event.shiftKey) {
			event.preventDefault();
			void submitDesc();
		} else if (event.key === 'Escape') {
			event.preventDefault();
			editingDesc = false;
		}
	}
	function onDescriptionClick(): void {
		if (nestedInDrawer) {
			void startEditDesc();
			return;
		}
		onOpen(task.id);
	}

	async function submitDesc(): Promise<void> {
		const value = descDraft.trim();
		if (!value || savingField) return;
		editingDesc = false;
		if (value !== task.descricao) await saveField({ descricao: value });
	}

	// Responsáveis múltiplos: estado local seedado do card. O seed inicial é
	// INTENCIONAL (render imediato dos avatares, sem flash) e a re-sincronização
	// com o servidor é feita pelo $effect abaixo — por isso o aviso de "captura só
	// o valor inicial" não se aplica aqui.
	// svelte-ignore state_referenced_locally
	let assignees = $state<TaskAssignee[]>(task.assignees ?? []);

	// Re-sincroniza com o card quando a lista vem do servidor: o re-fetch da lista
	// reatribui o prop `task`, disparando este efeito; sem ele os avatares ficariam
	// presos ao 1º valor (ex.: alteração feita em outra aba/sessão). Depende apenas
	// de `task` (não lê `assignees`), então NÃO conflita com a edição otimista do
	// picker — que altera só o estado local e não re-busca a lista.
	$effect(() => {
		assignees = task.assignees ?? [];
	});

	// --- Exclusão (mini-confirm inline) ---
	let confirming = $state(false);
	let deleting = $state(false);
	let deleteError = $state<string | null>(null);
	function askDelete(): void {
		deleteError = null;
		confirming = true;
	}
	async function doDelete(): Promise<void> {
		deleting = true;
		deleteError = null;
		const ok = await onDelete(task.id);
		deleting = false;
		if (ok) confirming = false;
		else deleteError = 'Não foi possível excluir a tarefa.';
	}

	// --- Comentários inline (store por linha, lazy) e ANEXO direto ---
	const inlineStore = createTaskDrawerStore();
	const panelId = $derived(`task-${task.id}`);
	let commentsOpen = $state(false);
	let commentsDirty = $state(false);
	let loadingComments = $state(false);
	let commentsError = $state<string | null>(null);
	let commentsBtn = $state<HTMLButtonElement | null>(null);
	let fileInput = $state<HTMLInputElement | null>(null);
	let uploading = $state(false);

	const commentsCount = $derived($inlineStore.detail?.comentarios.length ?? task.comments_count);
	const anexosCount = $derived($inlineStore.detail?.anexos.length ?? task.anexos_count);

	async function ensureDetail(): Promise<void> {
		if (get(inlineStore).detail?.id === task.id) return;
		await inlineStore.open(task.id, { mode: 'list' });
	}

	async function toggleComments(): Promise<void> {
		if (commentsOpen) {
			commentsOpen = false;
			return;
		}
		// Carrega o detalhe ANTES de abrir: assim o painel desliza direto até o
		// tamanho final (sem abrir pequeno com "Carregando…" e depois saltar).
		if (get(inlineStore).detail?.id !== task.id) {
			loadingComments = true;
			commentsError = null;
			await ensureDetail();
			loadingComments = false;
			commentsError = get(inlineStore).error;
		}
		commentsOpen = true;
	}

	function onPanelKeydown(event: KeyboardEvent): void {
		if (event.key !== 'Escape') return;
		commentsOpen = false;
		commentsBtn?.focus();
	}

	/**
	 * Fecha o painel de comentários ao clicar FORA dele — só se NÃO houver conteúdo
	 * não salvo (`commentsDirty`: texto no composer ou edição aberta). Ignora o
	 * próprio botão de comentários (ele já alterna). Captura no `pointerdown`.
	 */
	function closeCommentsOnClickOutside(node: HTMLElement) {
		function handle(event: PointerEvent): void {
			const target = event.target as Node;
			if (node.contains(target)) return;
			if (commentsBtn?.contains(target)) return;
			if (commentsDirty) return;
			commentsOpen = false;
		}
		document.addEventListener('pointerdown', handle, true);
		return {
			destroy() {
				document.removeEventListener('pointerdown', handle, true);
			}
		};
	}

	let galleryOpen = $state(false);

	/**
	 * Ícone de anexo: SE não há anexos → abre o seletor de arquivo (anexar). SE já
	 * há → abre a galeria navegável dos anexos existentes (ordem de anexo).
	 */
	async function onAnexoClick(): Promise<void> {
		if (anexosCount === 0) {
			pickAttachment();
			return;
		}
		await ensureDetail();
		galleryOpen = true;
	}

	/** Abre o seletor de arquivo direto; ao escolher, faz upload. */
	function pickAttachment(): void {
		fileInput?.click();
	}
	async function onAnexoChange(event: Event): Promise<void> {
		const input = event.currentTarget as HTMLInputElement;
		const file = input.files?.[0];
		input.value = '';
		if (!file) return;
		uploading = true;
		await ensureDetail();
		await inlineStore.uploadAttachment(file);
		uploading = false;
	}

	const slideParams = $derived({
		duration: prefersReducedMotion.current ? 0 : 240,
		easing: cubicOut
	});

	onDestroy(() => void inlineStore.close());
</script>

<div class="group/row border-b border-border-subtle last:border-b-0">
	<div class="task-hub-grid px-3 py-2 transition-colors duration-fast {commentsOpen ? '' : 'hover:bg-surface-muted'}">
		<!-- Descrição: texto abre o drawer; caneta habilita edição inline -->
		{#if editingDesc}
			<!-- svelte-ignore a11y_autofocus -->
			<textarea
				bind:this={descEl}
				bind:value={descDraft}
				onkeydown={onDescKeydown}
				onblur={submitDesc}
				oninput={resizeDesc}
				autofocus
				rows="1"
				aria-label="Editar descrição"
				class="min-h-7 w-full min-w-0 resize-y rounded-md border border-border-subtle bg-surface px-2 py-1 text-xs leading-normal text-text-primary focus:border-brand focus:outline-none 2xl:text-sm"
			></textarea>
		{:else}
			<div class="flex min-w-0 items-center gap-1">
				<button
					type="button"
					onclick={onDescriptionClick}
					title={nestedInDrawer ? 'Editar descrição' : undefined}
					class="min-w-0 break-words text-left text-xs text-text-primary transition-colors duration-fast hover:text-brand focus:outline-none focus-visible:ring-2 focus-visible:ring-brand 2xl:text-sm"
				>
					{task.descricao}
				</button>
				<button
					type="button"
					onclick={startEditDesc}
					title="Editar descrição"
					aria-label="Editar descrição"
					class="inline-flex h-6 w-6 shrink-0 items-center justify-center text-text-muted opacity-0 transition-all duration-fast hover:text-brand focus:outline-none focus-visible:opacity-100 focus-visible:rounded-md focus-visible:ring-2 focus-visible:ring-brand group-hover/row:opacity-100"
				>
					<i class="fas fa-pen text-2xs" aria-hidden="true"></i>
				</button>
			</div>
		{/if}

		<!-- Prioridade (chip editável via SelectMenu; wrapper text-center alinha o
		     chip ao centro da coluna, como o cabeçalho) -->
		<div class="text-center">
			<SelectMenu
				options={prioridadeMenuOptions}
				value={task.prioridade ?? ''}
				onSelect={(v) => saveField({ prioridade: v || null })}
				disabled={savingField}
				id={`${panelId}-prioridade`}
				ariaLabel="Prioridade"
				size="sm"
				unstyled
				trigger={prioridadeTrigger}
			/>
		</div>

		<!-- Tipo (chip editável via SelectMenu) -->
		<div class="text-center">
			<SelectMenu
				options={tipoMenuOptions}
				value={task.tipo_pedido ?? ''}
				onSelect={(v) => saveField({ tipo_pedido: v || null })}
				disabled={savingField}
				id={`${panelId}-tipo`}
				ariaLabel="Tipo de pedido"
				size="sm"
				unstyled
				trigger={tipoTrigger}
			/>
		</div>

		<!-- Status (chip editável via SelectMenu; rota própria) -->
		<div class="text-center">
			<SelectMenu
				options={statusMenuOptions}
				value={task.status}
				onSelect={(v) => changeStatus(v ?? task.status, statusChipEl ?? undefined)}
				disabled={savingField}
				id={`${panelId}-status`}
				ariaLabel="Status"
				size="sm"
				unstyled
				trigger={statusTrigger}
			/>
		</div>

		<!-- Responsáveis (múltiplos): avatares de iniciais + popover de busca -->
		<AssigneePicker taskId={task.id} bind:assignees disabled={savingField} />

		<!-- Ações: comentários (inline), anexar (seletor direto), excluir -->
		<div class="flex items-center justify-center gap-0.5">
			<button
				bind:this={commentsBtn}
				type="button"
				onclick={() => void toggleComments()}
				title="Comentários"
				aria-label={`Comentários (${commentsCount})`}
				aria-expanded={commentsOpen}
				aria-controls={`${panelId}-comments-region`}
				class="inline-flex items-center gap-0.5 rounded-md px-1 py-1 text-2xs font-semibold transition-colors duration-fast focus:outline-none focus-visible:ring-2 focus-visible:ring-brand {commentsOpen
					? 'text-brand'
					: 'text-text-muted hover:text-brand'}"
			>
				<i class="{loadingComments ? 'fas fa-spinner fa-spin' : 'far fa-comment'}" aria-hidden="true"></i><span class="min-w-[0.7rem] text-left tabular-nums">{#if commentsCount > 0}{commentsCount}{/if}</span>
			</button>
			<button
				type="button"
				onclick={() => void onAnexoClick()}
				disabled={uploading}
				title={anexosCount === 0 ? 'Anexar arquivo' : 'Ver anexos'}
				aria-label={anexosCount === 0
					? 'Anexar arquivo'
					: `Ver anexos (${anexosCount})`}
				class="inline-flex items-center gap-0.5 rounded-md px-1 py-1 text-2xs font-semibold text-text-muted transition-colors duration-fast hover:text-brand focus:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:opacity-50"
			>
				<i class="fas {uploading ? 'fa-spinner fa-spin' : 'fa-paperclip'}" aria-hidden="true"></i><span class="min-w-[0.7rem] text-left tabular-nums">{#if anexosCount > 0}{anexosCount}{/if}</span>
			</button>
			<input
				bind:this={fileInput}
				type="file"
				class="sr-only"
				onchange={onAnexoChange}
				aria-hidden="true"
				tabindex="-1"
			/>
			<button
				type="button"
				onclick={askDelete}
				aria-label="Excluir tarefa"
				title="Excluir tarefa"
				class="inline-flex h-7 w-7 items-center justify-center text-text-muted transition-colors duration-fast hover:text-danger focus:outline-none focus-visible:rounded-md focus-visible:ring-2 focus-visible:ring-danger"
			>
				<i class="fas fa-trash-can text-xs" aria-hidden="true"></i>
			</button>
		</div>
	</div>

	{#if commentsOpen}
		<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
		<div
			id={`${panelId}-comments-region`}
			role="region"
			aria-label={`Comentários da tarefa: ${task.descricao}`}
			transition:slide={slideParams}
			onkeydown={onPanelKeydown}
			use:closeCommentsOnClickOutside
			class="border-t border-border-subtle bg-surface-muted px-3 py-3"
		>
			{#if loadingComments}
				<p role="status" aria-live="polite" class="text-xs text-text-secondary">Carregando comentários…</p>
			{:else if commentsError}
				<p role="alert" class="text-xs text-danger">{commentsError}</p>
			{:else}
				<InlineCommentsTree store={inlineStore} idPrefix={panelId} bind:dirty={commentsDirty} />
			{/if}
		</div>
	{/if}

	{#if galleryOpen}
		<AttachmentLightbox
			anexos={$inlineStore.detail?.anexos ?? []}
			onClose={() => (galleryOpen = false)}
			onAdd={pickAttachment}
		/>
	{/if}

	{#if confirming}
		<!-- Confirmação centralizada (modal SPA), no mesmo padrão do "Arquivar finalizados". -->
		<Modal labelId={`${panelId}-delete-title`} onBackdrop={() => (confirming = false)}>
			<div class="flex flex-col gap-4">
				<h2 id={`${panelId}-delete-title`} class="font-heading text-lg font-bold text-text-primary">
					Excluir tarefa
				</h2>
				{#if deleteError}
					<p role="alert" class="text-sm text-danger">{deleteError}</p>
				{:else}
					<p class="text-sm text-text-secondary">
						Excluir a tarefa <b class="font-semibold text-text-primary">“{task.descricao}”</b>? Esta
						ação não pode ser desfeita.
					</p>
				{/if}
				<div class="flex justify-end gap-2">
					<button
						type="button"
						onclick={() => (confirming = false)}
						disabled={deleting}
						class="rounded-md border border-border-subtle px-4 py-2 text-sm font-semibold text-text-secondary hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:opacity-50"
					>
						Cancelar
					</button>
					<button
						type="button"
						onclick={() => void doDelete()}
						disabled={deleting}
						class="delete-confirm-btn rounded-md bg-danger px-4 py-2 text-sm font-semibold text-danger-fg hover:opacity-90 focus:outline-none focus-visible:ring-2 focus-visible:ring-danger disabled:opacity-50"
					>
						{deleting ? 'Excluindo…' : 'Excluir'}
					</button>
				</div>
			</div>
		</Modal>
	{/if}
</div>

{#snippet chipCaret(open: boolean)}
	<svg
		width="8"
		height="5"
		viewBox="0 0 10 6"
		class="shrink-0 opacity-60 transition-transform duration-fast"
		style:transform={open ? 'rotate(180deg)' : 'none'}
		aria-hidden="true"
	>
		<path
			d="M1 1 L5 5 L9 1"
			fill="none"
			stroke="currentColor"
			stroke-width="1.8"
			stroke-linecap="round"
			stroke-linejoin="round"
		/>
	</svg>
{/snippet}

<!-- Inversão de forma (plano-regua-de-cor §7.4): prioridade = ponto sólido +
     rótulo em texto normal; a pílula (.chip) pertence ao status e ao tipo. -->
{#snippet prioridadeTrigger({ open, selected }: { open: boolean; selected: SelectMenuOption | null })}
	<span
		class="inline-flex h-[22px] {CHIP_TRIGGER} items-center justify-center gap-1.5 whitespace-nowrap text-xs text-text-primary"
	>
		{#if priorityDotColor(task.prioridade)}
			<span
				aria-hidden="true"
				class="h-2 w-2 shrink-0 rounded-full"
				style:background={priorityDotColor(task.prioridade)}
			></span>
		{/if}
		{selected?.label ?? '—'}
		{@render chipCaret(open)}
	</span>
{/snippet}

{#snippet tipoTrigger({ open, selected }: { open: boolean; selected: SelectMenuOption | null })}
	<span class="{chipClass('neutral')} {CHIP_TRIGGER} justify-center gap-1">
		{selected?.label ?? '—'}
		{@render chipCaret(open)}
	</span>
{/snippet}

{#snippet statusTrigger({ open, selected }: { open: boolean; selected: SelectMenuOption | null })}
	<span
		bind:this={statusChipEl}
		class="{chipClass(statusTone(task.status))} {CHIP_TRIGGER} justify-center gap-1"
	>
		{selected?.label ?? statusLabel(task.status)}
		{@render chipCaret(open)}
	</span>
{/snippet}

