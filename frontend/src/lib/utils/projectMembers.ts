/**
 * Utils PUROS dos convites por projeto (S4): rótulos PT-BR, expiração padrão de
 * 90 dias (§7) e tradução dos erros das rotas novas.
 *
 * A ordem de `CONVITE_PAPEL_OPTIONS` é a do rank (maior → menor) e para no
 * `editor`: gestor NUNCA é concedível por convite — o teto é validado no
 * backend (`models/project_member.papeis_de_convite`), aqui é só a superfície.
 */

import type { ConvitePapel } from '$lib/types/projectMembers';
import type { ProjectAccessVia } from '$lib/types/entities';

/** Papel sugerido em um convite novo (o mais restritivo). */
export const CONVITE_PAPEL_PADRAO: ConvitePapel = 'leitor';

/** Janela padrão sugerida no formulário (§7: colaboração pontual em governo). */
export const CONVITE_EXPIRACAO_DIAS = 90;

export const CONVITE_PAPEL_OPTIONS: ReadonlyArray<{ value: ConvitePapel; label: string }> = [
	{ value: 'editor', label: 'Editor' },
	{ value: 'leitor', label: 'Leitor' }
];

/** Rótulo PT-BR do papel do convite; desconhecido cai no padrão. */
export function convitePapelLabel(papel: string | null | undefined): string {
	return papel === 'editor' ? 'Editor' : 'Leitor';
}

/** Normaliza o papel vindo da API (ausente/desconhecido ⇒ `leitor`). */
export function normalizeConvitePapel(raw: string | null | undefined): ConvitePapel {
	const option = CONVITE_PAPEL_OPTIONS.find((o) => o.value === raw);
	return option ? option.value : CONVITE_PAPEL_PADRAO;
}

/** Rótulo PT-BR do status do convite; desconhecido é tratado como revogado. */
export function conviteStatusLabel(status: string | null | undefined): string {
	if (status === 'ativo') return 'Ativo';
	if (status === 'expirado') return 'Expirado';
	return 'Revogado';
}

/** Tom do `Badge` para cada status (ativo = sucesso; expirado = alerta). */
export function conviteStatusTone(
	status: string | null | undefined
): 'success' | 'warning' | 'neutral' {
	if (status === 'ativo') return 'success';
	if (status === 'expirado') return 'warning';
	return 'neutral';
}

/**
 * Data ISO (YYYY-MM-DD) de `dias` à frente — semente do campo de expiração.
 *
 * Exemplo: `expiracaoPadraoIso(new Date('2026-01-01T12:00:00Z'))` ⇒ `'2026-04-01'`.
 */
export function expiracaoPadraoIso(
	agora: Date = new Date(),
	dias: number = CONVITE_EXPIRACAO_DIAS
): string {
	const alvo = new Date(agora.getTime());
	alvo.setUTCDate(alvo.getUTCDate() + dias);
	return alvo.toISOString().slice(0, 10);
}

/** Badge "Convidado": só quando o acesso passa por convite (`access_via`). */
export function isAcessoPorConvite(accessVia: ProjectAccessVia | null | undefined): boolean {
	return accessVia === 'convite' || accessVia === 'ambos';
}

/**
 * Mensagem PT-BR para as falhas das rotas de membro (contrato anti-enumeração
 * do §6.3: 404 = não vê o projeto OU flag off; 403 = vê mas não gerencia).
 */
export function conviteErrorMessage(status: number, code: string): string {
	if (status === 404 || code === 'not_found') return 'Projeto não encontrado.';
	if (status === 403 || code === 'forbidden')
		return 'Você não pode gerenciar os membros deste projeto.';
	if (status === 400 || code === 'validation') return 'Dados do convite inválidos.';
	return 'Não foi possível concluir a operação.';
}
