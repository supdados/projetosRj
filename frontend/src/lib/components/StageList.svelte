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
	import AreaResponsavelPicker from './AreaResponsavelPicker.svelte';
	import DatePickerPanel from './DatePickerPanel.svelte';
	import type {
		EtapaDetail,
		EtapaInlineField,
		EtapaResponsavelArea
	} from '$lib/types/projectDetail';
	import { dropStagePinningMeetings, moveStageSkippingMeetings } from '$lib/utils/stageReorder';
	import '$lib/styles/stage-chips.css';

	interface FieldState {
		pending?: boolean;
		error?: string | null;
	}
	interface NewStageDraft {
		descricao: string;
		data_inicio: string;
		data_fim: string;
		responsaveis: EtapaResponsavelArea[];
		iniciada: boolean;
		done: boolean;
	}

	interface Props {
		etapas: EtapaDetail[];
		projectId: number;
		/** Etapa em destaque temporário (deep-link ?focus_etapa da busca global). */
		highlightEtapaId?: number | null;
		readonly?: boolean;
		reordering?: boolean;
		reorderError?: string | null;
		/** Adição em andamento (spinner no confirmar). */
		addingStage?: boolean;
		addStageError?: string | null;
		rowStates?: Record<
			number,
			{
				fields?: Partial<Record<EtapaInlineField, FieldState>>;
				busy?: boolean;
			}
		>;
		onReorder: (orderedIds: number[]) => void;
		onUpdateField: (etapaId: number, field: EtapaInlineField, value: string) => void;
		onCycleStatus: (etapaId: number) => void;
		/** Dispensa manual do aviso inline de uma linha. */
		onSaveComentario: (etapaId: number, comentario: string) => void;
		onDelete: (etapaId: number) => void;
		onOpenTasks: (etapaId: number) => void;
		/** Adiciona uma etapa via composer inline; o pai chama a API. */
		/** Cria a etapa e devolve `true` no sucesso — o composer só fecha (e limpa
		 *  o rascunho) com essa confirmação; `false` mantém aberto p/ correção. */
		onAddStage: (draft: NewStageDraft) => Promise<boolean> | boolean;
		/** Etapa confirmada pelo servidor após salvar áreas responsáveis inline. */
		onResponsaveisSaved: (etapa: EtapaDetail) => void;
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
		highlightEtapaId = null,
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
		onResponsaveisSaved,
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
	let overId = $state<number | null>(null);
	let overPosition = $state<'top' | 'bottom'>('bottom');
	/** Altura (px) da linha arrastada, medida no dragstart, para o vão do placeholder. */
	let draggedRowHeight = $state<number | null>(null);
	/**
	 * Linha-fonte que colapsa durante o drag. Aplicado num setTimeout(0) DEPOIS
	 * do dragstart: colapsar o nó de forma síncrona dentro do dragstart cancela
	 * o drag nativo no Chrome/Firefox (mesma técnica do KanbanBoard).
	 */
	let collapsedId = $state<number | null>(null);
	let collapseTimer: ReturnType<typeof setTimeout> | null = null;
	/** Linha que acabou de aterrissar — recebe o pulso de assentamento. */
	let settledId = $state<number | null>(null);
	let settleTimer: ReturnType<typeof setTimeout> | null = null;

	/** Id da etapa diante da qual o vão do placeholder abre (`-1` = fim da lista). */
	const placeholderBeforeId = $derived.by(() => {
		if (draggedId === null || overId === null) return null;
		if (overPosition === 'top') return overId;
		const idx = etapas.findIndex((e) => e.id === overId);
		if (idx === -1) return null;
		return idx + 1 < etapas.length ? etapas[idx + 1].id : -1;
	});
	/** Altura do vão (desconta o padding da célula; fallback ~ linha comum). */
	const gapHeight = $derived(Math.max((draggedRowHeight ?? 56) - 6, 40));

	function markSettled(etapaId: number): void {
		if (
			typeof window !== 'undefined' &&
			window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
		) {
			return;
		}
		if (settleTimer) clearTimeout(settleTimer);
		settledId = etapaId;
		settleTimer = setTimeout(() => {
			settledId = null;
			settleTimer = null;
		}, 480);
	}

	/**
	 * Ghost de arraste = clone da PRÓPRIA linha, embrulhado numa tabela offscreen
	 * com as larguras de coluna copiadas (table-layout fixed sem thead usa a
	 * primeira linha para dimensionar). O clone mantém as classes scoped do
	 * Svelte, então herda o CSS real da tabela — o snapshot vira um cartão fiel.
	 */
	function buildRowGhost(row: HTMLElement): HTMLDivElement {
		const wrap = document.createElement('div');
		wrap.className = 'stage-drag-ghost-row';
		wrap.style.width = `${row.offsetWidth}px`;
		const sourceTable = row.closest('table');
		const table = document.createElement('table');
		table.className = sourceTable?.className ?? '';
		table.style.width = `${row.offsetWidth}px`;
		table.style.minWidth = '0';
		table.style.tableLayout = 'fixed';
		const tbody = document.createElement('tbody');
		const clone = row.cloneNode(true) as HTMLElement;
		Array.from(row.children).forEach((cell, i) => {
			const cloned = clone.children[i] as HTMLElement | undefined;
			if (cloned) cloned.style.width = `${(cell as HTMLElement).offsetWidth}px`;
		});
		tbody.appendChild(clone);
		table.appendChild(tbody);
		wrap.appendChild(table);
		return wrap;
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
		// Mede ANTES do colapso: o placeholder abre um vão do mesmo tamanho.
		draggedRowHeight = row.getBoundingClientRect().height;
		if (collapseTimer) clearTimeout(collapseTimer);
		collapseTimer = setTimeout(() => {
			if (draggedId === id) collapsedId = id;
			collapseTimer = null;
		}, 0);
		if (event.dataTransfer) {
			event.dataTransfer.effectAllowed = 'move';
			event.dataTransfer.setData('text/plain', String(id));
			ghostEl = buildRowGhost(row);
			document.body.appendChild(ghostEl);
			const rect = row.getBoundingClientRect();
			event.dataTransfer.setDragImage(
				ghostEl,
				Math.max(event.clientX - rect.left, 0),
				Math.max(event.clientY - rect.top, 0)
			);
		}
		setTimeout(() => {
			ghostEl?.remove();
			ghostEl = null;
		}, 0);
	}

	/** Mantém o alvo atual (cursor sobre o placeholder/linha não-alvo) e permite o drop. */
	function keepCurrentDropTarget(event: DragEvent): void {
		if (overId === null) return;
		event.preventDefault();
		if (event.dataTransfer) event.dataTransfer.dropEffect = 'move';
	}

	function onDragOver(event: DragEvent): void {
		if (draggedId === null) return;
		const row = (event.target as HTMLElement)?.closest('tr[data-etapa-id]') as HTMLElement | null;
		if (!row) {
			keepCurrentDropTarget(event);
			return;
		}
		const id = Number(row.dataset.etapaId);
		const etapa = etapas.find((e) => e.id === id);
		if (!etapa || etapa.is_google_meeting || id === draggedId) {
			keepCurrentDropTarget(event);
			return;
		}
		event.preventDefault();
		if (event.dataTransfer) event.dataTransfer.dropEffect = 'move';
		const rect = row.getBoundingClientRect();
		const position = event.clientY < rect.top + rect.height / 2 ? 'top' : 'bottom';
		overId = id;
		overPosition = position;
	}

	/** Saiu da tbody: fecha o vão (dragend cobre o cancelamento do drag). */
	function onTbodyDragLeave(event: DragEvent): void {
		const related = event.relatedTarget as Node | null;
		if (tbodyEl && related && tbodyEl.contains(related)) return;
		overId = null;
	}

	function onDrop(event: DragEvent): void {
		event.preventDefault();
		if (draggedId === null || overId === null) {
			resetDrag();
			return;
		}
		const ids = dropStagePinningMeetings(etapas, draggedId, overId, overPosition);
		if (!ids) {
			resetDrag();
			return;
		}
		const movedId = draggedId;
		onReorder(ids);
		resetDrag();
		markSettled(movedId);
	}

	function resetDrag(): void {
		if (collapseTimer) {
			clearTimeout(collapseTimer);
			collapseTimer = null;
		}
		draggedId = null;
		overId = null;
		collapsedId = null;
		draggedRowHeight = null;
	}

	/** Fallback por teclado: move a etapa uma posição pulando reuniões (paridade DnD). */
	function moveByKeyboard(index: number, delta: number): void {
		const ids = moveStageSkippingMeetings(etapas, index, delta);
		if (ids) onReorder(ids);
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
	let composerRowEl = $state<HTMLTableRowElement | null>(null);
	let draft = $state<NewStageDraft>({
		descricao: '',
		data_inicio: '',
		data_fim: '',
		responsaveis: [],
		iniciada: false,
		done: false
	});

	// Date picker custom do composer (mesmo calendário das células/calendário).
	let composerDateField = $state<'data_inicio' | 'data_fim' | null>(null);
	let composerDateAnchors = $state<Record<'data_inicio' | 'data_fim', HTMLElement | null>>({
		data_inicio: null,
		data_fim: null
	});

	function toggleComposerDate(field: 'data_inicio' | 'data_fim'): void {
		composerDateField = composerDateField === field ? null : field;
	}

	function pickComposerDate(iso: string | null): void {
		if (composerDateField) draft[composerDateField] = iso ?? '';
		composerDateField = null;
	}

	/** dd/mm/aaaa para exibição no trigger do composer; ISO fica no draft. */
	function composerDateLabel(iso: string): string {
		if (!iso) return '';
		const [y, m, d] = iso.split('-');
		return `${d}/${m}/${y}`;
	}

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
		// Fixa a altura do textarea já na abertura (igual ao estado pós-digitação)
		// para não dar o "pulinho" de crescimento na primeira vez que abre.
		autoResizeDescricao();
	}
	function closeComposer(): void {
		composerOpen = false;
		draft = {
			descricao: '',
			data_inicio: '',
			data_fim: '',
			responsaveis: [],
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
	async function submitComposer(): Promise<void> {
		if (!draft.descricao.trim() || addingStage) {
			descricaoEl?.focus();
			return;
		}
		// Fecha SÓ com a confirmação do pai: fechar antes do retorno deixa o texto
		// preenchido e cada Enter/clique fora cria uma etapa duplicada.
		const created = await onAddStage({ ...draft, descricao: draft.descricao.trim() });
		if (created) closeComposer();
	}
	function autoResizeDescricao(): void {
		if (descricaoEl) {
			descricaoEl.style.height = 'auto';
			// Soma a borda: a caixa é border-box e scrollHeight ignora a borda.
			const borderY = descricaoEl.offsetHeight - descricaoEl.clientHeight;
			descricaoEl.style.height = `${descricaoEl.scrollHeight + borderY}px`;
		}
	}
	/**
	 * Clique fora do composer: salva se já houver descrição, senão cancela.
	 * Usa pointerdown em captura — o calendário nativo de <input type=date> é
	 * renderizado fora do DOM, então não dispara este evento (sem falso positivo).
	 */
	function handleComposerOutsidePointer(event: PointerEvent): void {
		if (!composerOpen || addingStage) return;
		const target = event.target as Node | null;
		if (composerRowEl && target && composerRowEl.contains(target)) return;
		if (draft.descricao.trim()) {
			submitComposer();
		} else {
			closeComposer();
		}
	}
	function composerKeydown(event: KeyboardEvent): void {
		if (event.key === 'Escape') {
			event.preventDefault();
			closeComposer();
		} else if (event.key === 'Enter' && !event.shiftKey) {
			const target = event.target as HTMLElement;
			// Enter no status/data alterna o próprio controle, não submete o form.
			if (target?.closest('.composer-status-btn, .composer-date-trigger')) return;
			event.preventDefault();
			submitComposer();
		}
	}

	// Enquanto o composer está aberto, escuta cliques fora dele.
	$effect(() => {
		if (!composerOpen) return;
		document.addEventListener('pointerdown', handleComposerOutsidePointer, true);
		return () => document.removeEventListener('pointerdown', handleComposerOutsidePointer, true);
	});

	// Após adicionar com sucesso (etapas muda de tamanho), fecha o composer.
	// prevLen é semeado na primeira execução do effect para que a leitura
	// reativa de etapas.length aconteça dentro do effect, não na montagem.
	let prevLen: number | null = null;
	$effect(() => {
		const len = etapas.length;
		if (prevLen === null) {
			prevLen = len;
			return;
		}
		if (len !== prevLen) {
			prevLen = len;
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
				ondragleave={onTbodyDragLeave}
				ondrop={onDrop}
				ondragend={resetDrag}
			>
				{#each etapas as etapa, index (etapa.id)}
					{@const st = rowState(etapa.id)}
					{#if placeholderBeforeId === etapa.id}
						<tr class="stage-placeholder-row" aria-hidden="true">
							<td colspan="9">
								<div class="stage-placeholder-fill" style:height={`${gapHeight}px`}></div>
							</td>
						</tr>
					{/if}
					<StageRow
						{etapa}
						displayNumber={displayNumber(index)}
						{readonly}
						dragging={collapsedId === etapa.id}
						settled={settledId === etapa.id}
						highlighted={highlightEtapaId === etapa.id}
						fieldStates={st.fields}
						busy={st.busy}
						onUpdateField={(field, value) => onUpdateField(etapa.id, field, value)}
						onCycleStatus={() => onCycleStatus(etapa.id)}
						onSaveComentario={(c) => onSaveComentario(etapa.id, c)}
						onDelete={() => onDelete(etapa.id)}
						onOpenTasks={() => onOpenTasks(etapa.id)}
						onResponsaveisSaved={(e) => onResponsaveisSaved(e)}
						onDateContextMenu={(field, x, y) => onDateContextMenu(etapa.id, field, x, y)}
						onHandleKeydown={(e) => handleHandleKeydown(e, index)}
						{meetingSlot}
					/>
				{/each}

				{#if placeholderBeforeId === -1}
					<tr class="stage-placeholder-row" aria-hidden="true">
						<td colspan="9">
							<div class="stage-placeholder-fill" style:height={`${gapHeight}px`}></div>
						</td>
					</tr>
				{/if}

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
						<tr class="etapa-composer-row" bind:this={composerRowEl}>
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
								<button
									id="composer-data-inicio"
									bind:this={composerDateAnchors.data_inicio}
									type="button"
									aria-label="Data de início"
									aria-expanded={composerDateField === 'data_inicio'}
									onclick={() => toggleComposerDate('data_inicio')}
									onkeydown={composerKeydown}
									class="composer-input composer-date-trigger"
									class:composer-date-trigger--empty={!draft.data_inicio}
								>
									{composerDateLabel(draft.data_inicio) || 'Sem data'}
								</button>
								{#if composerDateField === 'data_inicio' && composerDateAnchors.data_inicio}
									<DatePickerPanel
										anchor={composerDateAnchors.data_inicio}
										value={draft.data_inicio || null}
										allowClear
										ariaLabel="Data de início"
										max={draft.data_fim || null}
										onPick={pickComposerDate}
										onClear={() => pickComposerDate(null)}
										onClose={() => (composerDateField = null)}
									/>
								{/if}
							</td>
							<td class="cell-date">
								<button
									id="composer-data-fim"
									bind:this={composerDateAnchors.data_fim}
									type="button"
									aria-label="Data de fim"
									aria-expanded={composerDateField === 'data_fim'}
									onclick={() => toggleComposerDate('data_fim')}
									onkeydown={composerKeydown}
									class="composer-input composer-date-trigger"
									class:composer-date-trigger--empty={!draft.data_fim}
								>
									{composerDateLabel(draft.data_fim) || 'Sem data'}
								</button>
								{#if composerDateField === 'data_fim' && composerDateAnchors.data_fim}
									<DatePickerPanel
										anchor={composerDateAnchors.data_fim}
										value={draft.data_fim || null}
										allowClear
										ariaLabel="Data de fim"
										min={draft.data_inicio || null}
										onPick={pickComposerDate}
										onClear={() => pickComposerDate(null)}
										onClose={() => (composerDateField = null)}
									/>
								{/if}
							</td>
							<td class="cell-responsavel">
								<AreaResponsavelPicker bind:selecionadas={draft.responsaveis} />
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
									class="grid h-7 w-7 flex-none place-items-center rounded-md text-text-muted transition-colors duration-fast hover:bg-surface-muted hover:text-brand active:scale-95 disabled:opacity-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
									title="Confirmar etapa"
									aria-label="Confirmar etapa"
									disabled={addingStage}
									onclick={submitComposer}
								>
									{#if addingStage}
										<i class="fas fa-spinner fa-spin text-xs" aria-hidden="true"></i>
									{:else}
										<i class="fas fa-check text-xs" aria-hidden="true"></i>
									{/if}
								</button>
								<button
									type="button"
									class="grid h-7 w-7 flex-none place-items-center rounded-md text-text-muted transition-colors duration-fast hover:bg-surface-muted hover:text-danger active:scale-95 disabled:opacity-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
									title="Cancelar adição"
									aria-label="Cancelar adição"
									disabled={addingStage}
									onclick={closeComposer}
								>
									<i class="fas fa-xmark text-xs" aria-hidden="true"></i>
								</button>
							</td>
						</tr>
						{#if addStageError}
							<tr><td colspan="9" class="composer-error"><span role="alert">{addStageError}</span></td></tr>
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
		background: var(--ds-color-surface-base);
		border: 1px solid var(--ds-color-border-base);
		border-radius: 14px;
		box-shadow: 0 8px 24px rgba(20, 45, 78, 0.06);
		overflow-x: hidden;
		overflow-y: visible;
	}
	:global([data-theme='dark']) .etapa-table-card {
		box-shadow: 0 8px 24px rgba(0, 0, 0, 0.40);
	}
	.etapa-table-wrap {
		overflow-x: auto;
		overflow-y: visible;
	}
	.etapa-table {
		width: 100%;
		min-width: 1100px;
		/* Larguras de coluna fixas: o conteúdo (ex.: <input type=date> em edição)
		   não pode mais esticar a coluna, então nada muda de largura ao editar. */
		table-layout: fixed;
		border-collapse: separate;
		border-spacing: 0;
		margin: 0;
		background: var(--ds-color-surface-base);
	}
	.etapa-table thead th {
		border-bottom: 1px solid var(--ds-color-border-base);
		background: var(--ds-color-surface-muted);
		color: var(--ds-color-text-secondary);
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
		text-align: center !important;
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

	/* Vão de inserção: preview tracejado de onde a linha aterrissará (paridade
	   com .kanban-placeholder). Altura/animação SÓ no <div> interno — height e
	   transition em <tr>/<td> são ignorados/recalculados pelo layout de tabela. */
	.stage-placeholder-row td {
		padding: 3px 8px;
		border-top: 1px solid var(--ds-color-border-base);
	}
	.stage-placeholder-fill {
		border-radius: 10px;
		border: 1.5px dashed var(--ds-color-border-brand-soft);
		background-color: var(--ds-color-wash-brand);
		pointer-events: none;
		animation: stage-placeholder-in 0.14s ease;
	}
	@keyframes stage-placeholder-in {
		from {
			opacity: 0;
			transform: scaleY(0.85);
		}
		to {
			opacity: 1;
			transform: scaleY(1);
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.stage-placeholder-fill {
			animation: none;
		}
	}
	/* Ghost = cartão com o clone fiel da linha (ver buildRowGhost). Offscreen no
	   DOM só o suficiente para o browser tirar o snapshot do setDragImage. */
	:global(.stage-drag-ghost-row) {
		position: fixed;
		top: -1200px;
		left: 0;
		z-index: -1;
		pointer-events: none;
		overflow: hidden;
		border-radius: 12px;
		border: 1px solid var(--ds-color-border-brand, #9db8d2);
		background: var(--ds-color-surface-base);
		box-shadow: 0 12px 36px rgba(0, 90, 146, 0.28);
	}
	:global(.stage-drag-ghost-row td) {
		border-top: 0 !important;
	}
	:global([data-theme='dark'] .stage-drag-ghost-row) {
		border-color: var(--ds-color-border-strong);
		box-shadow: 0 12px 36px rgba(0, 0, 0, 0.55);
	}

	.etapa-entry-row td,
	.etapa-composer-row td {
		border-top: 1px solid var(--ds-color-border-base);
		padding: 0.5rem 0.7rem;
	}
	/* Ocupa a linha inteira e centraliza: o tracejado vira a "última linha"
	   adicionável; ao clicar, vira o composer (estado atual). */
	.etapa-entry-btn {
		display: flex;
		width: 100%;
		align-items: center;
		justify-content: center;
		gap: 0.45rem;
		background: none;
		border: 1px dashed var(--ds-color-border-strong);
		border-radius: 8px;
		padding: 0.6rem 0.9rem;
		color: var(--ds-color-text-brand);
		font-size: 0.82rem;
		font-weight: 600;
		cursor: pointer;
		transition:
			background 0.16s ease,
			border-color 0.16s ease;
	}
	.etapa-entry-btn:hover {
		background: rgba(37, 99, 235, 0.07);
		border-color: var(--ds-color-border-strong);
	}
	.composer-drag-placeholder {
		color: var(--ds-color-border-strong);
	}
	.composer-textarea,
	.composer-input {
		width: 100%;
		padding: 0.38rem 0.58rem;
		border: 1px solid var(--stage-input-border);
		border-radius: 7px;
		font-size: 0.875rem;
		color: var(--ds-color-text-primary);
		background: var(--ds-color-surface-base);
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
		border-color: var(--ds-color-border-brand);
		box-shadow: 0 0 0 var(--ds-focus-halo-width) var(--ds-color-focus-halo);
	}
	.composer-date-trigger {
		cursor: pointer;
		text-align: center;
		font-variant-numeric: tabular-nums;
	}
	.composer-date-trigger--empty {
		color: var(--ds-color-text-muted);
	}
	.etapa-task-pill-placeholder {
		color: var(--ds-color-text-muted);
		font-weight: 500;
	}
	.cell-drag {
		width: 44px;
	}
	.cell-number {
		width: 64px;
		font-family: var(--ds-font-family-mono, ui-monospace, monospace);
		color: var(--ds-color-text-secondary);
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
	.composer-error,
	.no-etapas-cell {
		padding: 0.7rem;
		text-align: center;
		color: var(--ds-color-text-secondary);
	}
	.composer-error {
		color: var(--ds-color-text-danger);
	}
	.no-etapas-cell i {
		font-size: 1.5rem;
		color: var(--ds-color-text-muted);
		display: block;
		margin-bottom: 0.5rem;
	}
	.no-etapas-cell p {
		margin: 0;
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
