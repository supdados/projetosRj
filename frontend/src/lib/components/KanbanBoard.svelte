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
	 *   - cada card tem um botão "Mover" que abre um menu de status alvo
	 *     (alternativa de teclado ao drag-and-drop);
	 *   - um região `aria-live="polite"` anuncia as movimentações e erros.
	 */
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
	}

	let { store }: Props = $props();

	/** Contexto do drag em curso (estado canônico no componente, não no DOM). */
	interface DragContext {
		card: BoardCard;
		fromStatus: TaskStatus;
	}

	let dragContext = $state<DragContext | null>(null);
	let overStatus = $state<TaskStatus | null>(null);
	/** Mensagem para leitores de tela (movimentações/erros). */
	let liveMessage = $state<string>('');
	/** Card cujo menu de "mover por teclado" está aberto (id) ou null. */
	let keyboardMenuFor = $state<number | null>(null);

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
		keyboardMenuFor = null;
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

	/** Alternativa de teclado: move o card para o fim da coluna alvo. */
	async function moveByKeyboard(card: BoardCard, fromStatus: TaskStatus, toStatus: TaskStatus): Promise<void> {
		keyboardMenuFor = null;
		if (fromStatus === toStatus) return;
		const target = columns.find((c) => c.status === toStatus);
		await commitMove(card, fromStatus, toStatus, target ? target.tasks.length : 0);
	}

	function toggleKeyboardMenu(cardId: number): void {
		keyboardMenuFor = keyboardMenuFor === cardId ? null : cardId;
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
						draggingId={dragContext?.card.id ?? null}
						canDrop={canDropOn(status)}
						isOver={overStatus === status}
						{onCardDragStart}
						{onCardDragEnd}
						{onZoneDragEnter}
						{onZoneDragOver}
						{onZoneDragLeave}
						{onZoneDrop}
					/>

					<!-- Alternativa acessível ao DnD (teclado/clique): um controle por
					     card que abre um menu de status alvo. canItemMoveToStatus
					     desabilita alvos inválidos, espelhando a regra do drop. -->
					{#each column.tasks as card (card.id)}
						<div class="relative px-2">
							<button
								type="button"
								onclick={() => toggleKeyboardMenu(card.id)}
								aria-haspopup="menu"
								aria-expanded={keyboardMenuFor === card.id}
								class="w-full rounded-sm border border-border-subtle bg-surface px-2 py-1 text-left text-xs text-text-secondary transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
							>
								Mover: {card.descricao}
							</button>
							{#if keyboardMenuFor === card.id}
								<div
									class="absolute left-2 right-2 top-full z-10 mt-1 flex flex-col gap-1 rounded-md border border-border-subtle bg-surface p-2 shadow-md"
									role="menu"
									aria-label={`Mover "${card.descricao}" para`}
								>
									<p class="px-1 text-xs font-semibold text-text-muted">Mover para</p>
									{#each TASK_STATUS_ORDER as target (target)}
										{@const allowed = canItemMoveToStatus(card, target, status)}
										<button
											type="button"
											role="menuitem"
											disabled={target === status || !allowed}
											onclick={() => moveByKeyboard(card, status, target)}
											class="rounded-sm px-2 py-1 text-left text-sm text-text-primary transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:cursor-not-allowed disabled:opacity-50"
										>
											{STATUS_LABELS[target]}
										</button>
									{/each}
								</div>
							{/if}
						</div>
					{/each}
				</div>
			{/if}
		{/each}
	</div>
</div>
