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

/**
 * Filtros do corpo de `POST /api/tarefas/arquivar-finalizadas` (espelham
 * `_read_task_filter_values`). Mesmos nomes dos query params do hub.
 */
export interface TaskHubFilterValues {
	project?: string;
	orgao?: string | number | null;
	prioridade?: string;
	tipo?: string;
	status?: string;
	responsavel?: string;
}

/**
 * Body de `POST /api/tarefas` (criar tarefa via composer/quick-add). Espelha o
 * payload aceito por `api_tarefa_criar` (`project_id`/`etapa_id` como alias).
 */
export interface CreateTarefaInput {
	project?: string | number | null;
	project_id?: string | number | null;
	etapa?: string | number | null;
	etapa_id?: string | number | null;
	descricao: string;
	status?: string;
	responsavel?: string | null;
	prioridade?: string | null;
	tipo_pedido?: string | null;
}

/**
 * Card devolvido por `POST /api/tarefas` (= `serialize_task_card` + extras de
 * contexto de projeto/etapa e permissões expostas por `_stage_card_payload`).
 */
export interface CreatedTaskCard extends TaskCard {
	etapa_descricao: string | null;
	project_titulo: string | null;
	project_orgao_sigla: string | null;
	comments_count: number;
	anexos_count: number;
	permissions: {
		can_delete: boolean;
		can_finalize: boolean;
		is_author: boolean;
	};
}

/** Resposta de `POST /api/tarefas`. */
export interface CreateTarefaResult {
	task: CreatedTaskCard;
}

/** Resposta de `POST /api/tarefas/<id>/excluir`. */
export interface DeleteTarefaResult {
	item_id: number;
	message: string;
}

/** Resposta de `POST /api/tarefas/<id>/mover-etapa`. */
export interface MoverEtapaResult {
	task_id: number;
	etapa_id: number | null;
	previous_etapa_id: number | null;
	/** Presente quando a etapa de destino está concluída. */
	warning?: string;
}

/** Resposta de `POST /api/tarefas/arquivar-finalizadas`. */
export interface ArchiveFinalizadasResult {
	archived_count: number;
	archived_task_ids: string[];
	message: string;
}

/** Sugestão de responsável do picker do hub (`GET .../sugestoes-responsavel`). */
export interface HubResponsavelSuggestion {
	id: number;
	name: string;
}
