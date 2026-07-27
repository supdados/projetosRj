/**
 * Relatórios administrativos (S4/F3-25), em `routes/api/admin_reports.py`.
 *
 *   GET /api/admin/relatorios/grants-orfaos -> { grants: GrantOrfao[] }
 *
 * Rota admin (`api_admin_required`): fica no contrato 403 `forbidden` — o 404
 * anti-enumeração da S5 vale só para recurso de projeto (TR-1).
 */

import { get } from './client';
import type { GrantOrfao } from '$lib/types/adminReports';

interface GrantsOrfaosData {
	grants: GrantOrfao[];
}

/** Convites ativos cujo concedente perdeu a gestão do projeto (admin). */
export async function fetchGrantsOrfaos(signal?: AbortSignal): Promise<GrantOrfao[]> {
	const data = await get<GrantsOrfaosData>('/api/admin/relatorios/grants-orfaos', signal);
	return data.grants;
}
