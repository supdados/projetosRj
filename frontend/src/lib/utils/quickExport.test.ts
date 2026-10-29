/** Testes da exportação rápida: querystring (só área) e frase de escopo do modal. */
import { describe, it, expect } from 'vitest';

import {
	QUICK_EXPORT_COLUMNS,
	buildQuickExportParams,
	describeQuickExportScope
} from './quickExport';

describe('QUICK_EXPORT_COLUMNS', () => {
	it('espelha os cabeçalhos fixos do backend, na ordem', () => {
		expect(QUICK_EXPORT_COLUMNS.map((c) => c.rotulo)).toEqual([
			'ID',
			'Situação',
			'Objeto / Produto',
			'Localização',
			'Escopo',
			'Execução física e financeira',
			'Contratos e instrumentos',
			'Datas de início e fim previstas',
			'Próximas etapas e prazos',
			'Ponto crítico / Riscos',
			'Processo SEI',
			'TCE',
			'Responsável'
		]);
	});

	it('marca como "a preencher" só as colunas sem campo no sistema', () => {
		expect(QUICK_EXPORT_COLUMNS.filter((c) => c.aPreencher).map((c) => c.rotulo)).toEqual([
			'Contratos e instrumentos',
			'Ponto crítico / Riscos'
		]);
	});
});

describe('buildQuickExportParams', () => {
	it('sem área exporta todos os projetos visíveis', () => {
		expect(buildQuickExportParams(null).toString()).toBe('rapida=1');
		expect(buildQuickExportParams({ orgao: undefined }).toString()).toBe('rapida=1');
	});

	it('envia a área e o recorte "apenas esta área"', () => {
		expect(buildQuickExportParams({ orgao: 12 }).toString()).toBe('rapida=1&orgao=12');
		expect(buildQuickExportParams({ orgao: 12, apenas_orgao: true }).toString()).toBe(
			'rapida=1&orgao=12&apenas_orgao=1'
		);
	});

	it('ignora apenas_orgao sem área', () => {
		expect(buildQuickExportParams({ apenas_orgao: true }).toString()).toBe('rapida=1');
	});
});

describe('describeQuickExportScope', () => {
	it('sem área descreve todos os projetos', () => {
		expect(describeQuickExportScope(null, null)).toBe('Todos os projetos · todos os status');
	});

	it('usa o rótulo da área e marca o recorte sem subáreas', () => {
		expect(describeQuickExportScope({ orgao: 12 }, 'SETD')).toBe('Área SETD · todos os status');
		expect(describeQuickExportScope({ orgao: 12, apenas_orgao: true }, 'SETD')).toBe(
			'Área SETD (sem subáreas) · todos os status'
		);
	});

	it('sem rótulo conhecido cai em "Área selecionada"', () => {
		expect(describeQuickExportScope({ orgao: 12 }, null)).toBe(
			'Área selecionada · todos os status'
		);
	});
});
