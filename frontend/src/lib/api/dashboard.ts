/**
 * Acesso tipado ao endpoint do Dashboard (GET /api/dashboard).
 *
 * O backend (routes/api/dashboard.py) devolve os contadores ANINHADOS em
 * `counts.projects.*` e `counts.tasks.*`. A UI, porém, consome a forma PLANA
 * `DashboardData` (mesmos nomes do template Jinja `index.html`). Este modulo
 * busca a forma crua e a ACHATA para `DashboardData` — sem este mapeamento os
 * numeros somem (todos os campos planos ficavam `undefined`).
 *
 * Sem 403/404 de autorizacao: o backend AGREGA so o que o usuario ve — projeto
 * fora do rank nao entra nos contadores em vez de virar erro.
 */

import { get } from './client';
import { createSwrCache } from './swrCache';
import type { Project } from '$lib/types/entities';
import type { DashboardData, DashboardRecentTask } from '$lib/types/dashboard';

// Ultimo payload bom por escopo de orgao (chave = orgaoScopeQuery). Permite a
// pagina reabrir com dado instantaneo (SWR) em vez do flash de loading.
const dashboardCache = createSwrCache<DashboardData>();

/** Ultimo dashboard carregado para o escopo, ou null (sincrono, para o 1o render). */
export function peekDashboard(orgaoQuery = ''): DashboardData | null {
	return dashboardCache.peek(orgaoQuery);
}

/** Forma crua devolvida pelo backend (contadores aninhados em `counts`). */
interface RawDashboardData {
	recent_projects: Project[];
	recent_tasks: DashboardRecentTask[];
	objetivos?: unknown;
	selected_orgao: number | null;
	counts: {
		projects: {
			total: number;
			urgente: number;
			alta: number;
			media: number;
			baixa: number;
			vigente: number;
			finalizado: number;
			em_atraso: number;
		};
		tasks: {
			open_total: number;
			total: number;
			nao_iniciada: number;
			em_andamento: number;
			para_validacao: number;
			para_ajustes: number;
			finalizada: number;
			urgente: number;
			alta: number;
			media: number;
			baixa: number;
			atencao: number;
			tipo_bug: number;
			tipo_melhoria: number;
			tipo_duvida: number;
			tipo_outros: number;
			tipo_implementacao: number;
		};
	};
}

/**
 * Achata a forma crua (`counts.projects.*` / `counts.tasks.*`) para os campos
 * planos que a UI consome. Mapeamento 1:1 com os nomes do template Jinja.
 */
function flattenDashboard(raw: RawDashboardData): DashboardData {
	const p = raw.counts.projects;
	const t = raw.counts.tasks;
	return {
		recent_projects: raw.recent_projects ?? [],
		recent_tasks: raw.recent_tasks ?? [],

		num_projects: p.total,
		count_urgente: p.urgente,
		count_alta: p.alta,
		count_media: p.media,
		count_baixa: p.baixa,
		count_vigente: p.vigente,
		count_finalizado: p.finalizado,
		projetos_em_atraso: p.em_atraso,

		dashboard_open_tasks_count: t.open_total,
		dashboard_open_items_count: t.open_total,

		task_items_nao_iniciada: t.nao_iniciada,
		task_items_em_andamento: t.em_andamento,
		task_items_para_validacao: t.para_validacao,
		task_items_para_ajustes: t.para_ajustes,
		task_items_finalizada: t.finalizada,
		task_items_total: t.total,

		task_urgente_count: t.urgente,
		task_alta_count: t.alta,
		task_media_count: t.media,
		task_baixa_count: t.baixa,
		task_atencao_count: t.atencao,

		task_tipo_bug_count: t.tipo_bug,
		task_tipo_melhoria_count: t.tipo_melhoria,
		task_tipo_duvida_count: t.tipo_duvida,
		task_tipo_outros_count: t.tipo_outros,
		task_tipo_implementacao_count: t.tipo_implementacao,

		selected_orgao: raw.selected_orgao
	};
}

/**
 * Busca os dados do Dashboard do usuario autenticado (forma plana).
 *
 * `orgaoQuery` e a querystring de escopo de orgao SEM o `?` (ex.: `orgao=3`),
 * tal como exportada por `orgaoScopeQuery` ($lib/stores/orgaoScope). Vazia =>
 * "Todos os orgaos" (sem filtro). O backend sanitiza `?orgao=` para o usuario
 * corrente, entao este filtro e apenas cosmetico/UX.
 *
 * Exemplo:
 *   const data = await fetchDashboard($orgaoScopeQuery);
 */
export async function fetchDashboard(
	orgaoQuery = '',
	signal?: AbortSignal
): Promise<DashboardData> {
	const path = orgaoQuery ? `/api/dashboard?${orgaoQuery}` : '/api/dashboard';
	const raw = await get<RawDashboardData>(path, signal);
	const data = flattenDashboard(raw);
	dashboardCache.store(orgaoQuery, data);
	return data;
}
