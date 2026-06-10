/**
 * Testes unitários dos utils PUROS de prioridade de tarefa.
 *
 * Cobre `priorityRank` (espelho de `task_priority_sort_rank` do backend) e
 * `sortByPriority` (ordenação urgente → baixa, estável para empates — mantém a
 * ordem manual `Task.ordem`).
 */
import { describe, it, expect } from 'vitest';
import { priorityRank, sortByPriority, TASK_PRIORIDADE_ORDER } from './taskPriority';

describe('priorityRank', () => {
	it('ordena urgente=0 … baixa=3', () => {
		expect(priorityRank('urgente')).toBe(0);
		expect(priorityRank('alta')).toBe(1);
		expect(priorityRank('media')).toBe(2);
		expect(priorityRank('baixa')).toBe(3);
	});

	it('prioridade ausente/desconhecida vai por último', () => {
		const last = TASK_PRIORIDADE_ORDER.length;
		expect(priorityRank(null)).toBe(last);
		expect(priorityRank(undefined)).toBe(last);
		expect(priorityRank('inexistente')).toBe(last);
	});
});

describe('sortByPriority', () => {
	it('ordena urgente → alta → media → baixa', () => {
		const cards = [
			{ id: 1, prioridade: 'baixa' },
			{ id: 2, prioridade: 'urgente' },
			{ id: 3, prioridade: 'media' },
			{ id: 4, prioridade: 'alta' }
		];
		expect(sortByPriority(cards).map((c) => c.id)).toEqual([2, 4, 3, 1]);
	});

	it('é estável: mesma prioridade preserva a ordem de entrada (Task.ordem)', () => {
		const cards = [
			{ id: 7, prioridade: 'alta' },
			{ id: 3, prioridade: 'alta' },
			{ id: 5, prioridade: 'alta' }
		];
		expect(sortByPriority(cards).map((c) => c.id)).toEqual([7, 3, 5]);
	});

	it('prioridade ausente vai para o fim da coluna', () => {
		const cards = [
			{ id: 1, prioridade: null },
			{ id: 2, prioridade: 'baixa' }
		];
		expect(sortByPriority(cards).map((c) => c.id)).toEqual([2, 1]);
	});

	it('não muta a lista original', () => {
		const cards = [
			{ id: 1, prioridade: 'baixa' },
			{ id: 2, prioridade: 'urgente' }
		];
		sortByPriority(cards);
		expect(cards.map((c) => c.id)).toEqual([1, 2]);
	});
});
