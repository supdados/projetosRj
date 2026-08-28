/**
 * Testes dos modelos de CSV da importação: cabeçalhos exatos do round-trip
 * com o export e linhas de exemplo com o mesmo nº de colunas do cabeçalho.
 */
import { describe, it, expect } from 'vitest';

import { buildImportTemplateCsv } from './importTemplates';

/** Linhas do CSV já sem o BOM (os exemplos não usam célula com `;` escapado). */
function linhasDe(csv: string): string[][] {
	expect(csv.startsWith('\uFEFF')).toBe(true);
	const corpo = csv.slice(1);
	expect(corpo.endsWith('\r\n')).toBe(true);
	return corpo
		.split('\r\n')
		.filter((linha) => linha !== '')
		.map((linha) => linha.split(';'));
}

describe('modelo simples', () => {
	it('tem os cabeçalhos exatos do export e 1 projeto de exemplo', () => {
		const linhas = linhasDe(buildImportTemplateCsv('simples'));

		expect(linhas[0]).toEqual([
			'Título',
			'Descrição',
			'Status',
			'Prioridade',
			'Tipo de entrega',
			'Projeto especial',
			'Área responsável',
			'Órgão',
			'Observação',
			'Processos SEI',
			'Data de início',
			'Data de fim'
		]);
		expect(linhas).toHaveLength(2);
	});

	it('mantém todas as linhas com o nº de colunas do cabeçalho', () => {
		const linhas = linhasDe(buildImportTemplateCsv('simples'));

		for (const linha of linhas) expect(linha).toHaveLength(linhas[0].length);
	});
});

describe('modelo com etapas', () => {
	it('tem Ref Projeto primeiro e os cabeçalhos de etapa do export', () => {
		const linhas = linhasDe(buildImportTemplateCsv('com_etapas'));

		expect(linhas[0]).toEqual([
			'Ref Projeto',
			'Título',
			'Descrição',
			'Status',
			'Prioridade',
			'Tipo de entrega',
			'Projeto especial',
			'Área responsável',
			'Órgão',
			'Observação',
			'Processos SEI',
			'Etapa',
			'Etapa Data de início',
			'Etapa Data de fim',
			'Etapa Responsável',
			'Etapa Situação',
			'Etapa Comentários'
		]);
	});

	it('exemplifica 2 projetos com refs contíguas e colunas alinhadas', () => {
		const linhas = linhasDe(buildImportTemplateCsv('com_etapas'));
		const refs = linhas.slice(1).map((linha) => linha[0]);

		for (const linha of linhas) expect(linha).toHaveLength(linhas[0].length);
		expect(refs).toEqual(['P1', 'P1', 'P1', 'P2', 'P2']);
	});
});
