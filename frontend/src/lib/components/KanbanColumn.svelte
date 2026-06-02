<script lang="ts">
	/**
	 * Coluna do Kanban (Fase 5b-1): um status + seus cards, atuando como dropzone.
	 *
	 * A coluna NÃO guarda estado próprio — recebe `column` (status/label/tasks) da
	 * store e os callbacks de DnD do `KanbanBoard`. O feedback visual de drop
	 * (`canDrop`/`isOver`) é controlado pelo board, que decide via
	 * `canItemMoveToStatus` (util puro) se o drop é válido; aqui só refletimos.
	 *
	 * Acessibilidade: a dropzone é uma lista (`<ul>`); cards arrastáveis são os
	 * itens. O board mantém um aria-live para anunciar movimentações.
	 */
	import KanbanCard from '$lib/components/KanbanCard.svelte';
	import type { BoardCard, BoardColumn } from '$lib/types/board';
	import type { TaskStatus } from '$lib/utils/taskStatus';

	interface Props {
		column: BoardColumn;
		/** Id do card sendo arrastado no momento (para feedback no card). */
		draggingId?: number | null;
		/** A coluna é alvo válido para o drag em curso? (define cursor/realce). */
		canDrop?: boolean;
		/** Há um drag em andamento sobre esta coluna? */
		isOver?: boolean;
		onCardDragStart?: (event: DragEvent, card: BoardCard, status: TaskStatus) => void;
		onCardDragEnd?: (event: DragEvent) => void;
		onZoneDragEnter?: (event: DragEvent, status: TaskStatus) => void;
		onZoneDragOver?: (event: DragEvent, status: TaskStatus) => void;
		onZoneDragLeave?: (event: DragEvent, status: TaskStatus) => void;
		onZoneDrop?: (event: DragEvent, status: TaskStatus) => void;
		/** Teclado no card focado: mover entre colunas (alternativa ao DnD). */
		onCardKeydown?: (event: KeyboardEvent, card: BoardCard, status: TaskStatus) => void;
	}

	let {
		column,
		draggingId = null,
		canDrop = true,
		isOver = false,
		onCardDragStart,
		onCardDragEnd,
		onZoneDragEnter,
		onZoneDragOver,
		onZoneDragLeave,
		onZoneDrop,
		onCardKeydown
	}: Props = $props();

	const count = $derived(column.tasks.length);
</script>

<section
	class="flex min-w-[16rem] flex-1 flex-col rounded-lg border border-border-subtle bg-surface-muted"
	aria-labelledby={`kanban-col-${column.status}`}
>
	<header class="flex items-center justify-between gap-2 border-b border-border-subtle px-3 py-2">
		<h2
			id={`kanban-col-${column.status}`}
			class="font-heading text-sm font-semibold text-text-primary"
		>
			{column.label}
		</h2>
		<span
			class="inline-flex min-w-[1.5rem] items-center justify-center rounded-sm bg-surface px-1.5 py-0.5 text-xs font-medium text-text-secondary"
		>
			{count}
		</span>
	</header>

	<ul
		class="flex min-h-[6rem] flex-1 flex-col gap-2 p-2 transition-colors duration-fast {isOver &&
		canDrop
			? 'bg-primary-100/60 outline outline-2 outline-primary-500'
			: ''} {isOver && !canDrop ? 'cursor-not-allowed bg-surface-muted opacity-70' : ''}"
		data-status={column.status}
		aria-label={`Coluna ${column.label}`}
		ondragenter={(event) => onZoneDragEnter?.(event, column.status)}
		ondragover={(event) => onZoneDragOver?.(event, column.status)}
		ondragleave={(event) => onZoneDragLeave?.(event, column.status)}
		ondrop={(event) => onZoneDrop?.(event, column.status)}
	>
		{#each column.tasks as card, index (card.id)}
			<li>
				<KanbanCard
					{card}
					dragging={draggingId === card.id}
					columnLabel={column.label}
					position={index + 1}
					setSize={count}
					ondragstart={(event) => onCardDragStart?.(event, card, column.status)}
					ondragend={(event) => onCardDragEnd?.(event)}
					onkeydown={(event) => onCardKeydown?.(event, card, column.status)}
				/>
			</li>
		{:else}
			<li class="rounded-md border border-dashed border-border-subtle px-3 py-4 text-center text-xs text-text-muted">
				Sem tarefas
			</li>
		{/each}
	</ul>
</section>
