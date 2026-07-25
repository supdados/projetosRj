/**
 * Acesso tipado ao CRUD de Usuários (Admin), consumindo
 * `/api/admin/usuarios*` (routes/api/admin_users.py) no envelope canônico.
 *
 * Leituras simples usam `client.get` (desempacota `data`). Mutations usam
 * `client.post` (que injeta `X-CSRFToken` e trata 401/CSRF) — espelhando as
 * rotas Flask POST da Fase 4.
 *
 * Exceção: a LISTA paginada precisa da `meta` do envelope (page/per_page/
 * total/total_pages), que `client.get` descarta ao devolver só `data` — por
 * isso usa `getWithMeta`.
 */

import { get, getWithMeta, post, put, del } from './client';
import { createSwrCache } from './swrCache';
import type {
	AdminUsersListResult,
	AdminUserDetail,
	AdminUser,
	AdminUserCreatePayload,
	AdminUserUpdatePayload,
	AdminUsersPageMeta,
	AdminOrgaoOption
} from '$lib/types/adminUsers';

/** Envelope cru de sucesso da lista, incluindo a `meta` de paginação. */
interface AdminUsersListEnvelope {
	usuarios: AdminUser[];
}

/** Filtros da listagem paginada de usuários. */
export interface AdminUsersListParams {
	page?: number;
	q?: string;
	areaId?: number;
}

/** Monta a querystring da listagem, omitindo valores vazios/default. */
function buildAdminUsersQuery({ page = 1, q = '', areaId }: AdminUsersListParams): string {
	const params = new URLSearchParams();
	if (page > 1) params.set('page', String(page));
	if (q.trim()) params.set('q', q.trim());
	if (areaId) params.set('area_id', String(areaId));
	const qs = params.toString();
	return qs ? `?${qs}` : '';
}

// Ultimo payload bom por chave de filtros (querystring de
// `buildAdminUsersQuery`). SWR: a tela reabre com o dado antigo e revalida em
// silencio (ver dashboard.ts).
const adminUsersCache = createSwrCache<AdminUsersListResult>();

/** Ultima listagem carregada para os filtros, ou null (sincrono, 1o render). */
export function peekAdminUsers(params: AdminUsersListParams = {}): AdminUsersListResult | null {
	return adminUsersCache.peek(buildAdminUsersQuery(params));
}

/**
 * Lista paginada de usuários (GET /api/admin/usuarios), capturando a `meta`
 * de paginação via `getWithMeta` do client (que preserva `meta` e trata
 * 401/CSRF com a mesma semântica do `get`/`post`).
 */
export async function fetchAdminUsers(
	params: AdminUsersListParams = {},
	signal?: AbortSignal
): Promise<AdminUsersListResult> {
	const { page = 1 } = params;
	const qs = buildAdminUsersQuery(params);
	const { data, meta } = await getWithMeta<AdminUsersListEnvelope>(
		`/api/admin/usuarios${qs}`,
		signal
	);
	const pageMeta: AdminUsersPageMeta = (meta as AdminUsersPageMeta | undefined) ?? {
		page,
		per_page: data.usuarios.length,
		total: data.usuarios.length,
		total_pages: 1
	};
	const result: AdminUsersListResult = { usuarios: data.usuarios, meta: pageMeta };
	adminUsersCache.store(qs, result);
	return result;
}

/**
 * Opções de órgãos (ativos, com profundidade) para o form de CRIAÇÃO de
 * usuário. Usa o endpoint enveloped GET /api/admin/orgaos/opcoes, que já
 * devolve a lista achatada (somente ativos, ordenados por `(depth, sigla)`)
 * — o front não precisa mais achatar a árvore de `/api/admin/orgaos`.
 */
// Ultimas opcoes boas (endpoint sem filtros — mesma lista serve criação e
// edição). SWR: a tela reabre com o dado antigo e revalida em silencio.
const orgaoOptionsCache = createSwrCache<AdminOrgaoOption[]>();
const ORGAO_OPTIONS_KEY = 'opcoes';

/** Ultimas opções de órgão carregadas, ou null (sincrono, para o 1o render). */
export function peekOrgaoOptionsForUser(): AdminOrgaoOption[] | null {
	return orgaoOptionsCache.peek(ORGAO_OPTIONS_KEY);
}

export async function fetchOrgaoOptionsForUser(
	signal?: AbortSignal
): Promise<AdminOrgaoOption[]> {
	const opcoes = await get<AdminOrgaoOption[]>('/api/admin/orgaos/opcoes', signal);
	const result = Array.isArray(opcoes) ? opcoes : [];
	orgaoOptionsCache.store(ORGAO_OPTIONS_KEY, result);
	return result;
}

// Ultimo detalhe bom por id de usuário. SWR: a tela reabre com o dado antigo e
// revalida em silencio (ver dashboard.ts).
const adminUserDetailCache = createSwrCache<AdminUserDetail>();

/** Ultimo detalhe carregado do usuário, ou null (sincrono, 1o render). */
export function peekAdminUserDetail(userId: number): AdminUserDetail | null {
	return adminUserDetailCache.peek(String(userId));
}

/** Detalhe + opções de órgãos de um usuário (GET /api/admin/usuarios/<id>). */
export async function fetchAdminUserDetail(
	userId: number,
	signal?: AbortSignal
): Promise<AdminUserDetail> {
	const data = await get<AdminUserDetail>(`/api/admin/usuarios/${userId}`, signal);
	adminUserDetailCache.store(String(userId), data);
	return data;
}

/** Cria um usuário (POST /api/admin/usuarios). */
export function createAdminUser(
	payload: AdminUserCreatePayload
): Promise<{ usuario: AdminUser }> {
	return post<{ usuario: AdminUser }>('/api/admin/usuarios', payload);
}

/** Edita um usuário (PUT /api/admin/usuarios/<id>). */
export function updateAdminUser(
	userId: number,
	payload: AdminUserUpdatePayload
): Promise<{ usuario: AdminUser }> {
	return put<{ usuario: AdminUser }>(`/api/admin/usuarios/${userId}`, payload);
}

/** Remove CPF + vínculo Gov.br (POST /api/admin/usuarios/<id>/remover-cpf). */
export function removeAdminUserCpf(
	userId: number
): Promise<{ usuario: AdminUser }> {
	return post<{ usuario: AdminUser }>(`/api/admin/usuarios/${userId}/remover-cpf`);
}

/** Exclui um usuário (DELETE /api/admin/usuarios/<id>). */
export function deleteAdminUser(
	userId: number
): Promise<{ deleted_id: number }> {
	return del<{ deleted_id: number }>(`/api/admin/usuarios/${userId}`);
}
