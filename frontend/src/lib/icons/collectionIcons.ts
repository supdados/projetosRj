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
	| 'calendario';

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
	]
};
