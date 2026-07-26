/**
 * Tipos do CRUD de Usuários (Admin) — espelham os endpoints
 * `GET/POST /api/admin/usuarios*` (routes/api/admin_users.py) e o serializer
 * `serialize_admin_user` (routes/api/serializers.py).
 *
 * O envelope `{ok, data}` é desempacotado por `client.ts`; os tipos abaixo
 * descrevem apenas `data` (e a `meta` de paginação chega à parte). NUNCA há
 * `password_hash`/`govbr_sub` — o backend nunca os serializa.
 */

import type { OrgaoPapel } from './entities';

export type { OrgaoPapel };

/** Vínculo mínimo de órgão exposto em `serialize_admin_user.orgaos`. */
export interface AdminUserOrgaoRef {
	id: number;
	sigla: string;
	nome: string;
	papel: OrgaoPapel;
}

/**
 * Par área × papel do payload NOVO de escrita (`orgaos`). O backend também
 * aceita o formato antigo `orgaos_responsavel: [id]` (tudo `gestor`), mantido
 * apenas para deploy desacoplado — a SPA sempre envia os pares.
 */
export interface AdminUserOrgaoVinculo {
	orgao_id: number;
	papel: OrgaoPapel;
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
 * Opção de órgão (ativo) com hierarquia, para o seletor em árvore do form.
 * Espelha `_serialize_orgao_option_row`: `(id, sigla, nome, pai_id)`.
 */
export interface AdminOrgaoOption {
	id: number;
	sigla: string;
	nome: string;
	pai_id: number | null;
}

/** Metadados de paginação da lista (`meta`), per_page fixo em 20. */
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
	/** Vínculos de área com papel (chave `orgaos` no backend). */
	orgaos: AdminUserOrgaoVinculo[];
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
	orgaos: AdminUserOrgaoVinculo[];
}
