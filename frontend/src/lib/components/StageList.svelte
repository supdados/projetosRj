<script lang="ts">
	/**
	 * Tabela de etapas do Detalhe de Projeto — paridade VISUAL + INTERAÇÃO com v4.5.
	 *
	 * Reproduz fielmente (_project_stages_section.html + 07-stage-dnd.js + 05-stage-composer.js):
	 *  - Cartão com tabela (.etapa-v4-table) e cabeçalho de colunas.
	 *  - DRAG-AND-DROP HTML5 nativo via alça (.drag-handle): ghost customizado,
	 *    drop-indicator (linha azul) acima/abaixo conforme o cursor, classes
	 *    .dragging/.drag-over; ao soltar, emite onReorder(novaOrdem).
	 *  - LINHA DE ENTRADA inline ("Adicionar nova etapa") que abre o COMPOSER inline
	 *    (textarea descrição + datas + responsável + status ciclo + confirmar/cancelar),
	 *    com Enter salva, Escape cancela, auto-resize.
	 *  - MENU DE CONTEXTO de dias úteis nas células de data (+7/+14/+21) e MODAL de
	 *    confirmação de cascata — ambos delegados ao pai (que chama os endpoints).
	 *
	 * CASCATA É SERVER-SIDE: este componente só emite intenções; a página chama a API
	 * e RE-BUSCA. Acessibilidade: DnD com fallback por teclado (mover ↑/↓ na alça).
	 */
	import StageRow from './StageRow.svelte';
	import type { EtapaDetail, EtapaInlineField } from '$lib/types/projectDetail';

	interface FieldState {
		pending?: boolean;
		error?: string | null;
	}
	interface NewStageDraft {
		descricao: string;
		data_inicio: string;
		data_fim: string;
		responsavel: string;
		iniciada: boolean;
		done: boolean;
	}

	interface Props {
		etapas: EtapaDetail[];
		projectId: number;
		readonly?: boolean;
		reordering?: boolean;
		reorderError?: string | null;
		/** Adição em andamento (spinner no confirmar). */
		addingStage?: boolean;
		addStageError?: string | null;
		rowStates?: Record<
			number,
			{ fields?: Partial<Record<EtapaInlineField, FieldState>>; busy?: boolean; error?: string | null }
		>;
		onReorder: (orderedIds: number[]) => void;
		onUpdateField: (etapaId: number, field: EtapaInlineField, value: string) => void;
		onCycleStatus: (etapaId: number) => void;
		onSaveComentario: (etapaId: number, comentario: string) => void;
		onDelete: (etapaId: number) => void;
		onOpenTasks: (etapaId: number) => void;
		/** Adiciona uma etapa via composer inline; o pai chama a API. */
		onAddStage: (draft: NewStageDraft) => void;
		/** Pede o menu de contexto de dias úteis numa data; o pai exibe/aplica. */
		onDateContextMenu: (
			etapaId: number,
			field: 'data_inicio' | 'data_fim',
			clientX: number,
			clientY: number
		) => void;
		meetingSlot?: import('svelte').Snippet<[EtapaDetail]>;
	}

	let {
		etapas,
		projectId,
		readonly = false,
		reordering = false,
		reorderError = null,
		addingStage = false,
		addStageError = null,
		rowStates = {},
		onReorder,
		onUpdateField,
		onCycleStatus,
		onSaveComentario,
		onDelete,
		onOpenTasks,
		onAddStage,
		onDateContextMenu,
		meetingSlot
	}: Props = $props();

	let tbodyEl = $state<HTMLTableSectionElement | null>(null);

	// Apenas etapas arrastáveis (workflow, não reuniões) participam da reordenação.
	const draggableEtapas = $derived(etapas.filter((e) => !e.is_google_meeting));
	const canReorder = $derived(!readonly && !reordering && draggableEtapas.length > 1);

	/** Numeração de exibição "projectId.posicao" (1-based, ordem de render). */
	function displayNumber(index: number): string {
		return `${projectId}.${index + 1}`;
	}

	// ---- Drag and drop (HTML5 nativo, alça) ----
	let draggedId = $state<number | null>(null);
	let ghostEl: HTMLDivElement | null = null;
	let dropIndicatorEl: HTMLDivElement | null = null;
	let overId = $state<number | null>(null);
	let overPosition = $state<'top' | 'bottom'>('bottom');

	function ensureDropIndicator(): HTMLDivElement {
		if (!dropIndicatorEl) {
			dropIndicatorEl = document.createElement('div');
			dropIndicatorEl.className = 'stage-drop-indicator';
			document.body.appendChild(dropIndicatorEl);
		}
		return dropIndicatorEl;
	}
	function showDropIndicator(row: HTMLElement, position: 'top' | 'bottom'): void {
		if (!tbodyEl) return;
		const ind = ensureDropIndicator();
		const rect = row.getBoundingClientRect();
		const tableRect = tbodyEl.getBoundingClientRect();
		ind.style.left = `${tableRect.left}px`;
		ind.style.width = `${tableRect.width}px`;
		ind.style.top = position === 'top' ? `${rect.top - 2}px` : `${rect.bottom - 1}px`;
		ind.classList.add('show');
	}
	function hideDropIndicator(): void {
		dropIndicatorEl?.classList.remove('show');
	}

	function onDragStart(event: DragEvent): void {
		const handle = (event.target as HTMLElement)?.closest('.drag-handle');
		const row = (event.target as HTMLElement)?.closest('tr[data-etapa-id]') as HTMLElement | null;
		if (!handle || !row || !canReorder) {
			event.preventDefault();
			return;
		}
		const id = Number(row.dataset.etapaId);
		draggedId = id;
		if (event.dataTransfer) {
			event.dataTransfer.effectAllowed = 'move';
			event.dataTransfer.setData('text/plain', String(id));
			// Ghost customizado (paridade com .drag-ghost-custom do legado).
			// Construído com DOM seguro (textContent), sem innerHTML.
			ghostEl = document.createElement('div');
			ghostEl.className = 'stage-drag-ghost';
			const icon = document.createElement('i');
			icon.className = 'fas fa-arrows-alt';
			const label = document.createElement('span');
			const desc = row.querySelector('.etapa-descricao')?.textContent?.trim() ?? 'Movendo etapa…';
			label.textContent = desc.slice(0, 60) + (desc.length > 60 ? '…' : '');
			ghostEl.append(icon, label);
			document.body.appendChild(ghostEl);
			event.dataTransfer.setDragImage(ghostEl, 20, 20);
		}
		setTimeout(() => {
			ghostEl?.remove();
			ghostEl = null;
		}, 0);
	}

	function onDragOver(event: DragEvent): void {
		if (draggedId === null) return;
		const row = (event.target as HTMLElement)?.closest('tr[data-etapa-id]') as HTMLElement | null;
		if (!row) return;
		const id = Number(row.dataset.etapaId);
		const etapa = etapas.find((e) => e.id === id);
		if (!etapa || etapa.is_google_meeting || id === draggedId) return;
		event.preventDefault();
		if (event.dataTransfer) event.dataTransfer.dropEffect = 'move';
		const rect = row.getBoundingClientRect();
		const position = event.clientY < rect.top + rect.height / 2 ? 'top' : 'bottom';
		overId = id;
		overPosition = position;
		showDropIndicator(row, position);
	}

	function onDrop(event: DragEvent): void {
		event.preventDefault();
		if (draggedId === null || overId === null) {
			resetDrag();
			return;
		}
		const ids = etapas.map((e) => e.id);
		const fromIdx = ids.indexOf(draggedId);
		if (fromIdx === -1) {
			resetDrag();
			return;
		}
		const [moved] = ids.splice(fromIdx, 1);
		const toIdx = ids.indexOf(overId);
		if (toIdx === -1) {
			resetDrag();
			return;
		}
		const insertAt = overPosition === 'top' ? toIdx : toIdx + 1;
		ids.splice(insertAt, 0, moved);
		onReorder(ids);
		resetDrag();
	}

	function resetDrag(): void {
		draggedId = null;
		overId = null;
		hideDropIndicator();
	}

	/** Fallback por teclado: move a etapa uma posição (mesma intenção do DnD). */
	function moveByKeyboard(index: number, delta: number): void {
		const target = index + delta;
		if (target < 0 || target >= etapas.length) return;
		const ids = etapas.map((e) => e.id);
		const [moved] = ids.splice(index, 1);
		ids.splice(target, 0, moved);
		onReorder(ids);
	}

	function handleHandleKeydown(event: KeyboardEvent, index: number): void {
		if (!canReorder) return;
		if (event.key === 'ArrowUp') {
			event.preventDefault();
			moveByKeyboard(index, -1);
		} else if (event.key === 'ArrowDown') {
			event.preventDefault();
			moveByKeyboard(index, 1);
		}
	}

	function rowState(etapaId: number) {
		return rowStates[etapaId] ?? {};
	}

	// ---- Composer inline (adicionar etapa) ----
	let composerOpen = $state(false);
	let descricaoEl = $state<HTMLTextAreaElement | null>(null);
	let draft = $state<NewStageDraft>({
		descricao: '',
		data_inicio: '',
		data_fim: '',
		responsavel: '',
		iniciada: false,
		done: false
	});

	const composerStatusState = $derived(draft.done ? 'done' : draft.iniciada ? 'started' : 'idle');
	const composerStatusLabel = $derived(
		composerStatusState === 'done'
			? 'Concluída'
			: composerStatusState === 'started'
				? 'Iniciada'
				: 'Não iniciada'
	);
	const composerStatusIcon = $derived(
		composerStatusState === 'done'
			? 'fas fa-check-circle'
			: composerStatusState === 'started'
				? 'fas fa-play-circle'
				: 'far fa-circle'
	);
	const newStageNumber = $derived(`${projectId}.${etapas.length + 1}`);

	async function openComposer(): Promise<void> {
		composerOpen = true;
		await Promise.resolve();
		descricaoEl?.focus();
	}
	function closeComposer(): void {
		composerOpen = false;
		draft = {
			descricao: '',
			data_inicio: '',
			data_fim: '',
			responsavel: '',
			iniciada: false,
			done: false
		};
	}
	function cycleComposerStatus(): void {
		if (!draft.iniciada) {
			draft.iniciada = true;
			draft.done = false;
		} else if (!draft.done) {
			draft.done = true;
		} else {
			draft.iniciada = false;
			draft.done = false;
		}
	}
	function submitComposer(): void {
		if (!draft.descricao.trim() || addingStage) {
			descricaoEl?.focus();
			return;
		}
		onAddStage({ ...draft, descricao: draft.descricao.trim() });
	}
	function autoResizeDescricao(): void {
		if (descricaoEl) {
			descricaoEl.style.height = 'auto';
			descricaoEl.style.height = `${descricaoEl.scrollHeight}px`;
		}
	}
	function composerKeydown(event: KeyboardEvent): void {
		if (event.key === 'Escape') {
			event.preventDefault();
			closeComposer();
		} else if (event.key === 'Enter' && !event.shiftKey) {
			const target = event.target as HTMLElement;
			if (target?.closest('.composer-status-btn')) return;
			event.preventDefault();
			submitComposer();
		}
	}

	// Após adicionar com sucesso (etapas muda de tamanho), fecha o composer.
	let prevLen = etapas.length;
	$effect(() => {
		if (etapas.length !== prevLen) {
			prevLen = etapas.length;
			if (composerOpen && !addingStage) closeComposer();
		}
	});
</script>

{#if reorderError}
	<p role="alert" class="mb-2 text-sm text-danger">{reorderError}</p>
{/if}

<div class="etapa-table-card">
	<div class="etapa-table-wrap">
		<table class="etapa-table" aria-busy={reordering}>
			<thead>
				<tr>
					<th class="col-drag"></th>
					<th class="col-number">ID</th>
					<th class="col-desc">Descrição</th>
					<th class="col-date">Data Início</th>
					<th class="col-date">Data Fim</th>
					<th class="col-responsavel">Responsável</th>
					<th class="col-tasks">Tarefas</th>
					<th class="col-status">Status</th>
					<th class="col-actions">Ações</th>
				</tr>
			</thead>
			<tbody
				bind:this={tbodyEl}
				ondragstart={onDragStart}
				ondragover={onDragOver}
				ondrop={onDrop}
				ondragend={resetDrag}
			>
				{#each etapas as etapa, index (etapa.id)}
					{@const st = rowState(etapa.id)}
					<StageRow
						{etapa}
						displayNumber={displayNumber(index)}
						{readonly}
						fieldStates={st.fields}
						busy={st.busy}
						rowError={st.error}
						onUpdateField={(field, value) => onUpdateField(etapa.id, field, value)}
						onCycleStatus={() => onCycleStatus(etapa.id)}
						onSaveComentario={(c) => onSaveComentario(etapa.id, c)}
						onDelete={() => onDelete(etapa.id)}
						onOpenTasks={() => onOpenTasks(etapa.id)}
						onDateContextMenu={(field, x, y) => onDateContextMenu(etapa.id, field, x, y)}
						onHandleKeydown={(e) => handleHandleKeydown(e, index)}
						{meetingSlot}
					/>
				{/each}

				{#if !readonly}
					{#if !composerOpen}
						<tr class="etapa-entry-row">
							<td colspan="9">
								<button type="button" class="etapa-entry-btn" onclick={openComposer}>
									<i class="fas fa-plus-circle" aria-hidden="true"></i>
									<span>Adicionar nova etapa</span>
								</button>
							</td>
						</tr>
					{:else}
						<tr class="etapa-composer-row">
							<td class="cell-drag">
								<span class="composer-drag-placeholder" aria-hidden="true">
									<i class="fas fa-grip-vertical"></i>
								</span>
							</td>
							<td class="cell-number">{newStageNumber}</td>
							<td class="cell-desc">
								<label class="sr-only" for="composer-descricao">Descrição da etapa</label>
								<textarea
									id="composer-descricao"
									bind:this={descricaoEl}
									bind:value={draft.descricao}
									rows="1"
									required
									placeholder="Descreva a nova etapa"
									class="composer-textarea"
									oninput={autoResizeDescricao}
									onkeydown={composerKeydown}
								></textarea>
							</td>
							<td class="cell-date">
								<label class="sr-only" for="composer-data-inicio">Data de início</label>
								<input
									id="composer-data-inicio"
									type="date"
									bind:value={draft.data_inicio}
									class="composer-input"
									onkeydown={composerKeydown}
								/>
							</td>
							<td class="cell-date">
								<label class="sr-only" for="composer-data-fim">Data de fim</label>
								<input
									id="composer-data-fim"
									type="date"
									bind:value={draft.data_fim}
									class="composer-input"
									onkeydown={composerKeydown}
								/>
							</td>
							<td class="cell-responsavel">
								<label class="sr-only" for="composer-responsavel">Responsável</label>
								<input
									id="composer-responsavel"
									type="text"
									bind:value={draft.responsavel}
									placeholder="Responsável"
									class="composer-input"
									onkeydown={composerKeydown}
								/>
							</td>
							<td class="cell-tasks">
								<span class="etapa-task-pill-placeholder" aria-hidden="true">—</span>
							</td>
							<td class="cell-status">
								<button
									type="button"
									class="etapa-status-toggle etapa-status-toggle-{composerStatusState} composer-status-btn"
									title="Clique para alternar o status"
									onclick={cycleComposerStatus}
								>
									<i class={composerStatusIcon} aria-hidden="true"></i>
									<span>{composerStatusLabel}</span>
								</button>
							</td>
							<td class="cell-actions composer-actions">
								<button
									type="button"
									class="composer-icon-btn composer-confirm"
									title="Confirmar etapa"
									aria-label="Confirmar etapa"
									disabled={addingStage}
									onclick={submitComposer}
								>
									{#if addingStage}
										<i class="fas fa-spinner fa-spin" aria-hidden="true"></i>
									{:else}
										<i class="fas fa-check" aria-hidden="true"></i>
									{/if}
								</button>
								<button
									type="button"
									class="composer-icon-btn composer-cancel"
									title="Cancelar adição"
									aria-label="Cancelar adição"
									disabled={addingStage}
									onclick={closeComposer}
								>
									<i class="fas fa-times" aria-hidden="true"></i>
								</button>
							</td>
						</tr>
						{#if addStageError}
							<tr><td colspan="9" class="composer-error" role="alert">{addStageError}</td></tr>
						{/if}
					{/if}
				{/if}

				{#if etapas.length === 0 && readonly}
					<tr>
						<td colspan="9" class="no-etapas-cell">
							<i class="fas fa-tasks" aria-hidden="true"></i>
							<p>Nenhuma etapa adicionada ainda.</p>
						</td>
					</tr>
				{/if}
			</tbody>
		</table>
	</div>
</div>

{#if canReorder}
	<p class="sr-only" aria-live="polite">
		Use a alça de arraste e as setas para cima/baixo para reordenar as etapas.
	</p>
{/if}

<style>
	.etapa-table-card {
		background: var(--app-color-surface, #fff);
		border: 1px solid var(--app-color-border, #dfe8f2);
		border-radius: 14px;
		box-shadow: 0 8px 24px rgba(20, 45, 78, 0.06);
		overflow-x: hidden;
		overflow-y: visible;
	}
	.etapa-table-wrap {
		overflow-x: auto;
		overflow-y: visible;
	}
	.etapa-table {
		width: 100%;
		min-width: 1100px;
		border-collapse: separate;
		border-spacing: 0;
		margin: 0;
		background: var(--app-color-surface, #fff);
	}
	.etapa-table thead th {
		border-bottom: 1px solid var(--app-color-border, #dfe7f1);
		background: var(--app-color-surface-muted, #f4f8fc);
		color: #546f8d;
		font-size: 0.72rem;
		text-transform: uppercase;
		letter-spacing: 0.04em;
		font-weight: 700;
		padding: 0.58rem 0.7rem;
		white-space: nowrap;
		text-align: left;
	}
	.col-drag {
		width: 44px;
	}
	.col-number {
		width: 64px;
	}
	.col-desc {
		width: 306px;
	}
	.col-date {
		width: 130px;
		text-align: center !important;
	}
	.col-responsavel {
		width: 170px;
		text-align: center !important;
	}
	.col-tasks {
		width: 140px;
		text-align: center !important;
	}
	.col-status {
		width: 150px;
		text-align: center !important;
	}
	.col-actions {
		width: 72px;
		text-align: center !important;
	}

	.etapa-table :global(tr.etapa-draggable-row) {
		transition: all 0.35s ease;
		position: relative;
	}

	:global(.stage-drop-indicator) {
		position: fixed;
		height: 3px;
		background: linear-gradient(90deg, #005a92 0%, rgba(0, 90, 146, 0.8) 50%, #005a92 100%);
		border-radius: 2px;
		z-index: 1000;
		opacity: 0;
		transition: opacity 0.2s ease;
		box-shadow: 0 2px 8px rgba(0, 90, 146, 0.4);
		pointer-events: none;
	}
	:global(.stage-drop-indicator.show) {
		opacity: 1;
	}
	:global(.stage-drag-ghost) {
		display: inline-flex;
		align-items: center;
		gap: 0.5rem;
		background: rgba(255, 255, 255, 0.95);
		backdrop-filter: blur(20px);
		border: 1px solid #dfe7f1;
		box-shadow: 0 8px 32px rgba(0, 90, 146, 0.2);
		border-radius: 12px;
		padding: 0.75rem 1.25rem;
		color: #263f59;
		font-size: 0.875rem;
		font-weight: 600;
	}

	.etapa-entry-row td,
	.etapa-composer-row td {
		border-top: 1px solid var(--app-color-border, #edf2f8);
		padding: 0.5rem 0.7rem;
	}
	.etapa-entry-btn {
		display: inline-flex;
		align-items: center;
		gap: 0.45rem;
		background: none;
		border: 1px dashed #c3d3e8;
		border-radius: 8px;
		padding: 0.45rem 0.9rem;
		color: #2856b6;
		font-size: 0.82rem;
		font-weight: 600;
		cursor: pointer;
		transition:
			background 0.16s ease,
			border-color 0.16s ease;
	}
	.etapa-entry-btn:hover {
		background: rgba(37, 99, 235, 0.07);
		border-color: #9fc0e8;
	}
	.composer-drag-placeholder {
		color: #c3d3e8;
	}
	.composer-textarea,
	.composer-input {
		width: 100%;
		padding: 0.38rem 0.58rem;
		border: 1px solid #c4d5e7;
		border-radius: 7px;
		font-size: 0.875rem;
		color: #3e556f;
		background: #fff;
		font-family: inherit;
		line-height: 1.45;
		box-sizing: border-box;
	}
	.composer-textarea {
		resize: none;
		overflow: hidden;
		display: block;
	}
	.composer-textarea:focus,
	.composer-input:focus {
		outline: none;
		border-color: #7ea6ce;
		box-shadow: 0 0 0 3px rgba(30, 84, 143, 0.12);
	}
	.etapa-task-pill-placeholder {
		color: #9fb1c6;
		font-weight: 500;
	}
	.cell-drag {
		width: 44px;
	}
	.cell-number {
		width: 64px;
		font-family: var(--ds-font-family-mono, ui-monospace, monospace);
		color: #5f7691;
		font-weight: 500;
	}
	.cell-desc {
		width: 306px;
	}
	.cell-date {
		width: 130px;
		text-align: center;
	}
	.cell-responsavel {
		width: 170px;
		text-align: center;
	}
	.cell-tasks {
		width: 140px;
		text-align: center;
	}
	.cell-status {
		width: 150px;
		text-align: center;
	}
	.cell-actions {
		width: 72px;
		text-align: center;
	}
	.composer-actions {
		display: flex;
		gap: 0.3rem;
		justify-content: center;
	}
	.composer-icon-btn {
		width: 32px;
		height: 32px;
		border-radius: 8px;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		border: 1px solid #cbdcf0;
		background: #fff;
		cursor: pointer;
		transition: all 0.16s ease;
	}
	.composer-confirm {
		color: #1d714e;
		border-color: #b9dfca;
		background: #eaf7f1;
	}
	.composer-confirm:hover:not(:disabled) {
		background: #e3f4eb;
	}
	.composer-cancel {
		color: #972d2d;
	}
	.composer-cancel:hover:not(:disabled) {
		background: rgba(169, 59, 59, 0.14);
		border-color: rgba(184, 63, 63, 0.5);
	}
	.composer-icon-btn:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}
	.composer-error,
	.no-etapas-cell {
		padding: 0.7rem;
		text-align: center;
		color: #64748b;
	}
	.composer-error {
		color: var(--app-color-danger, #b42323);
	}
	.no-etapas-cell i {
		font-size: 1.5rem;
		color: #94a3b8;
		display: block;
		margin-bottom: 0.5rem;
	}
	.no-etapas-cell p {
		margin: 0;
	}

	.etapa-status-toggle {
		height: 30px;
		min-width: 124px;
		border-radius: 7px;
		border: 1px solid #cbdcf0;
		padding: 0 0.58rem;
		background: #fff;
		color: #2b4d6f;
		font-weight: 600;
		font-size: 0.78rem;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		gap: 0.3rem;
		cursor: pointer;
		transition: all 0.16s ease;
	}
	.etapa-status-toggle-done {
		background: #eaf7f1;
		border-color: #b9dfca;
		color: #1d714e;
	}
	.etapa-status-toggle-started {
		background: #edf5ff;
		border-color: #c5d8ee;
		color: #255585;
	}

	.sr-only {
		position: absolute;
		width: 1px;
		height: 1px;
		padding: 0;
		margin: -1px;
		overflow: hidden;
		clip: rect(0, 0, 0, 0);
		white-space: nowrap;
		border: 0;
	}
</style>
