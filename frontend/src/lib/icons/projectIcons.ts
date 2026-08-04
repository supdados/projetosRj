// Registry de ícones de projeto e entrega (redesign 2026) — paths em viewBox 24.
export interface ProjectIconPath {
	d: string;
	opacity?: string;
	fillRule?: 'evenodd';
	transform?: string;
}

export type ProjectIconId =
	| 'projeto-ativo'
	| 'projeto-suspenso'
	| 'projeto-finalizado'
	| 'entrega-sistema'
	| 'entrega-painel'
	| 'entrega-norma'
	| 'entrega-instrumento'
	| 'entrega-fluxo'
	| 'entrega-eventos'
	| 'entrega-outro'
	| 'selo-abep'
	| 'selo-tce'
	| 'selo-forum'
	| 'documentacao'
	| 'produto'
	| 'observacao'
	| 'link'
	| 'historico';

export const PROJECT_ICONS: Record<ProjectIconId, ProjectIconPath[]> = {
	'projeto-ativo': [
		{ d: 'M12 3A9 9 0 1 1 3 12H5.8A6.2 6.2 0 1 0 12 5.8Z' },
		{ d: 'M12 9.4A2.6 2.6 0 1 1 12 14.6A2.6 2.6 0 1 1 12 9.4Z' }
	],
	'projeto-suspenso': [
		{
			d: 'M12 3A9 9 0 1 1 12 21A9 9 0 1 1 12 3ZM12 5.8A6.2 6.2 0 1 0 12 18.2A6.2 6.2 0 1 0 12 5.8Z',
			fillRule: 'evenodd'
		},
		{ d: 'M9.3 8.8H11.1V15.2H9.3Z' },
		{ d: 'M12.9 8.8H14.7V15.2H12.9Z' }
	],
	'projeto-finalizado': [
		{
			d: 'M12 3A9 9 0 1 1 12 21A9 9 0 1 1 12 3ZM12 5.4A6.6 6.6 0 1 0 12 18.6A6.6 6.6 0 1 0 12 5.4ZM12 6.6A5.4 5.4 0 1 1 12 17.4A5.4 5.4 0 1 1 12 6.6Z',
			fillRule: 'evenodd'
		}
	],
	'entrega-sistema': [
		{ d: 'M2.6 3.4H21.4V16.2H2.6ZM4.8 5.6H19.2V14H4.8Z', fillRule: 'evenodd' },
		{ d: 'M10.4 16.2H13.6V19.2H10.4Z' },
		{ d: 'M6.8 19.2H17.2V21.4H6.8Z' }
	],
	'entrega-painel': [
		{ d: 'M4.2 14.6H7V19.4H4.2Z' },
		{ d: 'M8.8 9.8H11.6V19.4H8.8Z' },
		{ d: 'M13.4 12.6H16.2V19.4H13.4Z' },
		{ d: 'M18 6.6H20.8V19.4H18Z' },
		{ d: 'M2.6 19.4H21.4V21.4H2.6Z', opacity: '.48' }
	],
	'entrega-norma': [
		{
			d: 'M5.4 3.4H18.6V20.6H5.4ZM7.6 7.4H16.4V8.8H7.6ZM7.6 10.4H16.4V11.8H7.6ZM7.6 13.4H12.8V14.8H7.6ZM14.6 15.4A2.4 2.4 0 1 1 14.6 20.2A2.4 2.4 0 1 1 14.6 15.4Z',
			fillRule: 'evenodd'
		},
		{ d: 'M14.6 16.6A1.2 1.2 0 1 1 14.6 19A1.2 1.2 0 1 1 14.6 16.6Z' }
	],
	'entrega-instrumento': [
		{ d: 'M2.6 3.4H12.6L16.4 7.2V12.8H2.6Z' },
		{ d: 'M21.4 20.6H11.4L7.6 16.8V11.2H21.4Z', opacity: '.48' }
	],
	'entrega-fluxo': [{ d: 'M2.6 3.4H11V13H15.4V10.6L21.4 14.8L15.4 19V16.6H7.4V7H2.6Z' }],
	'entrega-eventos': [
		{ d: 'M2 18.4H22V20.8H2Z' },
		{ d: 'M3.2 14.6H5.8V18.4H3.2Z', opacity: '.48' },
		{ d: 'M17.4 14.6H20V18.4H17.4Z', opacity: '.48' },
		{ d: 'M7.4 4H9.9V18.4H7.4Z' },
		{ d: 'M9.9 4.6H19.5L16.8 7.9L19.5 11.2H9.9Z' }
	],
	'entrega-outro': [
		{ d: 'M2.8 2.8H11.2V11.2H2.8Z' },
		{ d: 'M17 2.8A4.2 4.2 0 1 1 17 11.2A4.2 4.2 0 1 1 17 2.8Z', opacity: '.48' },
		{ d: 'M2.8 12.8H8.4L11.2 15.6V21.2H2.8Z', opacity: '.48' },
		{ d: 'M12.8 12.8H21.2V21.2H12.8Z' }
	],
	'selo-abep': [
		{
			d: 'M9.2 2.6H14.8L18.4 6.2V11.8L14.8 15.4H9.2L5.6 11.8V6.2ZM10.1 4.8H13.9L16.2 7.1V10.9L13.9 13.2H10.1L7.8 10.9V7.1Z',
			fillRule: 'evenodd'
		},
		{ d: 'M8.8 17.2H15.2V19.4H8.8Z', opacity: '.48' },
		{ d: 'M6.6 19.4H17.4V21.4H6.6Z', opacity: '.48' }
	],
	'selo-tce': [
		{ d: 'M3.4 8.4V6.2L5.6 4H18.4L20.6 6.2V8.4Z' },
		{ d: 'M5.6 8.4H8.4V17.2H5.6Z' },
		{ d: 'M10.6 8.4H13.4V17.2H10.6Z' },
		{ d: 'M15.6 8.4H18.4V17.2H15.6Z' },
		{ d: 'M4.6 17.2H19.4V19.4H4.6Z', opacity: '.48' },
		{ d: 'M2.6 19.4H21.4V21.4H2.6Z', opacity: '.48' }
	],
	// Duas falas (fórum); os dois vazados do balão da frente encurtam de 8.6 para
	// 5.0 — a "simplificação".
	'selo-forum': [
		{
			d: 'M14 2.6H19.4A2 2 0 0 1 21.4 4.6V7.4A2 2 0 0 1 19.4 9.4H14A2 2 0 0 1 12 7.4V4.6A2 2 0 0 1 14 2.6ZM16.8 9.4H19.4V11.4Z',
			opacity: '.48'
		},
		{
			d: 'M5.2 7.8H13.8A2.6 2.6 0 0 1 16.4 10.4V15.6A2.6 2.6 0 0 1 13.8 18.2H10.2L6 20.8V18.2H5.2A2.6 2.6 0 0 1 2.6 15.6V10.4A2.6 2.6 0 0 1 5.2 7.8ZM5.2 10.4H13.8V12.2H5.2ZM5.2 13.8H10.2V15.6H5.2Z',
			fillRule: 'evenodd'
		}
	],
	documentacao: [
		{ d: 'M2.6 5.4L11.4 7.4V19.8L2.6 17.8Z', opacity: '.48' },
		{
			d: 'M21.4 5.4L12.6 7.4V19.8L21.4 17.8ZM14.6 10.4L19.4 9.3V10.7L14.6 11.8ZM14.6 13.4L18 12.6V14L14.6 14.8Z',
			fillRule: 'evenodd'
		}
	],
	produto: [
		{
			d: 'M10.8 4H20.6V20H10.8L4 12ZM9.6 9.2A2.8 2.8 0 1 0 9.6 14.8A2.8 2.8 0 1 0 9.6 9.2Z',
			fillRule: 'evenodd'
		}
	],
	observacao: [
		{ d: 'M3.4 4.6H10.6V11.8L7.2 19.4H3.4L6.6 11.8H3.4Z' },
		{ d: 'M13.4 4.6H20.6V11.8L17.2 19.4H13.4L16.6 11.8H13.4Z', opacity: '.48' }
	],
	link: [
		{
			d: 'M6.6 5.8H13.6A3.6 3.6 0 0 1 13.6 13H6.6A3.6 3.6 0 0 1 6.6 5.8ZM8.4 8.4H13.6A1 1 0 0 1 13.6 10.4H8.4A1 1 0 0 1 8.4 8.4Z',
			fillRule: 'evenodd',
			transform: 'rotate(-45 12 12)'
		},
		{
			d: 'M17.4 11H10.4A3.6 3.6 0 0 0 10.4 18.2H17.4A3.6 3.6 0 0 0 17.4 11ZM15.6 13.6H10.4A1 1 0 0 0 10.4 15.6H15.6A1 1 0 0 0 15.6 13.6Z',
			fillRule: 'evenodd',
			opacity: '.48',
			transform: 'rotate(-45 12 12)'
		}
	],
	historico: [
		{ d: 'M2.6 3.4H4.4V20.6H2.6Z', opacity: '.48' },
		{ d: 'M2.6 5.4H4.4V7.4H2.6Z' },
		{ d: 'M6.2 4.4H21.4V8.4H6.2ZM8.2 5.8H16.6V7H8.2Z', fillRule: 'evenodd' },
		{ d: 'M6.2 10H18.6V14H6.2Z', opacity: '.48' },
		{ d: 'M6.2 15.6H15.8V19.6H6.2Z', opacity: '.48' }
	]
};
