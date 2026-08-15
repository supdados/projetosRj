import { describe, it, expect } from 'vitest';
import {
	formatDateBR,
	formatIsoDateBR,
	formatIsoDateBRLocalTz,
	formatIsoDatePartsBR
} from './dateFormat';

describe('formatIsoDateBR', () => {
	it('formata YYYY-MM-DD sem deslocar o dia pelo fuso', () => {
		expect(formatIsoDateBR('2026-08-05')).toBe('05/08/2026');
		expect(formatIsoDateBR('2026-01-01')).toBe('01/01/2026');
	});

	it('formata timestamp com hora lendo o dia em UTC', () => {
		expect(formatIsoDateBR('2026-08-05T23:30:00Z')).toBe('05/08/2026');
	});

	it('devolve o fallback para vazio, null, undefined e ISO inválido', () => {
		expect(formatIsoDateBR(null)).toBe('');
		expect(formatIsoDateBR(undefined)).toBe('');
		expect(formatIsoDateBR('')).toBe('');
		expect(formatIsoDateBR('data-torta')).toBe('');
		expect(formatIsoDateBR(null, '—')).toBe('—');
		expect(formatIsoDateBR('data-torta', 'Sem data')).toBe('Sem data');
	});
});

describe('formatDateBR', () => {
	it('formata um Date lendo os campos em UTC', () => {
		expect(formatDateBR(new Date('2026-12-31T00:00:00Z'))).toBe('31/12/2026');
	});
});

describe('formatIsoDateBRLocalTz', () => {
	it('formata timestamp no fuso local', () => {
		const iso = '2026-08-05T12:00:00Z';
		const esperado = new Date(iso).toLocaleDateString('pt-BR', {
			day: '2-digit',
			month: '2-digit',
			year: 'numeric'
		});
		expect(formatIsoDateBRLocalTz(iso)).toBe(esperado);
	});

	it('devolve null para vazio, null e ISO inválido', () => {
		expect(formatIsoDateBRLocalTz(null)).toBeNull();
		expect(formatIsoDateBRLocalTz('')).toBeNull();
		expect(formatIsoDateBRLocalTz('nada')).toBeNull();
	});
});

describe('formatIsoDatePartsBR', () => {
	it('reordena os pedaços de um YYYY-MM-DD', () => {
		expect(formatIsoDatePartsBR('2026-08-05')).toBe('05/08/2026');
	});

	it('devolve string vazia para vazio, null e undefined', () => {
		expect(formatIsoDatePartsBR('')).toBe('');
		expect(formatIsoDatePartsBR(null)).toBe('');
		expect(formatIsoDatePartsBR(undefined)).toBe('');
	});

	it('devolve a entrada intacta quando não tem 10 caracteres', () => {
		expect(formatIsoDatePartsBR('2026-08-05T10:00:00Z')).toBe('2026-08-05T10:00:00Z');
		expect(formatIsoDatePartsBR('2026-8-5')).toBe('2026-8-5');
	});

	it('não desloca o dia (paridade com formatIsoDateBR para data pura)', () => {
		expect(formatIsoDatePartsBR('2026-01-01')).toBe(formatIsoDateBR('2026-01-01'));
	});
});
