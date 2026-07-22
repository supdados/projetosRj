<script lang="ts">
	/**
	 * Uma LINHA da tabela de etapas (paridade com _project_stages_section.html +
	 * 07-stage-dnd.js + etapa-status-tasks.css). CONTROLADA por callbacks.
	 *
	 * Reproduz fielmente o v4.5:
	 *  - célula com alça de arraste (.drag-handle, draggable) — o DnD vive no StageList;
	 *  - célula de ID (project.id.index) monoespaçada;
	 *  - célula de descrição com EDITOR INLINE (textarea auto-resize) + comentário
	 *    inline (display/placeholder clicável);
	 *  - células de data com EDITOR INLINE (input date) + menu de contexto (+dias úteis,
	 *    emitido ao pai); responsável com editor inline;
	 *  - pílula de tarefas (.etapa-task-pill) com contagem done/total e estado vazio;
	 *  - botão de STATUS CICLO único (idle → started → done → idle);
	 *  - ação de excluir (.btn-floating).
	 *
	 * Etapa concluída => células com line-through e edição bloqueada (toast no pai).
	 * Reuniões Google: renderizadas read-only (slot meetingSlot).
	 */
	import { tick } from 'svelte';
	import InlineEditField from './InlineEditField.svelte';
	import AreaResponsavelPicker from './AreaResponsavelPicker.svelte';
	import type { EtapaDetail, EtapaInlineField } from '$lib/types/projectDetail';
	import '$lib/styles/stage-chips.css';

	interface FieldState {
		pending?: boolean;
		error?: string | null;
	}

	interface Props {
		etapa: EtapaDetail;
		/** Número de exibição "projectId.index" (1-based). */
		displayNumber: string;
		readonly?: boolean;
		/** Linha-fonte colapsada durante o drag (o placeholder mostra o destino). */
		dragging?: boolean;
		/** Acabou de aterrissar no drop — pulso de assentamento. */
		settled?: boolean;
		/** Destaque temporário (deep-link ?focus_etapa da busca global). */
		highlighted?: boolean;
		fieldStates?: Partial<Record<EtapaInlineField, FieldState>>;
		busy?: boolean;
		rowError?: string | null;
		meetingSlot?: import('svelte').Snippet<[EtapaDetail]>;
		onUpdateField: (field: EtapaInlineField, value: string) => void;
		/** Ciclo de status (idle→started→done→idle) — o pai decide o endpoint. */
		onCycleStatus: () => void;
		onSaveComentario: (comentario: string) => void;
		onDelete: () => void;
		/** Abre o quick-add de tarefas (pílula). */
		onOpenTasks: () => void;
		/** Etapa confirmada pelo servidor após salvar áreas responsáveis. */
		onResponsaveisSaved: (etapa: EtapaDetail) => void;
		/** Menu de contexto de dias úteis numa célula de data. */
		onDateContextMenu: (field: 'data_inicio' | 'data_fim', clientX: number, clientY: number) => void;
		/** Teclado na alça de arraste (ArrowUp/ArrowDown) — fallback acessível do DnD. */
		onHandleKeydown?: (event: KeyboardEvent) => void;
	}

	let {
		etapa,
		displayNumber,
		readonly = false,
		dragging = false,
		settled = false,
		highlighted = false,
		fieldStates = {},
		busy = false,
		rowError = null,
		meetingSlot,
		onUpdateField,
		onCycleStatus,
		onSaveComentario,
		onDelete,
		onOpenTasks,
		onResponsaveisSaved,
		onDateContextMenu,
		onHandleKeydown
	}: Props = $props();

	const isMeeting = $derived(etapa.is_google_meeting);
	const locked = $derived(readonly || isMeeting);
	const statusState = $derived(etapa.done ? 'done' : etapa.iniciada ? 'started' : 'idle');

	let editingComment = $state(false);
	let commentDraft = $state('');
	let commentEl = $state<HTMLTextAreaElement | null>(null);
	// Valor otimista do comentário: evita piscar o placeholder/valor antigo entre
	// o blur e a confirmação do servidor (mesmo padrão do InlineEditField).
	let optimisticComment = $state<string | null>(null);
	let sawCommentBusy = $state(false);

	const shownComment = $derived(optimisticComment ?? etapa.comentarios);

	$effect(() => {
		if (optimisticComment === null) {
			sawCommentBusy = false;
			return;
		}
		if (busy) {
			sawCommentBusy = true;
			return;
		}
		if ((etapa.comentarios ?? '') === optimisticComment || rowError || sawCommentBusy) {
			optimisticComment = null;
			sawCommentBusy = false;
		}
	});

	function fieldState(field: EtapaInlineField): FieldState {
		return fieldStates[field] ?? {};
	}

	// Ajusta a altura do textarea ao conteúdo (auto-grow). Sem isso, o `rows="1"`
	// + `overflow:hidden` prendia a edição em 1 linha, rolando até o cursor e
	// exibindo só a última palavra de um comentário com várias linhas.
	function resizeComment(): void {
		const el = commentEl;
		if (!el) return;
		el.style.height = 'auto';
		el.style.height = `${el.scrollHeight}px`;
	}

	async function startComment(): Promise<void> {
		if (locked || etapa.done) return;
		commentDraft = shownComment ?? '';
		editingComment = true;
		// Foca direto na caixa para que digitar (e o blur ao clicar fora) funcionem
		// já no primeiro clique.
		await tick();
		commentEl?.focus();
		resizeComment();
	}
	function commitComment(): void {
		const text = commentDraft.trim();
		editingComment = false;
		// Clicar fora sem digitar nada apenas fecha; com texto, salva.
		if (text) {
			optimisticComment = text; // segura o valor novo no display até o servidor confirmar
			onSaveComentario(text);
		} else {
			commentDraft = shownComment ?? '';
		}
	}
	function cancelComment(): void {
		editingComment = false;
		commentDraft = shownComment ?? '';
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

	function dateContext(field: 'data_inicio' | 'data_fim', event: MouseEvent): void {
		if (locked || etapa.done) return;
		event.preventDefault();
		onDateContextMenu(field, event.clientX, event.clientY);
	}

	const statusLabel = $derived(
		statusState === 'done' ? 'Concluída' : statusState === 'started' ? 'Iniciada' : 'Não iniciada'
	);
	const statusIcon = $derived(
		statusState === 'done'
			? 'fas fa-check-circle'
			: statusState === 'started'
				? 'fas fa-play-circle'
				: 'far fa-circle'
	);
	// UX preventivo: a validação dura de datas na conclusão é do backend.
	const missingDatesForDone = $derived(
		statusState === 'started' && (!etapa.data_inicio || !etapa.data_fim)
	);
	const statusTitle = $derived(
		missingDatesForDone
			? 'Defina as datas de início e fim antes de concluir a etapa'
			: statusState === 'done'
				? 'Clique para voltar para não iniciada'
				: statusState === 'started'
					? 'Clique para marcar como concluída'
					: 'Clique para marcar como iniciada'
	);

	const rowTextClass = $derived(etapa.done && !isMeeting ? 'etapa-done-text' : '');
</script>

{#if isMeeting}
	<!-- ===== Linha de reunião Google (read-only) ===== -->
	<tr
		class="etapa-row etapa-row-google-meeting"
		class:is-focus-highlight={highlighted}
		data-etapa-id={etapa.id}
	>
		<td class="cell-drag cell-meeting-drag">
			<i class="fab fa-google etapa-meeting-drag-icon" aria-hidden="true"></i>
		</td>
		<td class="cell-number">{displayNumber}</td>
		<td class="cell-desc" colspan="7">
			<div class="etapa-descricao">{etapa.descricao ?? '—'}</div>
			{#if etapa.meeting?.owner_email}
				<div class="etapa-meeting-owner" title={etapa.meeting.owner_email}>
					<i class="far fa-user" aria-hidden="true"></i><span>{etapa.meeting.owner_email}</span>
				</div>
			{/if}
			{#if meetingSlot}
				<div class="etapa-meeting-slot">{@render meetingSlot(etapa)}</div>
			{/if}
		</td>
	</tr>
{:else}
	<!-- ===== Linha de etapa regular ===== -->
	<tr
		class="etapa-row etapa-draggable-row {etapa.done
			? 'etapa-done'
			: etapa.iniciada
				? 'etapa-iniciada'
				: ''}"
		class:is-dragging={dragging}
		class:is-drop-settling={settled}
		class:is-focus-highlight={highlighted}
		data-etapa-id={etapa.id}
		aria-busy={busy}
	>
		<td class="cell-drag" class:is-locked={locked}>
			{#if !locked}
				<span
					class="drag-handle"
					draggable="true"
					role="button"
					tabindex="0"
					aria-label="Arraste para reordenar a etapa (ou use as setas para cima/baixo)"
					title="Arraste para reordenar"
					onkeydown={onHandleKeydown}
				>
					<i class="fas fa-grip-vertical" aria-hidden="true"></i>
				</span>
			{/if}
		</td>
		<td class="cell-number">{displayNumber}</td>

		<!-- Descrição + comentário -->
		<td class="cell-desc {rowTextClass}">
			<div class="etapa-descricao-main">
				{#if locked || etapa.done}
					<span class="etapa-descricao">{etapa.descricao ?? '—'}</span>
				{:else}
					<InlineEditField
						variant="cell"
						kind="textarea"
						fieldId={`etapa-${etapa.id}-descricao`}
						label="Descrição da etapa"
						value={etapa.descricao}
						pending={fieldState('descricao').pending}
						error={fieldState('descricao').error}
						onSave={(v) => onUpdateField('descricao', v)}
					>
						{#snippet display(v)}
							<span class="etapa-descricao">{v || '—'}</span>
						{/snippet}
					</InlineEditField>
				{/if}
			</div>
			<div class="etapa-descricao-comment">
				{#if editingComment}
					<textarea
						bind:this={commentEl}
						bind:value={commentDraft}
						rows="1"
						disabled={busy}
						placeholder="Escreva um comentário"
						aria-label="Comentário da etapa"
						class="etapa-comment-editor"
						onblur={commitComment}
						oninput={resizeComment}
						onkeydown={(e) => {
							if (e.key === 'Enter' && !e.shiftKey) {
								e.preventDefault();
								commitComment();
							} else if (e.key === 'Escape') {
								cancelComment();
							}
						}}
					></textarea>
				{:else if shownComment}
					<button
						type="button"
						class="etapa-comentario-display"
						title="Clique para editar"
						disabled={locked || etapa.done}
						onclick={startComment}
					>
						{shownComment}
					</button>
				{:else if !locked && !etapa.done}
					<button type="button" class="etapa-comentario-placeholder" onclick={startComment}>
						adicionar comentário
					</button>
				{/if}
			</div>
		</td>

		<!-- Data início -->
		<td
			class="cell-date {rowTextClass}"
			oncontextmenu={(e) => dateContext('data_inicio', e)}
		>
			{#if locked || etapa.done}
				<span class="cell-readonly" class:editable-field-empty={!etapa.data_inicio}>
					{formatDateBr(etapa.data_inicio)}
				</span>
			{:else}
				<InlineEditField
					variant="cell"
					kind="date"
					centered
					fieldId={`etapa-${etapa.id}-data_inicio`}
					label="Data de início"
					value={etapa.data_inicio}
					emptyLabel="Sem data"
					maxDate={etapa.data_inicio ? null : etapa.data_fim}
					pending={fieldState('data_inicio').pending}
					error={fieldState('data_inicio').error}
					onSave={(v) => onUpdateField('data_inicio', v)}
				>
					{#snippet display(v)}
						{formatDateBr(v)}
					{/snippet}
				</InlineEditField>
			{/if}
		</td>

		<!-- Data fim -->
		<td
			class="cell-date {rowTextClass}"
			oncontextmenu={(e) => dateContext('data_fim', e)}
		>
			{#if locked || etapa.done}
				<span class="cell-readonly" class:editable-field-empty={!etapa.data_fim}>
					{formatDateBr(etapa.data_fim)}
				</span>
			{:else}
				<InlineEditField
					variant="cell"
					kind="date"
					centered
					fieldId={`etapa-${etapa.id}-data_fim`}
					label="Data de fim"
					value={etapa.data_fim}
					emptyLabel="Sem data"
					minDate={etapa.data_inicio}
					pending={fieldState('data_fim').pending}
					error={fieldState('data_fim').error}
					onSave={(v) => onUpdateField('data_fim', v)}
				>
					{#snippet display(v)}
						{formatDateBr(v)}
					{/snippet}
				</InlineEditField>
			{/if}
		</td>

		<!-- Responsável (áreas) -->
		<td class="cell-responsavel {rowTextClass}">
			{#if locked || etapa.done}
				{#if etapa.responsaveis.length > 0}
					<span class="stage-resp-chips" aria-label="Áreas responsáveis">
						{#each etapa.responsaveis as r (r.area_id ?? r.label)}
							<span class="stage-resp-chip">{r.label}</span>
						{/each}
					</span>
				{:else}
					<span class="cell-readonly" class:editable-field-empty={!etapa.responsavel}>
						{etapa.responsavel || 'Sem responsável'}
					</span>
				{/if}
			{:else}
				<AreaResponsavelPicker
					etapaId={etapa.id}
					selecionadas={etapa.responsaveis}
					onSaved={(e) => onResponsaveisSaved(e)}
				/>
			{/if}
		</td>

		<!-- Tarefas (pílula) -->
		<td class="cell-tasks">
			{#if readonly}
				<span class="text-muted-small">-</span>
			{:else}
				<button
					type="button"
					class="etapa-task-pill"
					class:is-empty={etapa.task_count.total === 0}
					class:is-stage-done={etapa.done}
					aria-disabled={etapa.done ? 'true' : undefined}
					tabindex={etapa.done ? -1 : undefined}
					title={etapa.done
						? 'Etapa concluída — desfaça a conclusão para criar tarefas'
						: 'Criar tarefa nesta etapa'}
					onclick={() => !etapa.done && onOpenTasks()}
				>
					<span class="etapa-task-pill-has">
						<span class="etapa-task-pill-count">{etapa.task_count.done}/{etapa.task_count.total}</span>
					</span>
					<span class="etapa-task-pill-add">
						<i class="fas fa-plus" aria-hidden="true"></i>
						<span>Tarefas</span>
					</span>
				</button>
			{/if}
		</td>

		<!-- Status (ciclo) -->
		<td class="cell-status">
			<button
				type="button"
				class="etapa-status-toggle etapa-status-toggle-{statusState}"
				data-state={statusState}
				disabled={readonly || busy}
				title={statusTitle}
				onclick={onCycleStatus}
			>
				<i class={statusIcon} aria-hidden="true"></i>
				<span>{statusLabel}</span>
			</button>
		</td>

		<!-- Ações -->
		<td class="cell-actions">
			{#if !readonly}
				<button
					type="button"
					class="btn-floating"
					title="Excluir Etapa"
					disabled={busy}
					onclick={onDelete}
				>
					<i class="fas fa-trash" aria-hidden="true"></i>
				</button>
			{:else}
				<span class="text-muted-small">-</span>
			{/if}
		</td>
	</tr>
{/if}

<style>
	.etapa-row :global(td) {
		border-top: 1px solid var(--color-border);
		padding: 0.62rem 0.7rem;
		vertical-align: middle;
		color: var(--color-text-primary);
		font-size: 0.875rem;
	}
	.etapa-row:hover :global(td) {
		background: var(--color-surface-muted);
	}

	/* Linha-fonte colapsada durante o drag: altura de <tr> vem do conteúdo, então
	   o colapso zera padding/borda das células E o conteúdo (display:none nos
	   filhos + font-size 0 para nós de texto soltos, ex. o número da etapa). */
	.etapa-row.is-dragging {
		opacity: 0;
		pointer-events: none;
	}
	.etapa-row.is-dragging :global(td) {
		padding-top: 0;
		padding-bottom: 0;
		border-top-width: 0;
		font-size: 0;
		line-height: 0;
	}
	.etapa-row.is-dragging :global(td > *) {
		display: none;
	}

	/* Pulso de assentamento pós-drop (paridade com o kanban; background/sombra
	   em vez de transform — scale em display:table-row é imprevisível). */
	@keyframes stage-drop-settle {
		0% {
			background-color: color-mix(in srgb, var(--ds-color-primary-500) 14%, transparent);
		}
		100% {
			background-color: transparent;
		}
	}
	.etapa-row.is-drop-settling :global(td) {
		animation: stage-drop-settle 0.45s ease;
	}
	@media (prefers-reduced-motion: reduce) {
		.etapa-row.is-drop-settling :global(td) {
			animation: none;
		}
	}

	/* Destaque do deep-link ?focus_etapa (busca global): segura o realce e some
	   suave. Aplica no <td> pela mesma razão do pulso de drop (background). */
	@keyframes stage-focus-highlight {
		0%,
		62% {
			background-color: color-mix(in srgb, var(--ds-color-primary-500) 16%, transparent);
		}
		100% {
			background-color: transparent;
		}
	}
	.etapa-row.is-focus-highlight :global(td) {
		animation: stage-focus-highlight 2.4s ease;
	}
	@media (prefers-reduced-motion: reduce) {
		.etapa-row.is-focus-highlight :global(td) {
			animation: none;
			background-color: color-mix(in srgb, var(--ds-color-primary-500) 12%, transparent);
		}
	}

	.cell-drag {
		width: 44px;
		color: var(--color-text-muted);
	}
	.drag-handle {
		display: inline-flex;
		cursor: grab;
		color: var(--color-text-muted);
		transition: color 0.16s ease;
	}
	.drag-handle:hover {
		color: var(--color-text-secondary);
	}
	.drag-handle:active {
		cursor: grabbing;
	}

	.cell-number {
		width: 64px;
		font-family: var(--ds-font-family-mono, ui-monospace, monospace);
		color: var(--color-text-secondary);
		font-weight: 500;
		white-space: nowrap;
		text-align: center;
	}

	/* SEM display:flex aqui: flex num <td> o tira do layout de tabela — a célula
	   deixa de esticar até a altura da linha e a border-top desalinha das outras
	   colunas (o "buraco" na divisória). Os filhos já empilham como blocos. */
	.cell-desc {
		width: 306px;
		min-width: 306px;
		padding-left: 0.4rem;
	}
	/* Mesma altura da caixa do .editable-field (editável) para que a descrição
	   tenha altura constante entre os estados editável e concluído (read-only). */
	.etapa-descricao-main {
		display: flex;
		align-items: center;
		min-height: 1.75rem;
	}
	.etapa-descricao {
		font-weight: 600;
		color: var(--color-text-primary);
	}
	.etapa-done .etapa-descricao,
	.etapa-done-text {
		color: var(--color-text-muted) !important;
		text-decoration: line-through;
	}
	/* Reserva a altura de uma linha de comentário para que a célula tenha a MESMA
	   altura nos 3 estados (não iniciada / iniciada / concluída) — concluída não
	   tem placeholder, mas o espaço continua reservado. */
	.etapa-descricao-comment {
		display: block;
		min-height: 1.65rem;
	}
	/* Display, placeholder e editor compartilham EXATAMENTE a mesma caixa
	   (padding + borda + line-height) para que clicar-para-editar não cresça nem
	   encolha a linha. */
	.etapa-comentario-display,
	.etapa-comentario-placeholder,
	.etapa-comment-editor {
		/* block (não inline-block): elimina o espaço de descida da line-box que
		   fazia a linha crescer ao entrar em edição do comentário. */
		display: block;
		width: 100%;
		box-sizing: border-box;
		padding: 0.18rem 0.45rem;
		border: 1px solid transparent;
		border-radius: 6px;
		text-align: left;
		font-size: 0.78rem;
		line-height: 1.45;
		font-family: inherit;
	}
	.etapa-comentario-display,
	.etapa-comentario-placeholder {
		background: none;
		color: var(--color-text-secondary);
		cursor: pointer;
	}
	.etapa-comentario-display:hover,
	.etapa-comentario-placeholder:hover {
		color: var(--ds-color-primary-500);
	}
	.etapa-comentario-display:disabled {
		cursor: default;
		text-decoration: line-through;
	}
	/* O placeholder "adicionar comentário" só aparece ao passar o mouse na linha
	   (ou ao receber foco via teclado). */
	.etapa-comentario-placeholder {
		opacity: 0;
		transition: opacity 0.16s ease;
	}
	.etapa-row:hover .etapa-comentario-placeholder,
	.etapa-comentario-placeholder:focus-visible {
		opacity: 1;
	}
	.etapa-comment-editor {
		color: var(--color-text-primary);
		background: var(--color-surface);
		border-color: var(--stage-input-border);
		resize: none;
		overflow: hidden;
	}
	.etapa-comment-editor:focus {
		outline: none;
		border-color: var(--ds-color-primary-500);
		box-shadow: 0 0 0 3px var(--ds-color-primary-100);
	}

	.cell-date {
		width: 130px;
		text-align: center;
		font-family: var(--ds-font-family-mono, ui-monospace, monospace);
		color: var(--color-text-secondary);
		font-weight: 500;
		white-space: nowrap;
	}
	.cell-responsavel {
		width: 170px;
		min-width: 170px;
		text-align: center;
	}
	.stage-resp-chips {
		display: inline-flex;
		flex-wrap: wrap;
		gap: 0.25rem;
		justify-content: center;
	}
	.stage-resp-chip {
		border: 1px solid var(--stage-chip-border);
		border-radius: 6px;
		font-size: 0.75rem;
		padding: 0.1rem 0.45rem;
	}
	.cell-readonly {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		min-height: 30px;
		width: 100%;
		padding: 0.22rem 0.48rem;
		border-radius: 8px;
	}
	.cell-readonly.editable-field-empty {
		color: var(--color-text-secondary);
		background: var(--color-surface-muted);
		border: 1px dashed var(--color-border);
	}
	.etapa-done .cell-readonly.editable-field-empty {
		background: transparent;
		border-color: transparent;
		color: var(--color-text-muted);
	}

	.cell-tasks {
		width: 140px;
		text-align: center;
	}
	/* Pílula de tarefas — paridade com 05-stage-task-quick-add.css */
	.etapa-task-pill {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		gap: 0.34rem;
		width: 116px;
		height: 32px;
		padding: 0 0.7rem;
		border-radius: 8px;
		border: 1px solid #cfe0f5;
		background: #eef4ff;
		color: #2856b6;
		font-size: 0.78rem;
		font-weight: 600;
		line-height: 1;
		cursor: pointer;
		transition:
			background-color 0.16s ease,
			border-color 0.16s ease,
			color 0.16s ease;
	}
	.etapa-task-pill:hover,
	.etapa-task-pill:focus-visible {
		background: #e2ecff;
		border-color: #b6cdf0;
		color: #1d4ed8;
		outline: none;
	}
	:global([data-theme='dark']) .etapa-task-pill:hover,
	:global([data-theme='dark']) .etapa-task-pill:focus-visible {
		background: rgba(78, 149, 204, 0.18);
		border-color: rgba(196, 210, 222, 0.46);
		color: var(--ds-color-primary-500);
	}
	.etapa-task-pill-has,
	.etapa-task-pill-add {
		display: inline-flex;
		align-items: center;
		gap: 0.32rem;
		line-height: 1;
	}
	.etapa-task-pill-count {
		font-weight: 700;
	}
	.etapa-task-pill i {
		font-size: 0.9rem;
	}
	.etapa-task-pill-add {
		display: none;
	}
	.etapa-task-pill.is-empty {
		background: transparent;
		border-style: dashed;
		border-color: #c3d3e8;
		color: #5a7799;
	}
	.etapa-task-pill.is-empty:hover,
	.etapa-task-pill.is-empty:focus-visible {
		background: rgba(37, 99, 235, 0.07);
		border-color: #9fc0e8;
		color: #1d4ed8;
	}
	:global([data-theme='dark']) .etapa-task-pill.is-empty {
		border-color: var(--color-border);
		color: var(--color-text-secondary);
	}
	:global([data-theme='dark']) .etapa-task-pill.is-empty:hover,
	:global([data-theme='dark']) .etapa-task-pill.is-empty:focus-visible {
		background: rgba(78, 149, 204, 0.12);
		border-color: var(--color-border-strong);
	}
	.etapa-task-pill.is-empty .etapa-task-pill-has {
		display: none;
	}
	.etapa-task-pill.is-empty .etapa-task-pill-add {
		display: inline-flex;
	}
	.etapa-task-pill.is-stage-done {
		opacity: 0.4;
		cursor: not-allowed;
	}

	.cell-status {
		width: 150px;
		text-align: center;
	}

	.cell-actions {
		width: 72px;
		text-align: center;
	}
	.btn-floating {
		width: 32px;
		height: 32px;
		border-radius: 8px;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		padding: 0;
		border: 1px solid transparent;
		font-size: 0.875rem;
		background: transparent;
		color: var(--color-text-secondary);
		cursor: pointer;
		transition:
			color 0.16s ease,
			border-color 0.16s ease,
			background-color 0.16s ease;
	}
	.btn-floating:hover:not(:disabled) {
		border-color: var(--stage-danger-border-hover);
		color: var(--stage-danger-text);
		background: var(--stage-danger-bg-hover);
	}
	.btn-floating:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.text-muted-small {
		color: var(--color-text-muted);
		font-size: 0.78rem;
	}

	.etapa-meeting-drag-icon {
		color: #4285f4;
		font-size: 1.15rem;
	}
	.cell-meeting-drag {
		text-align: center;
	}
	.etapa-meeting-owner {
		display: inline-flex;
		align-items: center;
		gap: 0.34rem;
		max-width: 100%;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		color: var(--color-text-secondary);
		font-size: 0.72rem;
		font-weight: 500;
		margin-top: 0.15rem;
	}
	.etapa-meeting-slot {
		margin-top: 0.4rem;
	}

	:global([data-theme='dark']) .etapa-task-pill {
		background: rgba(78, 149, 204, 0.18);
		border-color: rgba(196, 210, 222, 0.46);
		color: var(--ds-color-primary-500);
	}
</style>
