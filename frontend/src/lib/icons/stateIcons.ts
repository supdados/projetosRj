/**
 * Ícones de estado (status de tarefa/etapa e prioridade) — substituem o ponto
 * sólido. A cor NUNCA vem daqui: todo traço/preenchimento é `currentColor`, e
 * quem renderiza aplica o token (`--ds-color-status-*` / `--ds-color-priority-*`),
 * preservando o esquema de cor que o dot já usava.
 *
 * Prioridade: anel de 4 arcos; a intensidade cresce acendendo mais arcos.
 * Status: círculo de 8.5 com o miolo indicando o estágio.
 */

export type StateIconId =
	| 'prio-sem'
	| 'prio-baixa'
	| 'prio-media'
	| 'prio-alta'
	| 'prio-urgente'
	| 'status-nao-iniciada'
	| 'status-em-andamento'
	| 'status-para-validacao'
	| 'status-para-ajustes'
	| 'status-finalizada';

export interface StateIconShape {
	kind: 'path' | 'circle';
	/** `kind: 'path'` */
	d?: string;
	/** `kind: 'circle'` */
	cx?: number;
	cy?: number;
	r?: number;
	fill?: string;
	stroke?: string;
	strokeWidth?: number;
	strokeDasharray?: string;
	opacity?: string;
}

/** Arcos do anel de prioridade, no sentido horário a partir do topo-direito. */
const ARC_1 = 'M12.89 3.55a8.5 8.5 0 0 1 7.56 7.56';
const ARC_2 = 'M20.45 12.89a8.5 8.5 0 0 1-7.56 7.56';
const ARC_3 = 'M11.11 20.45a8.5 8.5 0 0 1-7.56-7.56';
const ARC_4 = 'M3.55 11.11a8.5 8.5 0 0 1 7.56-7.56';

/** Arco apagado: os arcos não se sobrepõem, então a opacidade por path
    equivale ao `<g opacity>` do arquivo original. */
const DIM = '.2';

const ring = (acesos: number): StateIconShape[] =>
	[ARC_1, ARC_2, ARC_3, ARC_4].map((d, i) => ({
		kind: 'path' as const,
		d,
		...(i < acesos ? {} : { opacity: DIM })
	}));

/** Contorno do círculo de status — mesmo raio nos cinco estágios. */
const STATUS_RING: StateIconShape = { kind: 'circle', cx: 12, cy: 12, r: 8.5 };

/** Tinta recortada do miolo cheio: acompanha a superfície, não é branco fixo —
    no escuro a `finalizada` é um verde claro e o branco sumiria. */
const KNOCKOUT = 'var(--ds-color-surface-base)';

/** Distingue ids deste registry dos de `projectIcons` no union do SelectMenu. */
export function isStateIconId(id: string): id is StateIconId {
	return id in STATE_ICONS;
}

export const STATE_ICONS: Record<StateIconId, StateIconShape[]> = {
	'prio-sem': ring(0),
	'prio-baixa': ring(1),
	'prio-media': ring(2),
	'prio-alta': ring(3),
	'prio-urgente': [
		...ring(4),
		{ kind: 'circle', cx: 12, cy: 12, r: 2.7, fill: 'currentColor', stroke: 'none' }
	],
	'status-nao-iniciada': [{ ...STATUS_RING, strokeDasharray: '3.4 3.9', opacity: '.5' }],
	'status-em-andamento': [
		STATUS_RING,
		{ kind: 'path', d: 'M12 7.7a4.3 4.3 0 0 1 0 8.6z', fill: 'currentColor', stroke: 'none' }
	],
	'status-para-validacao': [
		STATUS_RING,
		{ kind: 'circle', cx: 12, cy: 12, r: 4.3, fill: 'currentColor', stroke: 'none' }
	],
	'status-para-ajustes': [
		STATUS_RING,
		{ kind: 'path', d: 'M14.8 7.8 8.4 12l6.4 4.2z', fill: 'currentColor', stroke: 'none' }
	],
	'status-finalizada': [
		{ kind: 'circle', cx: 12, cy: 12, r: 10, fill: 'currentColor', stroke: 'none' },
		{
			kind: 'path',
			d: 'm7.3 12.3 3.2 3.1 6.2-6.6',
			fill: 'none',
			stroke: KNOCKOUT,
			strokeWidth: 2.6
		}
	]
};
