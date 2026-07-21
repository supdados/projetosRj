/**
 * Testes dos helpers puros de reordenação (bug 2.17): teclado e drop com a
 * MESMA semântica — reuniões Google pinadas, etapa movida pula as reuniões.
 */
import { describe, it, expect } from 'vitest';
import {
	dropStagePinningMeetings,
	moveStageSkippingMeetings,
	type ReorderableStage
} from './stageReorder';

const E1: ReorderableStage = { id: 1 };
const M: ReorderableStage = { id: 2, is_google_meeting: true };
const E2: ReorderableStage = { id: 3 };
const E3: ReorderableStage = { id: 4 };

describe('moveStageSkippingMeetings', () => {
	it('sobe a etapa pulando a reunião, mantendo-a na posição absoluta', () => {
		const stages = [E1, M, E2, E3];
		expect(moveStageSkippingMeetings(stages, 3, -1)).toEqual([1, 2, 4, 3]);
	});

	it('desce a etapa pulando a reunião logo abaixo', () => {
		const stages = [E1, M, E2, E3];
		// E1 (index 0) desce uma posição entre as arrastáveis [E1,E2,E3] → [E2,E1,E3]
		expect(moveStageSkippingMeetings(stages, 0, 1)).toEqual([3, 2, 1, 4]);
	});

	it('reordena normalmente quando não há reuniões', () => {
		const stages = [E1, E2, E3];
		expect(moveStageSkippingMeetings(stages, 2, -1)).toEqual([1, 4, 3]);
	});

	it('não faz nada ao tentar mover uma reunião', () => {
		const stages = [E1, M, E2];
		expect(moveStageSkippingMeetings(stages, 1, -1)).toBeNull();
	});

	it('não move além do topo do subconjunto arrastável', () => {
		const stages = [E1, M, E2];
		expect(moveStageSkippingMeetings(stages, 0, -1)).toBeNull();
	});

	it('não move além do fim do subconjunto arrastável', () => {
		const stages = [E1, M, E2];
		expect(moveStageSkippingMeetings(stages, 2, 1)).toBeNull();
	});

	it('trata índice fora da lista como no-op', () => {
		const stages = [E1, E2];
		expect(moveStageSkippingMeetings(stages, 5, -1)).toBeNull();
	});
});

describe('dropStagePinningMeetings', () => {
	it('drop cruzando a reunião mantém a reunião pinada (mesmo resultado do teclado)', () => {
		const stages = [E1, M, E2];
		// E1 solto abaixo de E2: a reunião NÃO flui — [E2, M, E1], como no teclado.
		expect(dropStagePinningMeetings(stages, E1.id, E2.id, 'bottom')).toEqual([3, 2, 1]);
		expect(moveStageSkippingMeetings(stages, 0, 1)).toEqual([3, 2, 1]);
	});

	it('drop acima do alvo insere antes dele no subconjunto arrastável', () => {
		const stages = [E1, M, E2, E3];
		expect(dropStagePinningMeetings(stages, E3.id, E1.id, 'top')).toEqual([4, 2, 1, 3]);
	});

	it('drop abaixo do alvo insere depois dele, reunião segue pinada', () => {
		const stages = [E1, M, E2, E3];
		expect(dropStagePinningMeetings(stages, E1.id, E2.id, 'bottom')).toEqual([3, 2, 1, 4]);
	});

	it('reordena normalmente quando não há reuniões', () => {
		const stages = [E1, E2, E3];
		expect(dropStagePinningMeetings(stages, E3.id, E1.id, 'top')).toEqual([4, 1, 3]);
	});

	it('é no-op ao soltar sobre si mesma, sobre reunião ou com ids desconhecidos', () => {
		const stages = [E1, M, E2];
		expect(dropStagePinningMeetings(stages, E1.id, E1.id, 'top')).toBeNull();
		expect(dropStagePinningMeetings(stages, E1.id, M.id, 'top')).toBeNull();
		expect(dropStagePinningMeetings(stages, M.id, E1.id, 'top')).toBeNull();
		expect(dropStagePinningMeetings(stages, 99, E1.id, 'top')).toBeNull();
		expect(dropStagePinningMeetings(stages, E1.id, 99, 'top')).toBeNull();
	});
});
