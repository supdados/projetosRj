/**
 * Cache em memória (vida = sessão) do catálogo EEGD da cascata
 * objetivo → resultado → indicadores do CriarProjetoModal.
 *
 * Por que existe: sem ele o clique num resultado muda a altura do card DUAS
 * vezes (colapso imediato + chegada da rede). Com o prefetch em hover/foco, o
 * clique encontra os dados em memória e a cascata faz UMA transição só.
 *
 * Não há invalidação: o catálogo é estático dentro de uma sessão; alteração no
 * backend só aparece após recarregar a SPA.
 *
 * @example
 *   prefetchIndicadores('42');            // hover no resultado
 *   const itens = peekIndicadores('42');  // no clique: síncrono, ou null
 */
import {
	fetchIndicadoresStrict,
	fetchResultadosStrict,
	type IndicadorCatalogo,
	type ResultadoCatalogo
} from './projects';

const resultadosPorObjetivo = new Map<string, ResultadoCatalogo[]>();
const indicadoresPorResultado = new Map<string, IndicadorCatalogo[]>();
const resultadosEmVoo = new Map<string, Promise<ResultadoCatalogo[]>>();
const indicadoresEmVoo = new Map<string, Promise<IndicadorCatalogo[]>>();

function carregar<T>(
	chave: string,
	cache: Map<string, T[]>,
	emVoo: Map<string, Promise<T[]>>,
	buscar: (id: string) => Promise<T[]>
): Promise<T[]> {
	const cacheado = cache.get(chave);
	if (cacheado) return Promise.resolve(cacheado);

	const jaEmVoo = emVoo.get(chave);
	if (jaEmVoo) return jaEmVoo;

	const promessa = buscar(chave)
		.then((itens) => {
			// `[]` TAMBÉM é cacheado: com o fetch estrito, lista vazia é resposta
			// legítima (200) e não erro.
			cache.set(chave, itens);
			return itens;
		})
		.finally(() => emVoo.delete(chave));

	emVoo.set(chave, promessa);
	return promessa;
}

/** Leitura SÍNCRONA; `null` = ainda não cacheado. */
export function peekResultados(objetivoId: string): ResultadoCatalogo[] | null {
	return resultadosPorObjetivo.get(objetivoId) ?? null;
}

/** Leitura SÍNCRONA; `null` = ainda não cacheado. */
export function peekIndicadores(resultadoId: string): IndicadorCatalogo[] | null {
	return indicadoresPorResultado.get(resultadoId) ?? null;
}

export function loadResultados(objetivoId: string): Promise<ResultadoCatalogo[]> {
	return carregar(objetivoId, resultadosPorObjetivo, resultadosEmVoo, fetchResultadosStrict);
}

export function loadIndicadores(resultadoId: string): Promise<IndicadorCatalogo[]> {
	return carregar(resultadoId, indicadoresPorResultado, indicadoresEmVoo, fetchIndicadoresStrict);
}

/** Aquecimento fire-and-forget (hover/foco). Falha silenciosa: não cacheia erro. */
export function prefetchResultados(objetivoId: string): void {
	void loadResultados(objetivoId).catch(() => undefined);
}

/** Aquecimento fire-and-forget (hover/foco). Falha silenciosa: não cacheia erro. */
export function prefetchIndicadores(resultadoId: string): void {
	void loadIndicadores(resultadoId).catch(() => undefined);
}
