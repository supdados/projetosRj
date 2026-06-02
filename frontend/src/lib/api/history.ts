/**
 * Acesso tipado ao endpoint de Historico de projeto
 * (GET /api/projetos/<id>/historico).
 *
 * Devolve a `ProjectHistoryData` ja desempacotada do envelope (`client.ts`),
 * respeitando o `orgao_scope` aplicado no servidor (`user_can_access_project`).
 * Em falha, `client.ts` lanca `ApiClientError` com `code`:
 *   - `not_found` (404) quando o projeto nao existe;
 *   - `forbidden` (403) quando esta fora do escopo do usuario;
 *   - `unauthenticated` (401) ja redireciona para /login.
 */

import { get } from './client';
import type { ProjectHistoryData } from '$lib/types/history';

/** Busca o historico de um projeto pelo id. */
export function fetchProjectHistory(
	projectId: number,
	signal?: AbortSignal
): Promise<ProjectHistoryData> {
	return get<ProjectHistoryData>(`/api/projetos/${projectId}/historico`, signal);
}
