/**
 * Números da CAPA de uma coleção (card do índice e tela de sucesso do modal
 * Nova coleção): barra segmentada das etapas por situação, a linha de três
 * números (concluídas · vigentes · atrasadas) e a pílula "N áreas".
 *
 * As faixas vêm prontas do backend (`collection_rollups`): concluída, em
 * andamento e atrasada são excludentes; "não iniciada" é o resto do total.
 * Classes em mapa ESTÁTICO — o Tailwind só compila classe inteira no fonte.
 *
 * Exemplo:
 *   segmentosDaBarra({ etapas_total: 10, etapas_concluidas: 4, etapas_em_andamento: 3, etapas_atrasadas: 1 })
 *   // → concluídas 4, vigentes 3, atrasadas 1, não iniciadas 2
 */

import type { AreaColecao, ColecaoResumo } from '$lib/types/collections';

export type FaixaEtapa = 'concluidas' | 'andamento' | 'atrasadas' | 'nao_iniciadas';

/** As três faixas que viram número embaixo da barra (não iniciada só pinta a barra). */
export type FaixaComNumero = Exclude<FaixaEtapa, 'nao_iniciadas'>;

/** Só os contadores de etapa do resumo — o que a capa precisa para desenhar. */
export type EtapasDaColecao = Pick<
	ColecaoResumo,
	'etapas_total' | 'etapas_concluidas' | 'etapas_em_andamento' | 'etapas_atrasadas'
>;

export interface SegmentoBarra {
	faixa: FaixaEtapa;
	valor: number;
	/** Cor do segmento (fundo). */
	classe: string;
	/** "4 concluídas" — tooltip do segmento. */
	rotulo: string;
}

export interface NumeroAndamento {
	faixa: FaixaComNumero;
	valor: number;
	/** Rótulo sem o número ("concluídas"), concordando com o valor. */
	rotulo: string;
	/** Cor da bolinha ao lado do número. */
	pontoClasse: string;
}

interface DefinicaoFaixa {
	singular: string;
	plural: string;
	classe: string;
}

const FAIXAS: Readonly<Record<FaixaEtapa, DefinicaoFaixa>> = {
	concluidas: { singular: 'concluída', plural: 'concluídas', classe: 'bg-success-600' },
	andamento: { singular: 'vigente', plural: 'vigentes', classe: 'bg-primary-600' },
	atrasadas: { singular: 'atrasada', plural: 'atrasadas', classe: 'bg-danger-600' },
	nao_iniciadas: { singular: 'não iniciada', plural: 'não iniciadas', classe: 'bg-border-strong' }
};

const ORDEM_DA_BARRA: readonly FaixaEtapa[] = ['concluidas', 'andamento', 'atrasadas', 'nao_iniciadas'];
const ORDEM_DOS_NUMEROS: readonly FaixaComNumero[] = ['concluidas', 'andamento', 'atrasadas'];

/** `"1 projeto"` / `"3 projetos"`; plural irregular via `formaPlural`. */
export function plural(n: number, singular: string, formaPlural = `${singular}s`): string {
	return `${n} ${n === 1 ? singular : formaPlural}`;
}

/**
 * Contagem por faixa. `?? 0`: payload antigo em cache SWR (sem as faixas
 * novas) não quebra a capa — sai tudo como "não iniciada".
 */
export function contagemPorFaixa(etapas: EtapasDaColecao): Record<FaixaEtapa, number> {
	const concluidas = etapas.etapas_concluidas ?? 0;
	const andamento = etapas.etapas_em_andamento ?? 0;
	const atrasadas = etapas.etapas_atrasadas ?? 0;
	const resto = (etapas.etapas_total ?? 0) - concluidas - andamento - atrasadas;
	return { concluidas, andamento, atrasadas, nao_iniciadas: Math.max(0, resto) };
}

/** Segmentos da barra (faixa vazia não vira segmento), na ordem da régua. */
export function segmentosDaBarra(etapas: EtapasDaColecao): SegmentoBarra[] {
	const contagem = contagemPorFaixa(etapas);
	return ORDEM_DA_BARRA.filter((faixa) => contagem[faixa] > 0).map((faixa) => {
		const def = FAIXAS[faixa];
		return {
			faixa,
			valor: contagem[faixa],
			classe: def.classe,
			rotulo: plural(contagem[faixa], def.singular, def.plural)
		};
	});
}

/** Os três números embaixo da barra — sempre os três, mesmo zerados. */
export function numerosDoAndamento(etapas: EtapasDaColecao): NumeroAndamento[] {
	const contagem = contagemPorFaixa(etapas);
	return ORDEM_DOS_NUMEROS.map((faixa) => {
		const def = FAIXAS[faixa];
		return {
			faixa,
			valor: contagem[faixa],
			rotulo: contagem[faixa] === 1 ? def.singular : def.plural,
			pontoClasse: def.classe
		};
	});
}

/** Nome exibido de uma área; projeto sem órgão vira "Sem área". */
export function nomeDaArea(area: Pick<AreaColecao, 'sigla'>): string {
	return area.sigla ?? 'Sem área';
}

/** Quantas áreas de verdade ("Sem área" não é uma área). */
export function quantasAreas(areas: readonly Pick<AreaColecao, 'sigla'>[]): number {
	return areas.filter((area) => area.sigla !== null).length;
}

/**
 * Rótulo da pílula: conta só áreas de verdade; coleção só com projetos sem
 * órgão mostra "Sem área".
 */
export function rotuloAreas(areas: readonly Pick<AreaColecao, 'sigla'>[]): string {
	const reais = quantasAreas(areas);
	if (reais === 0 && areas.length > 0) return 'Sem área';
	return plural(reais, 'área');
}

/**
 * Agrupa as siglas dos projetos escolhidos no MESMO formato e ordem do backend
 * (`areas_por_colecao`): mais projetos primeiro, empate pela sigla, sem órgão
 * por último. Alimenta a pílula da capa ao vivo no modal Nova coleção.
 */
export function areasDasSiglas(siglas: readonly (string | null)[]): AreaColecao[] {
	return somarAreas([], siglas.map((sigla) => ({ sigla, projetos: 1 })));
}

/**
 * Soma duas listas de áreas (mesma sigla = projetos somados), na ordem do
 * backend. Uso: a pílula do "Adicionar projetos" mostra as áreas que a
 * coleção TERÁ — as atuais mais as dos projetos marcados.
 */
export function somarAreas(
	atuais: readonly AreaColecao[],
	novas: readonly AreaColecao[]
): AreaColecao[] {
	const contagem = new Map<string | null, number>();
	for (const area of [...atuais, ...novas]) {
		contagem.set(area.sigla, (contagem.get(area.sigla) ?? 0) + area.projetos);
	}
	return [...contagem]
		.map(([sigla, projetos]) => ({ sigla, projetos }))
		.sort((a, b) => {
			if (a.projetos !== b.projetos) return b.projetos - a.projetos;
			if (a.sigla === null || b.sigla === null) return a.sigla === null ? 1 : -1;
			return a.sigla.localeCompare(b.sigla, 'pt-BR');
		});
}
