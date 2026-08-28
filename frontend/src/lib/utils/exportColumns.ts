/**
 * Registry das colunas do export de projetos e de etapas (espelho de
 * `services/project_export.py`) e persistência da última seleção do usuário
 * em `localStorage`.
 */

/** Coluna exportável: slug enviado ao backend + rótulo exibido no modal. */
export interface ExportColumn {
	slug: string;
	label: string;
}

/** Chave da preferência de colunas de projeto no `localStorage`. */
export const EXPORT_COLUMNS_STORAGE_KEY = 'projetosrj.export.colunas';

/** Chave da preferência de colunas de etapa no `localStorage`. */
export const EXPORT_STAGE_COLUMNS_STORAGE_KEY = 'projetosrj.export.colunasEtapa';

/** As 18 colunas de projeto disponíveis, na ordem em que aparecem no modal. */
export const EXPORT_COLUMNS: readonly ExportColumn[] = [
	{ slug: 'id', label: 'ID' },
	{ slug: 'titulo', label: 'Título' },
	{ slug: 'descricao', label: 'Descrição' },
	{ slug: 'sei', label: 'Processos SEI' },
	{ slug: 'area', label: 'Área responsável' },
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

/** Preset padrão de colunas de projeto (espelha `DEFAULT_EXPORT_SLUGS`). */
export const DEFAULT_SLUGS: readonly string[] = [
	'id',
	'titulo',
	'descricao',
	'sei',
	'area',
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

/** Colunas do modo com etapas (espelha `EXPORT_STAGE_COLUMNS` do backend). */
export const EXPORT_STAGE_COLUMNS: readonly ExportColumn[] = [
	{ slug: 'etapa', label: 'Etapa' },
	{ slug: 'etapa_data_inicio', label: 'Etapa Data de início' },
	{ slug: 'etapa_data_fim', label: 'Etapa Data de fim' },
	{ slug: 'etapa_responsavel', label: 'Etapa Responsável' },
	{ slug: 'etapa_situacao', label: 'Etapa Situação' },
	{ slug: 'etapa_comentarios', label: 'Etapa Comentários' }
] as const;

/** Preset padrão do modo com etapas: todas as colunas de etapa. */
export const DEFAULT_STAGE_SLUGS: readonly string[] = EXPORT_STAGE_COLUMNS.map((c) => c.slug);

/** Armazenamento mínimo usado pela persistência (injetável nos testes). */
export interface SlugStorage {
	getItem(key: string): string | null;
	setItem(key: string, value: string): void;
}

/** Registry de um conjunto de colunas: slugs válidos, preset e chave de storage. */
interface SlugRegistry {
	conhecidos: ReadonlySet<string>;
	padrao: readonly string[];
	chave: string;
}

function criarRegistry(
	colunas: readonly ExportColumn[],
	padrao: readonly string[],
	chave: string
): SlugRegistry {
	return { conhecidos: new Set(colunas.map((coluna) => coluna.slug)), padrao, chave };
}

const REGISTRY_PROJETO = criarRegistry(EXPORT_COLUMNS, DEFAULT_SLUGS, EXPORT_COLUMNS_STORAGE_KEY);
const REGISTRY_ETAPA = criarRegistry(
	EXPORT_STAGE_COLUMNS,
	DEFAULT_STAGE_SLUGS,
	EXPORT_STAGE_COLUMNS_STORAGE_KEY
);

function sanitizeSlugs(raw: unknown, registry: SlugRegistry): string[] {
	if (!Array.isArray(raw)) return [...registry.padrao];
	const slugs: string[] = [];
	for (const item of raw) {
		if (typeof item !== 'string' || !registry.conhecidos.has(item)) continue;
		if (slugs.includes(item)) continue;
		slugs.push(item);
	}
	return slugs.length > 0 ? slugs : [...registry.padrao];
}

function resolveStorage(storage?: SlugStorage): SlugStorage | null {
	if (storage) return storage;
	if (typeof window === 'undefined') return null;
	return window.localStorage;
}

function loadSlugs(registry: SlugRegistry, storage?: SlugStorage): string[] {
	const target = resolveStorage(storage);
	if (!target) return [...registry.padrao];
	try {
		const raw = target.getItem(registry.chave);
		return raw ? sanitizeSlugs(JSON.parse(raw), registry) : [...registry.padrao];
	} catch {
		return [...registry.padrao];
	}
}

function saveSlugs(
	slugs: readonly string[],
	registry: SlugRegistry,
	storage?: SlugStorage
): void {
	const target = resolveStorage(storage);
	if (!target) return;
	try {
		target.setItem(registry.chave, JSON.stringify(slugs));
	} catch {
		// localStorage indisponivel — a seleção vale só para esta sessão.
	}
}

/**
 * Filtra slugs desconhecidos e duplicados de um payload não confiável.
 * Lista vazia (ou payload inválido) cai no preset padrão.
 *
 * @example
 * sanitizeStoredSlugs(['titulo', 'inexistente']); // ['titulo']
 */
export function sanitizeStoredSlugs(raw: unknown): string[] {
	return sanitizeSlugs(raw, REGISTRY_PROJETO);
}

/** Versão de `sanitizeStoredSlugs` para as colunas de etapa. */
export function sanitizeStoredStageSlugs(raw: unknown): string[] {
	return sanitizeSlugs(raw, REGISTRY_ETAPA);
}

/** `true` quando a seleção é exatamente o preset padrão (mesma ordem incluída). */
export function isDefaultSelection(slugs: readonly string[]): boolean {
	if (slugs.length !== DEFAULT_SLUGS.length) return false;
	return slugs.every((slug, i) => slug === DEFAULT_SLUGS[i]);
}

/** Lê a seleção de colunas de projeto persistida, já sanitizada. */
export function loadStoredSlugs(storage?: SlugStorage): string[] {
	return loadSlugs(REGISTRY_PROJETO, storage);
}

/** Persiste a seleção de colunas de projeto (silencioso sem `localStorage`). */
export function saveStoredSlugs(slugs: readonly string[], storage?: SlugStorage): void {
	saveSlugs(slugs, REGISTRY_PROJETO, storage);
}

/** Lê a seleção de colunas de etapa persistida, já sanitizada. */
export function loadStoredStageSlugs(storage?: SlugStorage): string[] {
	return loadSlugs(REGISTRY_ETAPA, storage);
}

/** Persiste a seleção de colunas de etapa (silencioso sem `localStorage`). */
export function saveStoredStageSlugs(slugs: readonly string[], storage?: SlugStorage): void {
	saveSlugs(slugs, REGISTRY_ETAPA, storage);
}
