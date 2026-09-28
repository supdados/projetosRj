import type { TaskHubFilterValues } from '$lib/types/tasks';

/** Filtro local prevalece; sem ele, lista, Kanban e lote usam o órgão global. */
export function effectiveTaskFilters(
	filters: TaskHubFilterValues,
	globalOrgaoId: number | null
): TaskHubFilterValues {
	const localOrgao = filters.orgao === null || filters.orgao === undefined ? '' : String(filters.orgao);
	return {
		project: filters.project || undefined,
		orgao: localOrgao || (globalOrgaoId === null ? undefined : String(globalOrgaoId)),
		apenas_orgao: localOrgao && filters.apenas_orgao ? true : undefined,
		search: filters.search?.trim() || undefined,
		tipo: filters.tipo || undefined,
		prioridade: filters.prioridade || undefined,
		status: filters.status || undefined,
		responsavel: filters.responsavel || undefined
	};
}

/** Serialização comum da consulta para manter lista e Kanban equivalentes. */
export function taskFilterParams(filters: TaskHubFilterValues): URLSearchParams {
	const params = new URLSearchParams();
	for (const key of ['project', 'prioridade', 'tipo', 'status', 'responsavel', 'search'] as const) {
		if (filters[key]) params.set(key, filters[key]);
	}
	if (filters.orgao !== undefined && filters.orgao !== null && filters.orgao !== '') {
		params.set('orgao', String(filters.orgao));
		if (filters.apenas_orgao) params.set('apenas_orgao', '1');
	}
	return params;
}
