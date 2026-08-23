/**
 * Registry das colunas do export de projetos (espelho de `services/project_export.py`)
 * e persistência da última seleção do usuário em `localStorage`.
 */

/** Coluna exportável: slug enviado ao backend + rótulo exibido no modal. */
export interface ExportColumn {
	slug: string;
	label: string;
}

/** Chave da preferência de colunas no `localStorage`. */
export const EXPORT_COLUMNS_STORAGE_KEY = 'projetosrj.export.colunas';

/** As 17 colunas disponíveis, na ordem em que aparecem no modal. */
export const EXPORT_COLUMNS: readonly ExportColumn[] = [
	{ slug: 'id', label: 'ID' },
	{ slug: 'titulo', label: 'Título' },
	{ slug: 'descricao', label: 'Descrição' },
	{ slug: 'sei', label: 'Processos SEI' },
	{ slug: 'orgao', label: 'Órgão' },
	{ slug: 'status', label: 'Status' },
	{ slug: 'prioridade', label: 'Prioridade' },
	{ slug: 'data_inicio', label: 'Data de início' },
	{ slug: 'data_fim', label: 'Data de fim' },
	{ slug: 'objetivo', label: 'Objetivo EEGD' },
	{ slug: 'resultado', label: 'Resultado EEGD' },
	{ slug: 'indicadores', label: 'Indicadores EEGD' },
	{ slug: 'tipo_entrega', label: 'Tipo de entrega' },
	{ slug: 'projeto_especial', label: 'Projeto especial' },
	{ slug: 'observacao', label: 'Observação' },
	{ slug: 'total_etapas', label: 'Total de etapas' },
	{ slug: 'cumprimento', label: 'Cumprimento (%)' }
] as const;

/** Preset padrão: as 13 colunas do export legado (`/projects/download`). */
export const DEFAULT_SLUGS: readonly string[] = [
	'id',
	'titulo',
	'descricao',
	'sei',
	'orgao',
	'status',
	'data_inicio',
	'data_fim',
	'objetivo',
	'resultado',
	'indicadores',
	'total_etapas',
	'cumprimento'
] as const;

/** Armazenamento mínimo usado pela persistência (injetável nos testes). */
export interface SlugStorage {
	getItem(key: string): string | null;
	setItem(key: string, value: string): void;
}

const KNOWN_SLUGS = new Set(EXPORT_COLUMNS.map((column) => column.slug));

/**
 * Filtra slugs desconhecidos e duplicados de um payload não confiável.
 * Lista vazia (ou payload inválido) cai no preset padrão.
 *
 * @example
 * sanitizeStoredSlugs(['titulo', 'inexistente']); // ['titulo']
 */
export function sanitizeStoredSlugs(raw: unknown): string[] {
	if (!Array.isArray(raw)) return [...DEFAULT_SLUGS];
	const slugs: string[] = [];
	for (const item of raw) {
		if (typeof item !== 'string' || !KNOWN_SLUGS.has(item) || slugs.includes(item)) continue;
		slugs.push(item);
	}
	return slugs.length > 0 ? slugs : [...DEFAULT_SLUGS];
}

/** `true` quando a seleção é exatamente o preset padrão (mesma ordem incluída). */
export function isDefaultSelection(slugs: readonly string[]): boolean {
	if (slugs.length !== DEFAULT_SLUGS.length) return false;
	return slugs.every((slug, i) => slug === DEFAULT_SLUGS[i]);
}

function resolveStorage(storage?: SlugStorage): SlugStorage | null {
	if (storage) return storage;
	if (typeof window === 'undefined') return null;
	return window.localStorage;
}

/** Lê a seleção persistida, já sanitizada (preset se ausente/corrompida). */
export function loadStoredSlugs(storage?: SlugStorage): string[] {
	const target = resolveStorage(storage);
	if (!target) return [...DEFAULT_SLUGS];
	try {
		const raw = target.getItem(EXPORT_COLUMNS_STORAGE_KEY);
		return raw ? sanitizeStoredSlugs(JSON.parse(raw)) : [...DEFAULT_SLUGS];
	} catch {
		return [...DEFAULT_SLUGS];
	}
}

/** Persiste a seleção (silencioso quando o `localStorage` está indisponível). */
export function saveStoredSlugs(slugs: readonly string[], storage?: SlugStorage): void {
	const target = resolveStorage(storage);
	if (!target) return;
	try {
		target.setItem(EXPORT_COLUMNS_STORAGE_KEY, JSON.stringify(slugs));
	} catch {
		// localStorage indisponivel — a seleção vale só para esta sessão.
	}
}
