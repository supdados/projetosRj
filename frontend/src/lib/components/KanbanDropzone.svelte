<script lang="ts">
	/**
	 * Zona de drop do Kanban: a lista de cards de UM status, com scroll interno,
	 * placeholder de inserção e dica de vazio. Sem estado próprio — recebe
	 * `tasks` da store e lê o estado de drag do board via `zoneView(status)`.
	 */
	import KanbanCard from '$lib/components/KanbanCard.svelte';
	import type { BoardCard } from '$lib/types/board';
	import type { KanbanDndProps } from '$lib/types/kanbanDnd';
	import type { TaskStatus } from '$lib/utils/taskStatus';

	interface Props extends KanbanDndProps {
		status: TaskStatus;
		/** Rótulo da zona para aria e para o aria-label dos cards. */
		label: string;
		tasks: BoardCard[];
	}

	let {
		status,
		label,
		tasks,
		zoneView,
		draggingId,
		settledId,
		placeholderHeight,
		onCardDragStart,
		onCardDragEnd,
		onZoneDragEnter,
		onZoneDragOver,
		onZoneDragLeave,
		onZoneDrop,
		onCardKeydown
	}: Props = $props();

	const view = $derived(zoneView(status));
	const count = $derived(tasks.length);

	/**
	 * Resolve o placeholder para um ALVO ESTÁVEL: o id do card visível diante do
	 * qual o vão abre (`-1` = fim da lista). `placeholderIndex` conta apenas os
	 * cards visíveis (o card-fonte colapsado fica fora), enquanto o `{#each}`
	 * itera TODOS — comparar por id evita o off-by-one na coluna de origem.
	 */
	const placeholderBeforeId = $derived.by(() => {
		if (view.placeholderIndex === null || !view.isOver || !view.canDrop) return null;
		const visible = tasks.filter((task) => task.id !== draggingId);
		if (view.placeholderIndex >= visible.length) return -1;
		return visible[view.placeholderIndex].id;
	});

	const showEmptyHint = $derived(count === 0 && placeholderBeforeId === null);

	/** Altura do vão do placeholder (fallback ~ card de uma linha). */
	const gapHeight = $derived(placeholderHeight && placeholderHeight > 0 ? placeholderHeight : 72);
</script>

<ul
	class="kanban-dropzone flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto overflow-x-hidden rounded-lg px-1 py-1 [contain:layout] transition-[opacity] duration-fast {view.isOver &&
	!view.canDrop
		? 'cursor-not-allowed opacity-60'
		: ''}"
	data-status={status}
	aria-label={`Coluna ${label}`}
	ondragenter={(event) => onZoneDragEnter(event, status)}
	ondragover={(event) => onZoneDragOver(event, status)}
	ondragleave={(event) => onZoneDragLeave(event, status)}
	ondrop={(event) => onZoneDrop(event, status)}
>
	{#each tasks as card, index (card.id)}
		{#if placeholderBeforeId === card.id}
			<li aria-hidden="true" class="kanban-placeholder" style:height={`${gapHeight}px`}></li>
		{/if}
		<li>
			<KanbanCard
				{card}
				dragging={draggingId === card.id}
				settled={settledId === card.id}
				columnLabel={label}
				position={index + 1}
				setSize={count}
				ondragstart={(event) => onCardDragStart(event, card, status)}
				ondragend={(event) => onCardDragEnd(event)}
				onkeydown={(event) => onCardKeydown(event, card, status)}
			/>
		</li>
	{/each}

	{#if placeholderBeforeId === -1}
		<li aria-hidden="true" class="kanban-placeholder" style:height={`${gapHeight}px`}></li>
	{/if}

	{#if showEmptyHint}
		<li
			class="flex min-h-[40px] flex-1 items-center justify-center rounded-lg border border-dashed border-border-strong px-3 py-3 text-center text-xs text-text-muted"
		>
			Sem itens nesta etapa
		</li>
	{/if}
</ul>

<style>
	/* Vão de inserção: preview tracejado de onde o card aterrissará. */
	.kanban-placeholder {
		flex-shrink: 0;
		border-radius: 12px;
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

	/* Scroll interno da zona: barra de 5px, quase invisível; cada zona rola
	 * por dentro. CUIDADO (armadilhas reais, ver css-scrollbars §3.1):
	 *   1. `.app-shell > main` (app.css) define scrollbar-color, e scrollbar-color
	 *      é propriedade HERDADA — ela desce até esta dropzone. Com o valor
	 *      computado ≠ auto, o Chromium 121+ IGNORA todos os ::-webkit-scrollbar*
	 *      do elemento e desenha a barra padrão (a azulada grossa). O reset
	 *      `auto` abaixo devolve o controle aos pseudo-elementos.
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
			scrollbar-color: var(--color-border-strong) transparent;
		}
	}
	.kanban-dropzone::-webkit-scrollbar {
		width: 5px;
	}
	.kanban-dropzone::-webkit-scrollbar-track {
		background: transparent;
	}
	.kanban-dropzone::-webkit-scrollbar-thumb {
		background: color-mix(in srgb, var(--color-border-strong) 80%, transparent);
		border-radius: 999px;
		min-height: 32px;
	}
	.kanban-dropzone::-webkit-scrollbar-thumb:hover {
		background: var(--color-border-strong);
	}

	@media (prefers-reduced-motion: reduce) {
		.kanban-placeholder {
			animation: none;
		}
	}
</style>
