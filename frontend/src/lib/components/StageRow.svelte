<script lang="ts">
	/**
	 * Uma etapa do Detalhe de Projeto. CONTROLADA por callbacks (sem chamar API).
	 *
	 * Referências visuais: templates/projects/_project_stages_section.html e
	 * _stage_tasks_panel.html. Cobre: datas (início/fim), responsável, toggles
	 * iniciada/concluída, comentário, ações editar/excluir, e as TAREFAS DA ETAPA
	 * SOMENTE LEITURA (contagem; lista simples carregada sob demanda pela página).
	 *
	 * Restrições da Fase 5a:
	 *   - Edição inline de campos da etapa (descricao/data_inicio/data_fim/
	 *     responsavel) via <InlineEditField> -> `onUpdateField`. A página chama o
	 *     endpoint update-field (cascata de datas server-side) e re-renderiza.
	 *   - Toggles iniciada/done -> `onToggleIniciada`/`onToggleDone`.
	 *   - Comentário -> `onSaveComentario` (textarea com salvar/cancelar).
	 *   - Editar (completo)/Excluir -> `onEdit`/`onDelete`.
	 *   - DnD é gerido pelo StageList (pai); aqui só expomos uma alça `draggable`.
	 *   - Reuniões Google (`is_google_meeting`) renderizam READ-ONLY (Fase 6).
	 *   - Tarefas: NUNCA mutadas; lista simples opcional via `tasks` + `onLoadTasks`.
	 *
	 * Acessibilidade: linha como região rotulada pela descrição; toggles como
	 * checkboxes acessíveis; datas com <time datetime>; alça de arraste com label.
	 */
	import { getContext } from 'svelte';
	import Badge from './Badge.svelte';
	import InlineEditField from './InlineEditField.svelte';
	import type { EtapaDetail, EtapaTask, EtapaInlineField } from '$lib/types/projectDetail';

	/**
	 * Abertura do drawer de tarefa (Fase 5b-2) via contexto fornecido pela página
	 * de Detalhe — quando presente, as tarefas da etapa abrem o drawer (modo
	 * drawer-only). Ausente => texto puro (comportamento read-only da Fase 5a).
	 */
	const openTaskDrawer = getContext<((taskId: number) => void) | undefined>('openTaskDrawer');

	interface FieldState {
		pending?: boolean;
		error?: string | null;
	}

	interface Props {
		etapa: EtapaDetail;
		/** Bloqueia toda mutação (sem permissão). */
		readonly?: boolean;
		/** Estados pending/erro por campo inline, controlados pela página. */
		fieldStates?: Partial<Record<EtapaInlineField, FieldState>>;
		/** Em andamento: toggle iniciada/done/comentário/excluir. */
		busy?: boolean;
		/** Erro de operação de linha (toggle/comentário/excluir). */
		rowError?: string | null;
		/** Tarefas da etapa (SOMENTE LEITURA) já carregadas; `null` = não carregadas. */
		tasks?: EtapaTask[] | null;
		/** Carregando a lista de tarefas (read-only). */
		tasksLoading?: boolean;
		/** Snippet opcional do conteúdo de reunião Google (Fase 6, read-only). */
		meetingSlot?: import('svelte').Snippet<[EtapaDetail]>;
		/** Edição inline de um campo: a página chama update-field e re-renderiza. */
		onUpdateField: (field: EtapaInlineField, value: string) => void;
		/** Alterna `iniciada`. */
		onToggleIniciada: () => void;
		/** Alterna `done` (concluída). */
		onToggleDone: () => void;
		/** Salva o comentário (string vazia limpa). */
		onSaveComentario: (comentario: string) => void;
		/** Abre a edição completa da etapa (página decide a UI). */
		onEdit: () => void;
		/** Exclui a etapa (página confirma e chama o endpoint). */
		onDelete: () => void;
		/** Pede o carregamento read-only das tarefas da etapa. */
		onLoadTasks?: () => void;
	}

	let {
		etapa,
		readonly = false,
		fieldStates = {},
		busy = false,
		rowError = null,
		tasks = null,
		tasksLoading = false,
		meetingSlot,
		onUpdateField,
		onToggleIniciada,
		onToggleDone,
		onSaveComentario,
		onEdit,
		onDelete,
		onLoadTasks
	}: Props = $props();

	const isMeeting = $derived(etapa.is_google_meeting);
	// Reuniões Google e falta de permissão tornam a etapa read-only (Fase 5a/6).
	const locked = $derived(readonly || isMeeting);
	const fieldId = $derived(`etapa-${etapa.id}`);

	let editingComment = $state(false);
	let commentDraft = $state('');

	function fieldState(field: EtapaInlineField): FieldState {
		return fieldStates[field] ?? {};
	}

	function startComment(): void {
		// Comentário não pode ser editado em etapa concluída (regra do backend).
		if (locked || etapa.done) return;
		commentDraft = etapa.comentarios ?? '';
		editingComment = true;
	}

	function commitComment(): void {
		onSaveComentario(commentDraft.trim());
		editingComment = false;
	}

	function cancelComment(): void {
		editingComment = false;
		commentDraft = etapa.comentarios ?? '';
	}

	function toggleTasks(): void {
		if (tasks === null) onLoadTasks?.();
	}

	function formatDateBr(iso: string | null): string {
		if (!iso) return 'Sem data';
		const parsed = new Date(iso);
		if (Number.isNaN(parsed.getTime())) return 'Sem data';
		return parsed.toLocaleDateString('pt-BR', {
			day: '2-digit',
			month: '2-digit',
			year: 'numeric',
			timeZone: 'UTC'
		});
	}
</script>

<!--
	Card da etapa. Fidelidade a .etapa-v4-table-card / .etapa-draggable-row do
	original: raio 14px (rounded-xl), sombra suave (0 8px 24px rgba(20,45,78,.06)),
	e micro-lift no hover (translateY(-1px) + sombra), transição all 0.16s ease.
-->
<article
	aria-label={`Etapa: ${etapa.descricao ?? 'sem descrição'}`}
	class="stage-row flex flex-col gap-3 rounded-xl border border-border-subtle bg-surface px-4 py-3 shadow-sm transition-[transform,box-shadow,border-color] duration-fast ease-out hover:-translate-y-px hover:border-border-strong hover:shadow-md {etapa.done
		? 'opacity-90'
		: ''}"
>
	<div class="flex flex-wrap items-start justify-between gap-3">
		<div class="flex min-w-0 items-start gap-2">
			{#if !locked}
				<span
					class="mt-0.5 cursor-grab select-none text-text-muted transition-colors duration-fast ease-out hover:text-text-secondary active:cursor-grabbing"
					aria-label="Arraste para reordenar a etapa"
					title="Arraste para reordenar"
				>
					⠿
				</span>
			{/if}
			<div class="flex min-w-0 flex-col gap-1">
				{#if locked}
					<h3 class="break-words font-heading text-base font-semibold {etapa.done ? 'text-text-muted line-through' : 'text-text-primary'}">
						{etapa.descricao ?? '—'}
					</h3>
				{:else}
					<InlineEditField
						fieldId={`${fieldId}-descricao`}
						label="Descrição da etapa"
						value={etapa.descricao}
						kind="text"
						pending={fieldState('descricao').pending}
						error={fieldState('descricao').error}
						onSave={(v) => onUpdateField('descricao', v)}
					/>
				{/if}
			</div>
		</div>

		<div class="flex flex-wrap items-center gap-2">
			{#if isMeeting}
				<Badge tone="info">Reunião Google</Badge>
			{/if}
			{#if etapa.done}
				<Badge tone="success">Concluída</Badge>
			{:else if etapa.iniciada}
				<Badge tone="primary">Iniciada</Badge>
			{:else}
				<Badge tone="neutral">Não iniciada</Badge>
			{/if}
		</div>
	</div>

	{#if isMeeting && meetingSlot}
		<!-- Fase 6: conteúdo de reunião Google renderizado READ-ONLY pela página. -->
		{@render meetingSlot(etapa)}
	{/if}

	<!-- Datas + responsável -->
	<div class="grid gap-3 sm:grid-cols-3">
		{#if locked}
			<div class="flex flex-col gap-1">
				<span class="text-xs font-semibold uppercase tracking-wide text-text-muted">Início</span>
				<time class="text-sm text-text-secondary" datetime={etapa.data_inicio ?? undefined}>
					{formatDateBr(etapa.data_inicio)}
				</time>
			</div>
			<div class="flex flex-col gap-1">
				<span class="text-xs font-semibold uppercase tracking-wide text-text-muted">Fim</span>
				<time class="text-sm text-text-secondary" datetime={etapa.data_fim ?? undefined}>
					{formatDateBr(etapa.data_fim)}
				</time>
			</div>
			<div class="flex flex-col gap-1">
				<span class="text-xs font-semibold uppercase tracking-wide text-text-muted">Responsável</span>
				<span class="text-sm text-text-secondary">{etapa.responsavel || 'Sem responsável'}</span>
			</div>
		{:else}
			<InlineEditField
				fieldId={`${fieldId}-data_inicio`}
				label="Início"
				value={etapa.data_inicio}
				kind="date"
				emptyLabel="Sem data"
				pending={fieldState('data_inicio').pending}
				error={fieldState('data_inicio').error}
				onSave={(v) => onUpdateField('data_inicio', v)}
			>
				{#snippet display(value)}
					<time datetime={value ?? undefined}>{formatDateBr(value)}</time>
				{/snippet}
			</InlineEditField>
			<InlineEditField
				fieldId={`${fieldId}-data_fim`}
				label="Fim"
				value={etapa.data_fim}
				kind="date"
				emptyLabel="Sem data"
				pending={fieldState('data_fim').pending}
				error={fieldState('data_fim').error}
				onSave={(v) => onUpdateField('data_fim', v)}
			>
				{#snippet display(value)}
					<time datetime={value ?? undefined}>{formatDateBr(value)}</time>
				{/snippet}
			</InlineEditField>
			<InlineEditField
				fieldId={`${fieldId}-responsavel`}
				label="Responsável"
				value={etapa.responsavel}
				kind="text"
				emptyLabel="Sem responsável"
				pending={fieldState('responsavel').pending}
				error={fieldState('responsavel').error}
				onSave={(v) => onUpdateField('responsavel', v)}
			/>
		{/if}
	</div>

	<!-- Toggles iniciada/concluída -->
	{#if !locked}
		<div class="flex flex-wrap items-center gap-4">
			<label class="inline-flex cursor-pointer items-center gap-2 text-sm text-text-secondary transition-colors duration-fast ease-out hover:text-text-primary">
				<input
					type="checkbox"
					checked={etapa.iniciada}
					disabled={busy}
					onchange={onToggleIniciada}
					class="h-4 w-4 rounded border-border-subtle text-primary-500 transition-colors duration-fast ease-out focus:ring-primary-500"
				/>
				Iniciada
			</label>
			<label class="inline-flex cursor-pointer items-center gap-2 text-sm text-text-secondary transition-colors duration-fast ease-out hover:text-text-primary">
				<input
					type="checkbox"
					checked={etapa.done}
					disabled={busy || !etapa.iniciada}
					onchange={onToggleDone}
					class="h-4 w-4 rounded border-border-subtle text-success transition-colors duration-fast ease-out focus:ring-success"
				/>
				Concluída
			</label>
		</div>
	{/if}

	<!-- Comentário -->
	<div class="flex flex-col gap-2">
		{#if editingComment}
			<textarea
				bind:value={commentDraft}
				rows="2"
				disabled={busy}
				aria-label={`Comentário da etapa ${etapa.descricao ?? ''}`}
				class="w-full rounded-md border border-border-subtle bg-surface px-3 py-2 text-sm text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
			></textarea>
			<div class="flex items-center gap-2">
				<button
					type="button"
					onclick={commitComment}
					disabled={busy}
					class="rounded-md border border-primary-500 bg-primary-100 px-3 py-1.5 text-sm font-medium text-primary-700 transition-colors duration-fast hover:bg-primary-500 hover:text-white disabled:opacity-60 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
				>
					{busy ? 'Salvando…' : 'Salvar comentário'}
				</button>
				<button
					type="button"
					onclick={cancelComment}
					disabled={busy}
					class="rounded-md border border-border-subtle bg-surface px-3 py-1.5 text-sm font-medium text-text-primary transition-colors duration-fast hover:bg-surface-muted disabled:opacity-60 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
				>
					Cancelar
				</button>
			</div>
		{:else}
			<div class="flex items-start justify-between gap-2">
				<div class="min-w-0 text-sm">
					<span class="text-xs font-semibold uppercase tracking-wide text-text-muted">Comentário</span>
					{#if etapa.comentarios}
						<p class="whitespace-pre-wrap break-words text-text-secondary">{etapa.comentarios}</p>
					{:else}
						<p class="text-text-muted">Sem comentário</p>
					{/if}
				</div>
				{#if !locked && !etapa.done}
					<button
						type="button"
						onclick={startComment}
						disabled={busy}
						class="shrink-0 rounded-md border border-border-subtle bg-surface px-2 py-1 text-xs font-medium text-text-secondary transition-colors duration-fast hover:bg-surface-muted disabled:opacity-60 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
					>
						{etapa.comentarios ? 'Editar' : 'Adicionar'}
					</button>
				{/if}
			</div>
		{/if}
	</div>

	<!-- Tarefas da etapa: SOMENTE LEITURA (contagem + lista simples) -->
	<details class="flex flex-col gap-2">
		<!-- svelte-ignore a11y_no_redundant_roles -->
		<summary
			onclick={toggleTasks}
			class="cursor-pointer list-none text-sm text-text-secondary transition-colors duration-fast ease-out hover:text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
		>
			Tarefas:
			<strong class="font-medium text-text-primary">
				{etapa.task_count.done}/{etapa.task_count.total}
			</strong>
			{#if etapa.task_count.total > 0}
				<span class="text-text-muted">(somente leitura)</span>
			{/if}
		</summary>

		{#if tasksLoading}
			<p role="status" aria-live="polite" class="text-sm text-text-muted">Carregando tarefas…</p>
		{:else if tasks && tasks.length > 0}
			<ul class="flex flex-col gap-1 pl-1">
				{#each tasks as task (task.id)}
					<li class="flex items-center gap-2 text-sm text-text-secondary">
						<span class="text-text-muted" aria-hidden="true">•</span>
						{#if openTaskDrawer}
							<button
								type="button"
								onclick={() => openTaskDrawer?.(task.id)}
								class="break-words text-left hover:text-primary-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 {task.status === 'finalizada' ? 'line-through text-text-muted' : ''}"
							>
								{task.descricao}
							</button>
						{:else}
							<span class="break-words {task.status === 'finalizada' ? 'line-through text-text-muted' : ''}">
								{task.descricao}
							</span>
						{/if}
					</li>
				{/each}
			</ul>
		{:else if tasks && tasks.length === 0}
			<p class="text-sm text-text-muted">Nenhuma tarefa nesta etapa.</p>
		{/if}
	</details>

	<!-- Ações editar/excluir -->
	{#if !locked}
		<div class="flex items-center gap-2">
			<button
				type="button"
				onclick={onEdit}
				disabled={busy}
				class="rounded-md border border-border-subtle bg-surface px-3 py-1.5 text-sm font-medium text-text-primary transition-colors duration-fast ease-out hover:bg-surface-muted hover:text-primary-700 disabled:opacity-60 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
			>
				Editar etapa
			</button>
			<button
				type="button"
				onclick={onDelete}
				disabled={busy}
				class="rounded-md border border-danger bg-surface px-3 py-1.5 text-sm font-medium text-danger transition-colors duration-fast ease-out hover:bg-danger hover:text-white disabled:opacity-60 focus:outline-none focus-visible:ring-2 focus-visible:ring-danger"
			>
				Excluir
			</button>
		</div>
	{/if}

	{#if rowError}
		<p role="alert" class="text-sm text-danger">{rowError}</p>
	{/if}
</article>
