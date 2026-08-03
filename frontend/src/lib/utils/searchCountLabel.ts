/**
 * Rotulo do contador da busca global quando o backend satura o total no teto.
 *
 * `routes/search.py` conta com `SELECT count(*) FROM (<query> LIMIT cap)` para nao
 * varrer as tabelas a cada tecla do typeahead: acima do teto o numero deixa de ser
 * exato e vira "99+" (teto 100). Sem flag de saturacao o total e exato.
 */

/** Metadados opcionais de teto de contagem (`meta.counts_capped*`). */
export interface SearchCountCapMeta {
	capped?: boolean;
	capAt?: number | null;
}

/**
 * Formata o total de um grupo: exato, ou `${cap - 1}+` quando saturou no teto.
 *
 * Exemplo: `formatSearchCount(100, { capped: true, capAt: 100 })` -> `'99+'`.
 */
export function formatSearchCount(total: number, meta: SearchCountCapMeta = {}): string {
	const { capped = false, capAt = null } = meta;
	if (capped && capAt && capAt > 1) return `${capAt - 1}+`;
	return String(total);
}
