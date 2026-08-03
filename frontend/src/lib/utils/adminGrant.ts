/**
 * Espelho no cliente da politica `services/admin_grant_policy.py`.
 *
 * O backend e a fonte da verdade (403 `forbidden`); isto so evita que o usuario
 * bata numa parede clicando em algo que sera negado.
 */

export const MSG_SO_SUPER_ADMIN_ALTERA_PERFIL =
	'Somente o administrador principal pode alterar esta permissão.';

export const MSG_SO_SUPER_ADMIN_GERE_ADMIN =
	'Somente o administrador principal pode editar ou excluir outro administrador.';

/** Quem enxerga a tela (`GET /api/me`); `null` enquanto a sessao nao carregou. */
export interface GrantViewer {
	id: number;
	is_super_admin?: boolean;
}

/** Alvo da acao (linha da lista ou detalhe do admin). */
export interface GrantTarget {
	id: number;
	is_admin: boolean;
	is_super_admin?: boolean;
}

/**
 * True somente para o admin principal. Fail-closed: viewer ausente ou payload
 * de backend antigo (sem `is_super_admin`) devolve `false`.
 *
 * @example canGrantAdmin({ id: 1, is_super_admin: true }) // true
 */
export function canGrantAdmin(viewer: GrantViewer | null | undefined): boolean {
	return Boolean(viewer?.is_super_admin);
}

/**
 * True quando o viewer pode editar o alvo: super admin edita qualquer um,
 * admin comum edita a si mesmo e usuarios que nao sao administradores.
 *
 * @example canManageUser({ id: 2 }, { id: 3, is_admin: true }) // false
 */
export function canManageUser(
	viewer: GrantViewer | null | undefined,
	target: GrantTarget
): boolean {
	if (!viewer) return false;
	if (canGrantAdmin(viewer)) return true;
	if (viewer.id === target.id) return true;
	return !target.is_admin && !target.is_super_admin;
}

/**
 * True quando o viewer pode excluir o alvo. O admin principal e indelevel e
 * ninguem exclui a propria conta (guard ja existente na lista).
 *
 * @example canDeleteUser({ id: 1, is_super_admin: true }, { id: 1, is_admin: true }) // false
 */
export function canDeleteUser(
	viewer: GrantViewer | null | undefined,
	target: GrantTarget
): boolean {
	if (!viewer) return false;
	if (target.is_super_admin) return false;
	if (viewer.id === target.id) return false;
	return canManageUser(viewer, target);
}
