/**
 * Regressão: o filtro "Coleção" de /projetos oferecia só as coleções próprias,
 * embora o `?colecao=` do servidor aceite as recebidas (share aceito/legado).
 */
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import type { ColecaoResumo } from '$lib/types/collections';
import { GRUPO_COMPARTILHADAS, GRUPO_MINHAS, opcoesDoFiltroColecao } from './colecaoFiltro';

type ColecaoDoFiltro = Pick<ColecaoResumo, 'id' | 'nome' | 'papel'>;

const FAVORITOS: ColecaoDoFiltro = { id: 1, nome: 'Favoritos', papel: 'dono' };
const MINHA: ColecaoDoFiltro = { id: 2, nome: 'Obras', papel: 'dono' };
const RECEBIDA_LEITOR: ColecaoDoFiltro = { id: 7, nome: 'Saúde', papel: 'viewer' };
const RECEBIDA_EDITOR: ColecaoDoFiltro = { id: 8, nome: 'Educação', papel: 'editor' };

describe('opcoesDoFiltroColecao', () => {
	it('inclui as recebidas (leitor e editor) no grupo "Compartilhadas comigo"', () => {
		const opcoes = opcoesDoFiltroColecao([FAVORITOS, MINHA, RECEBIDA_LEITOR, RECEBIDA_EDITOR]);
		expect(opcoes).toEqual([
			{ value: '1', label: 'Favoritos', group: GRUPO_MINHAS },
			{ value: '2', label: 'Obras', group: GRUPO_MINHAS },
			{ value: '7', label: 'Saúde', group: GRUPO_COMPARTILHADAS },
			{ value: '8', label: 'Educação', group: GRUPO_COMPARTILHADAS }
		]);
		expect(GRUPO_COMPARTILHADAS).toBe('Compartilhadas comigo');
	});

	it('as minhas vêm antes mesmo que o índice intercale as recebidas', () => {
		const opcoes = opcoesDoFiltroColecao([RECEBIDA_LEITOR, FAVORITOS, MINHA]);
		expect(opcoes.map((o) => o.value)).toEqual(['1', '2', '7']);
	});

	it('sem coleção recebida, a lista fica como sempre: Favoritos primeiro e sem cabeçalho', () => {
		expect(opcoesDoFiltroColecao([FAVORITOS, MINHA])).toEqual([
			{ value: '1', label: 'Favoritos' },
			{ value: '2', label: 'Obras' }
		]);
	});
});

describe('/projetos usa o catálogo inteiro no filtro', () => {
	it('o menu "Coleção" sai de `opcoesDoFiltroColecao`, sem o corte em `papel === dono`', () => {
		const pagina = readFileSync(
			new URL('../../routes/(app)/projetos/+page.svelte', import.meta.url),
			'utf8'
		);
		expect(pagina).toContain('opcoesDoFiltroColecao(colecoesCatalog)');
		expect(pagina).not.toMatch(/colecoesCatalog\s*\.filter\(\(c\) => c\.papel === 'dono'\)/);
	});
});
