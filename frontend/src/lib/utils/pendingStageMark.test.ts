import { describe, it, expect } from 'vitest';
import { pendingStageMark } from './pendingStageMark';

const HOJE = '2026-10-13';

describe('pendingStageMark', () => {
	it('marca atrasada em vermelho com os dias de atraso no tooltip', () => {
		expect(
			pendingStageMark('atrasada', { data_inicio: '2026-09-01', data_fim: '2026-10-01' }, HOJE)
		).toEqual({
			label: 'Atrasada',
			chipClass: 'chip--danger',
			title: 'Venceu há 12 dias (01/10/2026)'
		});
	});

	it('usa o singular para um dia de atraso', () => {
		const mark = pendingStageMark(
			'atrasada',
			{ data_inicio: '2026-10-01', data_fim: '2026-10-12' },
			HOJE
		);
		expect(mark?.title).toBe('Venceu há 1 dia (12/10/2026)');
	});

	it('marca em andamento pelos dias até o fim, sem repetir o vocabulário de Status', () => {
		expect(
			pendingStageMark('andamento', { data_inicio: '2026-10-01', data_fim: '2026-12-31' }, HOJE)
		).toEqual({
			label: 'Termina em 79 dias',
			chipClass: 'chip--neutral',
			title: 'Em andamento desde 01/10/2026'
		});
		expect(
			pendingStageMark('andamento', { data_inicio: '2026-10-01', data_fim: HOJE }, HOJE)?.label
		).toBe('Termina hoje');
		expect(
			pendingStageMark('andamento', { data_inicio: '2026-10-01', data_fim: null }, HOJE)?.label
		).toBe('Sem data de fim');
	});

	it('conta os dias até o início das próximas etapas', () => {
		const etapa = { data_inicio: '2026-10-18', data_fim: '2026-12-31' };
		expect(pendingStageMark('7dias', etapa, HOJE)).toEqual({
			label: 'Começa em 5 dias',
			chipClass: 'chip--neutral',
			title: null
		});
		expect(
			pendingStageMark('7dias', { data_inicio: '2026-10-14', data_fim: '2026-10-20' }, HOJE)?.label
		).toBe('Começa amanhã');
	});

	it('etapa legada sem início é marcada pelo fim', () => {
		expect(
			pendingStageMark('14dias', { data_inicio: null, data_fim: '2026-10-23' }, HOJE)?.label
		).toBe('Termina em 10 dias');
		expect(
			pendingStageMark('7dias', { data_inicio: null, data_fim: HOJE }, HOJE)?.label
		).toBe('Termina hoje');
	});

	it('não marca etapas fora das faixas', () => {
		const etapa = { data_inicio: '2026-12-01', data_fim: '2026-12-31' };
		expect(pendingStageMark('futuro', etapa, HOJE)).toBeNull();
		expect(pendingStageMark('sem_data', { data_inicio: null, data_fim: null }, HOJE)).toBeNull();
	});
});
