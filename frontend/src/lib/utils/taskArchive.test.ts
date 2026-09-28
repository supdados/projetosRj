import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('$lib/api/client', () => ({ get: vi.fn(), post: vi.fn() }));

import { get, post } from '$lib/api/client';
import { fetchTarefas } from '$lib/api/tasks';
import { getBoard } from '$lib/api/board';
import { effectiveTaskFilters } from './taskFilters';
import { archiveFilteredTasks } from './taskArchive';

beforeEach(() => vi.resetAllMocks());

describe('P1-04: consulta e confirmação compartilham filtros', () => {
	it('transmite os mesmos filtros completos na lista, no Kanban e no lote', async () => {
		const filters = effectiveTaskFilters({
			project: '3', tipo: 'bug', prioridade: 'alta', responsavel: 'Maria',
			status: 'finalizada', search: '  termo exclusivo ', orgao: '', apenas_orgao: true
		}, 7);
		await fetchTarefas({ ...filters, page: 2 });
		await getBoard(filters);
		const listParams = new URL(String(vi.mocked(get).mock.calls[0][0]), 'https://local.test').searchParams;
		const boardParams = new URL(String(vi.mocked(get).mock.calls[1][0]), 'https://local.test').searchParams;
		listParams.delete('page');
		expect(listParams.toString()).toBe(boardParams.toString());
		expect(Object.fromEntries(boardParams)).toEqual({
			project: '3', tipo: 'bug', prioridade: 'alta', responsavel: 'Maria',
			status: 'finalizada', search: 'termo exclusivo', orgao: '7'
		});
		vi.mocked(post).mockResolvedValueOnce({ total: 2, task_ids: [10, 20] });
		vi.mocked(post).mockResolvedValueOnce({ archived_count: 2, archived_task_ids: ['10', '20'] });
		const confirm = vi.fn().mockResolvedValue(true);
		await archiveFilteredTasks(filters, confirm);
		expect(confirm).toHaveBeenCalledWith(2);
		expect(post).toHaveBeenNthCalledWith(1, '/api/tarefas/arquivar-finalizadas', { ...filters, preview: true }, undefined);
		expect(post).toHaveBeenNthCalledWith(2, '/api/tarefas/arquivar-finalizadas', { ...filters, task_ids: [10, 20] }, undefined);
	});

	it('órgão local prevalece e apenas_orgao não é aplicado ao fallback global', () => {
		expect(effectiveTaskFilters({ orgao: 3, apenas_orgao: true }, 7)).toMatchObject({ orgao: '3', apenas_orgao: true });
		expect(effectiveTaskFilters({ orgao: '', apenas_orgao: true }, 7)).toMatchObject({ orgao: '7', apenas_orgao: undefined });
		expect(effectiveTaskFilters({}, null)).toMatchObject({ orgao: undefined });
	});

	it('mudança de filtros durante a confirmação não amplia o lote anunciado', async () => {
		const filters = effectiveTaskFilters({ tipo: 'bug' }, 7);
		vi.mocked(post).mockResolvedValueOnce({ total: 1, task_ids: [10] });
		await archiveFilteredTasks(filters, async () => {
			filters.tipo = '';
			filters.orgao = '8';
			return true;
		});
		expect(vi.mocked(post).mock.calls[1][1]).toMatchObject({ tipo: 'bug', orgao: '7', task_ids: [10] });
	});

	it('cancelar não executa o arquivamento', async () => {
		vi.mocked(post).mockResolvedValueOnce({ total: 1, task_ids: [10] });
		await expect(archiveFilteredTasks({}, async () => false)).resolves.toBeNull();
		expect(post).toHaveBeenCalledTimes(1);
	});

	it('conjunto vazio não apresenta confirmação nem faz mutação', async () => {
		vi.mocked(post).mockResolvedValueOnce({ total: 0, task_ids: [] });
		const confirm = vi.fn();
		await expect(archiveFilteredTasks({}, confirm)).resolves.toMatchObject({ archived_count: 0 });
		expect(confirm).not.toHaveBeenCalled();
		expect(post).toHaveBeenCalledTimes(1);
	});
});
