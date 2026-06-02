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
	import type { Snippet } from 'svelte';
	import KanbanCard from '$lib/components/KanbanCard.svelte';
	import type { BoardCard, BoardColumn } from '$lib/types/board';
	import type { TaskStatus } from '$lib/utils/taskStatus';

	interface Props {
		column: BoardColumn;
		/** Composer inline opcional, renderizado no rodapé da coluna (Fase 5b-3). */
		composer?: Snippet<[TaskStatus]>;
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
		composer,
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

	/**
	 * Tinta de cabeçalho por status (paridade com kanban.css
	 * `.task-items-kanban-column.status-* .task-items-kanban-col-head`). Usa
	 * tokens semânticos suaves (light-bg) para trocar sozinho no dark mode.
	 */
	const HEAD_TINT: Record<string, string> = {
		nao_iniciada: 'border-border-subtle bg-surface-muted',
		em_andamento: 'border-info/30 bg-info/10',
		para_validacao: 'border-warning/40 bg-warning/10',
		para_ajustes: 'border-danger/30 bg-danger/10',
		finalizada: 'border-success/30 bg-success/10'
	};
	const headTint = $derived(HEAD_TINT[column.status] ?? HEAD_TINT.nao_iniciada);
</script>

<!--
	Coluna do Kanban — fidelidade a static/css/tasks/detail/kanban.css:
	  radius 12px (rounded-lg), borda + sombra 0 6px 16px, cabeçalho com tinta
	  por status, contador em pílula. A dropzone reproduz `.is-drag-over`
	  (fundo tintado + ring interno) e `.is-column-drag-target` (borda + ring),
	  com transição 0.16s ease (~duration-fast).
-->
<section
	class="kanban-column flex min-h-[340px] min-w-[200px] flex-1 flex-col overflow-hidden rounded-lg border border-border-subtle bg-canvas shadow-md transition-shadow duration-fast {isOver &&
	canDrop
		? 'is-column-drag-target border-primary-500'
		: ''}"
	aria-labelledby={`kanban-col-${column.status}`}
>
	<header
		class="flex items-center justify-between gap-2 rounded-t-lg border-b px-3 py-2.5 {headTint}"
	>
		<h2
			id={`kanban-col-${column.status}`}
			class="font-heading text-sm font-bold text-text-primary"
		>
			{column.label}
		</h2>
		<span
			class="inline-flex h-[22px] min-w-[24px] items-center justify-center rounded-full border border-border-subtle bg-surface px-1.5 text-xs font-semibold text-text-secondary"
		>
			{count}
		</span>
	</header>

	<ul
		class="flex min-h-[6rem] flex-1 flex-col gap-2 overflow-y-auto p-2 transition-[background-color,box-shadow] duration-fast {isOver &&
		canDrop
			? 'bg-primary-100/50 shadow-[inset_0_0_0_1px_var(--ds-color-primary-500)]'
			: ''} {isOver && !canDrop ? 'cursor-not-allowed opacity-70' : ''}"
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
			<li class="flex min-h-[40px] flex-1 items-center justify-center rounded-lg border border-dashed border-border-subtle bg-surface/80 px-3 py-3 text-center text-xs text-text-muted">
				Sem itens nesta etapa
			</li>
		{/each}
	</ul>

	{#if composer}
		<div class="px-[0.56rem] pb-[0.62rem] pt-[0.46rem]">
			{@render composer(column.status)}
		</div>
	{/if}
</section>

<style>
	/* `.is-column-drag-target` (kanban.css): ring duplo de realce da coluna alvo,
	   reproduzindo box-shadow: 0 0 0 2px rgba(139,176,215,.25), 0 6px 16px ... */
	.is-column-drag-target {
		box-shadow:
			0 0 0 2px rgba(31, 115, 181, 0.25),
			0 6px 16px rgba(19, 63, 101, 0.12);
	}
</style>
