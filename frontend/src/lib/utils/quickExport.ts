/**
 * Exportação rápida de projetos (`GET /api/projetos/exportar?rapida=1`): colunas
 * fixas, todos os status e só o filtro de área da lista. Sem escolha de colunas.
 */

/** Coluna fixa do CSV rápido; `aPreencher` = sem campo no sistema, sai vazia. */
export interface QuickExportColumn {
	rotulo: string;
	aPreencher: boolean;
}

/**
 * Cabeçalhos fixos do CSV rápido, na ordem da ficha de projetos estratégicos
 * (espelha `QUICK_EXPORT_COLUMNS` do backend); só exibição.
 */
export const QUICK_EXPORT_COLUMNS: readonly QuickExportColumn[] = [
	{ rotulo: 'ID', aPreencher: false },
	{ rotulo: 'Situação', aPreencher: false },
	{ rotulo: 'Objeto / Produto', aPreencher: false },
	{ rotulo: 'Localização', aPreencher: false },
	{ rotulo: 'Escopo', aPreencher: false },
	{ rotulo: 'Execução física e financeira', aPreencher: false },
	{ rotulo: 'Contratos e instrumentos', aPreencher: true },
	{ rotulo: 'Datas de início e fim previstas', aPreencher: false },
	{ rotulo: 'Próximas etapas e prazos', aPreencher: false },
	{ rotulo: 'Ponto crítico / Riscos', aPreencher: true },
	{ rotulo: 'Processo SEI', aPreencher: false },
	{ rotulo: 'TCE', aPreencher: false },
	{ rotulo: 'Responsável', aPreencher: false }
];

/** Filtro de área da lista — o único que a exportação rápida respeita. */
export interface QuickExportArea {
	orgao?: number | null;
	apenas_orgao?: boolean;
}

/**
 * Querystring da exportação rápida; `area` nulo exporta todos os projetos visíveis.
 *
 * @example buildQuickExportParams({ orgao: 12, apenas_orgao: true }).toString()
 * // 'rapida=1&orgao=12&apenas_orgao=1'
 */
export function buildQuickExportParams(area: QuickExportArea | null): URLSearchParams {
	const params = new URLSearchParams({ rapida: '1' });
	if (area?.orgao == null) return params;
	params.set('orgao', String(area.orgao));
	if (area.apenas_orgao) params.set('apenas_orgao', '1');
	return params;
}

/**
 * Frase do escopo exibida no modal no lugar dos radios de escopo.
 *
 * @example describeQuickExportScope({ orgao: 12 }, 'SETD') // 'Área SETD · todos os status'
 */
export function describeQuickExportScope(
	area: QuickExportArea | null,
	areaRotulo: string | null
): string {
	if (area?.orgao == null) return 'Todos os projetos · todos os status';
	const rotulo = areaRotulo ? `Área ${areaRotulo}` : 'Área selecionada';
	const recorte = area.apenas_orgao ? ' (sem subáreas)' : '';
	return `${rotulo}${recorte} · todos os status`;
}
