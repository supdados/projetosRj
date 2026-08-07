// Registry de ícones duotone de estado único (redesign 2026) — paths em viewBox 24.
export interface AppIconPath {
	d: string;
	opacity?: string;
	fillRule?: 'evenodd';
}

// Sub-paths de 'projetos' compartilhados com TopnavIcon.svelte (a folha cross-fada lá).
export const PROJETOS_ABA_D = 'M2.4 4.6H9.2L11.6 7.3H2.4Z';
export const PROJETOS_FOLHA_D = 'M10.4 5.4H18.6V9.2H10.4Z';
export const PROJETOS_PASTA_D = 'M2.4 7.3H18.9L21.6 10V19.4H2.4Z';

export type AppIconId =
	| 'criacao'
	| 'edicao'
	| 'status'
	| 'conclusao'
	| 'arquivo'
	| 'exclusao'
	| 'atribuicao'
	| 'convite'
	| 'comentario'
	| 'anexo'
	| 'etapa'
	| 'reuniao'
	| 'sino'
	| 'projetos'
	| 'tarefas'
	| 'calendario'
	| 'kebab';

export const APP_ICONS: Record<AppIconId, AppIconPath[]> = {
	criacao: [{ d: 'M10 3.4H14V10H19.2L20.6 11.4V14H14V20.6H10V14H3.4V10H10Z' }],
	edicao: [
		{ d: 'M5.4 15L16.4 4L20 7.6L9 18.6ZM8.6 11.8L12.2 15.4L13.2 14.4L9.6 10.8Z', fillRule: 'evenodd' },
		{ d: 'M5.4 15L9 18.6L5.1 18.9Z' },
		{ d: 'M16.4 4L20 7.6L21.8 5.8L18.2 2.2Z', opacity: '.48' }
	],
	status: [
		{ d: 'M3.6 15.4H8V20.4H3.6Z', opacity: '.48' },
		{ d: 'M9.8 11.4H14.2V20.4H9.8Z', opacity: '.48' },
		{ d: 'M16 7.4H19L20.4 8.8V20.4H16Z' }
	],
	conclusao: [
		{
			d: 'M7.6 2.8H16.4L21.2 7.6V16.4L16.4 21.2H7.6L2.8 16.4V7.6ZM10.6 17L5.6 12L7.9 9.7L10.6 12.4L16.5 6.5L18.8 8.8Z',
			fillRule: 'evenodd'
		}
	],
	arquivo: [
		{ d: 'M2.6 4.4H21.4V8H2.6Z', opacity: '.48' },
		{ d: 'M4.4 8.6H18L19.6 10.2V20.4H4.4ZM9.4 12H14.6V13.8H9.4Z', fillRule: 'evenodd' }
	],
	exclusao: [
		{ d: 'M9.4 2.6H14.6V4.8H9.4Z', opacity: '.48' },
		{ d: 'M3.2 5.4H20.8V7.6H3.2Z', opacity: '.48' },
		{ d: 'M5.4 8.6H18.6L17.3 21.4H6.7ZM9 11.4H10.6V18.6H9ZM13.4 11.4H15V18.6H13.4Z', fillRule: 'evenodd' }
	],
	atribuicao: [
		{ d: 'M9 5.4A3.2 3.2 0 1 1 9 11.8A3.2 3.2 0 1 1 9 5.4Z' },
		{ d: 'M2.6 19.4A6.4 6.4 0 0 1 15.4 19.4Z' },
		{ d: 'M17.2 11.6L14.4 8.8L15.7 7.5L17.2 9L20.6 5.6L21.9 6.9Z', opacity: '.48' }
	],
	convite: [
		{ d: 'M2.6 6.4H21.4V17.6H2.6ZM2.9 6.4L12 13.2L21.1 6.4V8.4L12 15.2L2.9 8.4Z', fillRule: 'evenodd' }
	],
	comentario: [
		{
			d: 'M2.6 4.4H18.4L21.4 7.4V16.4H8.4L4.4 20.4V16.4H2.6ZM6 8.6H18V10.2H6ZM6 12H14V13.6H6Z',
			fillRule: 'evenodd'
		}
	],
	anexo: [{ d: 'M17 4V16A5 5 0 0 1 7 16V8A3 3 0 0 1 13 8V14H11V8A1 1 0 0 0 9 8V16A3 3 0 0 0 15 16V4Z' }],
	etapa: [
		{ d: 'M2.6 4.4H4.2V15.4H8.6V17H2.6Z', opacity: '.48' },
		{ d: 'M9.4 9.4H13.4L15 11H9.4Z', opacity: '.48' },
		{ d: 'M9.4 11H19.4L21 12.6V19.6H9.4Z' }
	],
	reuniao: [
		{
			d: 'M2.6 5H19L21.4 7.4V21H2.6ZM4.7 9.4H19.3V10.4H4.7ZM6.2 12.6H8.3V14.7H6.2ZM15.6 12.6H17.7V14.7H15.6ZM10.9 12.6H13V14.7H10.9ZM6.2 16.4H8.3V18.5H6.2ZM9.8 15.3H14.1V19.6H9.8ZM10.8 16.3H13.1V18.6H10.8Z',
			fillRule: 'evenodd'
		}
	],
	sino: [
		{ d: 'M10.7 1.6H13.3V3.6H10.7Z', opacity: '.48' },
		{ d: 'M5.6 16.6V11.2A6.4 6.4 0 0 1 18.4 11.2V16.6Z' },
		{ d: 'M3.6 16.6H20.4V18.6H3.6Z', opacity: '.48' }
	],
	// Aba+folha num path só: a sobreposição delas deve render a .48 uniforme (doc usa <g opacity>).
	projetos: [
		{ d: `${PROJETOS_ABA_D}${PROJETOS_FOLHA_D}`, opacity: '.48' },
		{ d: PROJETOS_PASTA_D }
	],
	tarefas: [
		{
			d: 'M4.6 4.2H16.7L19.4 6.9V21.2H4.6ZM7.6 10.4H16.4V12.3H7.6ZM7.6 14.6H13.2V16.5H7.6Z',
			fillRule: 'evenodd'
		},
		{ d: 'M8.7 2.4H15.3V5.8H8.7Z', opacity: '.48' }
	],
	calendario: [
		{
			d: 'M2.6 5H19L21.4 7.4V21H2.6ZM4.7 9.4H19.3V10.4H4.7ZM6.2 12.6H8.3V14.7H6.2ZM10.9 12.6H13V14.7H10.9ZM15.6 12.6H17.7V14.7H15.6ZM6.2 16.4H8.3V18.5H6.2ZM10.9 16.4H13V18.5H10.9Z',
			fillRule: 'evenodd'
		}
	],
	// Menu contextual (3 pontos verticais); ponta e base a .48, centro sólido.
	kebab: [
		{ d: 'M13.8 5A1.8 1.8 0 1 1 10.2 5A1.8 1.8 0 1 1 13.8 5Z', opacity: '.48' },
		{ d: 'M13.8 12A1.8 1.8 0 1 1 10.2 12A1.8 1.8 0 1 1 13.8 12Z' },
		{ d: 'M13.8 19A1.8 1.8 0 1 1 10.2 19A1.8 1.8 0 1 1 13.8 19Z', opacity: '.48' }
	]
};
