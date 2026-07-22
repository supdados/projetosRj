/**
 * Resolve o deep-link `?focus_etapa=<id>` (busca global -> detalhe do projeto).
 *
 * Devolve o id da etapa-alvo apenas quando é um inteiro positivo E existe entre
 * as etapas carregadas; caso contrário `null` (ignora silenciosamente). Puro,
 * para ser testável sem DOM.
 *
 * @example
 *   resolveFocusEtapaId('?focus_etapa=12', [10, 12]) // 12
 *   resolveFocusEtapaId('?focus_etapa=99', [10, 12]) // null
 */
export function resolveFocusEtapaId(search: string, etapaIds: number[]): number | null {
	const raw = new URLSearchParams(search).get('focus_etapa');
	if (raw === null) return null;
	const id = Number(raw);
	if (!Number.isInteger(id) || id <= 0) return null;
	return etapaIds.includes(id) ? id : null;
}
