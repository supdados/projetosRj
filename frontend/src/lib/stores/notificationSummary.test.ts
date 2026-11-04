/**
 * Testes do store do resumo do sino: gravação, "marcar lidas", remoção local de
 * convite respondido e o atalho de consulta imediata registrado pelo sino.
 */
import { describe, expect, it, vi } from 'vitest';
import { get } from 'svelte/store';
import { createNotificationSummaryStore } from './notificationSummary';

const RESUMO = {
	unread_count: 2,
	convites_pendentes: 2,
	convites: [
		{ collection_id: 4, nome: 'Obras' },
		{ collection_id: 9, nome: 'Saúde' }
	]
};

describe('createNotificationSummaryStore', () => {
	it('começa vazio e grava o resumo do servidor', () => {
		const store = createNotificationSummaryStore();
		expect(get(store)).toBeNull();
		store.definir(RESUMO);
		expect(get(store)).toEqual(RESUMO);
	});

	it('marcar lidas troca só o unread_count (e nunca abaixo de zero)', () => {
		const store = createNotificationSummaryStore();
		store.definirNaoLidas(3);
		expect(get(store)).toBeNull();
		store.definir(RESUMO);
		store.definirNaoLidas(-1);
		expect(get(store)?.unread_count).toBe(0);
		expect(get(store)?.convites_pendentes).toBe(2);
	});

	it('convite respondido some na hora e o contador acompanha', () => {
		const store = createNotificationSummaryStore();
		store.definir(RESUMO);
		store.removerConvite(4);
		expect(get(store)?.convites).toEqual([{ collection_id: 9, nome: 'Saúde' }]);
		expect(get(store)?.convites_pendentes).toBe(1);
		const antes = get(store);
		store.removerConvite(123);
		expect(get(store)).toBe(antes);
	});

	it('atualizar chama o sino registrado e vira no-op sem ele', () => {
		const store = createNotificationSummaryStore();
		const consultar = vi.fn();
		store.atualizar();
		store.registrarAtualizador(consultar);
		store.atualizar();
		expect(consultar).toHaveBeenCalledTimes(1);
		store.registrarAtualizador(null);
		store.atualizar();
		expect(consultar).toHaveBeenCalledTimes(1);
	});

	it('limpar volta ao estado inicial e esquece o sino', () => {
		const store = createNotificationSummaryStore();
		const consultar = vi.fn();
		store.definir(RESUMO);
		store.registrarAtualizador(consultar);
		store.limpar();
		store.atualizar();
		expect(get(store)).toBeNull();
		expect(consultar).not.toHaveBeenCalled();
	});
});
