/**
 * Estado do mapeamento coluna-do-CSV → campo do projeto na revisão da importação:
 * cada campo pertence a no máximo uma coluna (escolher um campo já usado devolve
 * a coluna antiga para "Ignorar"), mesma unicidade que o backend revalida.
 */

/** Índice da coluna do CSV → campo escolhido (`null` = ignorar a coluna). */
export type ImportFieldMapping = Record<number, string | null>;

/**
 * Aplica a escolha de `campo` na coluna `indice` e devolve um NOVO mapeamento
 * com a unicidade resolvida.
 *
 * @example
 * applyFieldSelection({ 0: 'titulo', 2: null }, 2, 'titulo'); // { 0: null, 2: 'titulo' }
 */
export function applyFieldSelection(
	mapping: ImportFieldMapping,
	indice: number,
	campo: string | null
): ImportFieldMapping {
	const next: ImportFieldMapping = { ...mapping, [indice]: campo };
	if (campo === null) return next;
	for (const chave of Object.keys(next)) {
		const outro = Number(chave);
		if (outro !== indice && next[outro] === campo) next[outro] = null;
	}
	return next;
}

/** Quantidade de colunas com campo escolhido. */
export function countMapped(mapping: ImportFieldMapping): number {
	return Object.values(mapping).filter((campo) => campo !== null).length;
}

/** `true` quando alguma coluna está mapeada como título (obrigatório no envio). */
export function hasTitulo(mapping: ImportFieldMapping): boolean {
	return Object.values(mapping).includes('titulo');
}
