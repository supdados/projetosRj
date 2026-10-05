import type { TaskAssignee } from '$lib/types/tasks';

const candidatesCache = new Map<string, Promise<TaskAssignee[]>>();
let epoch = 0;

/** Geração do cache: muda a cada invalidação, para pickers montados saberem que a lista ficou velha. */
export function assigneeCandidatesEpoch(): number {
	return epoch;
}

/**
 * Lista de candidatos por chave (`t<tarefa>`/`p<projeto>`), com uma única requisição por chave.
 *
 * Exemplo: `await loadAssigneeCandidates('t12', () => fetchTaskCandidates(12).then((r) => r.users))`.
 */
export function loadAssigneeCandidates(
	key: string,
	fetcher: () => Promise<TaskAssignee[]>
): Promise<TaskAssignee[]> {
	const cached = candidatesCache.get(key);
	if (cached) return cached;
	const promise = fetcher();
	candidatesCache.set(key, promise);
	promise.catch(() => {
		if (candidatesCache.get(key) === promise) candidatesCache.delete(key);
	});
	return promise;
}

/**
 * Descarta as listas em cache depois de conceder/revogar acesso ao projeto.
 *
 * Exemplo: `onClose={() => { shareOpen = false; invalidateAssigneeCandidates(); }}`.
 */
export function invalidateAssigneeCandidates(): void {
	candidatesCache.clear();
	epoch += 1;
}
