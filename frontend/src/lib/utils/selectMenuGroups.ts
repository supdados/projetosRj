/**
 * Cabeçalhos de grupo do `SelectMenu`: onde cada grupo de opções começa e a
 * que cabeçalho cada opção pertence (para o `aria-describedby` — o leitor de
 * tela ouve "Obras, Compartilhadas comigo" em vez de só o nome).
 *
 * Grupo = sequência CONSECUTIVA de opções com o mesmo `group`; a busca filtra
 * antes, então um grupo sem opção visível some junto com o cabeçalho.
 *
 * Exemplo:
 *   const posicoes = posicoesNosGrupos(navItems.map((item) => item.option));
 *   posicoes[3].cabecalho; // 'Compartilhadas comigo' (a opção 3 abre o grupo)
 */

import type { SelectMenuOption } from '$lib/types/selectMenu';

export interface PosicaoNoGrupo {
	/** Rótulo a desenhar ANTES desta opção (ela abre o grupo), ou `null`. */
	cabecalho: string | null;
	/** Posição da opção que abriu o grupo desta (base do id do cabeçalho); `null` sem grupo. */
	inicio: number | null;
}

/** Uma posição por opção; `null` na lista = item sem opção (o "Todos"). */
export function posicoesNosGrupos(
	opcoes: readonly (Pick<SelectMenuOption, 'group'> | null)[]
): PosicaoNoGrupo[] {
	let inicio: number | null = null;
	return opcoes.map((opcao, index) => {
		const grupo = opcao?.group ?? null;
		if (grupo === null) {
			inicio = null;
			return { cabecalho: null, inicio: null };
		}
		const abre = (opcoes[index - 1]?.group ?? null) !== grupo;
		if (abre) inicio = index;
		return { cabecalho: abre ? grupo : null, inicio };
	});
}
