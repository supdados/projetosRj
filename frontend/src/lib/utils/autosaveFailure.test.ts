import { describe, expect, it, vi } from 'vitest';
import { createAutosave } from './autosave';

/** Falha controlada: a versão quebrada repete a chamada sem travar o runner. */
class ControlledPersistence {
	calls: string[] = [];
	reject: (error: Error) => void = () => {};
	resolve: (result: string) => void = () => {};
	persist = (snapshot: string): Promise<string> => {
		this.calls.push(snapshot);
		return new Promise((resolve, reject) => {
			this.resolve = resolve;
			this.reject = reject;
		});
	};
}

async function settleMicrotasks(): Promise<void> {
	for (let index = 0; index < 10; index++) await Promise.resolve();
}

describe('P1-03: falha persistente', () => {
	it.each(['422', '403', 'rede'])('não repete falha %s nem após múltiplos flushes', async (message) => {
		const persist = vi.fn().mockRejectedValue(new Error(message));
		const auto = createAutosave<string>(persist);
		auto.schedule('rascunho');
		await expect(auto.flush()).resolves.toBe(false);
		await expect(auto.flush()).resolves.toBe(false);
		await expect(auto.flush()).resolves.toBe(false);
		expect(persist).toHaveBeenCalledTimes(1);
		await expect(auto.retry()).resolves.toBe(false);
		expect(persist).toHaveBeenCalledTimes(2);
		expect(auto.phase).toBe('error');
		auto.cancel();
	});

	it('nova edição corrige a falha e substitui o snapshot inválido', async () => {
		const persist = vi.fn().mockRejectedValueOnce(new Error('inválido')).mockResolvedValue('ok');
		const auto = createAutosave<string>(persist);
		auto.schedule('');
		await expect(auto.flush()).resolves.toBe(false);
		auto.schedule('corrigido');
		await expect(auto.flush()).resolves.toBe(true);
		expect(persist.mock.calls).toEqual([[''], ['corrigido']]);
		expect(auto.phase).toBe('saved');
	});

	it('falha antiga não sobrescreve uma edição recebida durante a gravação', async () => {
		const persistence = new ControlledPersistence();
		const onSaved = vi.fn();
		const onError = vi.fn();
		const auto = createAutosave(persistence.persist, { onSaved, onError });
		auto.schedule('inválido');
		const flushed = auto.flush();
		auto.schedule('corrigido');
		persistence.reject(new Error('422'));
		await settleMicrotasks();
		expect(persistence.calls).toEqual(['inválido', 'corrigido']);
		persistence.resolve('ok');
		await expect(flushed).resolves.toBe(true);
		expect(onError).not.toHaveBeenCalled();
		expect(onSaved).toHaveBeenCalledWith('ok', 'corrigido');
	});

	it('encerra flush em erro e preserva a edição sem repetir a requisição', async () => {
		const persistence = new ControlledPersistence();
		const auto = createAutosave(persistence.persist);
		auto.schedule('');
		const flushed = auto.flush();
		persistence.reject(new Error('422: descrição obrigatória'));
		await settleMicrotasks();
		try {
			expect(persistence.calls).toEqual(['']);
			expect(auto.phase).toBe('error');
			expect(auto.hasPendingSave).toBe(true);
			await expect(flushed).resolves.toBe(false);
			await expect(auto.flush()).resolves.toBe(false);
			expect(persistence.calls).toHaveLength(1);
		} finally {
			auto.cancel();
			persistence.resolve('encerrado');
		}
	});
});
