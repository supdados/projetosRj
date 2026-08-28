/**
 * Testes do registry de colunas do export: sanitização do payload persistido
 * e roundtrip de leitura/gravação com um `localStorage` fake.
 */
import { describe, it, expect } from 'vitest';

import {
	DEFAULT_SLUGS,
	DEFAULT_STAGE_SLUGS,
	EXPORT_COLUMNS,
	EXPORT_COLUMNS_STORAGE_KEY,
	EXPORT_STAGE_COLUMNS,
	EXPORT_STAGE_COLUMNS_STORAGE_KEY,
	isDefaultSelection,
	loadStoredSlugs,
	loadStoredStageSlugs,
	sanitizeStoredSlugs,
	sanitizeStoredStageSlugs,
	saveStoredSlugs,
	saveStoredStageSlugs,
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
	it('tem as 18 colunas e o preset de 14 dentro do registry', () => {
		expect(EXPORT_COLUMNS).toHaveLength(18);
		expect(DEFAULT_SLUGS).toHaveLength(14);
		const conhecidos = EXPORT_COLUMNS.map((c) => c.slug);
		expect(DEFAULT_SLUGS.every((slug) => conhecidos.includes(slug))).toBe(true);
	});

	it('não repete slug nem rótulo', () => {
		expect(new Set(EXPORT_COLUMNS.map((c) => c.slug)).size).toBe(18);
		expect(new Set(EXPORT_COLUMNS.map((c) => c.label)).size).toBe(18);
	});

	it('põe Área responsável imediatamente antes de Órgão', () => {
		const slugs = EXPORT_COLUMNS.map((c) => c.slug);
		expect(slugs.indexOf('orgao')).toBe(slugs.indexOf('area') + 1);
		expect(DEFAULT_SLUGS.indexOf('orgao')).toBe(DEFAULT_SLUGS.indexOf('area') + 1);
	});
});

describe('registry de colunas de etapa', () => {
	it('espelha os 6 slugs do backend e usa todos no preset', () => {
		expect(EXPORT_STAGE_COLUMNS.map((c) => c.slug)).toEqual([
			'etapa',
			'etapa_data_inicio',
			'etapa_data_fim',
			'etapa_responsavel',
			'etapa_situacao',
			'etapa_comentarios'
		]);
		expect(DEFAULT_STAGE_SLUGS).toEqual(EXPORT_STAGE_COLUMNS.map((c) => c.slug));
	});

	it('não compartilha slug com as colunas de projeto', () => {
		const projeto = new Set(EXPORT_COLUMNS.map((c) => c.slug));
		expect(EXPORT_STAGE_COLUMNS.some((c) => projeto.has(c.slug))).toBe(false);
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

	it('rejeita slug de etapa na seleção de projeto e vice-versa', () => {
		expect(sanitizeStoredSlugs(['etapa'])).toEqual([...DEFAULT_SLUGS]);
		expect(sanitizeStoredStageSlugs(['titulo'])).toEqual([...DEFAULT_STAGE_SLUGS]);
	});
});

describe('sanitizeStoredStageSlugs', () => {
	it('filtra e preserva a ordem, caindo no preset quando sobra nada', () => {
		expect(sanitizeStoredStageSlugs(['etapa_situacao', 'etapa', 'etapa'])).toEqual([
			'etapa_situacao',
			'etapa'
		]);
		expect(sanitizeStoredStageSlugs([])).toEqual([...DEFAULT_STAGE_SLUGS]);
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

describe('persistência das colunas de etapa', () => {
	it('usa a chave projetosrj.export.colunasEtapa sem tocar a de projeto', () => {
		const storage = new ArmazenamentoFake();
		saveStoredSlugs(['titulo'], storage);
		saveStoredStageSlugs(['etapa', 'etapa_situacao'], storage);

		expect(storage.getItem(EXPORT_STAGE_COLUMNS_STORAGE_KEY)).toBe('["etapa","etapa_situacao"]');
		expect(loadStoredStageSlugs(storage)).toEqual(['etapa', 'etapa_situacao']);
		expect(loadStoredSlugs(storage)).toEqual(['titulo']);
	});

	it('devolve o preset de etapa quando não há nada gravado', () => {
		expect(loadStoredStageSlugs(new ArmazenamentoFake())).toEqual([...DEFAULT_STAGE_SLUGS]);
	});

	it('não explode quando o armazenamento falha', () => {
		const storage = new ArmazenamentoQuebrado();
		expect(() => saveStoredStageSlugs(['etapa'], storage)).not.toThrow();
		expect(loadStoredStageSlugs(storage)).toEqual([...DEFAULT_STAGE_SLUGS]);
	});
});
