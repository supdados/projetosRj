/**
 * Testes unitários dos utils PUROS de status de tarefa (B2).
 *
 * Cobre as regras UX-only do Kanban portadas em `taskStatus.ts`:
 *   - `canFinalize` nas DUAS formas (aninhada `permissions.can_finalize` —
 *     regressão do bug do Kanban — e plana `can_finalize`);
 *   - `canItemMoveToStatus` para alvo `finalizada` e demais alvos;
 *   - `normalizeStatus` (fallback de status desconhecido).
 */
import { describe, it, expect } from 'vitest';
import {
	canFinalize,
	canItemMoveToStatus,
	normalizeStatus,
	getStatusLabel,
	TASK_STATUS_ORDER
} from './taskStatus';

describe('normalizeStatus', () => {
	it('mantém cada status canônico', () => {
		for (const status of TASK_STATUS_ORDER) {
			expect(normalizeStatus(status)).toBe(status);
		}
	});

	it('cai em nao_iniciada para status desconhecido', () => {
		expect(normalizeStatus('inexistente')).toBe('nao_iniciada');
	});

	it('cai em nao_iniciada para null/undefined/vazio', () => {
		expect(normalizeStatus(null)).toBe('nao_iniciada');
		expect(normalizeStatus(undefined)).toBe('nao_iniciada');
		expect(normalizeStatus('')).toBe('nao_iniciada');
	});

	it('getStatusLabel usa a normalização (fallback PT-BR)', () => {
		expect(getStatusLabel('finalizada')).toBe('Finalizada');
		expect(getStatusLabel('lixo')).toBe('Não iniciada');
	});
});

describe('canFinalize', () => {
	it('false para item nulo/indefinido', () => {
		expect(canFinalize(null)).toBe(false);
		expect(canFinalize(undefined)).toBe(false);
	});

	describe('forma ANINHADA permissions.can_finalize (regressão do bug do Kanban)', () => {
		it('true quando permissions.can_finalize === true', () => {
			expect(canFinalize({ permissions: { can_finalize: true } })).toBe(true);
		});

		it('false quando permissions.can_finalize === false', () => {
			expect(canFinalize({ permissions: { can_finalize: false } })).toBe(false);
		});

		it('false quando permissions ausente/nulo', () => {
			expect(canFinalize({ permissions: null })).toBe(false);
			expect(canFinalize({})).toBe(false);
			expect(canFinalize({ permissions: {} })).toBe(false);
		});
	});

	describe('forma PLANA can_finalize', () => {
		it('true quando can_finalize === true', () => {
			expect(canFinalize({ can_finalize: true })).toBe(true);
		});

		it('false quando can_finalize === false', () => {
			expect(canFinalize({ can_finalize: false })).toBe(false);
		});

		it('a forma plana (boolean) tem precedência sobre a aninhada', () => {
			// can_finalize boolean explícito vence permissions.can_finalize.
			expect(canFinalize({ can_finalize: false, permissions: { can_finalize: true } })).toBe(
				false
			);
			expect(canFinalize({ can_finalize: true, permissions: { can_finalize: false } })).toBe(
				true
			);
		});

		it('cai na aninhada quando can_finalize não é boolean (null)', () => {
			expect(canFinalize({ can_finalize: null, permissions: { can_finalize: true } })).toBe(true);
		});
	});
});

describe('canItemMoveToStatus', () => {
	it('permite qualquer alvo != finalizada, independente de canFinalize', () => {
		const blocked = { status: 'em_andamento', permissions: { can_finalize: false } };
		expect(canItemMoveToStatus(blocked, 'em_andamento')).toBe(true);
		expect(canItemMoveToStatus(blocked, 'para_validacao')).toBe(true);
		expect(canItemMoveToStatus(blocked, 'para_ajustes')).toBe(true);
		expect(canItemMoveToStatus(blocked, 'nao_iniciada')).toBe(true);
	});

	it('alvo desconhecido (normaliza p/ nao_iniciada) é permitido', () => {
		const blocked = { permissions: { can_finalize: false } };
		expect(canItemMoveToStatus(blocked, 'lixo')).toBe(true);
	});

	describe('alvo = finalizada', () => {
		it('BLOQUEIA quando can_finalize false (forma aninhada)', () => {
			const item = { status: 'em_andamento', permissions: { can_finalize: false } };
			expect(canItemMoveToStatus(item, 'finalizada', 'em_andamento')).toBe(false);
		});

		it('PERMITE quando can_finalize true (forma aninhada)', () => {
			const item = { status: 'em_andamento', permissions: { can_finalize: true } };
			expect(canItemMoveToStatus(item, 'finalizada', 'em_andamento')).toBe(true);
		});

		it('PERMITE quando a ORIGEM já era finalizada, mesmo com can_finalize false', () => {
			const item = { status: 'finalizada', permissions: { can_finalize: false } };
			// previousStatus explícito
			expect(canItemMoveToStatus(item, 'finalizada', 'finalizada')).toBe(true);
			// origem derivada de item.status quando previousStatus ausente
			expect(canItemMoveToStatus(item, 'finalizada')).toBe(true);
		});

		it('previousStatus tem precedência sobre item.status para a origem', () => {
			const item = { status: 'finalizada', permissions: { can_finalize: false } };
			// previousStatus != finalizada -> volta a depender de canFinalize (false)
			expect(canItemMoveToStatus(item, 'finalizada', 'em_andamento')).toBe(false);
		});

		it('forma plana can_finalize também governa o alvo finalizada', () => {
			expect(
				canItemMoveToStatus({ status: 'em_andamento', can_finalize: true }, 'finalizada', 'em_andamento')
			).toBe(true);
			expect(
				canItemMoveToStatus(
					{ status: 'em_andamento', can_finalize: false },
					'finalizada',
					'em_andamento'
				)
			).toBe(false);
		});

		it('item nulo não pode finalizar', () => {
			expect(canItemMoveToStatus(null, 'finalizada', 'em_andamento')).toBe(false);
		});
	});
});
