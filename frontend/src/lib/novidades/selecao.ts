/**
 * Regras PURAS de qual novidade mostrar — sem Svelte, sem rede, testáveis.
 *
 * `temConteudo` vem injetado (o registro `conteudo.ts` importa componentes
 * Svelte): uma novidade ativa no banco sem conteúdo nesta versão do front
 * (deploy fora de ordem) é ignorada em vez de abrir um modal vazio.
 *
 * Ex.: `novidadeParaAbrirSozinha(itens, (slug) => slug in CONTEUDO_NOVIDADES)`.
 */
import type { NovidadeResumo } from '$lib/types/novidades';

export type TemConteudo = (slug: string) => boolean;

/** Parâmetro de URL que reabre uma novidade (ação "Rever" do toast). */
export const PARAM_NOVIDADE = 'novidade';

/** A mais recente ainda não vista — a que abre sozinha depois do login. */
export function novidadeParaAbrirSozinha(
	itens: readonly NovidadeResumo[],
	temConteudo: TemConteudo
): string | null {
	return itens.find((item) => !item.vista && temConteudo(item.slug))?.slug ?? null;
}

/** A mais recente com conteúdo, vista ou não — a que o botão "Novidades" abre. */
export function novidadeDoBotao(
	itens: readonly NovidadeResumo[],
	temConteudo: TemConteudo
): string | null {
	return itens.find((item) => temConteudo(item.slug))?.slug ?? null;
}

/** Ponto laranja no botão: há alguma novidade com conteúdo que a pessoa não viu. */
export function temNovidadeNaoVista(
	itens: readonly NovidadeResumo[],
	temConteudo: TemConteudo
): boolean {
	return novidadeParaAbrirSozinha(itens, temConteudo) !== null;
}

/** Cópia da lista com `slug` marcada como vista (atualização otimista). */
export function comoVista(itens: readonly NovidadeResumo[], slug: string): NovidadeResumo[] {
	return itens.map((item) => (item.slug === slug ? { ...item, vista: true } : item));
}

/** `?novidade=<slug>` da URL, ou `null`. Ex.: `/colecoes?novidade=colecoes-2026-11`. */
export function slugDaUrl(url: URL): string | null {
	const slug = url.searchParams.get(PARAM_NOVIDADE)?.trim();
	return slug ? slug : null;
}

/** A mesma URL sem o `?novidade=` (o parâmetro só serve para abrir uma vez). */
export function urlSemNovidade(url: URL): URL {
	const limpa = new URL(url);
	limpa.searchParams.delete(PARAM_NOVIDADE);
	return limpa;
}

/** Destino da ação "Rever" do toast: o caminho dado com `?novidade=<slug>`. */
export function hrefParaRever(caminho: string, slug: string): string {
	return `${caminho}?${PARAM_NOVIDADE}=${encodeURIComponent(slug)}`;
}
