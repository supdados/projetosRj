/**
 * Testes da unicidade do mapeamento de colunas: escolher um campo já usado
 * devolve a coluna antiga para "Ignorar", sem mutar o estado anterior.
 */
import { describe, it, expect } from 'vitest';

import {
	applyFieldSelection,
	countMapped,
	hasTitulo,
	type ImportFieldMapping
} from './importMappingState';

describe('applyFieldSelection', () => {
	it('rouba o campo da coluna anterior, que volta para ignorada', () => {
		const antes: ImportFieldMapping = { 0: 'titulo', 1: 'descricao', 2: null };

		expect(applyFieldSelection(antes, 2, 'titulo')).toEqual({
			0: null,
			1: 'descricao',
			2: 'titulo'
		});
	});

	it('não muta o mapeamento recebido', () => {
		const antes: ImportFieldMapping = { 0: 'titulo', 1: null };
		applyFieldSelection(antes, 1, 'titulo');

		expect(antes).toEqual({ 0: 'titulo', 1: null });
	});

	it('escolher "Ignorar" limpa só a coluna alvo', () => {
		const antes: ImportFieldMapping = { 0: 'titulo', 1: 'status' };

		expect(applyFieldSelection(antes, 0, null)).toEqual({ 0: null, 1: 'status' });
	});

	it('reescolher o mesmo campo na mesma coluna é idempotente', () => {
		const antes: ImportFieldMapping = { 0: 'titulo', 1: 'status' };

		expect(applyFieldSelection(antes, 0, 'titulo')).toEqual({ 0: 'titulo', 1: 'status' });
	});
});

describe('countMapped', () => {
	it('conta só as colunas com campo escolhido', () => {
		expect(countMapped({ 0: 'titulo', 1: null, 2: 'sei' })).toBe(2);
		expect(countMapped({})).toBe(0);
	});
});

describe('hasTitulo', () => {
	it('exige uma coluna mapeada como titulo', () => {
		expect(hasTitulo({ 0: 'titulo', 1: null })).toBe(true);
		expect(hasTitulo({ 0: 'descricao', 1: null })).toBe(false);
		expect(hasTitulo({})).toBe(false);
	});
});
