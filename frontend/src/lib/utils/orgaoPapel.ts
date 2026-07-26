/**
 * Papel do vínculo de área (`user_orgao.papel`) no front: rótulos PT-BR e
 * conversões puras entre o que a API devolve (`orgaos: [{id, papel}]`) e o que
 * o form envia (`orgaos: [{orgao_id, papel}]`).
 *
 * A ordem de `PAPEL_OPTIONS` é a do rank (maior → menor), espelhando
 * `PAPEL_RANK` de `services/authorization.py`. Nenhuma decisão de permissão
 * acontece aqui — autorização é server-side.
 */

import type {
	AdminUserOrgaoRef,
	AdminUserOrgaoVinculo,
	OrgaoPapel
} from '$lib/types/adminUsers';

/** Papel default de um vínculo novo (mesmo default do backend). */
export const PAPEL_PADRAO: OrgaoPapel = 'gestor';

export const PAPEL_OPTIONS: ReadonlyArray<{ value: OrgaoPapel; label: string }> = [
	{ value: 'gestor', label: 'Gestor' },
	{ value: 'editor', label: 'Editor' },
	{ value: 'leitor', label: 'Leitor' }
];

/** Rótulo PT-BR do papel; papel desconhecido cai no rótulo do default. */
export function papelLabel(papel: OrgaoPapel | string | null | undefined): string {
	const option = PAPEL_OPTIONS.find((o) => o.value === papel);
	return (option ?? PAPEL_OPTIONS[0]).label;
}

/** Normaliza o papel vindo da API (ausente/desconhecido ⇒ `gestor`). */
export function normalizePapel(raw: string | null | undefined): OrgaoPapel {
	const option = PAPEL_OPTIONS.find((o) => o.value === raw);
	return option ? option.value : PAPEL_PADRAO;
}

/**
 * Vínculos do form a partir de `serialize_admin_user.orgaos`, limitados às
 * áreas presentes no seletor. Vínculos a órgãos INATIVOS não são opção e ficam
 * de fora: o backend os preserva sozinho (`_inactive_current_pairs`).
 */
export function vinculosFromRefs(
	refs: readonly AdminUserOrgaoRef[],
	selectableIds: ReadonlySet<number>
): AdminUserOrgaoVinculo[] {
	return refs
		.filter((ref) => selectableIds.has(ref.id))
		.map((ref) => ({ orgao_id: ref.id, papel: normalizePapel(ref.papel) }));
}

/** Reconstrói os vínculos a partir da seleção de áreas, preservando os papéis já escolhidos. */
export function mergeVinculosComSelecao(
	vinculos: readonly AdminUserOrgaoVinculo[],
	selectedIds: readonly number[]
): AdminUserOrgaoVinculo[] {
	const papelById = new Map(vinculos.map((v) => [v.orgao_id, v.papel]));
	return selectedIds.map((orgaoId) => ({
		orgao_id: orgaoId,
		papel: papelById.get(orgaoId) ?? PAPEL_PADRAO
	}));
}

/** Troca o papel de UM vínculo (retorna nova lista; sem mutação). */
export function setVinculoPapel(
	vinculos: readonly AdminUserOrgaoVinculo[],
	orgaoId: number,
	papel: OrgaoPapel
): AdminUserOrgaoVinculo[] {
	return vinculos.map((v) => (v.orgao_id === orgaoId ? { ...v, papel } : v));
}
