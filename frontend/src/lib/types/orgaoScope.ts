/**
 * Tipos da árvore de órgãos VISÍVEL do usuário (seletor da topnav).
 *
 * Espelham `routes/orgao_scope.py` (`get_visible_orgao_tree` +
 * `build_nested_orgao_tree`), expostos por `GET /api/orgaos/escopo` no envelope
 * canônico. A árvore é aninhada: cada nó carrega seus `children` e as flags de
 * escopo (`is_user_orgao`/`is_user_ancestor`) que a topnav usa para destacar o
 * órgão do usuário.
 */

/** Nó da árvore de órgãos visível (aninhado em `children`). */
export interface OrgaoTreeNode {
	id: number;
	sigla: string | null;
	nome: string | null;
	tipo: string | null;
	pai_id: number | null;
	is_user_orgao: boolean;
	is_user_ancestor: boolean;
	is_inactive: boolean;
	children: OrgaoTreeNode[];
}

/** Carga de GET /api/orgaos/escopo (já desempacotada do envelope). */
export interface OrgaoScopeResult {
	tree: OrgaoTreeNode[];
}
