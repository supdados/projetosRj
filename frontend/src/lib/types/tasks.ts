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

import type { OrgaoOption } from './pendentes';

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
	/** Responsáveis múltiplos (avatares de iniciais). Substitui `responsavel`. */
	assignees: TaskAssignee[];
	/** Título da etapa à qual a tarefa pertence (ou `null` para "sem etapa"). */
	etapa_titulo: string | null;
	/**
	 * Código exibível da etapa (ex.: "42.1" = projeto.índice-visível), derivado no
	 * backend (`hub_stage_display_id`). `null` para o bucket "sem etapa".
	 */
	etapa_display_id: string | null;
	/** True quando esta tarefa abre um novo bloco de etapa no grupo. */
	is_first_of_stage: boolean;
	/** Nº de comentários (indicador na linha da lista). */
	comments_count: number;
	/** Nº de anexos (indicador na linha da lista). */
	anexos_count: number;
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
	/** Busca livre aplicada (descrição da tarefa ou título do projeto). */
	search: string;
	/** Órgão efetivamente aplicado pelo `orgao_scope` (id sanitizado). */
	selected_orgao: string | number | null;
}

/** Metadados de paginação por GRUPO de projeto (`pagination`). */
export interface TaskHubPagination {
	page: number;
	per_page: number | null;
	total_pages: number;
	total_groups: number;
}

/** Carga completa de GET /api/tarefas (já desempacotada do envelope). */
export interface TaskHubData {
	groups: TaskHubGroup[];
	project_options: TaskProjectOption[];
	filters: TaskHubFilters;
	/** True quando a visão inclui tarefas arquivadas (`modo=arquivadas`). */
	include_archived: boolean;
	/** Total de tarefas em TODOS os grupos (pré-paginação). */
	total_items: number;
	pagination: TaskHubPagination;
	/**
	 * Opções de órgão para o filtro (mesma fonte de Pendentes:
	 * `get_user_orgao_options` + `serialize_orgao_option`; `value` = id).
	 */
	orgaos_options: OrgaoOption[];
}

/** Filtros aceitos pelo endpoint (espelham os query params de /api/tarefas). */
export interface TaskHubQuery {
	project?: string;
	prioridade?: string;
	tipo?: string;
	status?: string;
	responsavel?: string;
	/** Busca livre por descrição da tarefa ou título do projeto. */
	search?: string;
	orgao?: string | number | null;
	modo?: TaskHubModo;
	/** Página (1-based) da lista paginada por grupo de projeto. */
	page?: number;
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
	/** Responsáveis múltiplos a atribuir na criação (notifica cada um). */
	assignee_ids?: number[];
	prioridade?: string | null;
	tipo_pedido?: string | null;
}

/**
 * Card devolvido por `POST /api/tarefas` (= `serialize_task_card` com
 * `with_context_labels` + `with_manage_permissions`).
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

/**
 * Responsável de uma tarefa (avatar de iniciais, sem foto). Mesma forma nos
 * candidatos do picker e em `TaskCard.assignees` — o backend serializa via
 * `serialize_assignee`.
 */
export interface TaskAssignee {
	id: number;
	name: string;
	/** Iniciais para o avatar (ex.: "AJ"). */
	initials: string;
	/** Linha secundária no dropdown (órgão ou @username). */
	subtitle?: string;
}

/** Sugestão de responsável do picker do hub (`GET .../sugestoes-responsavel`). */
export interface HubResponsavelSuggestion {
	id: number;
	name: string;
	initials: string;
	subtitle?: string;
}
