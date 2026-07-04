/**
 * Testes unitários da máscara de processo SEI (`seiFormat.ts`).
 *
 * Fixa o requisito de produto: colar o número JÁ com o prefixo "SEI-"
 * (ex.: "SEI-380001/000664/2026") não é erro — o prefixo é descartado e
 * sobram só os dígitos, que a máscara reagrupa em 6/6/4.
 */
import { describe, it, expect } from 'vitest';
import { seiDigitsOnly, formatSeiDigits, hasMinimumSeiDigits } from './seiFormat';

describe('seiDigitsOnly', () => {
	it('descarta o prefixo "SEI-" colado junto do número', () => {
		expect(seiDigitsOnly('SEI-380001/000664/2026')).toBe('3800010006642026');
	});

	it('aceita variações de caixa e espaçamento do prefixo', () => {
		expect(seiDigitsOnly('sei- 380001/000664/2026')).toBe('3800010006642026');
	});

	it('remove separadores de um número sem prefixo', () => {
		expect(seiDigitsOnly('380001/000664/2026')).toBe('3800010006642026');
	});

	it('trunca excesso além de 16 dígitos', () => {
		expect(seiDigitsOnly('123456789012345678999')).toBe('1234567890123456');
	});

	it('devolve vazio quando não há dígitos', () => {
		expect(seiDigitsOnly('SEI-')).toBe('');
		expect(seiDigitsOnly('')).toBe('');
	});
});

describe('formatSeiDigits', () => {
	it('não agrupa até 6 dígitos', () => {
		expect(formatSeiDigits('380001')).toBe('380001');
	});

	it('agrupa 6/n entre 7 e 12 dígitos', () => {
		expect(formatSeiDigits('3800010006')).toBe('380001/0006');
	});

	it('agrupa 6/6/4 com 16 dígitos', () => {
		expect(formatSeiDigits('3800010006642026')).toBe('380001/000664/2026');
	});

	it('reagrupa entrada já formatada (idempotente)', () => {
		expect(formatSeiDigits('380001/000664/2026')).toBe('380001/000664/2026');
	});
});

describe('hasMinimumSeiDigits', () => {
	it('exige o primeiro grupo completo (6 dígitos)', () => {
		expect(hasMinimumSeiDigits('380001')).toBe(true);
		expect(hasMinimumSeiDigits('380001/000664/2026')).toBe(true);
		expect(hasMinimumSeiDigits('38000')).toBe(false);
		expect(hasMinimumSeiDigits('')).toBe(false);
	});
});
