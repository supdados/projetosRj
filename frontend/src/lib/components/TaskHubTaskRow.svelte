<script lang="ts">
	/**
	 * Linha de tarefa do hub (modo lista) — nível 3 da hierarquia
	 * Projeto → Etapa → Tarefa. Edição INLINE na própria linha:
	 *   - descrição: caneta ao lado → textarea inline (Enter salva, Esc cancela);
	 *   - prioridade/tipo/status/responsável: <select> editável estilo-chip (clica,
	 *     abre o dropdown, escolhe) — salva direto via API e revalida a lista;
	 *   - comentários: painel inline expansível sob a linha (CommentsPanel + store
	 *     por linha, lazy); anexos: o ícone abre o seletor de arquivo direto.
	 * O clique na descrição (texto) abre o TaskDrawer completo.
	 */
	import { getContext, onDestroy } from 'svelte';
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
		prioridadeTone,
		chipClass
	} from '$lib/utils/taskLabels';
	import { saveFields } from '$lib/api/taskDrawer';
	import { updateTaskStatus } from '$lib/api/board';
	import { createTaskDrawerStore } from '$lib/stores/taskDrawer';
	import AssigneePicker from '$lib/components/AssigneePicker.svelte';
	import InlineCommentsTree from '$lib/components/InlineCommentsTree.svelte';
	import AttachmentLightbox from '$lib/components/AttachmentLightbox.svelte';

	interface Props {
		task: TaskCard;
		/** Abre o drawer completo da tarefa (clique na descrição). */
		onOpen: (id: number) => void;
		/** Exclui a tarefa; resolve `true` em sucesso. */
		onDelete: (id: number) => Promise<boolean>;
		/** Revalida a lista após uma edição inline (re-fetch server-autoritativo). */
		onChanged: () => void;
	}

	let { task, onOpen, onDelete, onChanged }: Props = $props();

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

	// Classe base do <select> estilo-chip (some o caret nativo; clica e abre o
	// dropdown). A cor vem do chipClass do tom atual.
	// `text-align-last: center` centraliza o VALOR exibido do <select> de forma
	// confiável entre navegadores (Safari/macOS não respeita só `text-center`).
	const SELECT_CHIP =
		'w-full cursor-pointer appearance-none text-center [text-align-last:center] disabled:opacity-50';

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
	function startEditDesc(): void {
		descDraft = task.descricao;
		editingDesc = true;
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
	async function submitDesc(): Promise<void> {
		const value = descDraft.trim();
		if (!value || savingField) return;
		editingDesc = false;
		if (value !== task.descricao) await saveField({ descricao: value });
	}

	// Responsáveis múltiplos: estado local seedado do card. O AssigneePicker
	// persiste no servidor e sincroniza esta lista a partir da resposta.
	let assignees = $state<TaskAssignee[]>(task.assignees ?? []);

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
	<div class="task-hub-grid px-3 py-2 transition-colors duration-fast {commentsOpen ? '' : 'hover:bg-primary-100/40'}">
		<!-- Descrição: texto abre o drawer; caneta habilita edição inline -->
		{#if editingDesc}
			<!-- svelte-ignore a11y_autofocus -->
			<textarea
				bind:value={descDraft}
				onkeydown={onDescKeydown}
				onblur={submitDesc}
				autofocus
				rows="1"
				aria-label="Editar descrição"
				class="min-h-[30px] w-full min-w-0 resize-y rounded-[5px] border border-border-subtle bg-surface px-2 py-1 text-sm leading-normal text-text-primary focus:border-primary-500 focus:outline-none"
			></textarea>
		{:else}
			<div class="flex min-w-0 items-center gap-1">
				<button
					type="button"
					onclick={() => onOpen(task.id)}
					class="min-w-0 break-words text-left text-sm text-text-primary transition-colors duration-fast hover:text-primary-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
				>
					{task.descricao}
				</button>
				<button
					type="button"
					onclick={startEditDesc}
					title="Editar descrição"
					aria-label="Editar descrição"
					class="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-text-muted opacity-0 transition-all duration-fast hover:bg-primary-100 hover:text-primary-700 focus:outline-none focus-visible:opacity-100 focus-visible:ring-2 focus-visible:ring-primary-500 group-hover/row:opacity-100"
				>
					<i class="fas fa-pen text-2xs" aria-hidden="true"></i>
				</button>
			</div>
		{/if}

		<!-- Prioridade (select estilo-chip) -->
		<select
			value={task.prioridade ?? ''}
			disabled={savingField}
			aria-label="Prioridade"
			onchange={(e) => saveField({ prioridade: e.currentTarget.value || null })}
			class="{chipClass(prioridadeTone(task.prioridade))} {SELECT_CHIP}"
		>
			{#each PRIORIDADE_OPTS as opt (opt.value)}
				<option value={opt.value}>{opt.label}</option>
			{/each}
		</select>

		<!-- Tipo (select estilo-chip) -->
		<select
			value={task.tipo_pedido ?? ''}
			disabled={savingField}
			aria-label="Tipo de pedido"
			onchange={(e) => saveField({ tipo_pedido: e.currentTarget.value || null })}
			class="{chipClass(task.tipo_pedido ? 'primary' : 'neutral')} {SELECT_CHIP}"
		>
			{#each TIPO_OPTS as opt (opt.value)}
				<option value={opt.value}>{opt.label}</option>
			{/each}
		</select>

		<!-- Status (select estilo-chip; rota própria) -->
		<select
			value={task.status}
			disabled={savingField}
			aria-label="Status"
			onchange={(e) => changeStatus(e.currentTarget.value, e.currentTarget)}
			class="{chipClass(statusTone(task.status))} {SELECT_CHIP}"
		>
			{#each STATUS_OPTS as opt (opt.value)}
				<option value={opt.value}>{statusLabel(opt.value)}</option>
			{/each}
		</select>

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
				class="inline-flex items-center gap-0.5 rounded-md px-1 py-1 text-2xs font-semibold transition-colors duration-fast focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 {commentsOpen
					? 'text-primary-700'
					: 'text-text-muted hover:text-primary-700'}"
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
				class="inline-flex items-center gap-0.5 rounded-md px-1 py-1 text-2xs font-semibold text-text-muted transition-colors duration-fast hover:text-primary-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-50"
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
				class="inline-flex h-7 w-7 items-center justify-center rounded-md text-text-muted transition-colors duration-fast hover:bg-danger/10 hover:text-danger focus:outline-none focus-visible:ring-2 focus-visible:ring-danger"
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
			class="border-t border-border-subtle bg-surface-muted/40 px-3 py-3"
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
		<div
			role="alertdialog"
			aria-label="Confirmar exclusão da tarefa"
			class="flex items-center justify-end gap-3 border-t border-danger/40 bg-danger/5 px-3 py-2"
		>
			{#if deleteError}
				<p role="alert" class="mr-auto text-xs text-danger">{deleteError}</p>
			{:else}
				<p class="mr-auto text-xs text-text-primary">Excluir esta tarefa?</p>
			{/if}
			<button
				type="button"
				onclick={() => (confirming = false)}
				disabled={deleting}
				class="rounded-md border border-border-subtle px-2.5 py-1 text-xs font-medium text-text-secondary hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-50"
			>
				Cancelar
			</button>
			<button
				type="button"
				onclick={() => void doDelete()}
				disabled={deleting}
				class="rounded-md bg-danger px-2.5 py-1 text-xs font-medium text-white hover:opacity-90 focus:outline-none focus-visible:ring-2 focus-visible:ring-danger disabled:opacity-50"
			>
				{deleting ? 'Excluindo…' : 'Excluir'}
			</button>
		</div>
	{/if}
</div>
