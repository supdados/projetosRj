<script lang="ts">
	/**
	 * Coluna do Kanban: um status + seus cards, atuando como dropzone.
	 *
	 * A coluna NÃO guarda estado próprio — recebe `column` (status/label/tasks) da
	 * store e os callbacks de DnD do `KanbanBoard`. O feedback visual de drop
	 * (`canDrop`/`isOver`) é controlado pelo board, que decide via
	 * `canItemMoveToStatus` (util puro) se o drop é válido; aqui só refletimos.
	 *
	 * PLACEHOLDER DE INSERÇÃO: durante o drag, o board informa `placeholderIndex`
	 * (posição de inserção entre os cards VISÍVEIS, i.e. excluindo o card-fonte
	 * colapsado) e `placeholderHeight` (altura do card arrastado). A coluna abre
	 * um "vão" tracejado naquela posição — preview exato de onde o card cairá.
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
		/** Composer inline opcional, renderizado no rodapé da coluna. */
		composer?: Snippet<[TaskStatus]>;
		/** Id do card sendo arrastado no momento (para feedback no card). */
		draggingId?: number | null;
		/** Id do card que acabou de aterrissar (animação `is-drop-settling`). */
		settledId?: number | null;
		/** A coluna é alvo válido para o drag em curso? (define cursor/realce). */
		canDrop?: boolean;
		/** Há um drag em andamento sobre esta coluna? */
		isOver?: boolean;
		/** Índice de inserção do placeholder (entre os cards visíveis) ou `null`. */
		placeholderIndex?: number | null;
		/** Altura (px) do card arrastado, para o vão do placeholder. */
		placeholderHeight?: number | null;
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
		settledId = null,
		canDrop = true,
		isOver = false,
		placeholderIndex = null,
		placeholderHeight = null,
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
	 * Resolve o placeholder para um ALVO ESTÁVEL: o id do card visível diante do
	 * qual o vão abre (`-1` = fim da lista). `placeholderIndex` conta apenas os
	 * cards visíveis (o card-fonte colapsado fica fora), enquanto o `{#each}`
	 * itera TODOS — comparar por id evita o off-by-one na coluna de origem.
	 */
	const placeholderBeforeId = $derived.by(() => {
		if (placeholderIndex === null || !isOver || !canDrop) return null;
		const visible = column.tasks.filter((task) => task.id !== draggingId);
		if (placeholderIndex >= visible.length) return -1;
		return visible[placeholderIndex].id;
	});

	const showEmptyHint = $derived(count === 0 && placeholderBeforeId === null);

	/** Altura do vão do placeholder (fallback ~ card de uma linha). */
	const gapHeight = $derived(placeholderHeight && placeholderHeight > 0 ? placeholderHeight : 72);
</script>

<!--
	Coluna — painel levemente azulado sobre o canvas, cabeçalho com tinta por
	status (referência: cinza / azul / amarelo / vermelho / verde) e contador em
	pílula branca. As tintas usam color-mix sobre as vars semânticas (dark-safe);
	o Tailwind 3 não gera `bg-info/10` para cores via var sem <alpha-value>.
-->
<section
	class="kanban-column kcol flex h-full min-h-0 min-w-[200px] flex-1 flex-col overflow-hidden rounded-lg border border-border-subtle transition-[box-shadow,border-color] duration-fast {isOver &&
	canDrop
		? 'is-column-drag-target border-primary-500'
		: ''}"
	aria-labelledby={`kanban-col-${column.status}`}
>
	<header class="kcol-head kcol-head--{column.status} flex shrink-0 items-center justify-between gap-2 border-b px-3 py-2.5">
		<h2
			id={`kanban-col-${column.status}`}
			class="font-heading truncate text-sm font-bold text-text-primary"
		>
			{column.label}
		</h2>
		<!-- {#key count}: remonta a pílula a cada mudança p/ rodar o "pop". -->
		{#key count}
			<span
				class="kcol-count inline-flex h-[24px] min-w-[26px] items-center justify-center rounded-full border border-border-subtle bg-surface px-1.5 text-xs font-bold tabular-nums text-text-secondary shadow-sm"
			>
				{count}
			</span>
		{/key}
	</header>

	<ul
		class="kanban-dropzone flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto overflow-x-hidden p-2 transition-[background-color,box-shadow] duration-fast {isOver && canDrop
			? 'is-zone-over'
			: ''} {isOver && !canDrop ? 'cursor-not-allowed opacity-60' : ''}"
		data-status={column.status}
		aria-label={`Coluna ${column.label}`}
		ondragenter={(event) => onZoneDragEnter?.(event, column.status)}
		ondragover={(event) => onZoneDragOver?.(event, column.status)}
		ondragleave={(event) => onZoneDragLeave?.(event, column.status)}
		ondrop={(event) => onZoneDrop?.(event, column.status)}
	>
		{#each column.tasks as card, index (card.id)}
			{#if placeholderBeforeId === card.id}
				<li aria-hidden="true" class="kanban-placeholder" style:height={`${gapHeight}px`}></li>
			{/if}
			<li>
				<KanbanCard
					{card}
					dragging={draggingId === card.id}
					settled={settledId === card.id}
					columnLabel={column.label}
					position={index + 1}
					setSize={count}
					ondragstart={(event) => onCardDragStart?.(event, card, column.status)}
					ondragend={(event) => onCardDragEnd?.(event)}
					onkeydown={(event) => onCardKeydown?.(event, card, column.status)}
				/>
			</li>
		{/each}

		{#if placeholderBeforeId === -1}
			<li aria-hidden="true" class="kanban-placeholder" style:height={`${gapHeight}px`}></li>
		{/if}

		{#if showEmptyHint}
			<li
				class="flex min-h-[40px] flex-1 items-center justify-center rounded-lg border border-dashed border-border-subtle px-3 py-3 text-center text-xs text-text-muted"
			>
				Sem itens nesta etapa
			</li>
		{/if}
	</ul>

	{#if composer}
		<div class="shrink-0 border-t border-border-subtle px-[0.56rem] pb-[0.62rem] pt-[0.46rem]">
			{@render composer(column.status)}
		</div>
	{/if}
</section>

<style>
	/* Painel da coluna: um passo abaixo do canvas, para os cards brancos saltarem. */
	.kcol {
		background-color: color-mix(in srgb, var(--ds-color-primary-600) 4%, var(--color-canvas));
		box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
	}

	/* Tinta do cabeçalho por status (referência visual do board). */
	.kcol-head {
		border-bottom-color: var(--color-border);
	}
	.kcol-head--nao_iniciada {
		background-color: color-mix(in srgb, var(--color-text-muted) 10%, var(--color-surface));
	}
	.kcol-head--em_andamento {
		background-color: color-mix(in srgb, var(--ds-color-info-600) 14%, var(--color-surface));
		border-bottom-color: color-mix(in srgb, var(--ds-color-info-600) 28%, transparent);
	}
	.kcol-head--para_validacao {
		background-color: color-mix(in srgb, var(--ds-color-warning-600) 16%, var(--color-surface));
		border-bottom-color: color-mix(in srgb, var(--ds-color-warning-600) 30%, transparent);
	}
	.kcol-head--para_ajustes {
		background-color: color-mix(in srgb, var(--ds-color-danger-600) 12%, var(--color-surface));
		border-bottom-color: color-mix(in srgb, var(--ds-color-danger-600) 26%, transparent);
	}
	.kcol-head--finalizada {
		background-color: color-mix(in srgb, var(--ds-color-success-600) 12%, var(--color-surface));
		border-bottom-color: color-mix(in srgb, var(--ds-color-success-600) 26%, transparent);
	}

	/* Pop da pílula de contagem quando o número muda (remontada via {#key}). */
	@keyframes kcol-count-pop {
		0% {
			transform: scale(1);
		}
		45% {
			transform: scale(1.18);
		}
		100% {
			transform: scale(1);
		}
	}
	.kcol-count {
		animation: kcol-count-pop 0.24s ease;
	}

	/* Dropzone realçada quando é alvo válido do drag em curso. */
	.is-zone-over {
		background-color: color-mix(in srgb, var(--ds-color-primary-500) 7%, transparent);
		box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--ds-color-primary-500) 45%, transparent);
	}

	/* `.is-column-drag-target`: ring duplo de realce da coluna alvo. */
	.is-column-drag-target {
		box-shadow:
			0 0 0 2px color-mix(in srgb, var(--ds-color-primary-500) 25%, transparent),
			0 6px 16px rgba(19, 63, 101, 0.12);
	}

	/* Vão de inserção: preview tracejado de onde o card aterrissará. */
	.kanban-placeholder {
		flex-shrink: 0;
		border-radius: 10px;
		border: 1.5px dashed color-mix(in srgb, var(--ds-color-primary-500) 45%, transparent);
		background-color: color-mix(in srgb, var(--ds-color-primary-500) 8%, transparent);
		pointer-events: none;
		animation: kanban-placeholder-in 0.14s ease;
	}
	@keyframes kanban-placeholder-in {
		from {
			opacity: 0;
			transform: scaleY(0.85);
		}
		to {
			opacity: 1;
			transform: scaleY(1);
		}
	}

	/* Scroll interno da coluna: barra fina; cada coluna rola por dentro. */
	.kanban-dropzone {
		scrollbar-width: thin;
		scrollbar-color: rgba(92, 126, 157, 0.54) transparent;
	}
	.kanban-dropzone::-webkit-scrollbar {
		width: 8px;
	}
	.kanban-dropzone::-webkit-scrollbar-track {
		background: transparent;
	}
	.kanban-dropzone::-webkit-scrollbar-thumb {
		background: rgba(92, 126, 157, 0.54);
		border-radius: 999px;
		border: 2px solid transparent;
		background-clip: padding-box;
		min-height: 40px;
	}
	.kanban-dropzone::-webkit-scrollbar-thumb:hover {
		background: rgba(70, 103, 133, 0.68);
		background-clip: padding-box;
	}

	@media (prefers-reduced-motion: reduce) {
		.kcol-count,
		.kanban-placeholder {
			animation: none;
		}
	}
</style>
