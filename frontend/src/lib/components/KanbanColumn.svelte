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
	Coluna (Variação B) — SEM caixa: as colunas flutuam direto no canvas e o
	cabeçalho vira uma FAIXA tingida por status (referência: cinza / azul /
	amarelo / vermelho / verde) com o contador em texto na mesma cor (opacidade
	reduzida), sem pílula. As tintas usam color-mix sobre as vars semânticas
	(dark-safe); o Tailwind 3 não gera `bg-info/10` para cores via var sem
	<alpha-value>.
-->
<section
	class="kanban-column kcol--{column.status} flex h-full min-h-0 min-w-[200px] flex-1 flex-col rounded-xl [contain:layout] transition-[box-shadow] duration-fast {isOver &&
	canDrop
		? 'is-column-drag-target'
		: ''}"
	aria-labelledby={`kanban-col-${column.status}`}
>
	<header class="kcol-head kcol-head--{column.status} flex shrink-0 items-center justify-between gap-2 rounded-[10px] px-3 py-2">
		<h2
			id={`kanban-col-${column.status}`}
			class="font-heading truncate text-[0.8125rem] font-bold"
		>
			{column.label}
		</h2>
		<!-- {#key count}: remonta o contador a cada mudança p/ rodar o "pop". -->
		{#key count}
			<span
				class="kcol-count inline-flex items-center justify-center text-[0.7rem] font-bold tabular-nums opacity-70"
			>
				{count}
			</span>
		{/key}
	</header>

	<ul
		class="kanban-dropzone flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto overflow-x-hidden rounded-lg px-1.5 py-2 [contain:layout] transition-[background-color,box-shadow] duration-fast {isOver && canDrop
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
		<!-- "+ adicionar" no rodapé: a coluna estica até a altura do board
		     (items-stretch) e a dropzone ocupa o flex-1, então o composer fica
		     alinhado na MESMA linha em todas as colunas. -->
		<div class="shrink-0 px-1.5 pb-1.5 pt-1">
			{@render composer(column.status)}
		</div>
	{/if}
</section>

<style>
	/*
	 * Fundo da COLUNA: a mesma cor do status, bem diluída (overlay translúcido
	 * sobre o canvas — dark-safe). A faixa do cabeçalho usa a versão mais forte.
	 */
	.kcol--nao_iniciada {
		background-color: color-mix(in srgb, var(--color-text-muted) 5%, transparent);
	}
	.kcol--em_andamento {
		background-color: color-mix(in srgb, var(--ds-color-info-600) 5%, transparent);
	}
	.kcol--para_validacao {
		background-color: color-mix(in srgb, var(--ds-color-warning-600) 6%, transparent);
	}
	.kcol--para_ajustes {
		background-color: color-mix(in srgb, var(--ds-color-danger-600) 4%, transparent);
	}
	.kcol--finalizada {
		background-color: color-mix(in srgb, var(--ds-color-success-600) 5%, transparent);
	}

	/*
	 * Faixa do cabeçalho por status (Variação B): fundo tingido e TEXTO na
	 * cor do status (título e contador herdam via color), sem borda nem caixa
	 * na coluna. Mistura sobre as vars semânticas — dark-safe.
	 */
	.kcol-head--nao_iniciada {
		background-color: color-mix(in srgb, var(--color-text-muted) 12%, var(--color-surface));
		color: var(--color-text-secondary);
	}
	.kcol-head--em_andamento {
		background-color: color-mix(in srgb, var(--ds-color-info-600) 14%, var(--color-surface));
		color: color-mix(in srgb, var(--ds-color-info-600) 62%, var(--color-text-primary));
	}
	.kcol-head--para_validacao {
		background-color: color-mix(in srgb, var(--ds-color-warning-600) 16%, var(--color-surface));
		color: color-mix(in srgb, var(--ds-color-warning-600) 62%, var(--color-text-primary));
	}
	.kcol-head--para_ajustes {
		background-color: color-mix(in srgb, var(--ds-color-danger-600) 12%, var(--color-surface));
		color: color-mix(in srgb, var(--ds-color-danger-600) 62%, var(--color-text-primary));
	}
	.kcol-head--finalizada {
		background-color: color-mix(in srgb, var(--ds-color-success-600) 12%, var(--color-surface));
		color: color-mix(in srgb, var(--ds-color-success-600) 62%, var(--color-text-primary));
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

	/* Scroll interno da coluna: barra de 1px, quase invisível; cada coluna rola
	 * por dentro. CUIDADO (armadilhas reais, ver css-scrollbars §3.1):
	 *   1. `.app-shell > main` (app.css) define scrollbar-color, e scrollbar-color
	 *      é propriedade HERDADA — ela desce até esta dropzone. Com o valor
	 *      computado ≠ auto, o Chromium 121+ IGNORA todos os ::-webkit-scrollbar*
	 *      do elemento e desenha a barra padrão (a azulada grossa). O reset
	 *      `auto` abaixo devolve o controle aos pseudo-elementos de 1px.
	 *   2. `@supports selector(::-webkit-scrollbar)` é TRUE também no Firefox
	 *      (pseudo-elementos -webkit- desconhecidos parseiam por compat), então
	 *      não serve para separar engines — o gate correto é `-moz-appearance`,
	 *      que só o Firefox suporta (lá o mínimo nativo é `thin`). */
	.kanban-dropzone {
		scrollbar-width: auto;
		scrollbar-color: auto;
	}
	@supports (-moz-appearance: none) {
		.kanban-dropzone {
			scrollbar-width: thin;
			scrollbar-color: rgba(92, 126, 157, 0.32) transparent;
		}
	}
	.kanban-dropzone::-webkit-scrollbar {
		width: 5px;
	}
	.kanban-dropzone::-webkit-scrollbar-track {
		background: transparent;
	}
	.kanban-dropzone::-webkit-scrollbar-thumb {
		background: rgba(92, 126, 157, 0.45);
		border-radius: 999px;
		min-height: 32px;
	}
	.kanban-dropzone::-webkit-scrollbar-thumb:hover {
		background: rgba(70, 103, 133, 0.7);
	}

	@media (prefers-reduced-motion: reduce) {
		.kcol-count,
		.kanban-placeholder {
			animation: none;
		}
	}
</style>
