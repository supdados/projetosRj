/**
 * Tipos do CRUD de Órgãos (árvore) do Admin — Fase 4.
 *
 * Espelham os serializers do backend (`routes/api/serializers.py`:
 * `serialize_orgao_node`, `serialize_orgao_form`, `serialize_orgao_tipo`) e as
 * cargas dos endpoints `/api/admin/orgaos*` (`routes/api/admin_orgaos.py`). O
 * envelope `{ok, data}` é desempacotado por `client.ts`; os tipos abaixo
 * descrevem apenas `data`. NUNCA expõem segredos (espelham o backend).
 */

/** Nó recursivo da árvore (serialize_orgao_node). */
export interface OrgaoNode {
	id: number;
	sigla: string | null;
	nome: string | null;
	tipo: string | null;
	tipo_id: number | null;
	pai_id: number | null;
	ordem: number | null;
	ativo: boolean;
	codigo_externo: string | null;
	filhos: OrgaoNode[];
}

/** Órgão serializado para o formulário de edição (serialize_orgao_form). */
export interface OrgaoForm {
	id: number;
	sigla: string | null;
	nome: string | null;
	tipo: string | null;
	tipo_id: number | null;
	pai_id: number | null;
	ordem: number | null;
	ativo: boolean;
	codigo_externo: string | null;
	data_inicio_vigencia: string | null;
	data_fim_vigencia: string | null;
}

/** Tipo de órgão do catálogo (serialize_orgao_tipo). */
export interface OrgaoTipo {
	id: number;
	nome: string | null;
	slug: string | null;
	nivel: number | null;
	descricao: string | null;
	ativo: boolean;
	is_system: boolean;
	permite_raiz: boolean;
}

/** Candidato a pai (id/sigla/nome) para o seletor do form. */
export interface CandidatoPai {
	id: number;
	sigla: string | null;
	nome: string | null;
}

/** Mapa nome-do-tipo -> nível (tipo_rank). */
export type TipoRank = Record<string, number>;

/** Carga de GET /api/admin/orgaos (árvore + catálogos). */
export interface OrgaoTreeData {
	arvore: OrgaoNode[];
	candidatos_pai: CandidatoPai[];
	tipos: OrgaoTipo[];
	tipo_rank: TipoRank;
	max_depth: number;
	total: number;
}

/** Carga de GET /api/admin/orgaos/<id> (form de edição + catálogos). */
export interface OrgaoDetailData {
	orgao: OrgaoForm;
	is_root: boolean;
	candidatos_pai: CandidatoPai[];
	tipos: OrgaoTipo[];
	tipo_rank: TipoRank;
	max_depth: number;
}

/** Payload aceito pelos endpoints create/update (espelha normalize_orgao_form). */
export interface OrgaoFormPayload {
	nome: string;
	sigla: string;
	tipo_id: number | string;
	pai_id?: number | string | null;
	ordem?: number | string;
	ativo?: string;
	codigo_externo?: string;
	data_inicio_vigencia?: string;
	data_fim_vigencia?: string;
}

/** Direção de reordenação entre irmãos. */
export type ReorderDirection = 'up' | 'down';
