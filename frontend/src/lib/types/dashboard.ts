/**
 * Tipo da carga do Dashboard (GET /api/dashboard).
 *
 * Espelha os campos JSON-serializaveis de `build_dashboard_context`
 * (routes/dashboard.py:20) — os MESMOS contadores e listas que o template
 * Jinja `index.html` consome, respeitando `orgao_scope` no servidor. As listas
 * `recent_projects` / `recent_tasks` chegam ja serializadas
 * (serialize_project_card / serialize_task_card). Derivados NAO sao
 * recalculados no cliente.
 */

import type { Project, Task } from './entities';

export interface DashboardData {
	recent_projects: Project[];
	recent_tasks: Task[];

	// Contadores de projeto (por prioridade / status / agregados)
	count_urgente: number;
	count_alta: number;
	count_media: number;
	count_baixa: number;
	count_vigente: number;
	count_finalizado: number;
	num_projects: number;
	projetos_em_atraso: number;

	// Contadores de tarefas em aberto
	dashboard_open_tasks_count: number;
	dashboard_open_items_count: number;

	// Tarefas por status
	task_items_nao_iniciada: number;
	task_items_em_andamento: number;
	task_items_para_validacao: number;
	task_items_para_ajustes: number;
	task_items_finalizada: number;
	task_items_total: number;

	// Tarefas em aberto por prioridade (+ atencao = validacao + ajustes)
	task_urgente_count: number;
	task_alta_count: number;
	task_media_count: number;
	task_baixa_count: number;
	task_atencao_count: number;

	selected_orgao: number | null;
}
