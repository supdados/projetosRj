/**
 * Tipos do CRUD de Usuários (Admin) — espelham os endpoints
 * `GET/POST /api/admin/usuarios*` (routes/api/admin_users.py) e o serializer
 * `serialize_admin_user` (routes/api/serializers.py).
 *
 * O envelope `{ok, data}` é desempacotado por `client.ts`; os tipos abaixo
 * descrevem apenas `data` (e a `meta` de paginação chega à parte). NUNCA há
 * `password_hash`/`govbr_sub` — o backend nunca os serializa.
 */

/** Vínculo mínimo de órgão exposto em `serialize_admin_user.orgaos`. */
export interface AdminUserOrgaoRef {
	id: number;
	sigla: string;
	nome: string;
}

/** Usuário serializado para o painel admin (`serialize_admin_user`). */
export interface AdminUser {
	id: number;
	name: string;
	username: string;
	is_admin: boolean;
	/** Campo legado de órgão (string livre). */
	orgao: string | null;
	orgaos: AdminUserOrgaoRef[];
	cpf_govbr: string | null;
	/** True quando há CPF + vínculo Gov.br ativo (govbr_sub presente). */
	has_govbr_link: boolean;
	/** True quando o CPF não é editável por já existir vínculo OAuth. */
	govbr_link_locked: boolean;
	auth_provider: string;
}

/**
 * Opção de órgão (ativo) com profundidade, para o seletor em árvore do form.
 * Espelha `_serialize_orgao_depth_option`: `(id, sigla, nome, depth)`.
 */
export interface AdminOrgaoOption {
	id: number;
	sigla: string;
	nome: string;
	depth: number;
}

/** Metadados de paginação da lista (`meta`), per_page fixo em 10. */
export interface AdminUsersPageMeta {
	page: number;
	per_page: number;
	total: number;
	total_pages: number;
}

/** Carga + meta da lista paginada (GET /api/admin/usuarios). */
export interface AdminUsersListResult {
	usuarios: AdminUser[];
	meta: AdminUsersPageMeta;
}

/** Carga do detalhe/form de edição (GET /api/admin/usuarios/<id>). */
export interface AdminUserDetail {
	usuario: AdminUser;
	orgao_ids: number[];
	orgaos_options: AdminOrgaoOption[];
}

/** Payload de criação (POST /api/admin/usuarios). */
export interface AdminUserCreatePayload {
	username: string;
	name: string;
	password: string;
	orgao?: string;
	is_admin: boolean;
	cpf_govbr?: string;
	/** Ids dos órgãos vinculados (chave `orgaos_responsavel` no backend). */
	orgaos_responsavel: number[];
}

/**
 * Payload de edição (POST /api/admin/usuarios/<id>). `username` é imutável e
 * não é enviado. `cpf_govbr` só é considerado quando o vínculo não está
 * travado; `password` só altera se não vazio.
 */
export interface AdminUserUpdatePayload {
	name: string;
	orgao?: string;
	is_admin: boolean;
	cpf_govbr?: string;
	password?: string;
	orgaos_responsavel: number[];
}
