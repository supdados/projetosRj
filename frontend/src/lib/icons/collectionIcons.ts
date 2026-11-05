// Registry de ícones duotone das Coleções (viewBox 24) — mesmo formato/mecanismo
// de render de `appIcons.ts` (path com camada principal + camada a opacity .48),
// consumido por <AppIcon>-like components via `<path d fill-rule opacity>`.
// Paths curados a partir do design de referência (telas 3a/3b de
// docs/parecer-design-colecoes.md), convertidos de stroke para fill sólido.
export interface CollectionIconPath {
	d: string;
	opacity?: string;
	fillRule?: 'evenodd';
}

export type CollectionIconId =
	| 'camadas'
	| 'servidores'
	| 'pessoas'
	| 'documento'
	| 'estrela'
	| 'rede'
	| 'capacitacao'
	| 'calendario'
	| 'dados'
	| 'indicadores'
	| 'seguranca'
	| 'orgao';

export const COLLECTION_ICONS: Record<CollectionIconId, CollectionIconPath[]> = {
	// Losango (topo, 3D) + degrau inferior — pilha de camadas.
	camadas: [
		{ d: 'M12 3 21 7.5 12 12 3 7.5Z', opacity: '.48' },
		{ d: 'M3 11.8 12 16.1 21 11.8 21 13.6 12 17.9 3 13.6Z' }
	],
	// Dois racks empilhados; o de baixo com 3 baias recortadas (evenodd).
	servidores: [
		{ d: 'M3 4H21V11H3Z', opacity: '.48' },
		{
			d: 'M3 13H21V20H3ZM5 15H8V16.4H5ZM10 15H13V16.4H10ZM15 15H18V16.4H15Z',
			fillRule: 'evenodd'
		}
	],
	// Duas cabeças (opacity, ao fundo) + dois "domos" de ombro sólidos.
	pessoas: [
		{ d: 'M12.2 8A3.2 3.2 0 1 1 5.8 8A3.2 3.2 0 1 1 12.2 8Z', opacity: '.48' },
		{ d: 'M19.6 7.6A2.6 2.6 0 1 1 14.4 7.6A2.6 2.6 0 1 1 19.6 7.6Z', opacity: '.48' },
		{ d: 'M13 19.6A5.5 5.5 0 0 1 22 19.6Z' },
		{ d: 'M3.4 19.6A5.5 5.5 0 0 1 14.4 19.6Z' }
	],
	// Página com quina dobrada (ao fundo) + dobra e 2 linhas de conteúdo sólidas.
	documento: [
		{ d: 'M7 3H14L19 8V21H7Z', opacity: '.48' },
		{ d: 'M14 3 14 8 19 8Z' },
		{ d: 'M9 12.6H15V13.8H9Z' },
		{ d: 'M9 16H15V17.2H9Z' }
	],
	// Estrela com halo translúcido atrás (glow) + estrela sólida na frente.
	estrela: [
		{
			d: 'M12 1.8 15 8 21.8 8.9 16.8 13.7 18 20.5 12 17.3 6 20.5 7.2 13.7 2.2 8.9 9 8Z',
			opacity: '.48'
		},
		{ d: 'M12 3 14.6 8.4 20.5 9.2 16.2 13.4 17.2 19.3 12 16.5 6.8 19.3 7.8 13.4 3.5 9.2 9.4 8.4Z' }
	],
	// 3 nós (opacity, ao fundo) conectados por hastes sólidas em Y.
	rede: [
		{
			d:
				'M14.4 5.4A2.4 2.4 0 1 1 9.6 5.4A2.4 2.4 0 1 1 14.4 5.4ZM8.4 18A2.4 2.4 0 1 1 3.6 18A2.4 2.4 0 1 1 8.4 18ZM20.4 18A2.4 2.4 0 1 1 15.6 18A2.4 2.4 0 1 1 20.4 18Z',
			opacity: '.48'
		},
		{
			d:
				'M11.4 7.8H12.6V11.2H11.4ZM11.6 11.6 12.4 10.8 7.5 15.5 6.7 16.3ZM12.4 11.6 11.6 10.8 16.5 15.5 17.3 16.3Z'
		}
	],
	// Capelo (losango, ao fundo) + faixa/base do capelo sólida.
	capacitacao: [
		{ d: 'M3 7.5 12 3 21 7.5 12 12Z', opacity: '.48' },
		{ d: 'M6.5 10H17.5V15A5.5 3 0 0 1 6.5 15Z' }
	],
	// Corpo do calendário (ao fundo) + faixa de cabeçalho e presilhas sólidas.
	calendario: [
		{ d: 'M3 5H21V21H3Z', opacity: '.48' },
		{ d: 'M3 9.4H21V10.6H3ZM7.4 3H8.6V7H7.4ZM15.4 3H16.6V7H15.4Z' }
	],
	// Cilindro de banco de dados: tampa (ao fundo) + dois anéis do corpo sólidos.
	dados: [
		{ d: 'M12 3C16.4 3 20 4.3 20 6S16.4 9 12 9 4 7.7 4 6 7.6 3 12 3Z', opacity: '.48' },
		{
			d:
				'M4 8.4C4 10.1 7.6 11.4 12 11.4S20 10.1 20 8.4V11.8C20 13.5 16.4 14.8 12 14.8S4 13.5 4 11.8ZM4 14.2C4 15.9 7.6 17.2 12 17.2S20 15.9 20 14.2V18C20 19.7 16.4 21 12 21S4 19.7 4 18Z'
		}
	],
	// Três barras crescentes (ao fundo) com topo e linha de base sólidos.
	indicadores: [
		{ d: 'M4.5 12H8.5V19H4.5ZM10 8H14V19H10ZM15.5 4H19.5V19H15.5Z', opacity: '.48' },
		{ d: 'M3 19.2H21V21H3ZM4.5 12H8.5V13.6H4.5ZM10 8H14V9.6H10ZM15.5 4H19.5V5.6H15.5Z' }
	],
	// Escudo (ao fundo) + visto sólido no centro.
	seguranca: [
		{ d: 'M12 2.5 20 5.5V11C20 15.9 16.6 20 12 21.5 7.4 20 4 15.9 4 11V5.5Z', opacity: '.48' },
		{ d: 'M10.6 15.6 7.4 12.4 8.6 11.2 10.6 13.2 15.4 8.4 16.6 9.6Z' }
	],
	// Prédio alto com janelas (ao fundo) + ala lateral sólida com janelas vazadas.
	orgao: [
		{ d: 'M4 3H14V21H4Z', opacity: '.48' },
		{
			d: 'M6.5 6H8.5V8H6.5ZM9.5 6H11.5V8H9.5ZM6.5 10H8.5V12H6.5ZM9.5 10H11.5V12H9.5ZM6.5 14H8.5V16H6.5ZM9.5 14H11.5V16H9.5Z'
		},
		{
			d: 'M15 9H20V21H15ZM16.5 11.5H18.5V13.5H16.5ZM16.5 15.5H18.5V17.5H16.5Z',
			fillRule: 'evenodd'
		}
	]
};
