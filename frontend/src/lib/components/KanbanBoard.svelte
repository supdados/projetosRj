<script lang="ts">
	/**
	 * Board do Kanban de Tarefas (jun/2026): os 4 status ativos como colunas
	 * IGUAIS — Não iniciada | Em andamento | Para validação | Para ajustes — e a
	 * Finalizada como trilho colapsável, com DnD nativo HTML5 (espelha
	 * `static/js/modules/kanban/board-dnd.js`).
	 *
	 * FONTE DE VERDADE = STORE: o board lê `$store.columns` e despacha mutações
	 * (`moveCard`/`reorder`) que são otimistas + confirmadas pelo backend +
	 * revertidas (rollback) se o servidor recusar. NADA de estado em `data-*`:
	 * o contexto de drag vive em estado reativo do componente (`dragContext`),
	 * não no DOM.
	 *
	 * UX-only durante o drag: usamos `canItemMoveToStatus` (util puro) para
	 * habilitar/desabilitar a dropzone "Finalizada" — o servidor é autoritativo.
	 *
	 * Acessibilidade:
	 *   - cada card é focável (`tabindex=0`) e responde a teclado (setas ←/→ para
	 *     mover entre colunas, Home/End para os extremos) — alternativa ao DnD,
	 *     sem texto redundante duplicado abaixo da coluna;
	 *   - um região `aria-live="polite"` anuncia as movimentações e erros.
	 */
	import { getContext, setContext, type Snippet } from 'svelte';
	import KanbanColumn from '$lib/components/KanbanColumn.svelte';
	import KanbanDoneColumn from '$lib/components/KanbanDoneColumn.svelte';
	import type { BoardStore } from '$lib/stores/board';
	import type { BoardCard } from '$lib/types/board';
	import type { KanbanZoneView } from '$lib/types/kanbanDnd';
	import {
		KANBAN_COLUMN_MOTION,
		type KanbanColumnMotionSignal
	} from '$lib/utils/kanbanColumnMotion';
	import {
		STATUS_LABELS,
		TASK_STATUS_ORDER,
		canItemMoveToStatus,
		normalizeStatus,
		type TaskStatus
	} from '$lib/utils/taskStatus';

	/**
	 * CONFETE ao concluir (paridade `taskFinalizeCelebration.trigger` disparado por
	 * `updateItemStatus` no legado): a página fornece o disparador via contexto.
	 * Recebe a ORIGEM (ponto do drop ou o card) para originar a celebração ali,
	 * como o `celebrationOrigin`/`resolveFinalizeCelebrationOrigin` do legado.
	 */
	type CelebrateOrigin = { x: number; y: number } | Element | null | undefined;
	const celebrateFinalize = getContext<((origin?: CelebrateOrigin) => void) | undefined>(
		'celebrateFinalize'
	);

	interface Props {
		store: BoardStore;
		/** Composer inline por coluna (Fase 5b-3), repassado para cada KanbanColumn. */
		composer?: Snippet<[TaskStatus]>;
	}

	let { store, composer }: Props = $props();

	// Sinal "morph de largura em curso" — ver kanbanColumnMotion.ts.
	const columnMotion = $state<KanbanColumnMotionSignal>({ active: false });
	setContext(KANBAN_COLUMN_MOTION, columnMotion);

	/** Contexto do drag em curso (estado canônico no componente, não no DOM). */
	interface DragContext {
		card: BoardCard;
		fromStatus: TaskStatus;
	}

	let dragContext = $state<DragContext | null>(null);
	let overStatus = $state<TaskStatus | null>(null);
	/**
	 * Índice de inserção sob o ponteiro na coluna `overStatus` (entre os cards
	 * visíveis) — dirige o PLACEHOLDER tracejado que mostra onde o card cairá.
	 */
	let overIndex = $state<number | null>(null);
	/** Altura (px) do card arrastado, medida no dragstart, para o vão do placeholder. */
	let dragCardHeight = $state<number | null>(null);
	/** Mensagem para leitores de tela (movimentações/erros). */
	let liveMessage = $state<string>('');

	/**
	 * Id do card-fonte que deve COLAPSAR (classe `is-dragging`). CRÍTICO: o legado
	 * (`board-dnd.js`) só adiciona `is-dragging` num `setTimeout(0)` DEPOIS do
	 * `dragstart`. Colapsar o elemento-fonte (height:0/opacity:0) de forma síncrona
	 * DENTRO do `dragstart` CANCELA o drag nativo no Chrome/Firefox (o nó que
	 * iniciou o gesto desaparece). Por isso o colapso é deferido e mora num estado
	 * separado do `dragContext` (que é síncrono e dirige a lógica de drop).
	 */
	let collapsedId = $state<number | null>(null);
	let collapseTimer: ReturnType<typeof setTimeout> | null = null;

	/**
	 * Card que acabou de aterrissar — recebe a animação de assentamento
	 * `is-drop-settling` (paridade `triggerDropSettle` do board-dnd.js, 0.28s
	 * ease). Limpo após a animação para não re-disparar em futuros renders.
	 */
	let settledId = $state<number | null>(null);
	let settleTimer: ReturnType<typeof setTimeout> | null = null;

	function markSettled(cardId: number): void {
		if (typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) {
			return;
		}
		if (settleTimer) clearTimeout(settleTimer);
		settledId = cardId;
		settleTimer = setTimeout(() => {
			settledId = null;
			settleTimer = null;
		}, 320);
	}

	const columns = $derived($store.columns);
	const boardError = $derived($store.error);

	const colNaoIniciada = $derived(columns.find((c) => c.status === 'nao_iniciada'));
	const colEmAndamento = $derived(columns.find((c) => c.status === 'em_andamento'));
	const colValidacao = $derived(columns.find((c) => c.status === 'para_validacao'));
	const colAjustes = $derived(columns.find((c) => c.status === 'para_ajustes'));
	const colFinalizada = $derived(columns.find((c) => c.status === 'finalizada'));

	/** Leitura reativa do estado de drag de uma zona (evita prop por status). */
	function zoneView(status: TaskStatus): KanbanZoneView {
		return {
			canDrop: canDropOn(status),
			isOver: overStatus === status,
			placeholderIndex: overStatus === status ? overIndex : null
		};
	}

	/**
	 * UX-only: a coluna `target` aceita o card em drag? Sempre `true` quando não
	 * há drag. Reflete `canItemMoveToStatus` do util puro (regra portada do JS).
	 */
	function canDropOn(target: TaskStatus): boolean {
		if (!dragContext) return true;
		return canItemMoveToStatus(dragContext.card, target, dragContext.fromStatus);
	}

	/**
	 * Calcula o índice de inserção numa dropzone a partir do ponteiro Y
	 * (espelha `getDragAfterElement` do board-dnd.js): conta os cards visíveis
	 * acima do meio do card sob o cursor.
	 */
	function dropIndex(zone: HTMLElement, clientY: number): number {
		const cards = Array.from(
			zone.querySelectorAll<HTMLElement>('[data-item-id]')
		).filter((el) => el.getAttribute('data-item-id') !== String(dragContext?.card.id));
		let index = 0;
		for (const child of cards) {
			const box = child.getBoundingClientRect();
			if (clientY > box.top + box.height / 2) index += 1;
		}
		return index;
	}

	function onCardDragStart(event: DragEvent, card: BoardCard, fromStatus: TaskStatus): void {
		dragContext = { card, fromStatus };
		// Mede o card-fonte ANTES do colapso: o placeholder abre um vão do mesmo
		// tamanho na coluna alvo (preview fiel do espaço que o card ocupará).
		dragCardHeight = (event.currentTarget as HTMLElement | null)?.offsetHeight ?? null;
		if (event.dataTransfer) {
			event.dataTransfer.effectAllowed = 'move';
			event.dataTransfer.setData('text/plain', String(card.id));
		}
		// Colapsa o card-fonte SÓ no próximo tick (paridade `setTimeout(0)` do
		// board-dnd.js). Fazê-lo síncrono aqui abortaria o drag nativo.
		if (collapseTimer) clearTimeout(collapseTimer);
		collapseTimer = setTimeout(() => {
			if (dragContext?.card.id === card.id) collapsedId = card.id;
			collapseTimer = null;
		}, 0);
	}

	function onCardDragEnd(): void {
		if (collapseTimer) {
			clearTimeout(collapseTimer);
			collapseTimer = null;
		}
		dragContext = null;
		overStatus = null;
		overIndex = null;
		dragCardHeight = null;
		collapsedId = null;
	}

	function onZoneDragEnter(event: DragEvent, status: TaskStatus): void {
		if (!dragContext) return;
		if (!canDropOn(status)) return;
		event.preventDefault();
		overStatus = status;
	}

	function onZoneDragOver(event: DragEvent, status: TaskStatus): void {
		if (!dragContext) return;
		if (!canDropOn(status)) {
			// Drop inválido: não chamamos preventDefault -> o browser bloqueia o drop.
			if (event.dataTransfer) event.dataTransfer.dropEffect = 'none';
			return;
		}
		event.preventDefault();
		if (event.dataTransfer) event.dataTransfer.dropEffect = 'move';
		overStatus = status;
		// Recalcula o índice de inserção sob o ponteiro (dirige o placeholder).
		const index = dropIndex(event.currentTarget as HTMLElement, event.clientY);
		if (index !== overIndex) overIndex = index;
	}

	function onZoneDragLeave(event: DragEvent, status: TaskStatus): void {
		const zone = event.currentTarget as HTMLElement;
		const related = event.relatedTarget as Node | null;
		if (related && zone.contains(related)) return;
		if (overStatus === status) {
			overStatus = null;
			overIndex = null;
		}
	}

	async function onZoneDrop(event: DragEvent, status: TaskStatus): Promise<void> {
		if (!dragContext) return;
		event.preventDefault();
		const ctx = dragContext;
		const zone = event.currentTarget as HTMLElement;
		const index = dropIndex(zone, event.clientY);
		// Origem da celebração = ponto do drop (paridade com celebrationOrigin do
		// card no legado): a chuva de confete nasce onde a tarefa foi solta.
		const dropOrigin = { x: event.clientX, y: event.clientY };
		if (collapseTimer) {
			clearTimeout(collapseTimer);
			collapseTimer = null;
		}
		dragContext = null;
		overStatus = null;
		overIndex = null;
		dragCardHeight = null;
		collapsedId = null;

		if (!canItemMoveToStatus(ctx.card, status, ctx.fromStatus)) {
			liveMessage = 'Sem permissão para finalizar esta tarefa.';
			return;
		}

		const ok = await commitMove(ctx.card, ctx.fromStatus, status, index);
		if (ok) markSettled(ctx.card.id);
		// CONFETE: só quando o servidor confirma a transição p/ "finalizada" vinda
		// de um status ativo (espelha shouldCelebrateFinalize do legado).
		if (
			ok &&
			normalizeStatus(status) === 'finalizada' &&
			normalizeStatus(ctx.fromStatus) !== 'finalizada'
		) {
			celebrateFinalize?.(dropOrigin);
		}
	}

	/**
	 * Persiste um movimento via store. Mesma chamada usada pelo DnD e pelo menu
	 * de teclado: reordena dentro da coluna ou move entre colunas.
	 */
	async function commitMove(
		card: BoardCard,
		fromStatus: TaskStatus,
		toStatus: TaskStatus,
		index: number
	): Promise<boolean> {
		if (fromStatus === toStatus) {
			const column = columns.find((c) => c.status === toStatus);
			if (!column) return false;
			const ids = column.tasks.map((task) => task.id).filter((id) => id !== card.id);
			const clamped = Math.max(0, Math.min(index, ids.length));
			ids.splice(clamped, 0, card.id);
			const ok = await store.reorder(toStatus, ids);
			liveMessage = ok
				? `Tarefa reordenada em ${STATUS_LABELS[toStatus]}.`
				: $store.error || 'Não foi possível reordenar a tarefa.';
			return ok;
		}

		const ok = await store.moveCard(card.id, fromStatus, toStatus, index);
		liveMessage = ok
			? `Tarefa movida para ${STATUS_LABELS[toStatus]}.`
			: $store.error || 'Não foi possível mover a tarefa.';
		return ok;
	}

	/**
	 * Próximo status válido a partir de `fromStatus` na direção dada
	 * (`+1` = direita/avançar, `-1` = esquerda/voltar), pulando alvos que
	 * `canItemMoveToStatus` reprova (ex.: finalizar sem permissão). Retorna
	 * `null` quando não há coluna válida naquela direção (extremo do board).
	 */
	function adjacentStatus(
		card: BoardCard,
		fromStatus: TaskStatus,
		direction: 1 | -1
	): TaskStatus | null {
		const start = TASK_STATUS_ORDER.indexOf(fromStatus);
		if (start === -1) return null;
		for (let i = start + direction; i >= 0 && i < TASK_STATUS_ORDER.length; i += direction) {
			const candidate = TASK_STATUS_ORDER[i];
			if (canItemMoveToStatus(card, candidate, fromStatus)) return candidate;
		}
		return null;
	}

	/**
	 * Move o card para o fim da coluna alvo (alvo já validado pelo chamador).
	 * `origin` (elemento do card focado) origina o confete na sua posição quando
	 * o teclado finaliza a tarefa — alternativa acessível ao DnD.
	 */
	async function moveToColumnEnd(
		card: BoardCard,
		fromStatus: TaskStatus,
		toStatus: TaskStatus,
		origin?: Element | null
	): Promise<void> {
		if (fromStatus === toStatus) return;
		const target = columns.find((c) => c.status === toStatus);
		const ok = await commitMove(card, fromStatus, toStatus, target ? target.tasks.length : 0);
		if (
			ok &&
			normalizeStatus(toStatus) === 'finalizada' &&
			normalizeStatus(fromStatus) !== 'finalizada'
		) {
			celebrateFinalize?.(origin ?? undefined);
		}
	}

	/**
	 * Teclado no card focado (alternativa ao DnD): setas ←/→ movem para a coluna
	 * anterior/seguinte válida; Home/End para a primeira/última coluna válida.
	 * Quando não há alvo válido naquela direção, anuncia o motivo sem mover.
	 */
	async function onCardKeydown(
		event: KeyboardEvent,
		card: BoardCard,
		fromStatus: TaskStatus
	): Promise<void> {
		let direction: 1 | -1;
		if (event.key === 'ArrowRight' || event.key === 'End') direction = 1;
		else if (event.key === 'ArrowLeft' || event.key === 'Home') direction = -1;
		else return;

		event.preventDefault();
		// O card focado é a origem visual da celebração quando o teclado finaliza.
		const cardEl = event.currentTarget as Element | null;

		if (event.key === 'Home' || event.key === 'End') {
			const edge = direction === 1 ? TASK_STATUS_ORDER.length - 1 : 0;
			const target = TASK_STATUS_ORDER[edge];
			if (target !== fromStatus && canItemMoveToStatus(card, target, fromStatus)) {
				await moveToColumnEnd(card, fromStatus, target, cardEl);
			} else {
				liveMessage = 'Sem permissão para finalizar esta tarefa.';
			}
			return;
		}

		const next = adjacentStatus(card, fromStatus, direction);
		if (!next) {
			liveMessage =
				direction === 1
					? 'Não é possível avançar esta tarefa.'
					: 'Esta tarefa já está na primeira coluna.';
			return;
		}
		await moveToColumnEnd(card, fromStatus, next, cardEl);
	}
</script>

<div class="flex flex-col gap-3">
	{#if boardError}
		<p role="alert" class="rounded-md border border-danger bg-surface px-4 py-2 text-sm text-danger">
			{boardError}
		</p>
	{/if}

	<!-- Anuncia movimentações/erros para leitores de tela. -->
	<p class="sr-only" role="status" aria-live="polite">{liveMessage}</p>

	<!-- Altura travada na viewport: a página não rola — cada coluna rola por
	     dentro. 10.5rem = topnav + header compacto + paddings. -->
	<div
		class="kanban-board flex min-h-[420px] h-[calc(100vh-10.5rem)] max-h-[calc(100vh-10.5rem)] w-full items-stretch gap-[0.62rem] overflow-x-auto pb-2"
		role="group"
		aria-label="Quadro Kanban de tarefas"
	>
		{#if colNaoIniciada && colEmAndamento && colValidacao && colAjustes && colFinalizada}
			<!-- Composer só em "Não iniciada": toda tarefa nasce ali. -->
			{#each [colNaoIniciada, colEmAndamento, colValidacao, colAjustes] as column (column.status)}
				<KanbanColumn
					{column}
					composer={column.status === 'nao_iniciada' ? composer : undefined}
					{zoneView}
					draggingId={collapsedId}
					{settledId}
					placeholderHeight={dragCardHeight}
					{onCardDragStart}
					{onCardDragEnd}
					{onZoneDragEnter}
					{onZoneDragOver}
					{onZoneDragLeave}
					{onZoneDrop}
					{onCardKeydown}
				/>
			{/each}
			<KanbanDoneColumn
				column={colFinalizada}
				{zoneView}
				draggingId={collapsedId}
				{settledId}
				placeholderHeight={dragCardHeight}
				{onCardDragStart}
				{onCardDragEnd}
				{onZoneDragEnter}
				{onZoneDragOver}
				{onZoneDragLeave}
				{onZoneDrop}
				{onCardKeydown}
			/>
		{/if}
	</div>
</div>
