/**
 * Acesso tipado ao endpoint do Dashboard (GET /api/dashboard).
 *
 * Devolve a `DashboardData` ja desempacotada do envelope (`client.ts`),
 * respeitando o `orgao_scope` aplicado no servidor.
 */

import { get } from './client';
import type { DashboardData } from '$lib/types/dashboard';

/** Busca os dados do Dashboard do usuario autenticado. */
export function fetchDashboard(signal?: AbortSignal): Promise<DashboardData> {
	return get<DashboardData>('/api/dashboard', signal);
}
