/**
 * Tipos da carga de "Lista de Projetos" (GET /api/projetos).
 *
 * Espelham `_serialize_projects_list_context` (routes/api/projects.py) e os
 * serializers `serialize_project_card` / `serialize_orgao_option`
 * (routes/api/serializers.py) — a MESMA fonte de verdade da tela Jinja
 * (templates/projects/list.html), respeitando o `orgao_scope` server-side.
 * Os filtros, opções e a paginação chegam JÁ resolvidos pelo backend; o
 * cliente NÃO recalcula nada.
 *
 * O envelope `{ok, data}` é desempacotado por `client.ts`; os tipos abaixo
 * descrevem apenas `data`.
 */

import type { Project } from './entities';

/** Opção de órgão serializada (serialize_orgao_option) para o `<select>`. */
export interface OrgaoOption {
	value: string;
	label: string;
	sigla: string | null;
	nome: string | null;
	tipo: string | null;
	pai_id: number | null;
	is_user_orgao: boolean;
	is_user_ancestor: boolean;
	is_inactive: boolean;
}

/**
 * Órgão ATRIBUÍVEL como Área Responsável no modal Criar Projeto (§5.4).
 *
 * Lista plana já filtrada pelo backend por rank >= editor
 * (routes/orgao_scope.scoped_orgao_options) — mesma fonte/shape do
 * `OrgaoDetailOption` do picker inline do Detalhe. O filtro da lista continua
 * em `orgaos_options` (visibilidade, sem rank).
 */
export interface OrgaoAssignableOption {
	id: number;
	sigla: string;
	nome: string;
	pai_id: number | null;
}

/** Opção de indicador ABEP (catalogs/abep.py: ABEP_INDICADORES_OPTIONS). */
export interface AbepIndicadorOption {
	code: string;
	title: string;
	value: string;
	label: string;
}

/** Opção genérica `{value, label}` (ex.: prazos/atrasos). */
export interface ValueLabelOption {
	value: string;
	label: string;
}

/** Opção de objetivo EEGD (serializada no contexto da lista). */
export interface ObjetivoOption {
	id: number;
	descricao: string;
}

/** Filtros efetivamente aplicados pelo backend (reconciliados na UI). */
export interface ProjectsListFilters {
	status: string | null;
	prioridade: string | null;
	atraso: string | null;
	special_project: string | null;
	delivery_type: string | null;
	abep_indicator: string | null;
	objetivo: string | null;
	colecao: number | null;
	q: string;
	selected_orgao: number | null;
}

/** Opções de filtro disponíveis (popular os seletores da UI). */
export interface ProjectsListOptions {
	special_projects_options: string[];
	delivery_types_options: string[];
	abep_indicadores_options: AbepIndicadorOption[];
	priorities: string[];
	statuses: string[];
	atrasos_options: ValueLabelOption[];
	orgaos_options: OrgaoOption[];
	orgaos_assignable_options: OrgaoAssignableOption[];
}

/** Metadados de paginação da listagem (`pagination`). */
export interface ProjectsListPagination {
	page: number;
	per_page: number;
	total: number;
	total_pages: number;
}

/** Carga completa de GET /api/projetos (já desempacotada). */
export interface ProjectsListData {
	projetos: Project[];
	filters: ProjectsListFilters;
	options: ProjectsListOptions;
	pagination: ProjectsListPagination;
}

/** Filtros aceitos pelo endpoint (espelham os query params de /api/projetos). */
export interface ProjectsListQuery {
	/** Omitido = backend aplica "Vigente"; `''` = todos os status. */
	status?: string;
	prioridade?: string;
	atraso?: string;
	special_project?: string;
	delivery_type?: string;
	abep_indicator?: string;
	objetivo?: string;
	q?: string;
	orgao?: number | null;
	/** Restringe aos projetos desta coleção do próprio usuário. */
	colecao?: number;
	/** Omite os projetos já pertencentes a esta coleção do próprio usuário. */
	excluir_colecao?: number;
	/** Tamanho da página; o backend limita a 100 (default 40). */
	per_page?: number;
	page?: number;
}
