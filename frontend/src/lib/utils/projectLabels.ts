/**
 * Valor de domínio do projeto → ícone do registry `projectIcons` — fonte única
 * dos chips de status, tipo de entrega e projeto especial (lista de projetos,
 * header do detalhe e modais). As strings espelham o backend
 * (`routes/projects/views.py`, `routes/api/project_detail.py`); as chaves ficam
 * em minúsculas porque dados legados variam a caixa ('Fluxo processual').
 *
 * O ícone herda a cor do chip via `currentColor`, então não há cor aqui.
 * Valores sem forma própria ('Inventário') caem em `null` e o site consumidor
 * decide o fallback.
 */

import type { ProjectIconId } from '$lib/icons/projectIcons';

const PROJECT_STATUS_ICON_ID: Record<string, ProjectIconId> = {
	vigente: 'projeto-ativo',
	suspenso: 'projeto-suspenso',
	finalizado: 'projeto-finalizado'
};

const DELIVERY_ICON_ID: Record<string, ProjectIconId> = {
	sistema: 'entrega-sistema',
	painel: 'entrega-painel',
	norma: 'entrega-norma',
	'instrumento de parceria': 'entrega-instrumento',
	'fluxo processual': 'entrega-fluxo',
	eventos: 'entrega-eventos',
	outro: 'entrega-outro'
};

const SPECIAL_PROJECT_ICON_ID: Record<string, ProjectIconId> = {
	abep: 'selo-abep',
	tce: 'selo-tce'
};

function iconIdFor(
	map: Record<string, ProjectIconId>,
	value: string | null | undefined
): ProjectIconId | null {
	if (!value) return null;
	return map[value.trim().toLowerCase()] ?? null;
}

/** @example projectStatusIconId('Vigente') // 'projeto-ativo' */
export function projectStatusIconId(value: string | null | undefined): ProjectIconId | null {
	return iconIdFor(PROJECT_STATUS_ICON_ID, value);
}

/** @example deliveryIconId('Fluxo Processual') // 'entrega-fluxo' */
export function deliveryIconId(value: string | null | undefined): ProjectIconId | null {
	return iconIdFor(DELIVERY_ICON_ID, value);
}

/** @example specialProjectIconId('ABEP') // 'selo-abep' */
export function specialProjectIconId(value: string | null | undefined): ProjectIconId | null {
	return iconIdFor(SPECIAL_PROJECT_ICON_ID, value);
}
