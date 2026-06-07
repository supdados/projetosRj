/**
 * Testes unitários dos utils PUROS de progresso do hub (card de projeto).
 * Cobrem contagem de finalizadas (via normalizeStatus), %, etapas preenchidas,
 * código do projeto e pluralização.
 */
import { describe, it, expect } from 'vitest';
import {
	countFinalizadas,
	progressPct,
	filledStagesCount,
	projectCode,
	pluralize
} from './taskProgress';
import type { TaskCard } from '../types/tasks';

function makeTask(overrides: Partial<TaskCard>): TaskCard {
	return {
		id: 1,
		descricao: 'x',
		status: 'nao_iniciada',
		responsavel: null,
		prioridade: null,
		tipo_pedido: null,
		ordem: null,
		project_id: 1,
		etapa_id: null,
		created_by_id: null,
		created_at: null,
		is_archived: false,
		archived_at: null,
		assignees: [],
		etapa_titulo: null,
		etapa_display_id: null,
		is_first_of_stage: false,
		comments_count: 0,
		anexos_count: 0,
		...overrides
	};
}

describe('countFinalizadas', () => {
	it('conta só as finalizadas (normaliza status desconhecido)', () => {
		const tasks = [
			makeTask({ status: 'finalizada' }),
			makeTask({ status: 'em_andamento' }),
			makeTask({ status: 'finalizada' }),
			makeTask({ status: 'inexistente' })
		];
		expect(countFinalizadas(tasks)).toBe(2);
	});

	it('retorna 0 para lista vazia', () => {
		expect(countFinalizadas([])).toBe(0);
	});
});

describe('progressPct', () => {
	it('arredonda done/total*100', () => {
		expect(progressPct(1, 3)).toBe(33);
		expect(progressPct(2, 3)).toBe(67);
		expect(progressPct(3, 3)).toBe(100);
	});

	it('guarda total 0', () => {
		expect(progressPct(0, 0)).toBe(0);
		expect(progressPct(5, 0)).toBe(0);
	});
});

describe('filledStagesCount', () => {
	it('conta etapas distintas por etapa_id', () => {
		const tasks = [
			makeTask({ etapa_id: 10 }),
			makeTask({ etapa_id: 10 }),
			makeTask({ etapa_id: 20 })
		];
		expect(filledStagesCount(tasks)).toBe(2);
	});

	it('agrupa o bucket sem etapa por título', () => {
		const tasks = [
			makeTask({ etapa_id: null, etapa_titulo: null }),
			makeTask({ etapa_id: null, etapa_titulo: null }),
			makeTask({ etapa_id: 7, etapa_titulo: 'A' })
		];
		expect(filledStagesCount(tasks)).toBe(2);
	});
});

describe('projectCode', () => {
	it('usa o id como string (sem prefixo)', () => {
		expect(projectCode({ project_id: 42 })).toBe('42');
	});

	it('retorna null sem projeto', () => {
		expect(projectCode({ project_id: null })).toBeNull();
	});
});

describe('pluralize', () => {
	it('usa singular para 1 e plural para o resto', () => {
		expect(pluralize(1, 'tarefa', 'tarefas')).toBe('1 tarefa');
		expect(pluralize(0, 'tarefa', 'tarefas')).toBe('0 tarefas');
		expect(pluralize(3, 'etapa', 'etapas')).toBe('3 etapas');
	});
});
