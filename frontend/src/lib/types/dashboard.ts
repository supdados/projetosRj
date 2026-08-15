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
import type { TaskAssignee } from './tasks';

/**
 * Tarefa recente do Dashboard: card canônico + responsáveis vinculados
 * (`assignees`) + indicadores de comentários/anexos (servidos por
 * `serialize_task_card` no backend). Usado nas linhas de
 * "Recentes" do painel de tarefas.
 */
export interface DashboardRecentTask extends Task {
	assignees: TaskAssignee[];
	comments_count: number;
	anexos_count: number;
}

export interface DashboardData {
	recent_projects: Project[];
	recent_tasks: DashboardRecentTask[];

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

	// Tarefas em aberto por tipo de pedido (bloco "Por tipo")
	task_tipo_bug_count: number;
	task_tipo_melhoria_count: number;
	task_tipo_duvida_count: number;
	task_tipo_outros_count: number;
	task_tipo_implementacao_count: number;

	selected_orgao: number | null;
}
