/**
 * Mutações da tela "Projetos Pendentes" (paridade com a UX do Jinja
 * `templates/projects/pendentes.html` + `static/js/pages/projects/detail/`).
 *
 * Reusa os endpoints /api JÁ existentes (envelope canônico, `client.ts`):
 *   - `POST /api/etapas/<id>/toggle-iniciada`  — não iniciada -> iniciada.
 *   - `POST /api/etapas/<id>/toggle`           — iniciada -> concluída.
 *   - `GET  /api/projetos/<pid>/etapas/<eid>/tarefas` — lista do quick-add.
 *   - `POST /api/tarefas`                      — cria tarefa (quick-add).
 *   - `POST /api/tarefas/<id>/excluir`         — exclui tarefa (quick-add).
 *
 * O toggle de status segue o MESMO ciclo da tela do projeto: idle ->
 * `/toggle-iniciada` (vira iniciada); started -> `/toggle` (vira concluída);
 * desmarcar iniciada zera `done`. O backend valida concluir etapa não iniciada
 * e etapa com tarefas abertas (422 `validation`).
 */

import { get, post } from './client';
import type { EtapaResult } from '$lib/types/projectDetail';
import type {
	StageTaskCard,
	StageTasksResult,
	CreateTaskInput,
	CreateTaskResult,
	DeleteTaskResult
} from '$lib/types/pendentes';

/** Alterna `iniciada` da etapa (idle -> iniciada; desmarcar zera `done`). */
export function toggleEtapaIniciada(
	etapaId: number,
	signal?: AbortSignal
): Promise<EtapaResult> {
	return post<EtapaResult>(`/api/etapas/${etapaId}/toggle-iniciada`, undefined, signal);
}

/** Alterna `done` da etapa (iniciada -> concluída). 422 se houver tarefa aberta. */
export function toggleEtapaDone(etapaId: number, signal?: AbortSignal): Promise<EtapaResult> {
	return post<EtapaResult>(`/api/etapas/${etapaId}/toggle`, undefined, signal);
}

/** Lista as tarefas (não arquivadas) de uma etapa para o quick-add. */
export function fetchStageTasks(
	projectId: number,
	etapaId: number,
	signal?: AbortSignal
): Promise<StageTasksResult> {
	return get<StageTasksResult>(
		`/api/projetos/${projectId}/etapas/${etapaId}/tarefas`,
		signal
	);
}

/** Cria uma tarefa dentro de uma etapa (quick-add). Devolve o card serializado. */
export function createStageTask(
	input: CreateTaskInput,
	signal?: AbortSignal
): Promise<CreateTaskResult> {
	return post<CreateTaskResult>('/api/tarefas', input, signal);
}

/** Exclui uma tarefa (quick-add). Devolve `{item_id, message}`. */
export function deleteStageTask(taskId: number, signal?: AbortSignal): Promise<DeleteTaskResult> {
	return post<DeleteTaskResult>(`/api/tarefas/${taskId}/excluir`, undefined, signal);
}

export type { StageTaskCard, StageTasksResult, CreateTaskInput };
