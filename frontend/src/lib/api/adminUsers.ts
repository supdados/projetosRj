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

import { get, post, ApiClientError } from './client';
import type { ApiResult } from '$lib/types/api';
import type {
	AdminUsersListResult,
	AdminUserDetail,
	AdminUser,
	AdminUserCreatePayload,
	AdminUserUpdatePayload,
	AdminUsersPageMeta,
	AdminOrgaoOption
} from '$lib/types/adminUsers';

/** Caminho de login do Flask (rota imutável). Navegação top-level. */
const LOGIN_PATH = '/login';

/** Envelope cru de sucesso da lista, incluindo a `meta` de paginação. */
interface AdminUsersListEnvelope {
	usuarios: AdminUser[];
}

/**
 * Lista paginada de usuários (GET /api/admin/usuarios), capturando a `meta`
 * que o `client.get` padrão descartaria. Em 401 navega para /login (igual a
 * client.ts); demais falhas viram `ApiClientError`.
 */
export async function fetchAdminUsers(
	page = 1,
	signal?: AbortSignal
): Promise<AdminUsersListResult> {
	const qs = page > 1 ? `?page=${page}` : '';
	const res = await fetch(`/api/admin/usuarios${qs}`, {
		method: 'GET',
		credentials: 'include',
		headers: { Accept: 'application/json' },
		signal
	});
	const body = (await res.json()) as ApiResult<AdminUsersListEnvelope> & {
		meta?: AdminUsersPageMeta;
	};

	if (!body.ok) {
		const { code, message } = body.error;
		if (res.status === 401 || code === 'unauthenticated') {
			if (typeof window !== 'undefined') window.location.assign(LOGIN_PATH);
			throw new ApiClientError('unauthenticated', message, res.status);
		}
		throw new ApiClientError(code, message, res.status);
	}

	const meta: AdminUsersPageMeta = body.meta ?? {
		page,
		per_page: body.data.usuarios.length,
		total: body.data.usuarios.length,
		total_pages: 1
	};
	return { usuarios: body.data.usuarios, meta };
}

/**
 * Nó da árvore de órgãos (GET /api/admin/orgaos), usado APENAS para popular o
 * seletor de órgãos do form de CRIAÇÃO — onde não há `usuario/<id>` cujo
 * detalhe traga `orgaos_options`. Espelha `serialize_orgao_node`.
 */
interface OrgaoTreeNode {
	id: number;
	sigla: string;
	nome: string;
	ativo: boolean;
	filhos: OrgaoTreeNode[];
}

interface OrgaoTreeData {
	arvore: OrgaoTreeNode[];
}

/** Achata a árvore (pré-ordem) em opções ativas com profundidade 1-based. */
function flattenActiveOrgaos(
	nodes: OrgaoTreeNode[],
	depth: number,
	acc: AdminOrgaoOption[]
): AdminOrgaoOption[] {
	for (const node of nodes) {
		if (node.ativo) {
			acc.push({ id: node.id, sigla: node.sigla, nome: node.nome, depth });
		}
		flattenActiveOrgaos(node.filhos ?? [], depth + 1, acc);
	}
	return acc;
}

/**
 * Opções de órgãos (ativos, com profundidade) para o form de CRIAÇÃO de
 * usuário. Reaproveita o GET da árvore de órgãos (`/api/admin/orgaos`) e a
 * achata, espelhando a semântica de `_list_orgaos_with_depth` (somente ativos,
 * indentação por profundidade) que o detalhe de usuário já entrega na edição.
 */
export async function fetchOrgaoOptionsForUser(
	signal?: AbortSignal
): Promise<AdminOrgaoOption[]> {
	const data = await get<OrgaoTreeData>('/api/admin/orgaos', signal);
	return flattenActiveOrgaos(data.arvore ?? [], 1, []);
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
