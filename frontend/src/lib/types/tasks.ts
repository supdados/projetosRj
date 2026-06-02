/**
 * Tipos da carga do Hub de Tarefas em modo lista (GET /api/tarefas).
 *
 * Espelham `_serialize_task_hub_context` / `_serialize_hub_group`
 * (routes/api/tasks.py) e o serializer `serialize_task_card`
 * (routes/api/serializers.py) — a MESMA fonte de verdade da rota Jinja
 * `/tarefas` (templates/tasks/hub.html), reusada via `build_task_hub_context`
 * e respeitando o `orgao_scope` server-side.
 *
 * Task e TaskItem são a MESMA tabela: existe um único tipo `TaskCard` com os
 * CAMPOS REAIS (`descricao`, `is_archived`, `archived_at`) — sem aliases
 * legados. Os agrupamentos por projeto/etapa chegam JÁ calculados no backend;
 * o cliente NÃO recalcula a hierarquia.
 */

/** Modo de listagem (`?modo=`): janela visível das tarefas do hub. */
export type TaskHubModo = 'ativas' | 'arquivadas' | 'finalizadas';

/**
 * Tarefa serializada para o card de lista (serialize_task_card + extras de
 * hub). Datas em ISO 8601 (ou `null`). `etapa_titulo` e `is_first_of_stage`
 * vêm do agrupador para que o cliente monte subgrupos por etapa sem recalcular.
 */
export interface TaskCard {
	id: number;
	descricao: string;
	status: string;
	responsavel: string | null;
	prioridade: string | null;
	tipo_pedido: string | null;
	ordem: number | null;
	project_id: number | null;
	etapa_id: number | null;
	created_by_id: number | null;
	created_at: string | null; // ISO 8601
	is_archived: boolean;
	archived_at: string | null; // ISO 8601
	/** Título da etapa à qual a tarefa pertence (ou `null` para "sem etapa"). */
	etapa_titulo: string | null;
	/** True quando esta tarefa abre um novo bloco de etapa no grupo. */
	is_first_of_stage: boolean;
}

/** Grupo de tarefas de um projeto (serialize_hub_group). */
export interface TaskHubGroup {
	key: string;
	project_id: number | null;
	project_value: string;
	project_titulo: string;
	project_orgao_sigla: string | null;
	tasks: TaskCard[];
}

/** Opção de projeto para o filtro (espelha `project_options` do hub). */
export interface TaskProjectOption {
	value: string;
	label: string;
	orgao_sigla: string;
}

/** Filtros selecionados resolvidos pelo backend (`filters`). */
export interface TaskHubFilters {
	project: string;
	prioridade: string;
	tipo: string;
	status: string;
	responsavel: string;
	/** Órgão efetivamente aplicado pelo `orgao_scope` (id sanitizado). */
	selected_orgao: string | number | null;
}

/** Carga completa de GET /api/tarefas (já desempacotada do envelope). */
export interface TaskHubData {
	groups: TaskHubGroup[];
	project_options: TaskProjectOption[];
	filters: TaskHubFilters;
	/** True quando a visão inclui tarefas arquivadas (`modo=arquivadas`). */
	include_archived: boolean;
	total_items: number;
}

/** Filtros aceitos pelo endpoint (espelham os query params de /api/tarefas). */
export interface TaskHubQuery {
	project?: string;
	prioridade?: string;
	tipo?: string;
	status?: string;
	responsavel?: string;
	orgao?: string | number | null;
	modo?: TaskHubModo;
}
