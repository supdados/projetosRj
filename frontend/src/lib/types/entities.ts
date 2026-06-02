/**
 * Tipos das entidades do dominio, alinhados aos CAMPOS REAIS dos modelos Flask.
 *
 * Principios (plano de migracao, secao "Tipos TypeScript das entidades"):
 *   - Campos reais; sem aliases legados. Em Task: `descricao`/`is_archived`/
 *     `archived_at` (NUNCA `titulo`/`is_finalized`). Task e TaskItem sao a MESMA
 *     tabela => UM unico tipo `Task`.
 *   - Segredos NUNCA aparecem: `password_hash`, tokens OAuth.
 *   - Derivados de projeto sao computados no backend (read-only); o cliente NAO
 *     os recalcula.
 *
 * Espelha `routes/api/serializers.py` (serialize_user / serialize_project_card /
 * serialize_task_card).
 */

// Enums alinhados a routes/tasks/constants.py (VALID_STATUSES).
export type TaskStatus =
	| 'nao_iniciada'
	| 'em_andamento'
	| 'para_validacao'
	| 'para_ajustes'
	| 'finalizada';

export type TaskPrioridade = 'baixa' | 'media' | 'alta' | 'urgente';

export type TaskTipo = 'bug' | 'melhoria' | 'duvida' | 'outros' | 'implementacao';

/** Status de projeto: strings magicas (sem constante central no backend). */
export type ProjectStatus = 'Vigente' | 'Finalizado';

/** Provedor de autenticacao derivado em serialize_user. */
export type AuthProvider = 'local' | 'govbr';

/** Vinculo minimo de orgao (serialize_user -> _orgao_ref_brief). */
export interface OrgaoRef {
	id: number;
	sigla: string;
	nome: string;
}

/** Usuario autenticado (GET /api/me). Sem segredos. */
export interface User {
	id: number;
	name: string;
	username: string;
	is_admin: boolean;
	orgaos: OrgaoRef[];
	auth_provider: AuthProvider;
}

/**
 * Projeto no formato "card" (serialize_project_card).
 * `orgao` (string) e o campo legado; `orgao_id`/`orgao_sigla` sao relacionais.
 * Os campos derivados sao read-only (NAO recalcular no cliente).
 */
export interface Project {
	id: number;
	titulo: string;
	status: ProjectStatus;
	prioridade: TaskPrioridade | string | null;
	orgao: string | null; // legado: string livre
	orgao_id: number | null;
	orgao_sigla: string | null;
	short_description: string | null;
	special_project: string | null;
	delivery_type: string | null; // tipo de entrega (também no card/lista)
	// derivados read-only (computados no backend)
	data_inicio_projeto: string | null; // ISO 8601
	data_fim_projeto: string | null; // ISO 8601
	total_workflow_etapas: number;
	todas_etapas_concluidas: boolean;
}

/**
 * Tarefa no formato "card" (serialize_task_card). UM unico tipo Task.
 * Campos reais: `descricao`, `is_archived`, `archived_at`.
 */
export interface Task {
	id: number;
	descricao: string; // NAO "titulo"
	status: TaskStatus;
	responsavel: string | null;
	prioridade: TaskPrioridade | null;
	tipo_pedido: TaskTipo | null;
	ordem: number;
	project_id: number | null;
	project_titulo: string | null; // titulo do projeto da tarefa (mini-lista "Recentes")
	etapa_id: number | null;
	created_by_id: number;
	created_at: string | null; // ISO 8601
	is_archived: boolean; // NAO "is_finalized"
	archived_at: string | null; // ISO 8601
}
