/**
 * Lista do seletor de projetos de coleção com a seleção sempre à vista: projeto
 * marcado que o filtro de status escondeu (ex.: Finalizado marcado com "Mostrar
 * todos" e depois o toggle desligado, ou sugestão de IA) volta fixado no topo.
 * Sem isso o contador diria "3 selecionados" com só 2 caixas marcadas na tela.
 *
 * Só fixa o que já passou por uma busca (`known`): sem o objeto não há o que
 * renderizar. A fixação é um retrato do momento da busca — desmarcar não tira a
 * linha de baixo do cursor; ela sai na próxima busca.
 *
 * Exemplo: `pinSelectedProjects([vigente], [finalizado.id], known)` devolve
 * `[finalizado, vigente]`.
 */
export function pinSelectedProjects<T extends { id: number }>(
	results: readonly T[],
	selectedIds: readonly number[],
	known: ReadonlyMap<number, T>
): T[] {
	const inResults = new Set(results.map((item) => item.id));
	const pinned = selectedIds
		.filter((id) => !inResults.has(id))
		.map((id) => known.get(id))
		.filter((item): item is T => item !== undefined);
	return [...pinned, ...results];
}
