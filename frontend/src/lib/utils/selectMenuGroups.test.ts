/** Testes dos cabeçalhos de grupo do SelectMenu (onde abrem e a quem cada opção pertence). */
import { describe, expect, it } from 'vitest';
import { posicoesNosGrupos } from './selectMenuGroups';

describe('posicoesNosGrupos', () => {
	it('sem `group` não há cabeçalho nenhum (menus de sempre ficam iguais)', () => {
		expect(posicoesNosGrupos([{}, {}])).toEqual([
			{ cabecalho: null, inicio: null },
			{ cabecalho: null, inicio: null }
		]);
	});

	it('cada grupo abre na 1ª opção dele e as seguintes apontam para ela', () => {
		const posicoes = posicoesNosGrupos([
			null, // o "Todos"
			{ group: 'Minhas' },
			{ group: 'Minhas' },
			{ group: 'Compartilhadas comigo' },
			{ group: 'Compartilhadas comigo' }
		]);
		expect(posicoes.map((p) => p.cabecalho)).toEqual([
			null,
			'Minhas',
			null,
			'Compartilhadas comigo',
			null
		]);
		expect(posicoes.map((p) => p.inicio)).toEqual([null, 1, 1, 3, 3]);
	});

	it('a busca que esvazia um grupo some com o cabeçalho dele', () => {
		const posicoes = posicoesNosGrupos([{ group: 'Compartilhadas comigo' }]);
		expect(posicoes).toEqual([{ cabecalho: 'Compartilhadas comigo', inicio: 0 }]);
	});
});
