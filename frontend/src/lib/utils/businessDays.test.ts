/**
 * Testes da aritmética de dias úteis usada pelo preview de etapas — precisa
 * bater com `services/etapas_dates` do backend, senão o preview mente.
 */
import { describe, it, expect } from 'vitest';
import { addBusinessDays, nextBusinessDay } from './businessDays';

const iso = (date: Date): string => date.toISOString().slice(0, 10);

describe('nextBusinessDay', () => {
	it('mantém a data quando já é dia útil', () => {
		expect(iso(nextBusinessDay(new Date('2026-07-24T00:00:00Z')))).toBe('2026-07-24');
	});

	it('empurra sábado e domingo para a segunda-feira', () => {
		expect(iso(nextBusinessDay(new Date('2026-07-25T00:00:00Z')))).toBe('2026-07-27');
		expect(iso(nextBusinessDay(new Date('2026-07-26T00:00:00Z')))).toBe('2026-07-27');
	});

	it('não muta a data recebida', () => {
		const base = new Date('2026-07-25T00:00:00Z');
		nextBusinessDay(base);
		expect(iso(base)).toBe('2026-07-25');
	});
});

describe('addBusinessDays', () => {
	it('devolve a mesma data para zero dias', () => {
		expect(iso(addBusinessDays(new Date('2026-07-24T00:00:00Z'), 0))).toBe('2026-07-24');
	});

	it('pula o fim de semana ao somar', () => {
		// sexta 24 + 1 dia útil = segunda 27
		expect(iso(addBusinessDays(new Date('2026-07-24T00:00:00Z'), 1))).toBe('2026-07-27');
	});

	it('soma uma semana útil inteira', () => {
		// segunda 20 + 5 dias úteis = segunda 27
		expect(iso(addBusinessDays(new Date('2026-07-20T00:00:00Z'), 5))).toBe('2026-07-27');
	});

	it('atravessa vários fins de semana', () => {
		// segunda 20 + 10 dias úteis = segunda 03/08
		expect(iso(addBusinessDays(new Date('2026-07-20T00:00:00Z'), 10))).toBe('2026-08-03');
	});

	it('não muta a data recebida', () => {
		const base = new Date('2026-07-20T00:00:00Z');
		addBusinessDays(base, 5);
		expect(iso(base)).toBe('2026-07-20');
	});
});
