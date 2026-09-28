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

import { getTaskDetail, saveFields, finalizarTask, arquivarTask } from '$lib/api/taskDrawer';
import { ApiClientError } from '$lib/api/client';
import { createTaskDrawerStore } from './taskDrawer';
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
	getTaskDetailMock.mockReset();
	saveFieldsMock.mockReset();
	getTaskDetailMock.mockImplementation((id: number) => Promise.resolve(makePayload(id)));
});

afterEach(() => {
	vi.useRealTimers();
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
		expect(getTaskDetailMock).not.toHaveBeenCalledWith(2, undefined);
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
