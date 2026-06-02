/**
 * Tipos da carga de "Projetos Pendentes" (GET /api/projetos-pendentes).
 *
 * Espelham `_serialize_pending_context` (routes/api/projects.py) e os
 * serializers `serialize_pending_project_row` / `serialize_etapa_card`
 * (routes/api/serializers.py) — a MESMA fonte de verdade da tela Jinja
 * (templates/projects/pendentes.html), respeitando o `orgao_scope`
 * server-side. Os buckets de urgência, o progresso de tarefas e os
 * contadores agregados chegam JÁ calculados no backend; o cliente NÃO os
 * recalcula.
 */

import type { Project } from './entities';

/** Janela de visibilidade ativa (espelha `filtro_periodo` do backend). */
export type PendingPeriodo = 'atrasados' | '7dias' | '14dias' | '21dias';

/** Classificação de urgência de uma etapa (valores de `etapa_bucket_map`). */
export type EtapaBucket =
	| 'atrasada'
	| '7dias'
	| '14dias'
	| '21dias'
	| 'sem_data'
	| 'futuro';

/**
 * Etapa serializada (serialize_etapa_card). Campos reais de `Etapa`; datas em
 * ISO 8601 (ou `null`). O bucket/progresso vêm à parte (mapas por `id`).
 */
export interface PendingEtapa {
	id: number;
	descricao: string;
	data_inicio: string | null; // ISO 8601
	data_fim: string | null; // ISO 8601
	responsavel: string | null;
	ordem: number;
	done: boolean;
	project_id: number | null;
	entry_type: string | null;
}

/** Progresso de tarefas de uma etapa (`etapa_task_progress[etapaId]`). */
export interface EtapaTaskProgress {
	total: number;
	done: number;
}

/**
 * Uma linha de "Projetos Pendentes" (serialize_pending_project_row):
 * projeto + etapas visíveis/ocultas + contadores agregados da linha.
 */
export interface PendingProjectRow {
	project: Project;
	etapas_visiveis: PendingEtapa[];
	etapas_outras: PendingEtapa[];
	qtd_visiveis: number;
	qtd_outras: number;
	qtd_atrasadas: number;
	qtd_7dias: number;
	qtd_14dias: number;
	qtd_21dias: number;
	qtd_sem_data: number;
	max_overdue_days: number;
}

/** Contadores agregados por bucket (`summary_counts`). */
export interface PendingSummaryCounts {
	total_projects: number;
	atrasada: number;
	'7dias': number;
	'14dias': number;
	'21dias': number;
	sem_data: number;
}

/** Metadados de paginação da listagem (`pagination`). */
export interface PendingPagination {
	page: number;
	per_page: number;
	total_pages: number;
	total: number;
}

/** Carga completa de GET /api/projetos-pendentes (já desempacotada). */
export interface PendingData {
	projetos: PendingProjectRow[];
	filtro_periodo: PendingPeriodo;
	selected_responsavel: string;
	selected_orgao: number | null;
	responsaveis_options: string[];
	/** Mapa `etapaId` (string) -> bucket de urgência. */
	etapa_bucket_map: Record<string, EtapaBucket>;
	/** Mapa `etapaId` (string) -> progresso de tarefas. */
	etapa_task_progress: Record<string, EtapaTaskProgress>;
	summary_counts: PendingSummaryCounts;
	pagination: PendingPagination;
}

/** Filtros aceitos pelo endpoint (espelham `?periodo`/`?responsavel`/`?orgao`/`?page`). */
export interface PendingFilters {
	periodo?: PendingPeriodo;
	responsavel?: string;
	orgao?: number | null;
	page?: number;
}
