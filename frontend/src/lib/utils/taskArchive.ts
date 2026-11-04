import { archiveFinalizadas, previewArchiveFinalizadas } from '$lib/api/tasks';
import type {
	ArchiveCandidate,
	ArchiveFinalizadasInput,
	ArchiveFinalizadasResult
} from '$lib/types/tasks';
import { normalizeStatus } from '$lib/utils/taskStatus';

/**
 * Revisão aberta no card "Arquivar concluídas": o escopo capturado na consulta
 * e as finalizadas que o servidor aceita arquivar (já filtradas por permissão).
 */
export interface ArchiveReview {
	filters: ArchiveFinalizadasInput;
	candidatas: ArchiveCandidate[];
}

/**
 * Consulta o que dá para arquivar e congela o escopo da revisão.
 *
 * Os filtros são copiados AQUI: mudar a tela enquanto o card está aberto não
 * amplia o lote que o usuário revisou. Serve à lista do hub (filtros, todas as
 * páginas), ao grupo de projeto e à etapa (`project` + `task_ids` visíveis).
 *
 *   const review = await startArchiveReview({ project: '12', task_ids: [3, 4] });
 */
export async function startArchiveReview(
	filters: ArchiveFinalizadasInput,
	signal?: AbortSignal
): Promise<ArchiveReview> {
	const captured = { ...filters };
	const preview = await previewArchiveFinalizadas(captured, signal);
	return { filters: captured, candidatas: preview.tarefas };
}

/**
 * Arquiva só os IDs marcados no card, no escopo congelado da revisão; o
 * servidor revalida status e permissão de cada um. Lista vazia não chama o
 * servidor: o lote sem `task_ids` arquivaria todo o escopo.
 *
 *   await confirmArchiveReview(review, [3]);
 */
export async function confirmArchiveReview(
	review: ArchiveReview,
	taskIds: number[],
	signal?: AbortSignal
): Promise<ArchiveFinalizadasResult> {
	if (taskIds.length === 0) {
		return { archived_count: 0, archived_task_ids: [], message: 'Nenhuma tarefa selecionada.' };
	}
	return archiveFinalizadas({ ...review.filters, task_ids: taskIds }, signal);
}

/** IDs das finalizadas de uma lista já carregada (etapa, grupo de projeto). */
export function finalizadaIds(tasks: { id: number; status: string }[]): number[] {
	return tasks.filter((t) => normalizeStatus(t.status) === 'finalizada').map((t) => t.id);
}

/** "1 tarefa" / "N tarefas". */
export function tarefasLabel(count: number): string {
	return count === 1 ? '1 tarefa' : `${count} tarefas`;
}

/** Toast de sucesso do lote: "1 tarefa arquivada." / "N tarefas arquivadas.". */
export function archivedMessage(count: number): string {
	return count === 1 ? '1 tarefa arquivada.' : `${count} tarefas arquivadas.`;
}
