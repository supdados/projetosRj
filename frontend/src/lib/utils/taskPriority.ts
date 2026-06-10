/**
 * Utilitários PUROS de prioridade de tarefa para o Kanban.
 *
 * Espelha a ordenação server-side (`task_priority_sort_rank` em
 * `routes/tasks/constants.py`): dentro de cada coluna de status, os cards são
 * ordenados por prioridade (urgente → alta → media → baixa; ausente por último).
 * Usado para manter a ordem após mutações OTIMISTAS na board store (criar/editar
 * card), já que o backend só reordena nas respostas de GET/reorder.
 *
 * Exemplo:
 *   sortByPriority([{ prioridade: 'baixa' }, { prioridade: 'urgente' }]);
 *   // => [{ prioridade: 'urgente' }, { prioridade: 'baixa' }]
 */

/**
 * Ordem canônica de prioridade (= `TASK_PRIORIDADE_ORDER` em
 * `routes/tasks/constants.py`), do MENOR para o MAIOR. NÃO reordenar.
 */
export const TASK_PRIORIDADE_ORDER = ['baixa', 'media', 'alta', 'urgente'] as const;

/** Peso por prioridade: 0 = urgente (topo) … 3 = baixa. Derivado da ordem canônica invertida. */
const PRIORITY_RANK: Readonly<Record<string, number>> = Object.fromEntries(
	[...TASK_PRIORIDADE_ORDER].reverse().map((prioridade, rank) => [prioridade, rank])
);

/** Peso de prioridade ausente/desconhecida: vai por último (igual ao fallback do backend). */
const PRIORITY_RANK_FALLBACK = TASK_PRIORIDADE_ORDER.length;

/**
 * Peso de ordenação de uma prioridade: 0 = urgente, 1 = alta, 2 = media,
 * 3 = baixa; `null`/desconhecida => 4 (por último). Menor vem primeiro.
 */
export function priorityRank(prioridade: string | null | undefined): number {
	if (prioridade == null) return PRIORITY_RANK_FALLBACK;
	return PRIORITY_RANK[prioridade] ?? PRIORITY_RANK_FALLBACK;
}

/**
 * Retorna uma NOVA lista ordenada por prioridade (urgente primeiro). O sort é
 * estável (ES2019+): cards de mesma prioridade preservam a ordem de entrada —
 * que reflete a ordem manual (`Task.ordem`) vinda do backend / do drag-and-drop.
 */
export function sortByPriority<T extends { prioridade: string | null }>(cards: T[]): T[] {
	return [...cards].sort((a, b) => priorityRank(a.prioridade) - priorityRank(b.prioridade));
}
