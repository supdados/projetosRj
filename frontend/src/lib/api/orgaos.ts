/**
 * Acesso tipado à árvore de órgãos VISÍVEL do usuário (seletor da topnav).
 *
 * Espelha `routes/orgao_scope.py` (`get_visible_orgao_tree` +
 * `build_nested_orgao_tree`), exposto por `GET /api/orgaos/escopo`. A árvore é
 * ANINHADA: cada nó traz `children` e as flags de escopo
 * (`is_user_orgao`/`is_user_ancestor`) que a topnav usa para destacar o órgão
 * do usuário e abrir o caminho até ele.
 *
 * O client (`get`) já desempacota o envelope canônico e devolve `data`.
 */

import { get } from './client';
import type { OrgaoScopeResult, OrgaoTreeNode } from '$lib/types/orgaoScope';

/** Busca a árvore de órgãos visível (aninhada). */
export async function fetchOrgaoScopeTree(signal?: AbortSignal): Promise<OrgaoTreeNode[]> {
	const result = await get<OrgaoScopeResult>('/api/orgaos/escopo', signal);
	return result.tree ?? [];
}
