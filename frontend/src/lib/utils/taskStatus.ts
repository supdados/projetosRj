/**
 * Utilitários PUROS de status de tarefa para o Kanban (Fase 5b-1).
 *
 * Porta EXATAMENTE a lógica de `static/js/modules/kanban-manager.js`
 * (`statusOrder`, `statusLabels`, `normalizeStatus`, `canItemMoveToStatus`,
 * `canFinalize`) para TypeScript, como funções puras e testáveis.
 *
 * IMPORTANTE: estas regras são SÓ para UX (habilitar/desabilitar o drop na
 * coluna "finalizada"). A decisão autoritativa de transição é server-side
 * (`routes/tasks/crud.py::_can_transition_task_to_status`,
 * `FINALIZE_DENIED_MESSAGE`, `VALID_STATUSES`); todo move DEVE ser confirmado
 * pelo backend e revertido (rollback) na store se o servidor recusar.
 *
 * Exemplo:
 *   canItemMoveToStatus({ status: 'em_andamento', can_finalize: false },
 *     'finalizada', 'em_andamento'); // => false
 */

/** Status canônico de uma tarefa (= `VALID_STATUSES` no backend). */
export type TaskStatus =
	| 'nao_iniciada'
	| 'em_andamento'
	| 'para_validacao'
	| 'para_ajustes'
	| 'finalizada';

/**
 * Ordem canônica das 5 colunas do board (= `TASK_STATUS_ORDER` em
 * `routes/tasks/constants.py`). NÃO reordenar.
 */
export const TASK_STATUS_ORDER: readonly TaskStatus[] = [
	'nao_iniciada',
	'em_andamento',
	'para_validacao',
	'para_ajustes',
	'finalizada'
] as const;

/** Rótulos PT-BR por status (espelha `statusLabels` do JS legado). */
export const STATUS_LABELS: Readonly<Record<TaskStatus, string>> = {
	nao_iniciada: 'Não iniciada',
	em_andamento: 'Em andamento',
	para_validacao: 'Para validação',
	para_ajustes: 'Para ajustes',
	finalizada: 'Finalizada'
};

/**
 * Item mínimo que as regras de UX precisam conhecer. O board usa `BoardCard`
 * (que satisfaz este shape), mas as funções aceitam qualquer item compatível —
 * inclusive o `{ status, can_finalize }` sintético do contexto de drag.
 */
export interface StatusRuleItem {
	status?: string | null;
	/** Forma plana (item sintético do drag / testes). */
	can_finalize?: boolean | null;
	/** Forma aninhada do `BoardCard` serializado pelo backend (`permissions.can_finalize`). */
	permissions?: { can_finalize?: boolean | null } | null;
}

/**
 * Normaliza um status arbitrário ao conjunto canônico. Status desconhecido
 * (dado legado) cai em `'nao_iniciada'` — idêntico ao `normalizeStatus` legado
 * e ao bucket de fallback do backend (`TASK_STATUS_ORDER[0]`).
 */
export function normalizeStatus(status: string | null | undefined): TaskStatus {
	return TASK_STATUS_ORDER.includes(status as TaskStatus)
		? (status as TaskStatus)
		: 'nao_iniciada';
}

/** Rótulo de exibição de um status (com normalização). */
export function getStatusLabel(status: string | null | undefined): string {
	return STATUS_LABELS[normalizeStatus(status)];
}

/**
 * UX-only: o item pode finalizar? Espelha `!!(item && item.canFinalize)`.
 * NÃO substitui a checagem autoritativa do servidor.
 */
export function canFinalize(item: StatusRuleItem | null | undefined): boolean {
	if (!item) return false;
	// Aceita a forma plana (`can_finalize`) E a aninhada do BoardCard
	// (`permissions.can_finalize`). Sem isso, o card do Kanban (que só tem a
	// forma aninhada) caía para `false` e o drop em "Finalizada" era sempre
	// bloqueado client-side, mesmo quando o backend permitiria.
	if (typeof item.can_finalize === 'boolean') return item.can_finalize;
	return !!item.permissions?.can_finalize;
}

/**
 * UX-only: o `item` pode ser movido para `targetStatus`?
 *
 * Porta EXATAMENTE `canItemMoveToStatus(item, targetStatus, previousStatus)`:
 *   - alvo != 'finalizada' -> true (sempre permitido);
 *   - origem (`previousStatus` ou `item.status`) == 'finalizada' -> true
 *     (já estava finalizada; reordenar/voltar não é "finalizar de novo");
 *   - caso contrário -> `canFinalize(item)`.
 *
 * Usado apenas para habilitar/desabilitar o drop; o move é confirmado pelo
 * backend e revertido na store se recusado.
 */
export function canItemMoveToStatus(
	item: StatusRuleItem | null | undefined,
	targetStatus: string | null | undefined,
	previousStatus?: string | null
): boolean {
	if (normalizeStatus(targetStatus) !== 'finalizada') {
		return true;
	}
	const origin = previousStatus || (item && item.status);
	if (normalizeStatus(origin) === 'finalizada') {
		return true;
	}
	return canFinalize(item);
}
