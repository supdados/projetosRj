/**
 * Funções puras de progresso/agregação do hub de tarefas — derivam métricas do
 * card de projeto (variation-d) a partir das tarefas já carregadas no front,
 * sem chamar o backend. Mantidas fora do markup para serem testáveis isoladas.
 *
 * O percentual reflete o conjunto EXIBIDO no grupo (respeita filtros/modo) — é
 * a semântica escolhida para o donut (tarefas finalizadas / total visível).
 */
import type { TaskCard, TaskHubGroup } from '../types/tasks';
import { normalizeStatus } from './taskStatus';

/** Quantas tarefas estão finalizadas (compara via `normalizeStatus`, não string crua). */
export function countFinalizadas(tasks: readonly TaskCard[]): number {
	let done = 0;
	for (const task of tasks) {
		if (normalizeStatus(task.status) === 'finalizada') done += 1;
	}
	return done;
}

/** Percentual inteiro `done/total` (0 quando `total` é 0). */
export function progressPct(done: number, total: number): number {
	if (total <= 0) return 0;
	return Math.round((done / total) * 100);
}

/**
 * Nº de etapas COM tarefas no grupo. Como o backend só envia etapas que têm
 * tarefas, contamos blocos distintos por `etapa_id` (ou pelo bucket "sem etapa").
 */
export function filledStagesCount(tasks: readonly TaskCard[]): number {
	const seen = new Set<string>();
	for (const task of tasks) {
		seen.add(task.etapa_id != null ? `e:${task.etapa_id}` : `t:${task.etapa_titulo ?? '__sem__'}`);
	}
	return seen.size;
}

/**
 * Rótulo da pill de código do projeto. Decisão do produto: usar o ID numérico
 * (sem prefixo). Grupos sem projeto (`project_id` nulo) não têm pill.
 */
export function projectCode(group: Pick<TaskHubGroup, 'project_id'>): string | null {
	return group.project_id != null ? String(group.project_id) : null;
}

/** Pluralização simples PT ("1 tarefa" / "3 tarefas"). */
export function pluralize(count: number, singular: string, plural: string): string {
	return `${count} ${count === 1 ? singular : plural}`;
}
