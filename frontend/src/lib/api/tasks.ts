/**
 * Acesso tipado ao Hub de Tarefas em modo lista (GET /api/tarefas).
 *
 * Devolve a `TaskHubData` já desempacotada do envelope (`client.ts`),
 * respeitando o `orgao_scope` aplicado no servidor. Os filtros
 * (`?project`/`?prioridade`/`?tipo`/`?status`/`?responsavel`/`?orgao`/`?modo`)
 * espelham os do hub Jinja `/tarefas`.
 *
 * Exemplo:
 *   const data = await fetchTarefas({ modo: 'finalizadas' });
 */

import { get, post } from './client';
import type {
	ArchiveFinalizadasResult,
	CreateTarefaInput,
	CreateTarefaResult,
	DeleteTarefaResult,
	HubResponsavelSuggestion,
	MoverEtapaResult,
	TaskAssignee,
	TaskCard,
	TaskHubData,
	TaskHubFilterValues,
	TaskHubQuery
} from '$lib/types/tasks';

/** Monta a querystring a partir dos filtros, omitindo valores vazios/nulos. */
function buildQuery(query: TaskHubQuery): string {
	const params = new URLSearchParams();
	if (query.project) params.set('project', query.project);
	if (query.prioridade) params.set('prioridade', query.prioridade);
	if (query.tipo) params.set('tipo', query.tipo);
	if (query.status) params.set('status', query.status);
	if (query.responsavel) params.set('responsavel', query.responsavel);
	if (query.orgao !== undefined && query.orgao !== null && query.orgao !== '') {
		params.set('orgao', String(query.orgao));
	}
	if (query.modo) params.set('modo', query.modo);
	const qs = params.toString();
	return qs ? `?${qs}` : '';
}

/**
 * Busca o Hub de Tarefas (modo lista) do usuário autenticado.
 *
 * Um filtro de órgão fora do escopo do usuário faz o backend devolver
 * `fail(422,'validation')`, que `client.ts` converte em `ApiClientError`.
 */
export function fetchTarefas(
	query: TaskHubQuery = {},
	signal?: AbortSignal
): Promise<TaskHubData> {
	return get<TaskHubData>(`/api/tarefas${buildQuery(query)}`, signal);
}

/**
 * Cria uma tarefa (composer inline do Kanban / quick-add).
 *
 * `POST /api/tarefas` — body `{project, etapa, descricao, status, responsavel,
 * prioridade, tipo_pedido}` (`project_id`/`etapa_id` aceitos como alias). Devolve
 * `{task}` com o card serializado (mesma base do board) + extras de contexto.
 * 422 (sem descrição/ responsável inválido), 403/404 (projeto/etapa fora de
 * escopo). FRONT: inserir card otimista SEM toast/som/confete (paridade).
 */
export function createTarefa(
	input: CreateTarefaInput,
	signal?: AbortSignal
): Promise<CreateTarefaResult> {
	return post<CreateTarefaResult>('/api/tarefas', input, signal);
}

/**
 * Exclui uma tarefa (card/drawer). `POST /api/tarefas/<id>/excluir`.
 *
 * Só autor/admin (403 `forbidden` com a mensagem do backend). Em sucesso devolve
 * `{item_id, message}`. FRONT: remover card/row, recolher grupo vazio, fechar
 * drawer; SEM toast/som/confete.
 */
export function deleteTarefa(taskId: number, signal?: AbortSignal): Promise<DeleteTarefaResult> {
	return post<DeleteTarefaResult>(`/api/tarefas/${taskId}/excluir`, undefined, signal);
}

/**
 * Move uma tarefa para outra etapa (DnD). `POST /api/tarefas/<id>/mover-etapa`.
 *
 * Body `{etapa_id}` (`"sem_etapa"` desassocia). A etapa precisa ser do MESMO
 * projeto (422). `warning` presente quando a etapa de destino está concluída.
 */
export function moverEtapa(
	taskId: number,
	etapaId: number | 'sem_etapa' | null,
	signal?: AbortSignal
): Promise<MoverEtapaResult> {
	return post<MoverEtapaResult>(
		`/api/tarefas/${taskId}/mover-etapa`,
		{ etapa_id: etapaId },
		signal
	);
}

/**
 * Arquiva finalizadas em lote no escopo dos filtros ativos.
 * `POST /api/tarefas/arquivar-finalizadas`.
 *
 * Devolve `{archived_count, archived_task_ids, message}`. Órgão fora do escopo
 * => 422. FRONT: confirmar antes; remover cada row pelo id; SEM toast/som/confete.
 */
export function archiveFinalizadas(
	filters: TaskHubFilterValues = {},
	signal?: AbortSignal
): Promise<ArchiveFinalizadasResult> {
	return post<ArchiveFinalizadasResult>('/api/tarefas/arquivar-finalizadas', filters, signal);
}

/**
 * Sugestões de responsável do hub (composer). `GET /api/tarefas/sugestoes-responsavel`.
 *
 * Aceita `?project=` OU `?orgao=`/`?area=` (sigla|id) e `?q=` (filtra por nome).
 * 400 (nenhum projeto/órgão), 403 (órgão fora do escopo), 404 (projeto).
 */
export function fetchHubResponsaveis(
	params: { project?: string; orgao?: string; q?: string },
	signal?: AbortSignal
): Promise<{ users: HubResponsavelSuggestion[] }> {
	const qs = new URLSearchParams();
	if (params.project) qs.set('project', params.project);
	if (params.orgao) qs.set('orgao', params.orgao);
	if (params.q) qs.set('q', params.q);
	const query = qs.toString();
	return get<{ users: HubResponsavelSuggestion[] }>(
		`/api/tarefas/sugestoes-responsavel${query ? `?${query}` : ''}`,
		signal
	);
}

/**
 * Candidatos a responsável de UMA tarefa (com acesso ao projeto/etapa).
 * `GET /api/tarefas/<id>/sugestoes-responsavel?q=`. Devolve a forma de
 * `TaskAssignee` (id, name, initials, subtitle) já filtrada por `q` (nome).
 */
export function fetchTaskCandidates(
	taskId: number,
	q?: string,
	signal?: AbortSignal
): Promise<{ users: TaskAssignee[] }> {
	const qs = q ? `?q=${encodeURIComponent(q)}` : '';
	return get<{ users: TaskAssignee[] }>(`/api/tarefas/${taskId}/sugestoes-responsavel${qs}`, signal);
}

/**
 * Define os responsáveis múltiplos de uma tarefa e notifica os adicionados.
 * `POST /api/tarefas/<id>/responsaveis` — body `{user_ids}`. 403 (não autor/admin),
 * 422 (payload inválido). Devolve `{task, detail}` com o card atualizado
 * (`task.assignees` reflete a nova lista).
 */
export function saveTaskAssignees(
	taskId: number,
	userIds: number[],
	signal?: AbortSignal
): Promise<{ task: TaskCard; detail: unknown }> {
	return post<{ task: TaskCard; detail: unknown }>(
		`/api/tarefas/${taskId}/responsaveis`,
		{ user_ids: userIds },
		signal
	);
}
