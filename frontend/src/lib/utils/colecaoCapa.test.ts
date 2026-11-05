import { describe, expect, it } from 'vitest';
import {
	areasDasSiglas,
	contagemPorFaixa,
	nomeDaArea,
	numerosDoAndamento,
	plural,
	quantasAreas,
	rotuloAreas,
	segmentosDaBarra,
	somarAreas,
	type EtapasDaColecao
} from './colecaoCapa';

const ETAPAS: EtapasDaColecao = {
	etapas_total: 10,
	etapas_concluidas: 4,
	etapas_em_andamento: 3,
	etapas_atrasadas: 1
};

describe('contagemPorFaixa', () => {
	it('não iniciadas são o resto do total', () => {
		expect(contagemPorFaixa(ETAPAS)).toEqual({
			concluidas: 4,
			andamento: 3,
			atrasadas: 1,
			nao_iniciadas: 2
		});
	});

	it('payload antigo sem as faixas novas cai tudo em não iniciadas', () => {
		const antigo = { etapas_total: 5, etapas_concluidas: 2 } as EtapasDaColecao;
		expect(contagemPorFaixa(antigo)).toEqual({
			concluidas: 2,
			andamento: 0,
			atrasadas: 0,
			nao_iniciadas: 3
		});
	});

	it('resto negativo (dado inconsistente) não vira segmento negativo', () => {
		const torto = { ...ETAPAS, etapas_total: 6 };
		expect(contagemPorFaixa(torto).nao_iniciadas).toBe(0);
	});
});

describe('segmentosDaBarra', () => {
	it('segue a ordem da régua e pula faixa vazia', () => {
		const segmentos = segmentosDaBarra({ ...ETAPAS, etapas_atrasadas: 0, etapas_total: 9 });
		expect(segmentos.map((s) => [s.faixa, s.valor])).toEqual([
			['concluidas', 4],
			['andamento', 3],
			['nao_iniciadas', 2]
		]);
	});

	it('rótulo concorda com o número', () => {
		const [atrasada] = segmentosDaBarra({
			etapas_total: 1,
			etapas_concluidas: 0,
			etapas_em_andamento: 0,
			etapas_atrasadas: 1
		});
		expect(atrasada.rotulo).toBe('1 atrasada');
	});

	it('coleção sem etapa não tem segmento', () => {
		const vazio = { etapas_total: 0, etapas_concluidas: 0, etapas_em_andamento: 0, etapas_atrasadas: 0 };
		expect(segmentosDaBarra(vazio)).toEqual([]);
	});
});

describe('numerosDoAndamento', () => {
	it('sempre três números, com singular e plural', () => {
		const numeros = numerosDoAndamento({ ...ETAPAS, etapas_em_andamento: 1, etapas_atrasadas: 0 });
		expect(numeros.map((n) => `${n.valor} ${n.rotulo}`)).toEqual([
			'4 concluídas',
			'1 vigente',
			'0 atrasadas'
		]);
	});
});

describe('áreas', () => {
	it('rotuloAreas conta só áreas reais', () => {
		expect(rotuloAreas([{ sigla: 'SUPEST' }, { sigla: null }])).toBe('1 área');
		expect(rotuloAreas([{ sigla: 'A' }, { sigla: 'B' }])).toBe('2 áreas');
		expect(rotuloAreas([{ sigla: null }])).toBe('Sem área');
		expect(rotuloAreas([])).toBe('0 áreas');
	});

	it('quantasAreas ignora projeto sem órgão', () => {
		expect(quantasAreas([{ sigla: 'A' }, { sigla: null }, { sigla: 'B' }])).toBe(2);
		expect(quantasAreas([])).toBe(0);
	});

	it('nomeDaArea troca órgão ausente por "Sem área"', () => {
		expect(nomeDaArea({ sigla: null })).toBe('Sem área');
		expect(nomeDaArea({ sigla: 'SETD' })).toBe('SETD');
	});

	it('areasDasSiglas agrupa na ordem do backend', () => {
		expect(areasDasSiglas(['SUPEST', null, 'SETD', 'SUPEST', 'ALFA'])).toEqual([
			{ sigla: 'SUPEST', projetos: 2 },
			{ sigla: 'ALFA', projetos: 1 },
			{ sigla: 'SETD', projetos: 1 },
			{ sigla: null, projetos: 1 }
		]);
	});
});

describe('somarAreas', () => {
	it('soma a mesma sigla e reordena', () => {
		const atuais = [
			{ sigla: 'SETD', projetos: 2 },
			{ sigla: 'ALFA', projetos: 1 }
		];
		const novas = [
			{ sigla: 'ALFA', projetos: 2 },
			{ sigla: null, projetos: 1 }
		];
		expect(somarAreas(atuais, novas)).toEqual([
			{ sigla: 'ALFA', projetos: 3 },
			{ sigla: 'SETD', projetos: 2 },
			{ sigla: null, projetos: 1 }
		]);
	});

	it('sem novas devolve as atuais (cópia ordenada)', () => {
		const atuais = [{ sigla: 'B', projetos: 1 }, { sigla: 'A', projetos: 1 }];
		expect(somarAreas(atuais, [])).toEqual([
			{ sigla: 'A', projetos: 1 },
			{ sigla: 'B', projetos: 1 }
		]);
	});
});

describe('plural', () => {
	it('aceita plural irregular', () => {
		expect(plural(1, 'área')).toBe('1 área');
		expect(plural(2, 'coleção', 'coleções')).toBe('2 coleções');
	});
});
