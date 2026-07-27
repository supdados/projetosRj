/**
 * Acesso tipado ao endpoint de Historico de projeto
 * (GET /api/projetos/<id>/historico).
 *
 * Devolve a `ProjectHistoryData` ja desempacotada do envelope (`client.ts`),
 * respeitando o rank efetivo do usuario no projeto. Em falha, `client.ts` lanca
 * `ApiClientError` com `code` (contrato S5):
 *   - `not_found` (404) quando o projeto nao existe OU o usuario nao tem acesso
 *     — casos indistinguiveis por design; a tela mostra "não existe ou você não
 *     tem acesso" e nunca revela qual dos dois;
 *   - `unauthenticated` (401) ja redireciona para /login.
 * Nao ha 403 aqui: ler o historico exige apenas rank leitor.
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
