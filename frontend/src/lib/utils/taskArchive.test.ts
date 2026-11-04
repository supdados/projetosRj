import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('$lib/api/client', () => ({ get: vi.fn(), post: vi.fn() }));

import { get, post } from '$lib/api/client';
import { fetchTarefas } from '$lib/api/tasks';
import { getBoard } from '$lib/api/board';
import { effectiveTaskFilters } from './taskFilters';
import {
	archivedMessage,
	confirmArchiveReview,
	finalizadaIds,
	startArchiveReview,
	tarefasLabel
} from './taskArchive';

const URL_LOTE = '/api/tarefas/arquivar-finalizadas';
const CANDIDATA = { id: 10, descricao: 'Publicar edital', project_titulo: 'Obra', assignees: [] };

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
		vi.mocked(post).mockResolvedValueOnce({ total: 2, task_ids: [10, 20], tarefas: [] });
		vi.mocked(post).mockResolvedValueOnce({ archived_count: 2, archived_task_ids: ['10', '20'] });
		const review = await startArchiveReview(filters);
		await confirmArchiveReview(review, [10, 20]);
		expect(post).toHaveBeenNthCalledWith(1, URL_LOTE, { ...filters, preview: true }, undefined);
		expect(post).toHaveBeenNthCalledWith(2, URL_LOTE, { ...filters, task_ids: [10, 20] }, undefined);
	});

	it('órgão local prevalece e apenas_orgao não é aplicado ao fallback global', () => {
		expect(effectiveTaskFilters({ orgao: 3, apenas_orgao: true }, 7)).toMatchObject({ orgao: '3', apenas_orgao: true });
		expect(effectiveTaskFilters({ orgao: '', apenas_orgao: true }, 7)).toMatchObject({ orgao: '7', apenas_orgao: undefined });
		expect(effectiveTaskFilters({}, null)).toMatchObject({ orgao: undefined });
	});

	it('mudança de filtros com o card aberto não amplia o lote revisado', async () => {
		const filters = effectiveTaskFilters({ tipo: 'bug' }, 7);
		vi.mocked(post).mockResolvedValueOnce({ total: 1, task_ids: [10], tarefas: [CANDIDATA] });
		const review = await startArchiveReview(filters);
		filters.tipo = '';
		filters.orgao = '8';
		await confirmArchiveReview(review, [10]);
		expect(vi.mocked(post).mock.calls[1][1]).toMatchObject({ tipo: 'bug', orgao: '7', task_ids: [10] });
	});
});

describe('revisão do card de arquivamento', () => {
	it('devolve as linhas que o servidor aceita arquivar', async () => {
		vi.mocked(post).mockResolvedValueOnce({ total: 1, task_ids: [10], tarefas: [CANDIDATA] });
		const review = await startArchiveReview({ project: '12', task_ids: [10, 11] });
		expect(review.candidatas).toEqual([CANDIDATA]);
		expect(post).toHaveBeenCalledWith(URL_LOTE, { project: '12', task_ids: [10, 11], preview: true }, undefined);
	});

	it('a confirmação troca os task_ids da consulta pelos marcados', async () => {
		vi.mocked(post).mockResolvedValueOnce({ archived_count: 1, archived_task_ids: ['10'], message: '' });
		await confirmArchiveReview({ filters: { project: '12', task_ids: [10, 11] }, candidatas: [] }, [10]);
		expect(post).toHaveBeenCalledWith(URL_LOTE, { project: '12', task_ids: [10] }, undefined);
	});

	it('seleção vazia não chama o servidor (lote sem IDs arquivaria o escopo todo)', async () => {
		await expect(confirmArchiveReview({ filters: {}, candidatas: [] }, [])).resolves.toMatchObject({
			archived_count: 0
		});
		expect(post).not.toHaveBeenCalled();
	});

	it('finalizadaIds pega só as finalizadas da lista', () => {
		expect(finalizadaIds([
			{ id: 1, status: 'finalizada' }, { id: 2, status: 'em_andamento' }, { id: 3, status: 'finalizada' }
		])).toEqual([1, 3]);
	});

	it('rótulos concordam singular e plural', () => {
		expect(tarefasLabel(1)).toBe('1 tarefa');
		expect(tarefasLabel(3)).toBe('3 tarefas');
		expect(archivedMessage(1)).toBe('1 tarefa arquivada.');
		expect(archivedMessage(4)).toBe('4 tarefas arquivadas.');
	});
});
