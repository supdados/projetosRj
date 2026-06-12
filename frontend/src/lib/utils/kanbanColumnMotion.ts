/**
 * Sinal board → cards: "morph de largura de coluna em curso". Ativo, os cards
 * suspendem a medição do rodapé (o ResizeObserver de todos eles dispararia a
 * cada frame, forçando reflow síncrono) e re-medem uma única vez quando
 * desliga. Achados em docs/refinamento-animacao-kanban-expandir.md.
 */
export interface KanbanColumnMotionSignal {
	active: boolean;
}

export const KANBAN_COLUMN_MOTION = Symbol('kanban-column-motion');
