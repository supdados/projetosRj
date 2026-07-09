/**
 * Áreas responsáveis de etapa (mudança #3) — endpoints exclusivos do
 * AreaResponsavelPicker. Envelope `{ok, data}` desempacotado por `client.ts`.
 */

import { get, post } from './client';
import type { EtapaDetail, EtapaResponsavelArea } from '$lib/types/projectDetail';

export interface AreaOption {
	id: number;
	sigla: string;
	nome: string;
}

/** GET /api/areas — TODAS as áreas ativas (busca é client-side). */
export function fetchAreas(signal?: AbortSignal): Promise<{ areas: AreaOption[] }> {
	return get<{ areas: AreaOption[] }>('/api/areas', signal);
}

/** POST /api/etapas/<id>/responsaveis — substitui a lista completa. */
export function saveEtapaResponsaveis(
	etapaId: number,
	areas: EtapaResponsavelArea[],
	signal?: AbortSignal
): Promise<{ etapa: EtapaDetail }> {
	return post<{ etapa: EtapaDetail }>(`/api/etapas/${etapaId}/responsaveis`, { areas }, signal);
}
