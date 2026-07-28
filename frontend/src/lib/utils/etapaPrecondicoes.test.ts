/**
 * Testes do gate cliente de conclusão de etapa. Os textos precisam bater com os
 * do backend (422), senão o usuário vê duas frases diferentes para o mesmo erro.
 */
import { describe, it, expect } from 'vitest';
import { podeConcluirEtapa, MOTIVO_DATAS_AUSENTES } from './etapaPrecondicoes';

const DATAS = ['2026-07-01', '2026-07-10'] as const;

describe('podeConcluirEtapa', () => {
	it('libera etapa sem tarefas e com datas', () => {
		expect(podeConcluirEtapa({ total: 0, done: 0 }, DATAS[0], DATAS[1])).toEqual({
			ok: true,
			motivo: null
		});
	});

	it('libera etapa com todas as tarefas concluídas', () => {
		expect(podeConcluirEtapa({ total: 3, done: 3 }, DATAS[0], DATAS[1])).toEqual({
			ok: true,
			motivo: null
		});
	});

	it('bloqueia com 1 tarefa pendente', () => {
		const resultado = podeConcluirEtapa({ total: 1, done: 0 }, DATAS[0], DATAS[1]);
		expect(resultado.ok).toBe(false);
		expect(resultado.motivo).toContain('1 tarefa(s) pendente(s)');
	});

	it('conta as pendentes pela diferença, não pelo total', () => {
		const resultado = podeConcluirEtapa({ total: 5, done: 2 }, DATAS[0], DATAS[1]);
		expect(resultado.ok).toBe(false);
		expect(resultado.motivo).toContain('3 tarefa(s) pendente(s)');
	});

	it('bloqueia sem data de início', () => {
		expect(podeConcluirEtapa({ total: 0, done: 0 }, null, DATAS[1])).toEqual({
			ok: false,
			motivo: MOTIVO_DATAS_AUSENTES
		});
	});

	it('bloqueia sem data de fim', () => {
		expect(podeConcluirEtapa({ total: 0, done: 0 }, DATAS[0], null)).toEqual({
			ok: false,
			motivo: MOTIVO_DATAS_AUSENTES
		});
	});

	it('prioriza o motivo de datas quando também há tarefas pendentes', () => {
		expect(podeConcluirEtapa({ total: 4, done: 1 }, null, null).motivo).toBe(
			MOTIVO_DATAS_AUSENTES
		);
	});

	it('tolera contagem inconsistente do servidor (done > total)', () => {
		expect(podeConcluirEtapa({ total: 1, done: 3 }, DATAS[0], DATAS[1])).toEqual({
			ok: true,
			motivo: null
		});
	});
});
