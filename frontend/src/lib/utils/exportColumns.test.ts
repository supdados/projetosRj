/**
 * Testes do registry de colunas do export: sanitização do payload persistido
 * e roundtrip de leitura/gravação com um `localStorage` fake.
 */
import { describe, it, expect } from 'vitest';

import {
	DEFAULT_SLUGS,
	EXPORT_COLUMNS,
	EXPORT_COLUMNS_STORAGE_KEY,
	isDefaultSelection,
	loadStoredSlugs,
	sanitizeStoredSlugs,
	saveStoredSlugs,
	type SlugStorage
} from './exportColumns';

/** `localStorage` em memória (o ambiente de teste é node, sem `window`). */
class ArmazenamentoFake implements SlugStorage {
	private dados = new Map<string, string>();

	getItem(key: string): string | null {
		return this.dados.get(key) ?? null;
	}

	setItem(key: string, value: string): void {
		this.dados.set(key, value);
	}
}

/** Armazenamento que sempre falha (modo privado / cota estourada). */
class ArmazenamentoQuebrado implements SlugStorage {
	getItem(): string | null {
		throw new Error('indisponível');
	}

	setItem(): void {
		throw new Error('indisponível');
	}
}

describe('registry de colunas', () => {
	it('tem as 17 colunas e o preset de 13 dentro do registry', () => {
		expect(EXPORT_COLUMNS).toHaveLength(17);
		expect(DEFAULT_SLUGS).toHaveLength(13);
		const conhecidos = EXPORT_COLUMNS.map((c) => c.slug);
		expect(DEFAULT_SLUGS.every((slug) => conhecidos.includes(slug))).toBe(true);
	});

	it('não repete slug nem rótulo', () => {
		expect(new Set(EXPORT_COLUMNS.map((c) => c.slug)).size).toBe(17);
		expect(new Set(EXPORT_COLUMNS.map((c) => c.label)).size).toBe(17);
	});
});

describe('sanitizeStoredSlugs', () => {
	it('descarta slug desconhecido, duplicado e não-string', () => {
		expect(sanitizeStoredSlugs(['titulo', 'inexistente', 'titulo', 7])).toEqual(['titulo']);
	});

	it('cai no preset quando a lista fica vazia ou o payload não é lista', () => {
		expect(sanitizeStoredSlugs([])).toEqual([...DEFAULT_SLUGS]);
		expect(sanitizeStoredSlugs(['nada'])).toEqual([...DEFAULT_SLUGS]);
		expect(sanitizeStoredSlugs(null)).toEqual([...DEFAULT_SLUGS]);
		expect(sanitizeStoredSlugs('titulo')).toEqual([...DEFAULT_SLUGS]);
	});

	it('preserva a ordem escolhida pelo usuário', () => {
		expect(sanitizeStoredSlugs(['status', 'id', 'titulo'])).toEqual(['status', 'id', 'titulo']);
	});
});

describe('isDefaultSelection', () => {
	it('reconhece o preset e rejeita qualquer divergência', () => {
		expect(isDefaultSelection([...DEFAULT_SLUGS])).toBe(true);
		expect(isDefaultSelection([...DEFAULT_SLUGS, 'prioridade'])).toBe(false);
		expect(isDefaultSelection(['titulo'])).toBe(false);
	});
});

describe('persistência', () => {
	it('faz roundtrip de save/load pela chave projetosrj.export.colunas', () => {
		const storage = new ArmazenamentoFake();
		saveStoredSlugs(['titulo', 'status'], storage);

		expect(storage.getItem(EXPORT_COLUMNS_STORAGE_KEY)).toBe('["titulo","status"]');
		expect(loadStoredSlugs(storage)).toEqual(['titulo', 'status']);
	});

	it('devolve o preset quando não há nada gravado ou o payload está corrompido', () => {
		const storage = new ArmazenamentoFake();
		expect(loadStoredSlugs(storage)).toEqual([...DEFAULT_SLUGS]);

		storage.setItem(EXPORT_COLUMNS_STORAGE_KEY, '{isso não é json');
		expect(loadStoredSlugs(storage)).toEqual([...DEFAULT_SLUGS]);
	});

	it('não explode quando o armazenamento falha', () => {
		const storage = new ArmazenamentoQuebrado();
		expect(() => saveStoredSlugs(['titulo'], storage)).not.toThrow();
		expect(loadStoredSlugs(storage)).toEqual([...DEFAULT_SLUGS]);
	});
});
