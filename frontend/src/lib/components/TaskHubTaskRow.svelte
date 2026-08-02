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
		priorityIconId,
		statusIconId,
		chipClass,
		tipoChipClass,
		prioridadeChipClass
	} from '$lib/utils/taskLabels';
	import { saveFields } from '$lib/api/taskDrawer';
	import { updateTaskStatus } from '$lib/api/board';
	import { ApiClientError } from '$lib/api/client';
	import { createTaskDrawerStore } from '$lib/stores/taskDrawer';
	import { flash } from '$lib/stores/flash';
	import { confirmAction } from '$lib/stores/confirm';
	import AssigneePicker from '$lib/components/AssigneePicker.svelte';
	import StateBanner from '$lib/components/StateBanner.svelte';
	import InlineCommentsTree from '$lib/components/InlineCommentsTree.svelte';
	import AttachmentLightbox from '$lib/components/AttachmentLightbox.svelte';
	import SelectMenu from '$lib/components/SelectMenu.svelte';
	import StateIcon from '$lib/components/StateIcon.svelte';
	import AppIcon from '$lib/components/AppIcon.svelte';
	import TaskTipoIcon from '$lib/components/TaskTipoIcon.svelte';
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
		para_validacao: 'var(--ds-color-status-validacao)',
		para_ajustes: 'var(--ds-color-fill-warning)',
		finalizada: 'var(--ds-color-fill-success)'
	};

	const prioridadeMenuOptions: SelectMenuOption[] = PRIORIDADE_OPTS.map((opt) => ({
		value: opt.value,
		label: opt.label,
		dot: priorityDotColor(opt.value),
		icon: priorityIconId(opt.value)
	}));
	const tipoMenuOptions: SelectMenuOption[] = TIPO_OPTS.map((opt) => ({
		value: opt.value,
		label: opt.label
	}));
	const statusMenuOptions: SelectMenuOption[] = STATUS_OPTS.map((opt) => ({
		value: opt.value,
		label: statusLabel(opt.value),
		dot: STATUS_DOT[opt.value],
		icon: statusIconId(opt.value)
	}));

	// Referência do chip de status: origem do confete de finalização.
	let statusChipEl = $state<HTMLElement | null>(null);

	let savingField = $state(false);

	// Celebração de finalização (confete), fornecida pela página via contexto — a
	// MESMA do Kanban/drawer. A lista dispara ao transicionar p/ "finalizada".
	const celebrateFinalize =
		getContext<((origin?: unknown) => void) | undefined>('celebrateFinalize');

	/** Motivo da falha vindo do backend (403/422 trazem texto útil). */
	function failureReason(err: unknown, fallback: string): string {
		return err instanceof ApiClientError ? err.message : fallback;
	}

	/** Salva campos (descricao/prioridade/tipo_pedido/responsavel) e revalida. */
	async function saveField(fields: TaskFieldEdits): Promise<void> {
		savingField = true;
		try {
			await saveFields(task.id, fields);
		} catch (err) {
			// A revalidação reverte o chip/texto; sem isto a reversão não se explica.
			flash.danger(failureReason(err, 'Não foi possível salvar a alteração.'), {
				key: `tarefa-${task.id}-salvar`
			});
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
		} catch (err) {
			flash.danger(failureReason(err, 'Não foi possível alterar o status desta tarefa.'), {
				key: `tarefa-${task.id}-status`
			});
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

	// --- Exclusão (mesmo texto e mesmo chassi de confirmação do kanban/drawer) ---
	async function askDelete(): Promise<void> {
		await confirmAction({
			title: 'Excluir esta tarefa?',
			description: `“${task.descricao}” e seus comentários e anexos serão apagados. Esta ação não pode ser desfeita.`,
			tone: 'danger',
			icon: 'trash',
			confirmLabel: 'Excluir tarefa',
			busyLabel: 'Excluindo…',
			// `run` mantém o diálogo aberto durante a exclusão: o backdrop não fecha
			// mais com a chamada em voo e a falha vira banner dentro do diálogo.
			run: async () => {
				const ok = await onDelete(task.id);
				if (!ok) throw new Error('Não foi possível excluir a tarefa.');
			}
		});
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

	// Mesmo teto do backend (MAX_CONTENT_LENGTH=10MB): sem a checagem no cliente o
	// 413 voltava sem corpo e o upload falhava em silêncio.
	const MAX_ANEXO_BYTES = 10 * 1024 * 1024;
	function anexoSizeLabel(bytes: number): string {
		if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
		return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
	}

	async function onAnexoChange(event: Event): Promise<void> {
		const input = event.currentTarget as HTMLInputElement;
		const file = input.files?.[0];
		input.value = '';
		if (!file) return;
		if (file.size > MAX_ANEXO_BYTES) {
			flash.danger(`O arquivo tem ${anexoSizeLabel(file.size)}; o limite é 10 MB.`, {
				key: `tarefa-${task.id}-anexo`
			});
			return;
		}
		uploading = true;
		await ensureDetail();
		const ok = await inlineStore.uploadAttachment(file);
		uploading = false;
		if (ok) return;
		flash.danger(get(inlineStore).error ?? 'Não foi possível enviar o anexo.', {
			key: `tarefa-${task.id}-anexo`
		});
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
					<AppIcon id="edicao" size={12} />
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
				optionIcon={tipoOptionIcon}
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
				{#if loadingComments}<i class="fas fa-spinner fa-spin" aria-hidden="true"></i>{:else}<AppIcon id="comentario" size={12} />{/if}<span class="min-w-[0.7rem] text-left tabular-nums">{#if commentsCount > 0}{commentsCount}{/if}</span>
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
				{#if uploading}<i class="fas fa-spinner fa-spin" aria-hidden="true"></i>{:else}<AppIcon id="anexo" size={12} />{/if}<span class="min-w-[0.7rem] text-left tabular-nums">{#if anexosCount > 0}{anexosCount}{/if}</span>
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
				onclick={() => void askDelete()}
				aria-label="Excluir tarefa"
				title="Excluir tarefa"
				class="inline-flex h-7 w-7 items-center justify-center text-text-muted transition-colors duration-fast hover:text-danger focus:outline-none focus-visible:rounded-md focus-visible:ring-2 focus-visible:ring-danger"
			>
				<AppIcon id="exclusao" size={14} />
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
				{#if $inlineStore.error}
					<!-- Erro de comentário/anexo do painel inline: era gravado e nunca exibido. -->
					<div class="mb-2">
						<StateBanner tone="danger" title={$inlineStore.error} />
					</div>
				{/if}
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

<!-- Prioridade e tipo são chips coloridos como o status; o ponto sólido de
     prioridade sobrevive só nas opções do dropdown. -->
{#snippet prioridadeTrigger({ open, selected }: { open: boolean; selected: SelectMenuOption | null })}
	<span class="{prioridadeChipClass(task.prioridade)} {CHIP_TRIGGER} justify-center gap-1">
		{#if task.prioridade}<StateIcon id={priorityIconId(task.prioridade)} size={13} />{/if}
		{selected?.label ?? '—'}
		{@render chipCaret(open)}
	</span>
{/snippet}

{#snippet tipoOptionIcon(opt: SelectMenuOption)}
	{#if opt.value}<TaskTipoIcon tipo={opt.value} size={14} />{/if}
{/snippet}

{#snippet tipoTrigger({ open, selected }: { open: boolean; selected: SelectMenuOption | null })}
	<span class="{tipoChipClass(task.tipo_pedido)} {CHIP_TRIGGER} justify-center gap-1">
		{#if task.tipo_pedido}<TaskTipoIcon tipo={task.tipo_pedido} size={14} />{/if}
		{selected?.label ?? '—'}
		{@render chipCaret(open)}
	</span>
{/snippet}

{#snippet statusTrigger({ open, selected }: { open: boolean; selected: SelectMenuOption | null })}
	<span
		bind:this={statusChipEl}
		class="{chipClass(statusTone(task.status))} {CHIP_TRIGGER} justify-center gap-1"
	>
		<StateIcon id={statusIconId(task.status)} size={13} />
		{selected?.label ?? statusLabel(task.status)}
		{@render chipCaret(open)}
	</span>
{/snippet}

