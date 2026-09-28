/**
 * Regressão do drawer de tarefa (bug 2.21 — perda de edição ao trocar de tarefa).
 *
 * `open()` deve dar FLUSH nas edições debounced da tarefa ANTERIOR antes de
 * carregar a nova (o antigo `cancel()` as descartava em silêncio):
 *   (a) editar campo na task A e abrir a task B antes do debounce -> `saveFields`
 *       é chamado com o id e os campos da task A;
 *   (b) uma falha termina a tentativa, preserva o rascunho e permite descarte.
 *
 * Segue o padrão de fake timers de `../utils/autosave.test.ts`.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { get } from 'svelte/store';

vi.mock('$lib/api/taskDrawer', () => ({
	getTaskDetail: vi.fn(),
	saveFields: vi.fn(),
	finalizarTask: vi.fn(),
	arquivarTask: vi.fn(),
	desarquivarTask: vi.fn(),
	reativarTask: vi.fn(),
	addComment: vi.fn(),
	editComment: vi.fn(),
	deleteComment: vi.fn(),
	listAttachments: vi.fn(),
	uploadAttachment: vi.fn(),
	deleteAttachment: vi.fn()
}));

vi.mock('$lib/api/tasks', () => ({
	deleteTarefa: vi.fn(),
	moverEtapa: vi.fn()
}));

import { getTaskDetail, saveFields, finalizarTask, arquivarTask, addComment } from '$lib/api/taskDrawer';
import { deleteTarefa, moverEtapa } from '$lib/api/tasks';
import { ApiClientError } from '$lib/api/client';
import { createTaskDrawerStore } from './taskDrawer';
import { createBoardStore } from './board';
import type { TaskDrawerPayload } from '$lib/types/taskDrawer';

const getTaskDetailMock = vi.mocked(getTaskDetail);
const saveFieldsMock = vi.mocked(saveFields);

/** Envelope `{task, detail}` mínimo mas completo o bastante para `applyPayload`. */
function makePayload(id: number): TaskDrawerPayload {
	const card = {
		id,
		descricao: `Tarefa ${id}`,
		status: 'a_fazer',
		responsavel: null,
		assignees: [],
		prioridade: null,
		tipo_pedido: null,
		ordem: null,
		project_id: null,
		project_titulo: null,
		etapa_id: null,
		created_by_id: null,
		created_at: null,
		is_archived: false,
		archived_at: null,
		comments_count: 0,
		anexos_count: 0,
		permissions: { can_finalize: true }
	};
	return {
		task: card,
		detail: {
			...card,
			etapa: null,
			project: null,
			comentarios: [],
			anexos: [],
			permissions: { can_finalize: true, can_edit: true, can_delete: true }
		}
	} as TaskDrawerPayload;
}

beforeEach(() => {
	vi.useFakeTimers();
	vi.clearAllMocks();
	vi.mocked(arquivarTask).mockReset();
	vi.mocked(finalizarTask).mockReset();
	getTaskDetailMock.mockReset();
	saveFieldsMock.mockReset();
	getTaskDetailMock.mockImplementation((id: number) => Promise.resolve(makePayload(id)));
});

class DeferredDrawerPayload<T = TaskDrawerPayload> {
	resolve!: (value: T) => void;
	reject!: (error: Error) => void;
	promise = new Promise<T>((resolve, reject) => {
		this.resolve = resolve;
		this.reject = reject;
	});
}

describe('P2-10: respostas de seleções antigas do drawer', () => {
	it('fechar no mesmo tick impede até o início da leitura antiga', async () => {
		const drawer = createTaskDrawerStore();
		await Promise.all([drawer.open(1), drawer.close()]);
		expect(getTaskDetailMock).not.toHaveBeenCalled();
		expect(get(drawer).status).toBe('closed');
	});

	it('A → B → A não aceita o primeiro GET de A', async () => {
		const old = new DeferredDrawerPayload();
		getTaskDetailMock.mockReturnValueOnce(old.promise);
		const drawer = createTaskDrawerStore();
		const first = drawer.open(1);
		await vi.advanceTimersByTimeAsync(0);
		await drawer.open(2);
		const fresh = makePayload(1);
		fresh.detail.descricao = 'A atual';
		getTaskDetailMock.mockResolvedValueOnce(fresh);
		await drawer.open(1);
		old.resolve(makePayload(1));
		await first;
		expect(get(drawer).detail?.descricao).toBe('A atual');
	});

	it('última abertura vence enquanto o autosave da anterior está em voo', async () => {
		const drawer = createTaskDrawerStore();
		await drawer.open(1);
		const saving = new DeferredDrawerPayload();
		saveFieldsMock.mockReturnValueOnce(saving.promise);
		drawer.editField({ descricao: 'rascunho A' });
		const first = drawer.open(2);
		const latest = drawer.open(3);
		saving.resolve(makePayload(1));
		await Promise.all([first, latest]);
		expect(get(drawer).taskId).toBe(3);
		expect(getTaskDetailMock.mock.calls.map(([id]) => id)).toEqual([1, 3]);
		expect(saveFieldsMock).toHaveBeenCalledTimes(1);
	});

	it('sinal externo cancela a leitura atual e encerra o carregamento', async () => {
		const result = new DeferredDrawerPayload();
		getTaskDetailMock.mockReturnValueOnce(result.promise);
		const drawer = createTaskDrawerStore();
		const controller = new AbortController();
		const opening = drawer.open(1, { signal: controller.signal });
		await vi.advanceTimersByTimeAsync(0);
		controller.abort();
		result.resolve(makePayload(1));
		await opening;
		expect(getTaskDetailMock.mock.calls[0][1]?.aborted).toBe(true);
		expect(get(drawer).status).toBe('closed');
	});

	it('excluir A depois de abrir B remove o cartão A e mantém B aberto', async () => {
		const result = new DeferredDrawerPayload<Awaited<ReturnType<typeof deleteTarefa>>>();
		vi.mocked(deleteTarefa).mockReturnValueOnce(result.promise);
		const removed = vi.fn();
		const drawer = createTaskDrawerStore({ onCardRemoved: removed });
		await drawer.open(1);
		const deleting = drawer.deleteTask();
		await vi.advanceTimersByTimeAsync(0);
		await drawer.open(2);
		result.resolve({ item_id: 1, message: 'Excluída' });
		await deleting;
		expect(get(drawer)).toMatchObject({ taskId: 2, status: 'ready' });
		expect(removed).toHaveBeenCalledWith(1);
	});

	it('mover etapa de A não usa open para substituir B', async () => {
		const result = new DeferredDrawerPayload<Awaited<ReturnType<typeof moverEtapa>>>();
		vi.mocked(moverEtapa).mockReturnValueOnce(result.promise);
		const drawer = createTaskDrawerStore();
		await drawer.open(1);
		const moving = drawer.moveEtapa(10);
		await vi.advanceTimersByTimeAsync(0);
		await drawer.open(2);
		result.resolve({ task_id: 1, etapa_id: 10, previous_etapa_id: null });
		await moving;
		expect(get(drawer)).toMatchObject({ taskId: 2, status: 'ready', error: null });
	});

	it('erro de comentário antigo não aparece na outra tarefa', async () => {
		const result = new DeferredDrawerPayload<Awaited<ReturnType<typeof addComment>>>();
		vi.mocked(addComment).mockReturnValueOnce(result.promise);
		const drawer = createTaskDrawerStore();
		await drawer.open(1);
		const adding = drawer.addComment('texto');
		await drawer.open(2);
		result.reject(new Error('erro antigo'));
		await adding;
		expect(get(drawer).error).toBeNull();
	});

	it('finalizar antigo não limpa o estado busy da ação nova', async () => {
		const first = new DeferredDrawerPayload();
		const second = new DeferredDrawerPayload();
		vi.mocked(finalizarTask).mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
		const drawer = createTaskDrawerStore();
		await drawer.open(1);
		const actionA = drawer.finalizar();
		await vi.advanceTimersByTimeAsync(0);
		await drawer.open(2);
		const actionB = drawer.finalizar();
		await vi.advanceTimersByTimeAsync(0);
		first.resolve(makePayload(1));
		await actionA;
		expect(get(drawer)).toMatchObject({ taskId: 2, acting: true });
		second.resolve(makePayload(2));
		await actionB;
		expect(get(drawer).acting).toBe(false);
	});

	it('GET atrasado não reabre após fechar', async () => {
		const response = new DeferredDrawerPayload();
		getTaskDetailMock.mockReturnValueOnce(response.promise);
		const changed = vi.fn();
		const drawer = createTaskDrawerStore({ onCardChanged: changed });
		const opening = drawer.open(1);
		await vi.advanceTimersByTimeAsync(0);
		await drawer.close();
		expect(getTaskDetailMock.mock.calls[0][1]?.aborted).toBe(true);
		response.resolve(makePayload(1));
		await opening;
		expect(get(drawer).status).toBe('closed');
		expect(changed).not.toHaveBeenCalled();
	});

	it.each(['success', 'error'])('resposta %s de A não substitui B', async (outcome) => {
		const response = new DeferredDrawerPayload();
		getTaskDetailMock.mockReturnValueOnce(response.promise);
		const drawer = createTaskDrawerStore();
		const opening = drawer.open(1);
		await vi.advanceTimersByTimeAsync(0);
		await drawer.open(2);
		if (outcome === 'error') response.reject(new Error('Erro antigo'));
		else response.resolve(makePayload(1));
		await opening;
		expect(get(drawer)).toMatchObject({ taskId: 2, status: 'ready', error: null });
	});

	it('ação concluída após fechar reconcilia o cartão sem reabrir', async () => {
		const response = new DeferredDrawerPayload();
		const changed = vi.fn();
		const drawer = createTaskDrawerStore({ onCardChanged: changed });
		await drawer.open(1);
		vi.mocked(finalizarTask).mockReturnValueOnce(response.promise);
		const action = drawer.finalizar();
		await vi.advanceTimersByTimeAsync(0);
		await drawer.close();
		const finalized = makePayload(1);
		finalized.task.status = finalized.detail.status = 'finalizada';
		response.resolve(finalized);
		await action;
		expect(get(drawer).status).toBe('closed');
		expect(changed).toHaveBeenLastCalledWith(finalized.task);
	});
});

afterEach(() => {
	vi.useRealTimers();
});

describe('P2-09: finalizadas permanecem no Kanban', () => {
	it('finalizar move para a coluna correta sem remover nem duplicar o cartão', async () => {
		const board = createBoardStore();
		board.addCard(makePayload(7).task, 'nao_iniciada');
		const drawer = createTaskDrawerStore({ onCardChanged: board.upsertCard, onCardRemoved: board.removeCard });
		await drawer.open(7);
		const finalized = makePayload(7);
		finalized.task.status = finalized.detail.status = 'finalizada';
		vi.mocked(finalizarTask).mockResolvedValue(finalized);
		await expect(drawer.finalizar()).resolves.toBe(true);
		drawer.applyExternalPayload(finalized);
		expect(get(board).total).toBe(1);
		expect(get(board).columns.find((column) => column.status === 'finalizada')?.tasks.map((task) => task.id)).toEqual([7]);
	});

	it('abrir/fechar mantém cartão e total; arquivar remove', async () => {
		const payload = makePayload(7);
		payload.task.status = payload.detail.status = 'finalizada';
		const board = createBoardStore();
		board.addCard(payload.task, 'finalizada');
		const drawer = createTaskDrawerStore({
			onCardChanged: board.upsertCard,
			onCardRemoved: board.removeCard
		});
		getTaskDetailMock.mockResolvedValue(payload);
		await drawer.open(7);
		await drawer.close();
		expect(get(board).total).toBe(1);
		expect(get(board).columns.find((column) => column.status === 'finalizada')?.tasks.map((task) => task.id)).toEqual([7]);
		await drawer.open(7);
		vi.mocked(arquivarTask).mockResolvedValue({
			task: { ...payload.task, is_archived: true },
			detail: { ...payload.detail, is_archived: true }
		});
		await drawer.arquivar();
		expect(get(board).total).toBe(0);
		expect(get(board).columns.every((column) => column.tasks.length === 0)).toBe(true);
	});
});

describe('taskDrawer open() — flush das edições pendentes (bug 2.21)', () => {
	it('salva os campos da task A ao abrir a task B antes do debounce', async () => {
		saveFieldsMock.mockResolvedValue(makePayload(1));
		const drawer = createTaskDrawerStore();

		await drawer.open(1);
		drawer.editField({ descricao: 'edição A' });
		// Sem avançar o timer: a edição segue apenas debounced (não persistida).
		expect(saveFieldsMock).not.toHaveBeenCalled();

		await drawer.open(2);

		expect(saveFieldsMock).toHaveBeenCalledTimes(1);
		expect(saveFieldsMock).toHaveBeenCalledWith(1, { descricao: 'edição A' });
		expect(get(drawer).taskId).toBe(2);
		expect(get(drawer).status).toBe('ready');
	});

	it('falha persistente preserva a edição até corrigir ou descartar, sem travar promises', async () => {
		saveFieldsMock.mockRejectedValue(new ApiClientError('validation', 'Descrição obrigatória.', 422));
		const drawer = createTaskDrawerStore();

		await drawer.open(1);
		drawer.editField({ descricao: '' });

		await expect(drawer.open(2)).resolves.toBe(false);
		await expect(drawer.close()).resolves.toBe(false);
		await vi.advanceTimersByTimeAsync(10000);
		expect(saveFieldsMock).toHaveBeenCalledTimes(1);
		expect(getTaskDetailMock.mock.calls.map(([id]) => id)).not.toContain(2);
		expect(get(drawer)).toMatchObject({ taskId: 1, autosave: 'error', error: 'Descrição obrigatória.' });
		expect(get(drawer).detail?.descricao).toBe('');

		drawer.discardAndClose();
		expect(get(drawer).status).toBe('closed');
		await drawer.open(2);
		expect(get(drawer).taskId).toBe(2);
		expect(get(drawer).status).toBe('ready');
	});

	it('retry explícito salva o rascunho e permite fechar', async () => {
		saveFieldsMock.mockRejectedValueOnce(new Error('rede')).mockResolvedValue(makePayload(1));
		const drawer = createTaskDrawerStore();
		await drawer.open(1);
		drawer.editField({ descricao: 'Meu rascunho' });
		await expect(drawer.flush()).resolves.toBe(false);
		await expect(drawer.retry()).resolves.toBe(true);
		await expect(drawer.close()).resolves.toBe(true);
		expect(saveFieldsMock.mock.calls).toEqual([
			[1, { descricao: 'Meu rascunho' }], [1, { descricao: 'Meu rascunho' }]
		]);
	});

	it('não executa ações de ciclo de vida quando o flush falha', async () => {
		saveFieldsMock.mockRejectedValue(new Error('rede'));
		const drawer = createTaskDrawerStore();
		await drawer.open(1);
		drawer.editField({ descricao: '' });
		await expect(drawer.finalizar()).resolves.toBe(false);
		await expect(drawer.arquivar()).resolves.toBe(false);
		expect(finalizarTask).not.toHaveBeenCalled();
		expect(arquivarTask).not.toHaveBeenCalled();
		expect(saveFieldsMock).toHaveBeenCalledTimes(1);
		drawer.discardAndClose();
	});
});
