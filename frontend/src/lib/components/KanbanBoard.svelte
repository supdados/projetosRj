<script lang="ts">
	/**
	 * Board do Kanban de Tarefas (Fase 5b-1): 5 colunas na ordem canônica, com
	 * DnD nativo HTML5 (espelha `static/js/modules/kanban/board-dnd.js`).
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
	import type { Snippet } from 'svelte';
	import KanbanColumn from '$lib/components/KanbanColumn.svelte';
	import type { BoardStore } from '$lib/stores/board';
	import type { BoardCard } from '$lib/types/board';
	import {
		STATUS_LABELS,
		TASK_STATUS_ORDER,
		canItemMoveToStatus,
		type TaskStatus
	} from '$lib/utils/taskStatus';

	interface Props {
		store: BoardStore;
		/** Composer inline por coluna (Fase 5b-3), repassado para cada KanbanColumn. */
		composer?: Snippet<[TaskStatus]>;
	}

	let { store, composer }: Props = $props();

	/** Contexto do drag em curso (estado canônico no componente, não no DOM). */
	interface DragContext {
		card: BoardCard;
		fromStatus: TaskStatus;
	}

	let dragContext = $state<DragContext | null>(null);
	let overStatus = $state<TaskStatus | null>(null);
	/** Mensagem para leitores de tela (movimentações/erros). */
	let liveMessage = $state<string>('');

	const columns = $derived($store.columns);
	const boardError = $derived($store.error);

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
		if (event.dataTransfer) {
			event.dataTransfer.effectAllowed = 'move';
			event.dataTransfer.setData('text/plain', String(card.id));
		}
	}

	function onCardDragEnd(): void {
		dragContext = null;
		overStatus = null;
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
	}

	function onZoneDragLeave(event: DragEvent, status: TaskStatus): void {
		const zone = event.currentTarget as HTMLElement;
		const related = event.relatedTarget as Node | null;
		if (related && zone.contains(related)) return;
		if (overStatus === status) overStatus = null;
	}

	async function onZoneDrop(event: DragEvent, status: TaskStatus): Promise<void> {
		if (!dragContext) return;
		event.preventDefault();
		const ctx = dragContext;
		const zone = event.currentTarget as HTMLElement;
		const index = dropIndex(zone, event.clientY);
		dragContext = null;
		overStatus = null;

		if (!canItemMoveToStatus(ctx.card, status, ctx.fromStatus)) {
			liveMessage = 'Sem permissão para finalizar esta tarefa.';
			return;
		}

		await commitMove(ctx.card, ctx.fromStatus, status, index);
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
	): Promise<void> {
		if (fromStatus === toStatus) {
			const column = columns.find((c) => c.status === toStatus);
			if (!column) return;
			const ids = column.tasks.map((task) => task.id).filter((id) => id !== card.id);
			const clamped = Math.max(0, Math.min(index, ids.length));
			ids.splice(clamped, 0, card.id);
			const ok = await store.reorder(toStatus, ids);
			liveMessage = ok
				? `Tarefa reordenada em ${STATUS_LABELS[toStatus]}.`
				: $store.error || 'Não foi possível reordenar a tarefa.';
			return;
		}

		const ok = await store.moveCard(card.id, fromStatus, toStatus, index);
		liveMessage = ok
			? `Tarefa movida para ${STATUS_LABELS[toStatus]}.`
			: $store.error || 'Não foi possível mover a tarefa.';
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

	/** Move o card para o fim da coluna alvo (alvo já validado pelo chamador). */
	async function moveToColumnEnd(
		card: BoardCard,
		fromStatus: TaskStatus,
		toStatus: TaskStatus
	): Promise<void> {
		if (fromStatus === toStatus) return;
		const target = columns.find((c) => c.status === toStatus);
		await commitMove(card, fromStatus, toStatus, target ? target.tasks.length : 0);
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

		if (event.key === 'Home' || event.key === 'End') {
			const edge = direction === 1 ? TASK_STATUS_ORDER.length - 1 : 0;
			const target = TASK_STATUS_ORDER[edge];
			if (target !== fromStatus && canItemMoveToStatus(card, target, fromStatus)) {
				await moveToColumnEnd(card, fromStatus, target);
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
		await moveToColumnEnd(card, fromStatus, next);
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

	<div
		class="flex w-full gap-3 overflow-x-auto pb-2"
		role="group"
		aria-label="Quadro Kanban de tarefas"
	>
		{#each TASK_STATUS_ORDER as status (status)}
			{@const column = columns.find((c) => c.status === status)}
			{#if column}
				<div class="flex flex-1 flex-col gap-2">
					<KanbanColumn
						{column}
						{composer}
						draggingId={dragContext?.card.id ?? null}
						canDrop={canDropOn(status)}
						isOver={overStatus === status}
						{onCardDragStart}
						{onCardDragEnd}
						{onZoneDragEnter}
						{onZoneDragOver}
						{onZoneDragLeave}
						{onZoneDrop}
						{onCardKeydown}
					/>
				</div>
			{/if}
		{/each}
	</div>
</div>
