/**
 * Acesso tipado ao CRUD de Órgãos (árvore) do Admin — Fase 4.
 *
 * Encapsula os endpoints `/api/admin/orgaos*` (`routes/api/admin_orgaos.py`),
 * protegidos por `api_admin_required` (403 para não-admin, 401 sem sessão). As
 * leituras usam `client.get`. CRUD de recurso é RESTful: editar usa
 * `client.put` e excluir usa `client.del`. As ações (move/reorder/toggle-ativo)
 * continuam em `client.post` — são comandos, não CRUD de recurso. Todos injetam
 * o `X-CSRFToken`.
 *
 * O envelope `{ok, data}` é desempacotado por `client.ts`; em falha lança
 * `ApiClientError` (com `code`/`status`), que a tela traduz para a UI.
 */

import { get, post, put, del } from './client';
import type {
	OrgaoDetailData,
	OrgaoForm,
	OrgaoFormPayload,
	OrgaoTreeData,
	ReorderDirection
} from '$lib/types/adminOrgaos';

const BASE = '/api/admin/orgaos';

/** Carrega a árvore completa de órgãos + catálogos (tipos, ranks, candidatos). */
export function fetchOrgaoTree(signal?: AbortSignal): Promise<OrgaoTreeData> {
	return get<OrgaoTreeData>(BASE, signal);
}

/** Carrega um órgão para o form de edição + candidatos a pai e catálogos. */
export function fetchOrgaoDetail(
	orgaoId: number,
	signal?: AbortSignal
): Promise<OrgaoDetailData> {
	return get<OrgaoDetailData>(`${BASE}/${orgaoId}`, signal);
}

/** Cria um órgão (subunidade ou raiz). Backend valida tipo/pai/profundidade. */
export function createOrgao(
	payload: OrgaoFormPayload,
	signal?: AbortSignal
): Promise<{ orgao: OrgaoForm }> {
	return post<{ orgao: OrgaoForm }>(BASE, payload, signal);
}

/** Edita um órgão existente (PUT — CRUD RESTful de recurso). */
export function updateOrgao(
	orgaoId: number,
	payload: OrgaoFormPayload,
	signal?: AbortSignal
): Promise<{ orgao: OrgaoForm }> {
	return put<{ orgao: OrgaoForm }>(`${BASE}/${orgaoId}`, payload, signal);
}

/** Exclui um órgão (DELETE; sem filhos e não-raiz; o backend protege os demais). */
export function deleteOrgao(
	orgaoId: number,
	signal?: AbortSignal
): Promise<{ deleted_id: number }> {
	return del<{ deleted_id: number }>(`${BASE}/${orgaoId}`, undefined, signal);
}

/** Move um órgão para um novo pai (ou raiz, com `pai_id` null). */
export function moveOrgao(
	orgaoId: number,
	paiId: number | null,
	signal?: AbortSignal
): Promise<{ orgao: OrgaoForm }> {
	return post<{ orgao: OrgaoForm }>(`${BASE}/${orgaoId}/move`, { pai_id: paiId }, signal);
}

/** Reordena um órgão entre os irmãos (idempotente nos extremos). */
export function reorderOrgao(
	orgaoId: number,
	direction: ReorderDirection,
	signal?: AbortSignal
): Promise<{ orgao: OrgaoForm }> {
	return post<{ orgao: OrgaoForm }>(`${BASE}/${orgaoId}/reorder`, { direction }, signal);
}

/** Alterna ativo/inativo de um órgão. */
export function toggleOrgaoAtivo(
	orgaoId: number,
	signal?: AbortSignal
): Promise<{ orgao: OrgaoForm }> {
	return post<{ orgao: OrgaoForm }>(`${BASE}/${orgaoId}/toggle-ativo`, undefined, signal);
}
