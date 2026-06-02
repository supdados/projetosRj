/**
 * Acesso tipado ao CRUD de Usuários (Admin), consumindo
 * `/api/admin/usuarios*` (routes/api/admin_users.py) no envelope canônico.
 *
 * Leituras simples usam `client.get` (desempacota `data`). Mutations usam
 * `client.post` (que injeta `X-CSRFToken` e trata 401/CSRF) — espelhando as
 * rotas Flask POST da Fase 4.
 *
 * Exceção: a LISTA paginada precisa da `meta` do envelope (page/per_page/
 * total/total_pages), que `client.get` descarta ao devolver só `data`. Como
 * `client.ts` NÃO pode ser editado, esta função faz um fetch GET próprio
 * (sem CSRF — leitura) e reaproveita `ApiClientError` para os erros. O 401 é
 * tratado aqui com a MESMA semântica de `client.ts` (navegação top-level para
 * /login), porque o callback Gov.br depende do cookie SameSite=Strict.
 */

import { get, getWithMeta, post } from './client';
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

/**
 * Lista paginada de usuários (GET /api/admin/usuarios), capturando a `meta`
 * de paginação via `getWithMeta` do client (que preserva `meta` e trata
 * 401/CSRF com a mesma semântica do `get`/`post`).
 */
export async function fetchAdminUsers(
	page = 1,
	signal?: AbortSignal
): Promise<AdminUsersListResult> {
	const qs = page > 1 ? `?page=${page}` : '';
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
	return { usuarios: data.usuarios, meta: pageMeta };
}

/**
 * Opções de órgãos (ativos, com profundidade) para o form de CRIAÇÃO de
 * usuário. Usa o endpoint enveloped GET /api/admin/orgaos/opcoes, que já
 * devolve a lista achatada (somente ativos, ordenados por `(depth, sigla)`)
 * — o front não precisa mais achatar a árvore de `/api/admin/orgaos`.
 */
export async function fetchOrgaoOptionsForUser(
	signal?: AbortSignal
): Promise<AdminOrgaoOption[]> {
	const opcoes = await get<AdminOrgaoOption[]>('/api/admin/orgaos/opcoes', signal);
	return Array.isArray(opcoes) ? opcoes : [];
}

/** Detalhe + opções de órgãos de um usuário (GET /api/admin/usuarios/<id>). */
export function fetchAdminUserDetail(
	userId: number,
	signal?: AbortSignal
): Promise<AdminUserDetail> {
	return get<AdminUserDetail>(`/api/admin/usuarios/${userId}`, signal);
}

/** Cria um usuário (POST /api/admin/usuarios). */
export function createAdminUser(
	payload: AdminUserCreatePayload
): Promise<{ usuario: AdminUser }> {
	return post<{ usuario: AdminUser }>('/api/admin/usuarios', payload);
}

/** Edita um usuário (POST /api/admin/usuarios/<id>). */
export function updateAdminUser(
	userId: number,
	payload: AdminUserUpdatePayload
): Promise<{ usuario: AdminUser }> {
	return post<{ usuario: AdminUser }>(`/api/admin/usuarios/${userId}`, payload);
}

/** Remove CPF + vínculo Gov.br (POST /api/admin/usuarios/<id>/remover-cpf). */
export function removeAdminUserCpf(
	userId: number
): Promise<{ usuario: AdminUser }> {
	return post<{ usuario: AdminUser }>(`/api/admin/usuarios/${userId}/remover-cpf`);
}

/** Exclui um usuário (POST /api/admin/usuarios/<id>/delete). */
export function deleteAdminUser(
	userId: number
): Promise<{ deleted_id: number }> {
	return post<{ deleted_id: number }>(`/api/admin/usuarios/${userId}/delete`);
}
