/**
 * Grade do índice de Coleções — fonte única para a página e o skeleton (a
 * troca loading → pronto não pode saltar de layout).
 *
 * Por quê colunas automáticas e não `lg:grid-cols-4`: com número fixo de
 * colunas o card só estica quando a tela cresce (a capa vira faixa larga e
 * vazia); aqui a LARGURA do card é que manda e a tela larga ganha colunas.
 * `auto-fill` (e não `auto-fit`) mantém as trilhas vazias, então com poucas
 * coleções o card fica na largura normal em vez de esticar até a borda.
 * `min(100%, …)` deixa a coluna única caber no celular sem overflow.
 *
 * Mínimo de 16.5rem (264px) + gap de 1.25rem: notebook de 1440px fica com 4
 * colunas de ~288px (o tamanho de referência) e monitor de 2048px com 6 da
 * mesma largura, em vez de 4 de ~440px.
 *
 * Ex.: `<div class={COLECOES_GRID_CLS}>…cards…</div>`.
 */
export const COLECOES_GRID_CLS =
	'grid gap-5 grid-cols-[repeat(auto-fill,minmax(min(100%,16.5rem),1fr))]';

/**
 * Só Favoritos (estado vazio): Favoritos numa coluna da largura de referência
 * do card e o painel ilustrado no resto da linha. Trilhas explícitas porque
 * "o resto da linha" de uma grade `auto-fill` depende de quantas colunas
 * couberam, e o painel não tem como saber isso. Abaixo de `md` empilha.
 *
 * Ex.: `<div class={COLECOES_GRID_VAZIO_CLS}><Favoritos/><ColecoesVazio/></div>`.
 */
export const COLECOES_GRID_VAZIO_CLS =
	'grid gap-5 grid-cols-1 items-start md:grid-cols-[18rem_minmax(0,1fr)]';
