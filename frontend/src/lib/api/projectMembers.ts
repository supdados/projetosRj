/**
 * Acesso tipado aos convites por projeto (S4/§6.5), em `routes/api/project_members.py`.
 *
 *   GET    /api/projetos/<id>/membros        -> { diretos, herdados }
 *   POST   /api/projetos/<id>/membros        -> cria/reativa convite
 *   PUT    /api/projetos/<id>/membros/<mid>  -> altera papel/expiração
 *   DELETE /api/projetos/<id>/membros/<mid>  -> revoga (soft)
 *   GET    /api/usuarios/busca?q=            -> { usuarios } convidáveis
 *
 * As mutações devolvem `void` de propósito: a UI RE-BUSCA a lista depois de
 * cada uma, então nenhum estado depende do corpo da resposta.
 *
 * Falhas chegam como `ApiClientError` (`client.ts`) com `code`/`status`:
 *   - 404 `not_found`  — projeto inexistente, rank 0 no projeto OU
 *     `CONVITES_HABILITADOS` off (anti-enumeração: os três respondem o MESMO
 *     corpo, "não existe ou você não tem acesso");
 *   - 403 `forbidden`  — vê o projeto mas não pode gerenciar membros;
 *   - 401 já redireciona para /login dentro do `client.ts`.
 * Use `conviteErrorMessage` (`$lib/utils/projectMembers`) para o texto PT-BR.
 */

import { get, post, put, del } from './client';
import type {
	ConviteCreatePayload,
	ConviteUpdatePayload,
	ProjectMembersData,
	UsuarioBuscaData,
	UsuarioConvidavel
} from '$lib/types/projectMembers';

/** Membros diretos + herdados de um projeto (só para quem gerencia). */
export function fetchProjectMembers(
	projectId: number,
	signal?: AbortSignal
): Promise<ProjectMembersData> {
	return get<ProjectMembersData>(`/api/projetos/${projectId}/membros`, signal);
}

/** Cria (ou reativa) o convite de um usuário no projeto. */
export async function createProjectMember(
	projectId: number,
	payload: ConviteCreatePayload
): Promise<void> {
	await post<unknown>(`/api/projetos/${projectId}/membros`, payload);
}

/** Altera papel e/ou expiração de um convite existente. */
export async function updateProjectMember(
	projectId: number,
	memberId: number,
	payload: ConviteUpdatePayload
): Promise<void> {
	await put<unknown>(`/api/projetos/${projectId}/membros/${memberId}`, payload);
}

/** Revoga um convite (soft: `revoked_at` + `revoked_by_id` no backend). */
export async function revokeProjectMember(projectId: number, memberId: number): Promise<void> {
	await del<unknown>(`/api/projetos/${projectId}/membros/${memberId}`);
}

/** Autocomplete de convidáveis; `q` vazio não chega a consultar o servidor. */
export async function searchInvitableUsers(
	q: string,
	signal?: AbortSignal
): Promise<UsuarioConvidavel[]> {
	const termo = q.trim();
	if (!termo) return [];
	const data = await get<UsuarioBuscaData>(
		`/api/usuarios/busca?q=${encodeURIComponent(termo)}`,
		signal
	);
	return data.usuarios;
}
