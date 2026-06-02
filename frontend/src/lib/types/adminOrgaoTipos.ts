/**
 * Tipos da tela "Admin > Tipos de Órgão" (CRUD), espelhando o serializer
 * `serialize_orgao_tipo` (routes/api/serializers.py) e os endpoints
 * `/api/admin/orgaos/tipos*` (routes/api/admin_orgaos.py) — a MESMA fonte de
 * verdade das telas Jinja `templates/admin/orgao_tipos.html` e
 * `orgao_tipo_form.html`.
 *
 * O envelope `{ok, data}` é desempacotado por `client.ts`; os tipos abaixo
 * descrevem apenas `data`. Mutations usam `client.post` (que injeta o
 * X-CSRFToken) — vide `$lib/api/adminOrgaoTipos`.
 */

/** Tipo de órgão serializado (serialize_orgao_tipo). NÃO expõe segredos. */
export interface AdminOrgaoTipo {
	id: number;
	nome: string;
	slug: string | null;
	nivel: number;
	descricao: string | null;
	ativo: boolean;
	/** Tipos-padrão protegidos (não editáveis livremente no backend). */
	is_system: boolean;
	permite_raiz: boolean;
}

/** Carga de GET /api/admin/orgaos/tipos: catálogo + contagem de uso. */
export interface AdminOrgaoTiposListData {
	tipos: AdminOrgaoTipo[];
	/** Map `tipo_id` (string) -> nº de órgãos vinculados. */
	usage_counts: Record<string, number>;
}

/** Carga de GET /api/admin/orgaos/tipos/<id> (detalhe para o form). */
export interface AdminOrgaoTipoDetailData {
	tipo: AdminOrgaoTipo;
}

/** Carga das mutations que devolvem o tipo (`create`/`update`/`toggle`). */
export interface AdminOrgaoTipoMutationData {
	tipo: AdminOrgaoTipo;
}

/** Carga de POST /api/admin/orgaos/tipos/<id>/delete. */
export interface AdminOrgaoTipoDeleteData {
	deleted_id: number;
}

/**
 * Payload do form criar/editar tipo. Espelha `_normalize_tipo_form`
 * (routes/admin_orgaos.py): `nome` e `nivel` obrigatórios; `slug` derivado do
 * nome quando vazio. As flags `ativo`/`permite_raiz` seguem a semântica de
 * presença do backend (`form.get(...) is not None`) — vide o módulo de API,
 * que omite a chave quando `false`.
 */
export interface AdminOrgaoTipoFormInput {
	nome: string;
	slug?: string;
	nivel: number;
	descricao?: string;
	ativo: boolean;
	permite_raiz: boolean;
}
