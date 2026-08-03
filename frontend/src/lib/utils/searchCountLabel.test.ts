import { describe, expect, it } from 'vitest';

import { formatSearchCount } from './searchCountLabel';

describe('formatSearchCount', () => {
	it('mostra o total exato quando o backend nao saturou a contagem', () => {
		expect(formatSearchCount(7)).toBe('7');
		expect(formatSearchCount(7, { capped: false, capAt: 100 })).toBe('7');
	});

	it('mostra "99+" quando o contador saturou no teto de 100', () => {
		expect(formatSearchCount(100, { capped: true, capAt: 100 })).toBe('99+');
	});

	it('acompanha o teto anunciado pelo backend', () => {
		expect(formatSearchCount(50, { capped: true, capAt: 50 })).toBe('49+');
	});

	it('cai para o total quando o teto vem ausente ou invalido', () => {
		expect(formatSearchCount(100, { capped: true, capAt: null })).toBe('100');
		expect(formatSearchCount(1, { capped: true, capAt: 1 })).toBe('1');
	});
});
