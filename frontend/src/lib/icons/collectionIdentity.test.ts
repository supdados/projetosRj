/**
 * Regressão: as classes da identidade da coleção GERAM CSS com a config real
 * do Tailwind. `extend.borderColor` declarava `success`/`warning`/`danger` como
 * string, o que apagava a escala de `colors` — `border-success-600` (swatch
 * ativo Verde/Âmbar/Vermelho) não compilava e a borda sumia sem erro de build.
 */
import postcss from 'postcss';
import tailwindcss from 'tailwindcss';
import { describe, expect, it } from 'vitest';
import config from '../../../tailwind.config';
import {
	COLECAO_CAPA_TOM,
	COLECAO_COR_OPTIONS,
	COLECAO_ICONE_ATIVO_CLASS,
	COLECAO_ICONE_OPTIONS,
	tomDaCapa
} from './collectionIdentity';
import { COLLECTION_ICONS } from './collectionIcons';

/** Compila só os utilitários das classes dadas, com o tema do projeto. */
async function cssDasClasses(classes: readonly string[]): Promise<string> {
	const plugin = tailwindcss({
		...config,
		content: [{ raw: classes.join(' '), extension: 'html' }],
		safelist: [],
		corePlugins: { preflight: false }
	});
	const resultado = await postcss([plugin]).process('@tailwind utilities;', { from: undefined });
	return resultado.css;
}

/** Corpo da regra `.classe { ... }`, ou `null` quando o Tailwind descartou a classe. */
function regraDe(css: string, classe: string): string | null {
	const inicio = css.indexOf(`.${classe} {`);
	if (inicio < 0) return null;
	return css.slice(inicio, css.indexOf('}', inicio));
}

const CLASSES_DA_IDENTIDADE = [
	...COLECAO_COR_OPTIONS.flatMap((opcao) => [opcao.wash, opcao.dot, opcao.ativo]),
	...Object.values(COLECAO_ICONE_ATIVO_CLASS).flatMap((classes) => classes.split(' ')),
	...Object.values(COLECAO_CAPA_TOM).flatMap((tom) => [tom.wash, tom.tinta, tom.selo])
];

describe('identidade da coleção × config do Tailwind', () => {
	it('toda classe de swatch e de ícone ativo gera CSS (nenhuma borda some)', async () => {
		const css = await cssDasClasses(CLASSES_DA_IDENTIDADE);
		const descartadas = [...new Set(CLASSES_DA_IDENTIDADE)].filter((c) => regraDe(css, c) === null);
		expect(descartadas).toEqual([]);
	});

	it('o degrau 600 das três famílias aponta para a escala fixa, como nas outras', async () => {
		const css = await cssDasClasses(['border-success-600', 'border-warning-600', 'border-danger-600']);
		expect(regraDe(css, 'border-success-600')).toContain('var(--ds-color-success-600)');
		expect(regraDe(css, 'border-warning-600')).toContain('var(--ds-color-warning-600)');
		expect(regraDe(css, 'border-danger-600')).toContain('var(--ds-color-danger-600)');
	});

	it('os tokens de papel (`border-success`, `-soft`) continuam com o valor do papel', async () => {
		const css = await cssDasClasses(['border-success', 'border-warning', 'border-danger', 'border-danger-soft']);
		expect(regraDe(css, 'border-success')).toContain('var(--ds-color-border-success)');
		expect(regraDe(css, 'border-warning')).toContain('var(--ds-color-border-warning)');
		expect(regraDe(css, 'border-danger')).toContain('var(--ds-color-border-danger)');
		expect(regraDe(css, 'border-danger-soft')).toContain('var(--ds-color-border-danger-soft)');
	});
});

describe('opções de ícone e tom da capa', () => {
	it('todo ícone escolhível tem desenho no registry (12, grade 6×2 do modal)', () => {
		expect(COLECAO_ICONE_OPTIONS).toHaveLength(12);
		const semDesenho = COLECAO_ICONE_OPTIONS.filter((o) => !COLLECTION_ICONS[o.id]?.length);
		expect(semDesenho).toEqual([]);
	});

	it('cor desconhecida cai no tom azul padrão', () => {
		expect(tomDaCapa('inexistente' as never)).toBe(COLECAO_CAPA_TOM.primary);
		expect(tomDaCapa('success')).toBe(COLECAO_CAPA_TOM.success);
	});
});
