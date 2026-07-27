/**
 * Utils PUROS dos convites por projeto (S4): rótulos PT-BR, períodos de
 * expiração do formulário (§7) e tradução dos erros das rotas novas.
 *
 * A ordem de `CONVITE_PAPEL_OPTIONS` é a do rank (maior → menor) e para no
 * `editor`: gestor NUNCA é concedível por convite — o teto é validado no
 * backend (`models/project_member.papeis_de_convite`), aqui é só a superfície.
 */

import type { ConvitePapel, ConviteLoteResultado } from '$lib/types/projectMembers';
import type { ProjectAccessVia } from '$lib/types/entities';
import { MSG_PROJETO_INACESSIVEL } from '$lib/utils/accessErrorMessages';

/** Papel sugerido em um convite novo (o mais restritivo). */
export const CONVITE_PAPEL_PADRAO: ConvitePapel = 'leitor';

/** Janela máxima do §7; hoje só o default do argumento de `expiracaoPadraoIso`. */
export const CONVITE_EXPIRACAO_DIAS = 90;

/** Período sugerido em um convite novo (§7: colaboração pontual em governo). */
export const CONVITE_PERIODO_PADRAO_DIAS = 30;

/**
 * Períodos oferecidos no convite: quem convida raciocina em duração ("mais um
 * mês"), não em data absoluta — a data ISO é derivada só no envio.
 * `dias: null` = indeterminado ⇒ `expires_at: null` (sem expiração no backend).
 */
export const CONVITE_PERIODO_OPTIONS: ReadonlyArray<{
	value: string;
	label: string;
	dias: number | null;
}> = [
	{ value: '15', label: '15 dias', dias: 15 },
	{ value: '30', label: '30 dias', dias: 30 },
	{ value: '45', label: '45 dias', dias: 45 },
	{ value: 'indeterminado', label: 'Indeterminado', dias: null }
];

export const CONVITE_PAPEL_OPTIONS: ReadonlyArray<{ value: ConvitePapel; label: string }> = [
	{ value: 'editor', label: 'Editor' },
	{ value: 'leitor', label: 'Leitor' }
];

/** Valor da opção que representa `dias` no seletor (null ⇒ indeterminado). */
export function convitePeriodoValue(dias: number | null): string {
	return dias == null ? 'indeterminado' : String(dias);
}

/** Dias do período escolhido no seletor; ausente/desconhecido cai no padrão. */
export function convitePeriodoDias(raw: string | null | undefined): number | null {
	const option = CONVITE_PERIODO_OPTIONS.find((o) => o.value === raw);
	return option ? option.dias : CONVITE_PERIODO_PADRAO_DIAS;
}

/** Rótulo PT-BR do papel do convite; desconhecido cai no padrão. */
export function convitePapelLabel(papel: string | null | undefined): string {
	return papel === 'editor' ? 'Editor' : 'Leitor';
}

/** Normaliza o papel vindo da API (ausente/desconhecido ⇒ `leitor`). */
export function normalizeConvitePapel(raw: string | null | undefined): ConvitePapel {
	const option = CONVITE_PAPEL_OPTIONS.find((o) => o.value === raw);
	return option ? option.value : CONVITE_PAPEL_PADRAO;
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

/** `expires_at` do período escolhido — indeterminado vira `null` (sem expiração). */
export function expiracaoDoPeriodo(dias: number | null, agora: Date = new Date()): string | null {
	return dias == null ? null : expiracaoPadraoIso(agora, dias);
}

/** Trecho "N pessoa(s) convidada(s)" — zero some do resumo em vez de virar "0". */
function trechoLote(n: number, singular: string, plural: string): string {
	if (n <= 0) return '';
	return `${n} ${n === 1 ? singular : plural}`;
}

/**
 * Resumo discreto do convite em lote por área, com os pulos traduzidos para o
 * motivo real ("já tinham acesso": próprio autor, acesso por área ou convite
 * ativo). Órgão sem ninguém elegível devolve tudo zerado.
 *
 * Exemplo: `conviteLoteResumo({convidados: 12, reativados: 0, pulados: 3})`
 * ⇒ `'12 pessoas convidadas · 3 já tinham acesso'`.
 */
export function conviteLoteResumo(resultado: ConviteLoteResultado): string {
	const partes = [
		trechoLote(resultado.convidados, 'pessoa convidada', 'pessoas convidadas'),
		trechoLote(resultado.reativados, 'convite reativado', 'convites reativados'),
		trechoLote(resultado.pulados, 'já tinha acesso', 'já tinham acesso')
	].filter(Boolean);
	return partes.length > 0 ? partes.join(' · ') : 'Ninguém novo para convidar nesta área.';
}

/** Badge "Convidado": só quando o acesso passa por convite (`access_via`). */
export function isAcessoPorConvite(accessVia: ProjectAccessVia | null | undefined): boolean {
	return accessVia === 'convite' || accessVia === 'ambos';
}

/**
 * Mensagem PT-BR para as falhas das rotas de membro (contrato anti-enumeração
 * do §6.3: 404 = não existe, não vê o projeto ou flag off — os três com a MESMA
 * mensagem; 403 = vê o projeto mas não gerencia membros).
 */
export function conviteErrorMessage(status: number, code: string): string {
	if (status === 404 || code === 'not_found') return MSG_PROJETO_INACESSIVEL;
	if (status === 403 || code === 'forbidden')
		return 'Você não pode gerenciar os membros deste projeto.';
	if (status === 400 || code === 'validation') return 'Dados do convite inválidos.';
	return 'Não foi possível concluir a operação.';
}
