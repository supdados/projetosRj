import { archiveFinalizadas, previewArchiveFinalizadas } from '$lib/api/tasks';
import type { ArchiveFinalizadasResult, TaskHubFilterValues } from '$lib/types/tasks';

/** Captura filtros e IDs antes da confirmação; o servidor revalida cada tarefa. */
export async function archiveFilteredTasks(
	filters: TaskHubFilterValues,
	confirm: (count: number) => Promise<boolean>
): Promise<ArchiveFinalizadasResult | null> {
	const confirmedFilters = { ...filters };
	const preview = await previewArchiveFinalizadas(confirmedFilters);
	if (preview.total === 0) {
		return {
			archived_count: 0, archived_task_ids: [],
			message: 'Nenhuma tarefa finalizada para arquivar nos filtros atuais.'
		};
	}
	if (!(await confirm(preview.total))) return null;
	return archiveFinalizadas({ ...confirmedFilters, task_ids: preview.task_ids });
}
