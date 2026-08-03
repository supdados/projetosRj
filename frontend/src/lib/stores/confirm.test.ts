/**
 * Regressão: diálogo de confirmação sobrevivia à navegação (o host vive no
 * layout), e confirmar depois rodava a closure `run` da página anterior.
 */
import { describe, expect, it } from 'vitest';
import { get } from 'svelte/store';
import {
	confirmAction,
	confirmRequest,
	dismissConfirmOnNavigation,
	resolveConfirm
} from './confirm';

const PENDENTE = Symbol('pendente');

/** Resolve para `PENDENTE` se a promise não tiver assentado até o próximo tick. */
function assentada<T>(promise: Promise<T>): Promise<T | typeof PENDENTE> {
	return Promise.race([promise, Promise.resolve(PENDENTE)]);
}

function abrir(run?: () => Promise<void>): Promise<boolean> {
	return confirmAction({ title: 'Excluir projeto?', confirmLabel: 'Excluir projeto', run });
}

describe('dismissConfirmOnNavigation', () => {
	it('recusa a solicitação pendente e desmonta o diálogo ao navegar', async () => {
		const resposta = abrir();
		expect(get(confirmRequest)).not.toBeNull();

		dismissConfirmOnNavigation(false);

		expect(await resposta).toBe(false);
		expect(get(confirmRequest)).toBeNull();
	});

	it('não fecha com `run` em voo — a ação precisa terminar', async () => {
		const resposta = abrir(async () => {});

		dismissConfirmOnNavigation(true);

		expect(await assentada(resposta)).toBe(PENDENTE);
		expect(get(confirmRequest)).not.toBeNull();

		resolveConfirm(true, get(confirmRequest)!.id);
		expect(await resposta).toBe(true);
	});

	it('é inócua sem diálogo aberto (afterNavigate de boot)', () => {
		expect(get(confirmRequest)).toBeNull();
		expect(() => dismissConfirmOnNavigation(false)).not.toThrow();
		expect(get(confirmRequest)).toBeNull();
	});

	it('mantém o guard de requestId: resposta atrasada não afeta a solicitação nova', async () => {
		const antiga = abrir();
		const idAntigo = get(confirmRequest)!.id;
		const nova = abrir();

		expect(await antiga).toBe(false);

		resolveConfirm(true, idAntigo);

		expect(await assentada(nova)).toBe(PENDENTE);
		expect(get(confirmRequest)).not.toBeNull();

		dismissConfirmOnNavigation(false);
		expect(await nova).toBe(false);
	});
});
