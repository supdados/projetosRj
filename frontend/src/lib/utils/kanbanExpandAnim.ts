/**
 * Sinal compartilhado página → cards do Kanban: "a transição de expandir/
 * retrair o quadro está em curso".
 *
 * Por quê: a transição muda a LARGURA das colunas a cada frame (margin
 * negativa viewport-relativa do wrapper), o que dispara o ResizeObserver do
 * rodapé de TODOS os cards visíveis ~60×/s — cada disparo força reflow
 * síncrono (scrollWidth/clientWidth) e até 3 re-renders. Com o sinal, os
 * cards SUSPENDEM a medição enquanto `active === true` e re-medem UMA vez
 * quando ele desliga, trocando O(cards × frames × 3) por O(cards × 1).
 * Achados completos em docs/refinamento-animacao-kanban-expandir.md.
 *
 * Uso: a página cria `$state({ active: false })` e publica via
 * `setContext(KANBAN_EXPAND_ANIM, sinal)`; o KanbanCard lê com `getContext`
 * (opcional — sem o contexto, o card só coalesce por rAF, sem pausa).
 */
export interface KanbanExpandAnimSignal {
	active: boolean;
}

export const KANBAN_EXPAND_ANIM = Symbol('kanban-expand-anim');
