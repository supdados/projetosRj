/**
 * Opções de IDENTIDADE de uma coleção (ícone + família de cor) e as classes do
 * estado ativo — as MESMAS no modal de criar, no de editar e no popover do
 * tile da página interna (eram três cópias, e um defeito de classe se
 * replicava nas três).
 *
 * Mapas ESTÁTICOS por família porque o Tailwind só compila classe que aparece
 * inteira no fonte (`border-${cor}-600` montada em runtime não existe). O
 * teste `collectionIdentity.test.ts` compila estas classes com a config real.
 *
 * Exemplo:
 *   {#each COLECAO_COR_OPTIONS as opcao (opcao.id)}
 *     <button class="{opcao.wash} {ativo ? opcao.ativo : 'border-transparent'}">
 */

import type { CollectionColorId, CollectionIconId } from '$lib/types/collections';

/** Ícone escolhível, com o rótulo acessível do botão. */
export interface OpcaoIconeColecao {
	id: CollectionIconId;
	label: string;
}

/** Família de cor escolhível: fundo do swatch, bolinha e borda quando ativa. */
export interface OpcaoCorColecao {
	id: CollectionColorId;
	label: string;
	wash: string;
	dot: string;
	ativo: string;
}

export const COLECAO_ICONE_OPTIONS: readonly OpcaoIconeColecao[] = [
	{ id: 'camadas', label: 'Camadas' },
	{ id: 'servidores', label: 'Servidores' },
	{ id: 'pessoas', label: 'Pessoas' },
	{ id: 'documento', label: 'Documento' },
	{ id: 'estrela', label: 'Estrela' },
	{ id: 'rede', label: 'Rede' },
	{ id: 'capacitacao', label: 'Capacitação' },
	{ id: 'calendario', label: 'Calendário' },
	{ id: 'dados', label: 'Dados' },
	{ id: 'indicadores', label: 'Indicadores' },
	{ id: 'seguranca', label: 'Segurança' },
	{ id: 'orgao', label: 'Órgão' }
];

export const COLECAO_COR_OPTIONS: readonly OpcaoCorColecao[] = [
	{ id: 'primary', label: 'Azul', wash: 'bg-wash-brand', dot: 'bg-primary-600', ativo: 'border-primary-600' },
	{ id: 'success', label: 'Verde', wash: 'bg-wash-success', dot: 'bg-success-600', ativo: 'border-success-600' },
	{ id: 'warning', label: 'Âmbar', wash: 'bg-wash-warning', dot: 'bg-warning-600', ativo: 'border-warning-600' },
	{ id: 'attention', label: 'Laranja', wash: 'bg-wash-attention', dot: 'bg-attention-600', ativo: 'border-attention-600' },
	{ id: 'danger', label: 'Vermelho', wash: 'bg-wash-danger', dot: 'bg-danger-600', ativo: 'border-danger-600' },
	{ id: 'neutral', label: 'Cinza', wash: 'bg-wash-neutral', dot: 'bg-neutral-600', ativo: 'border-neutral-600' }
];

/** Botão do ícone escolhido: borda + wash + tinta da família da coleção. */
export const COLECAO_ICONE_ATIVO_CLASS: Readonly<Record<CollectionColorId, string>> = {
	primary: 'border-primary-600 bg-wash-brand text-brand',
	success: 'border-success-600 bg-wash-success text-success',
	warning: 'border-warning-600 bg-wash-warning text-warning',
	attention: 'border-attention-600 bg-wash-attention text-attention',
	danger: 'border-danger-600 bg-wash-danger text-danger',
	neutral: 'border-neutral-600 bg-wash-neutral text-text-secondary'
};

/**
 * Tom da CAPA (card do índice, topo do modal Nova coleção, tela de sucesso):
 * `wash` pinta o fundo, `tinta` o ícone e a marca d'água, `selo` o círculo
 * sólido do visto da tela de sucesso. Mesmos degraus do `ColecaoIconTile`.
 */
export interface TomCapaColecao {
	wash: string;
	tinta: string;
	selo: string;
}

export const COLECAO_CAPA_TOM: Readonly<Record<CollectionColorId, TomCapaColecao>> = {
	primary: { wash: 'bg-wash-brand', tinta: 'text-brand', selo: 'bg-primary-600' },
	success: { wash: 'bg-wash-success', tinta: 'text-success', selo: 'bg-success-600' },
	warning: { wash: 'bg-wash-warning', tinta: 'text-warning', selo: 'bg-warning-600' },
	attention: { wash: 'bg-wash-attention', tinta: 'text-attention', selo: 'bg-attention-600' },
	danger: { wash: 'bg-wash-danger', tinta: 'text-danger', selo: 'bg-danger-600' },
	neutral: { wash: 'bg-wash-neutral', tinta: 'text-text-secondary', selo: 'bg-neutral-600' }
};

/** Cor fora da whitelist (drift do backend) cai no azul padrão em vez de sumir. */
export function tomDaCapa(cor: CollectionColorId): TomCapaColecao {
	return COLECAO_CAPA_TOM[cor] ?? COLECAO_CAPA_TOM.primary;
}
