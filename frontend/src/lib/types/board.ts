/**
 * Tipos da carga do Kanban de Tarefas (Fase 5b-1).
 *
 * Espelham `routes/api/board.py` (`api_tarefas_board`,
 * `api_tarefas_board_reordenar`, `api_tarefa_status`) e o serializer
 * `serialize_task_card` (`routes/api/serializers.py`). O board é READ-ONLY +
 * DnD de status/ordem nesta fase — sem drawer/edição/anexos/comentários.
 *
 * Task e TaskItem são a MESMA tabela: o card usa CAMPOS REAIS (`descricao`,
 * `is_archived`, `archived_at`) e inclui `permissions.can_finalize` (UX-only).
 */

import type { TaskStatus } from '$lib/utils/taskStatus';
import type { TaskAssignee } from '$lib/types/tasks';

/** Flags de permissão por card (UX-only; servidor é autoritativo). */
export interface BoardCardPermissions {
	can_finalize: boolean;
}

/**
 * Card do board (= `serialize_task_card`). Datas em ISO 8601 (ou `null`).
 * `status` é livre na origem (dado legado possível), mas o board agrupa por
 * coluna canônica via `normalizeStatus`.
 */
export interface BoardCard {
	id: number;
	descricao: string;
	status: string;
	/** Texto livre legado — NÃO usado para exibição (fonte é `assignees`);
	 *  só guarda nomes sem usuário correspondente pós-backfill. */
	responsavel: string | null;
	/** Responsáveis múltiplos (`serialize_task_assignees`) — avatares no rodapé
	 *  do card; única fonte de exibição de responsáveis. */
	assignees: TaskAssignee[];
	prioridade: string | null;
	tipo_pedido: string | null;
	ordem: number | null;
	project_id: number | null;
	/** Nome do projeto vinculado (link azul do card) — `null` em tarefa avulsa. */
	project_titulo: string | null;
	etapa_id: number | null;
	created_by_id: number | null;
	created_at: string | null; // ISO 8601
	is_archived: boolean;
	archived_at: string | null; // ISO 8601
	/** Contadores do rodapé do card (balão de comentários / clipe de anexos). */
	comments_count: number;
	anexos_count: number;
	permissions: BoardCardPermissions;
}

/**
 * Coluna do board (uma por status; sempre as 5, mesmo vazias). Espelha
 * `_group_tasks_into_columns`.
 */
export interface BoardColumn {
	status: TaskStatus;
	label: string;
	tasks: BoardCard[];
}

/** Filtros efetivos resolvidos pelo backend (`data.filters`). */
export interface BoardFilters {
	project: string;
	prioridade: string;
	tipo: string;
	status: string;
	responsavel: string;
	/** Órgão aplicado pelo `orgao_scope` (id sanitizado server-side). */
	selected_orgao: string | number | null;
}

/** Carga completa de `GET /api/tarefas/board` (desempacotada do envelope). */
export interface BoardData {
	columns: BoardColumn[];
	filters: BoardFilters;
	total: number;
}

/** Filtros aceitos pelo board (espelham os query params, iguais ao Hub). */
export interface BoardQuery {
	project?: string;
	prioridade?: string;
	tipo?: string;
	status?: string;
	responsavel?: string;
	orgao?: string | number | null;
}

/** Resposta de `POST /api/tarefas/<id>/status`: o card atualizado. */
export interface TaskStatusResult {
	task: BoardCard;
}

/** Uma coluna no payload de reordenação (estado canônico vindo da store). */
export interface BoardReorderColumn {
	status: TaskStatus;
	task_ids: number[];
}

/** Corpo de `POST /api/tarefas/board/reordenar`. */
export interface BoardReorderPayload {
	columns: BoardReorderColumn[];
	/** Card arrastado entre colunas — o ÚNICO que pode mudar de status no
	 *  servidor (omitido em reorder na mesma coluna). */
	moved_task_id?: number;
}

/** Resposta de `POST /api/tarefas/board/reordenar`: colunas afetadas. */
export interface BoardReorderResult {
	columns: BoardColumn[];
}
