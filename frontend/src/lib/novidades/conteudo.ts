/**
 * Conteúdo das Novidades, indexado pelo `slug` da tabela `novidade` do backend.
 *
 * O banco diz QUAIS estão ativas e quem já viu (`routes/api/novidades.py`); o
 * texto e as ilustrações moram aqui porque as ilustrações são componentes.
 *
 * Nova novidade:
 *   1. uma entrada aqui (passos + ilustrações em `components/novidades/<tema>/`);
 *   2. uma migração que insere a linha em `novidade` (ativa ou não);
 *   3. ligar/desligar e "mostrar de novo" ficam na tela Admin › Novidades.
 *
 * Texto: apresentar como se a pessoa visse a função pela primeira vez — nada de
 * "agora", "novo" ou comparação com o que existia antes.
 */
import type { Component } from 'svelte';
import VisualAgrupar from '$lib/components/novidades/colecoes/VisualAgrupar.svelte';
import VisualCompartilhar from '$lib/components/novidades/colecoes/VisualCompartilhar.svelte';
import VisualEditores from '$lib/components/novidades/colecoes/VisualEditores.svelte';
import VisualMontar from '$lib/components/novidades/colecoes/VisualMontar.svelte';

export interface PassoNovidade {
	titulo: string;
	texto: string;
	/** Dois pontos-chave curtos, com o ícone de check. */
	detalhes: readonly string[];
	/** Fundo do painel da ilustração — classe ESTÁTICA (o Tailwind não compila classe montada). */
	fundo: string;
	visual: Component;
}

export interface ConteudoNovidade {
	/** Aparece no sobretítulo "NOVIDADES · <rótulo>". */
	rotulo: string;
	passos: readonly PassoNovidade[];
	/** Botão do último passo: leva à função apresentada. */
	acaoFinal: { rotulo: string; href: string };
}

export const CONTEUDO_NOVIDADES: Readonly<Record<string, ConteudoNovidade>> = {
	'colecoes-2026-11': {
		rotulo: 'Coleções',
		acaoFinal: { rotulo: 'Abrir Coleções', href: '/colecoes' },
		passos: [
			{
				titulo: 'Agrupe projetos do jeito que você acompanha',
				texto:
					'Reúna projetos de várias áreas em uma coleção e veja, de uma vez, quantas etapas estão concluídas, vigentes ou atrasadas.',
				detalhes: [
					'Favoritos guarda os projetos que você marca com a estrela',
					'Passe o mouse nas áreas para ver de onde vem cada projeto'
				],
				fundo: 'bg-wash-brand',
				visual: VisualAgrupar
			},
			{
				titulo: 'Monte a coleção em uma só tela',
				texto:
					'Defina nome, cor e ícone, marque os projetos e escolha quem enxerga. A capa acompanha cada escolha antes de você salvar.',
				detalhes: [
					'Os projetos da sua área aparecem prontos para marcar',
					'Quem enxerga a coleção é definido na criação'
				],
				fundo: 'bg-wash-success',
				visual: VisualMontar
			},
			{
				titulo: 'Compartilhe com pessoas ou áreas',
				texto:
					'Convide pessoas ou uma área inteira. Cada pessoa aceita o convite pelo sino e, a partir daí, passa a ver a coleção.',
				detalhes: [
					'Leitores acompanham a coleção e leem os projetos',
					'Você vê quem aceitou, recusou ou saiu'
				],
				fundo: 'bg-wash-warning',
				visual: VisualCompartilhar
			},
			{
				titulo: 'Editores ajudam a montar',
				texto:
					'Quem é editor inclui projetos da própria área e remove só o que incluiu. Cada item mostra quem o adicionou.',
				detalhes: [
					'Quem sai da coleção leva junto os projetos que incluiu',
					'Editar, apagar e gerir acessos continua só com você'
				],
				fundo: 'bg-wash-attention',
				visual: VisualEditores
			}
		]
	}
};

export function temConteudoNovidade(slug: string): boolean {
	return Object.hasOwn(CONTEUDO_NOVIDADES, slug);
}
