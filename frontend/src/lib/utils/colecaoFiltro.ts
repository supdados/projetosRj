/**
 * Opções do filtro "Coleção" da Lista de Projetos (`?colecao=`).
 *
 * Regra do servidor (`colecao_com_papel_criterion`): o filtro vale para a
 * coleção de que sou DONO ou em que tenho share ACEITO/legado, sempre cruzado
 * com a visibilidade de cada projeto — um share não mostra projeto que a
 * pessoa não veria. O índice (`GET /api/colecoes`) já traz exatamente essas
 * (convite pendente fica fora), então o menu oferece todas: as minhas
 * primeiro (Favoritos incluída, na ordem do índice) e as recebidas no grupo
 * "Compartilhadas comigo".
 *
 * Exemplo:
 *   const options = opcoesDoFiltroColecao(colecoesCatalog);
 */

import type { ColecaoResumo } from '$lib/types/collections';
import type { SelectMenuOption } from '$lib/types/selectMenu';

/** Cabeçalhos dos grupos — os mesmos rótulos dos chips de escopo do índice. */
export const GRUPO_MINHAS = 'Minhas coleções';
export const GRUPO_COMPARTILHADAS = 'Compartilhadas comigo';

function opcaoDaColecao(colecao: Pick<ColecaoResumo, 'id' | 'nome'>, grupo?: string): SelectMenuOption {
	return grupo
		? { value: String(colecao.id), label: colecao.nome, group: grupo }
		: { value: String(colecao.id), label: colecao.nome };
}

/** Minhas + recebidas; sem recebida, a lista fica sem cabeçalho (não há o que separar). */
export function opcoesDoFiltroColecao(
	colecoes: readonly Pick<ColecaoResumo, 'id' | 'nome' | 'papel'>[]
): SelectMenuOption[] {
	const minhas = colecoes.filter((c) => c.papel === 'dono');
	const recebidas = colecoes.filter((c) => c.papel !== 'dono');
	const grupoDasMinhas = recebidas.length > 0 ? GRUPO_MINHAS : undefined;
	return [
		...minhas.map((c) => opcaoDaColecao(c, grupoDasMinhas)),
		...recebidas.map((c) => opcaoDaColecao(c, GRUPO_COMPARTILHADAS))
	];
}
