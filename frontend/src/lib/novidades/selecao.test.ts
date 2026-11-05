import { describe, expect, it } from 'vitest';
import type { NovidadeResumo } from '$lib/types/novidades';
import {
	comoVista,
	hrefParaRever,
	novidadeDoBotao,
	novidadeParaAbrirSozinha,
	slugDaUrl,
	temNovidadeNaoVista,
	urlSemNovidade
} from './selecao';

function item(slug: string, vista: boolean): NovidadeResumo {
	return { slug, titulo: slug, publicada_em: '2026-11-05T00:00:00Z', vista };
}

const COM_CONTEUDO = new Set(['nova', 'antiga']);
const temConteudo = (slug: string) => COM_CONTEUDO.has(slug);

describe('qual novidade abrir', () => {
	it('abre sozinha a mais recente não vista (a lista já vem da mais recente)', () => {
		expect(
			novidadeParaAbrirSozinha([item('nova', false), item('antiga', false)], temConteudo)
		).toBe('nova');
		expect(novidadeParaAbrirSozinha([item('nova', true), item('antiga', false)], temConteudo)).toBe(
			'antiga'
		);
	});

	it('ignora novidade ativa sem conteúdo nesta versão do front', () => {
		expect(novidadeParaAbrirSozinha([item('futura', false)], temConteudo)).toBeNull();
		expect(novidadeDoBotao([item('futura', false), item('antiga', true)], temConteudo)).toBe(
			'antiga'
		);
	});

	it('o botão abre a mais recente mesmo já vista; sem nenhuma, não há botão', () => {
		expect(novidadeDoBotao([item('nova', true)], temConteudo)).toBe('nova');
		expect(novidadeDoBotao([], temConteudo)).toBeNull();
	});

	it('o ponto do botão some quando tudo foi visto', () => {
		expect(temNovidadeNaoVista([item('nova', false)], temConteudo)).toBe(true);
		expect(temNovidadeNaoVista(comoVista([item('nova', false)], 'nova'), temConteudo)).toBe(false);
	});
});

describe('reabrir pela URL', () => {
	it('lê e limpa o ?novidade= sem mexer no resto', () => {
		const url = new URL('https://x.gov.br/colecoes?ordem=nome&novidade=nova');
		expect(slugDaUrl(url)).toBe('nova');
		expect(urlSemNovidade(url).toString()).toBe('https://x.gov.br/colecoes?ordem=nome');
		expect(slugDaUrl(new URL('https://x.gov.br/colecoes?novidade=%20'))).toBeNull();
	});

	it('monta o link "Rever" do toast', () => {
		expect(hrefParaRever('/colecoes', 'colecoes-2026-11')).toBe(
			'/colecoes?novidade=colecoes-2026-11'
		);
	});
});
