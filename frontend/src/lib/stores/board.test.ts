import { describe, it, expect, vi, beforeEach } from 'vitest';
import { get } from 'svelte/store';

vi.mock('$lib/api/board', () => ({
	getBoard: vi.fn(),
	reorderBoard: vi.fn(),
	updateTaskStatus: vi.fn()
}));

import { reorderBoard } from '$lib/api/board';
import { createBoardStore } from './board';
import type { BoardCard, BoardReorderPayload } from '$lib/types/board';

function makeCard(id: number): BoardCard {
	return {
		id,
		descricao: `Tarefa ${id}`,
		status: 'nao_iniciada',
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
		permissions: { can_finalize: false }
	};
}

describe('board store — total sincronizado com addCard/removeCard', () => {
	it('addCard incrementa total (baseline)', () => {
		const board = createBoardStore();
		board.addCard(makeCard(1), 'nao_iniciada');
		expect(get(board).total).toBe(1);
	});

	it('removeCard de card existente decrementa total', () => {
		const board = createBoardStore();
		board.addCard(makeCard(1), 'nao_iniciada');
		board.removeCard(1);
		expect(get(board).total).toBe(0);
	});

	it('removeCard de id inexistente não altera total', () => {
		const board = createBoardStore();
		board.addCard(makeCard(1), 'nao_iniciada');
		board.removeCard(999);
		expect(get(board).total).toBe(1);
	});
});

describe('board store — moved_task_id no payload de reordenação (bug 2.10)', () => {
	beforeEach(() => {
		vi.mocked(reorderBoard).mockReset();
		vi.mocked(reorderBoard).mockResolvedValue({ columns: [] });
	});

	function lastReorderPayload(): BoardReorderPayload {
		return vi.mocked(reorderBoard).mock.calls[0][0];
	}

	it('moveCard envia moved_task_id do card arrastado', async () => {
		const board = createBoardStore();
		board.addCard(makeCard(1), 'nao_iniciada');
		board.addCard(makeCard(2), 'nao_iniciada');

		const ok = await board.moveCard(1, 'nao_iniciada', 'em_andamento', 0);

		expect(ok).toBe(true);
		const payload = lastReorderPayload();
		expect(payload.moved_task_id).toBe(1);
		expect(payload.columns).toEqual([
			{ status: 'nao_iniciada', task_ids: [2] },
			{ status: 'em_andamento', task_ids: [1] }
		]);
	});

	it('moveCard na mesma coluna também envia moved_task_id', async () => {
		const board = createBoardStore();
		board.addCard(makeCard(1), 'nao_iniciada');
		board.addCard(makeCard(2), 'nao_iniciada');

		await board.moveCard(1, 'nao_iniciada', 'nao_iniciada', 1);

		expect(lastReorderPayload().moved_task_id).toBe(1);
	});

	it('reorder (mesma coluna, sem mudança de status) NÃO envia moved_task_id', async () => {
		const board = createBoardStore();
		board.addCard(makeCard(1), 'nao_iniciada');
		board.addCard(makeCard(2), 'nao_iniciada');

		const ok = await board.reorder('nao_iniciada', [1, 2]);

		expect(ok).toBe(true);
		const payload = lastReorderPayload();
		expect('moved_task_id' in payload).toBe(false);
		expect(payload.columns).toEqual([{ status: 'nao_iniciada', task_ids: [1, 2] }]);
	});
});

describe('board store — rollback não apaga mudanças concorrentes confirmadas (bug 2.11)', () => {
	beforeEach(() => {
		vi.mocked(reorderBoard).mockReset();
	});

	function columnTaskIds(board: ReturnType<typeof createBoardStore>, status: string): number[] {
		return get(board)
			.columns.find((column) => column.status === status)!
			.tasks.map((task) => task.id);
	}

	it('falha de moveCard reverte só o card movido, preservando move confirmado no meio', async () => {
		const board = createBoardStore();
		board.addCard(makeCard(1), 'nao_iniciada');
		board.addCard(makeCard(2), 'nao_iniciada'); // ordem: [2, 1]

		let rejectMoveX!: (err: unknown) => void;
		vi.mocked(reorderBoard)
			.mockImplementationOnce(
				() =>
					new Promise<never>((_, reject) => {
						rejectMoveX = reject;
					})
			)
			.mockResolvedValueOnce({ columns: [] });

		const moveX = board.moveCard(1, 'nao_iniciada', 'em_andamento', 0); // request lenta
		const okY = await board.moveCard(2, 'nao_iniciada', 'para_validacao', 0); // confirmado antes
		expect(okY).toBe(true);

		rejectMoveX(new Error('servidor recusou'));
		expect(await moveX).toBe(false);

		expect(columnTaskIds(board, 'em_andamento')).toEqual([]);
		expect(columnTaskIds(board, 'nao_iniciada')).toEqual([1]);
		expect(columnTaskIds(board, 'para_validacao')).toEqual([2]);
		expect(get(board).error).toBeTruthy();
	});

	it('falha de moveCard de card removido em voo só sinaliza erro (não recria o card)', async () => {
		const board = createBoardStore();
		board.addCard(makeCard(1), 'nao_iniciada');

		let rejectMoveX!: (err: unknown) => void;
		vi.mocked(reorderBoard).mockImplementationOnce(
			() =>
				new Promise<never>((_, reject) => {
					rejectMoveX = reject;
				})
		);

		const moveX = board.moveCard(1, 'nao_iniciada', 'em_andamento', 0);
		board.removeCard(1);

		rejectMoveX(new Error('servidor recusou'));
		expect(await moveX).toBe(false);

		expect(columnTaskIds(board, 'nao_iniciada')).toEqual([]);
		expect(columnTaskIds(board, 'em_andamento')).toEqual([]);
		expect(get(board).error).toBeTruthy();
	});

	it('upsert com prioridade editada mantém o card na posição (não teleporta na coluna)', () => {
		const board = createBoardStore();
		// ordem manual: [3, 2, 1] (unshift no addCard)
		board.addCard(makeCard(1), 'nao_iniciada');
		board.addCard(makeCard(2), 'nao_iniciada');
		board.addCard(makeCard(3), 'nao_iniciada');

		// Editar prioridade via drawer não pode reordenar: o salto tirava o card
		// da viewport e lia-se como "a tarefa sumiu" (bug 2026-08-02).
		board.upsertCard({ ...makeCard(2), prioridade: 'urgente' });

		expect(columnTaskIds(board, 'nao_iniciada')).toEqual([3, 2, 1]);
	});

	it('falha de reorder restaura ordem anterior sem apagar card adicionado em voo', async () => {
		const board = createBoardStore();
		board.addCard(makeCard(1), 'nao_iniciada');
		board.addCard(makeCard(2), 'nao_iniciada'); // ordem: [2, 1]

		let rejectReorder!: (err: unknown) => void;
		vi.mocked(reorderBoard).mockImplementationOnce(
			() =>
				new Promise<never>((_, reject) => {
					rejectReorder = reject;
				})
		);

		const pending = board.reorder('nao_iniciada', [1, 2]);
		board.addCard(makeCard(3), 'nao_iniciada'); // chega durante o voo

		rejectReorder(new Error('servidor recusou'));
		expect(await pending).toBe(false);

		expect(columnTaskIds(board, 'nao_iniciada')).toEqual([2, 1, 3]);
	});
});
