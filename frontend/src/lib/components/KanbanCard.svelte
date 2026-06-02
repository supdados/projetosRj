<script lang="ts">
	/**
	 * Card de tarefa no Kanban (Fase 5b-1) — SOMENTE LEITURA + arrastável.
	 *
	 * Mostra descrição, responsável, prioridade/tipo (via Badge) e o contexto de
	 * projeto/etapa. NÃO edita, não abre drawer, não tem ações (isso é 5b-2).
	 *
	 * ESTADO CANÔNICO NA STORE: este componente é puramente derivado do `card`
	 * recebido por prop. O atributo `data-can-finalize` exposto aqui é só uma
	 * dica para inspeção/teste — NÃO é fonte de estado; a regra de DnD usa o
	 * objeto `card` da store (`canItemMoveToStatus`), nunca o DOM.
	 *
	 * O drag em si é coordenado pelo `KanbanBoard` (HTML5 nativo); aqui só
	 * expomos `draggable` e propagamos os eventos `dragstart`/`dragend`.
	 */
	import { getContext } from 'svelte';
	import Badge from '$lib/components/Badge.svelte';
	import type { BoardCard } from '$lib/types/board';

	/**
	 * Abertura do drawer (Fase 5b-2): fornecida via contexto pela página, para não
	 * exigir prop drilling por KanbanBoard/KanbanColumn. Ausente quando o board é
	 * usado sem drawer.
	 */
	const openTaskDrawer = getContext<((taskId: number) => void) | undefined>('openTaskDrawer');

	type BadgeTone = 'neutral' | 'primary' | 'success' | 'warning' | 'danger' | 'info';

	interface Props {
		card: BoardCard;
		/** Indica que este card é o que está sendo arrastado (feedback visual). */
		dragging?: boolean;
		/** Rótulo da coluna atual (para o aria-label do card focável). */
		columnLabel?: string;
		/** Posição do card na coluna (1-based) para `aria-posinset`. */
		position?: number;
		/** Total de cards na coluna para `aria-setsize`. */
		setSize?: number;
		ondragstart?: (event: DragEvent) => void;
		ondragend?: (event: DragEvent) => void;
		/** Teclado no card focado: setas movem entre colunas (alternativa ao DnD). */
		onkeydown?: (event: KeyboardEvent) => void;
	}

	let {
		card,
		dragging = false,
		columnLabel = '',
		position,
		setSize,
		ondragstart,
		ondragend,
		onkeydown
	}: Props = $props();

	/** Rótulos PT das prioridades (espelham `prioridade_labels` do hub Jinja). */
	const PRIORIDADE_LABEL: Record<string, string> = {
		baixa: 'Baixa',
		media: 'Média',
		alta: 'Alta',
		urgente: 'Urgente'
	};
	const PRIORIDADE_TONE: Record<string, BadgeTone> = {
		baixa: 'neutral',
		media: 'info',
		alta: 'warning',
		urgente: 'danger'
	};

	/** Rótulos PT dos tipos de pedido (espelham `tipo_labels` do hub Jinja). */
	const TIPO_LABEL: Record<string, string> = {
		bug: 'Bug',
		melhoria: 'Melhoria',
		duvida: 'Dúvida',
		outros: 'Outros',
		implementacao: 'Implementação'
	};

	function prioridadeLabel(value: string | null): string | null {
		if (!value) return null;
		return PRIORIDADE_LABEL[value] ?? value;
	}
	function prioridadeTone(value: string | null): BadgeTone {
		if (!value) return 'neutral';
		return PRIORIDADE_TONE[value] ?? 'neutral';
	}
	function tipoLabel(value: string | null): string | null {
		if (!value) return null;
		return TIPO_LABEL[value] ?? value;
	}
</script>

<div
	class="flex cursor-grab flex-col gap-2 rounded-md border border-border-subtle bg-surface px-3 py-2.5 shadow-sm transition-opacity duration-fast focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 active:cursor-grabbing {dragging
		? 'opacity-40'
		: ''}"
	draggable="true"
	tabindex="0"
	data-item-id={card.id}
	data-can-finalize={card.permissions.can_finalize}
	role="button"
	aria-roledescription="Tarefa movível"
	aria-label={`${card.descricao}${columnLabel ? `, em ${columnLabel}` : ''}${
		position && setSize ? ` (${position} de ${setSize})` : ''
	}. Use as setas esquerda e direita para mover entre colunas.`}
	ondragstart={(event) => ondragstart?.(event)}
	ondragend={(event) => ondragend?.(event)}
	onkeydown={(event) => onkeydown?.(event)}
>
	<p class="text-sm text-text-primary">{card.descricao}</p>

	<div class="flex flex-wrap items-center gap-2">
		{#if prioridadeLabel(card.prioridade)}
			<Badge tone={prioridadeTone(card.prioridade)}>
				{prioridadeLabel(card.prioridade)}
			</Badge>
		{/if}
		{#if tipoLabel(card.tipo_pedido)}
			<span class="text-xs text-text-secondary">{tipoLabel(card.tipo_pedido)}</span>
		{/if}
	</div>

	{#if card.responsavel}
		<p class="text-xs text-text-muted">Responsável: {card.responsavel}</p>
	{/if}

	{#if openTaskDrawer}
		<button
			type="button"
			onclick={() => openTaskDrawer?.(card.id)}
			class="w-fit text-xs font-medium text-primary-700 hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
		>
			Abrir
		</button>
	{/if}
</div>
