/**
 * Testes unitários do autosave PURO (B2).
 *
 * Cobre as garantias de `createAutosave` sem DOM/Svelte, usando fake timers:
 *   - DEBOUNCE: edições em rajada coalescem numa única chamada de persistFn;
 *   - GUARDA DE RESPOSTA OBSOLETA (saveToken): resposta de save antigo é
 *     descartada (a última edição vence);
 *   - COALESCING (hasPendingSave): edição durante save em voo enfileira UM save;
 *   - flush(): salva o pendente imediatamente, cancelando o debounce;
 *   - cancel(): descarta o pendente e invalida resposta em voo;
 *   - onError: reporta o erro e reagenda o snapshot que falhou.
 *
 * NOTA: evitamos `vi.runAllTimersAsync()` porque o coalescing re-dispara saves
 * e, com promises controladas manualmente, isso pode girar o relógio fake sem
 * fim. Usamos `advanceTimersByTimeAsync` (limitado) + `flushMicrotasks`.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { createAutosave } from './autosave';

beforeEach(() => {
	vi.useFakeTimers();
});

afterEach(() => {
	vi.useRealTimers();
});

/** Drena a fila de microtasks (resolução de Promises já settled). */
async function flushMicrotasks(): Promise<void> {
	for (let i = 0; i < 5; i++) {
		await Promise.resolve();
	}
}

/** persistFn cuja Promise resolve manualmente, para controlar o timing. */
function deferredPersist<S, R>() {
	const calls: S[] = [];
	let resolveCurrent: ((value: R) => void) | null = null;
	const persistFn = (snapshot: S): Promise<R> => {
		calls.push(snapshot);
		return new Promise<R>((resolve) => {
			resolveCurrent = resolve;
		});
	};
	const resolve = (value: R) => {
		const r = resolveCurrent;
		resolveCurrent = null;
		r?.(value);
	};
	return { persistFn, calls, resolve };
}

describe('createAutosave debounce', () => {
	it('coalesce rajada de schedules numa única chamada com o último snapshot', async () => {
		const persistFn = vi.fn(async (s: string) => s);
		const auto = createAutosave<string, string>(persistFn, { debounceMs: 100 });

		auto.schedule('a');
		auto.schedule('b');
		auto.schedule('c');
		expect(persistFn).not.toHaveBeenCalled();
		expect(auto.hasPendingSave).toBe(true);

		await vi.advanceTimersByTimeAsync(100);
		await flushMicrotasks();
		expect(persistFn).toHaveBeenCalledTimes(1);
		expect(persistFn).toHaveBeenCalledWith('c');
	});

	it('não dispara antes do debounceMs', async () => {
		const persistFn = vi.fn(async (s: string) => s);
		const auto = createAutosave<string, string>(persistFn, { debounceMs: 520 });
		auto.schedule('x');
		await vi.advanceTimersByTimeAsync(519);
		expect(persistFn).not.toHaveBeenCalled();
		await vi.advanceTimersByTimeAsync(1);
		expect(persistFn).toHaveBeenCalledTimes(1);
	});

	it('transiciona fases pending -> saving -> saved', async () => {
		const phases: string[] = [];
		const persistFn = vi.fn(async (s: string) => s);
		const auto = createAutosave<string, string>(persistFn, {
			debounceMs: 50,
			onPhaseChange: (p) => phases.push(p)
		});
		auto.schedule('v');
		expect(phases).toEqual(['pending']);
		await vi.advanceTimersByTimeAsync(50);
		await flushMicrotasks();
		expect(phases).toEqual(['pending', 'saving', 'saved']);
	});
});

describe('createAutosave guarda de resposta obsoleta (saveToken)', () => {
	it('descarta o resultado de um save em voo invalidado por cancel()', async () => {
		const onSaved = vi.fn();
		const { persistFn, resolve } = deferredPersist<string, string>();
		const auto = createAutosave<string, string>(persistFn, { debounceMs: 10, onSaved });

		// Save entra em voo (token corrente).
		auto.schedule('old');
		await vi.advanceTimersByTimeAsync(10);
		expect(auto.isSaving).toBe(true);

		// cancel() incrementa o saveToken -> a resposta em voo vira obsoleta.
		auto.cancel();

		// Resolve o save ANTIGO: token mudou, resultado é DESCARTADO.
		resolve('old-result');
		await flushMicrotasks();
		expect(onSaved).not.toHaveBeenCalled();
		expect(auto.phase).toBe('idle');
	});
});

describe('createAutosave coalescing (edição durante save em voo)', () => {
	it('enfileira UM save e re-dispara ao terminar o atual', async () => {
		const { persistFn, calls, resolve } = deferredPersist<string, string>();
		const auto = createAutosave<string, string>(persistFn, { debounceMs: 10 });

		auto.schedule('first');
		await vi.advanceTimersByTimeAsync(10);
		expect(calls).toEqual(['first']);
		expect(auto.isSaving).toBe(true);

		// Edita durante o save em voo.
		auto.schedule('second');
		await vi.advanceTimersByTimeAsync(10);
		// Ainda não chamou de novo: só um save por vez.
		expect(calls).toEqual(['first']);
		expect(auto.hasPendingSave).toBe(true);

		// Termina o primeiro -> re-dispara o segundo.
		resolve('r1');
		await flushMicrotasks();
		expect(calls).toEqual(['first', 'second']);
	});
});

describe('createAutosave flush', () => {
	it('salva o pendente imediatamente, cancelando o debounce', async () => {
		const persistFn = vi.fn(async (s: string) => s);
		const auto = createAutosave<string, string>(persistFn, { debounceMs: 10000 });
		auto.schedule('now');
		// Sem avançar o timer: flush força o save.
		await auto.flush();
		expect(persistFn).toHaveBeenCalledTimes(1);
		expect(persistFn).toHaveBeenCalledWith('now');
		expect(auto.hasPendingSave).toBe(false);
	});

	it('flush sem pendente não chama persistFn', async () => {
		const persistFn = vi.fn(async (s: string) => s);
		const auto = createAutosave<string, string>(persistFn, { debounceMs: 10 });
		await auto.flush();
		expect(persistFn).not.toHaveBeenCalled();
	});

	it('flush aguarda o save em voo e drena a edição coalescida (não perde edição)', async () => {
		// Regressão (auditoria 2026-07-17): flush retornava com save em voo e o
		// cancel() seguinte do drawer descartava o snapshot coalescido.
		const { persistFn, calls, resolve } = deferredPersist<string, string>();
		const auto = createAutosave<string, string>(persistFn, { debounceMs: 10 });

		auto.schedule('first');
		await vi.advanceTimersByTimeAsync(10);
		expect(auto.isSaving).toBe(true);

		// Edição durante o voo, coalescida; flush ANTES do save assentar.
		auto.schedule('second');
		let settled = false;
		const flushed = auto.flush().then(() => {
			settled = true;
		});
		await flushMicrotasks();
		expect(settled).toBe(false);

		// 1º save assenta -> o coalescido re-dispara; flush segue aguardando.
		resolve('r1');
		await flushMicrotasks();
		expect(calls).toEqual(['first', 'second']);
		expect(settled).toBe(false);

		resolve('r2');
		await flushMicrotasks();
		await flushed;
		expect(auto.hasPendingSave).toBe(false);
		expect(auto.isSaving).toBe(false);
	});
});

describe('createAutosave cancel', () => {
	it('descarta o pendente sem salvar e volta para idle', async () => {
		const persistFn = vi.fn(async (s: string) => s);
		const phases: string[] = [];
		const auto = createAutosave<string, string>(persistFn, {
			debounceMs: 100,
			onPhaseChange: (p) => phases.push(p)
		});
		auto.schedule('discard');
		auto.cancel();
		await vi.advanceTimersByTimeAsync(200);
		expect(persistFn).not.toHaveBeenCalled();
		expect(auto.hasPendingSave).toBe(false);
		expect(auto.phase).toBe('idle');
	});
});

describe('createAutosave onError', () => {
	it('reporta erro e reagenda o snapshot que falhou (que então é re-salvo)', async () => {
		const onError = vi.fn();
		const onSaved = vi.fn();
		// Falha SÓ na 1ª tentativa; o retry coalescido (via finally) sucede.
		// Falhar sempre dispararia a recursão de retry do próprio autosave.
		let attempts = 0;
		const persistFn = vi.fn(async (s: string) => {
			attempts += 1;
			if (attempts === 1) throw new Error('boom');
			return s;
		});
		const auto = createAutosave<string, string>(persistFn, {
			debounceMs: 10,
			onError,
			onSaved
		});
		auto.schedule('bad');
		await vi.advanceTimersByTimeAsync(10);
		await flushMicrotasks();

		// 1ª tentativa: erro reportado e snapshot reagendado (não se perde edição).
		expect(onError).toHaveBeenCalledTimes(1);
		expect(onError.mock.calls[0][1]).toBe('bad');
		// O retry (finally re-dispara) salva o mesmo snapshot com sucesso.
		expect(persistFn).toHaveBeenCalledTimes(2);
		expect(onSaved).toHaveBeenCalledWith('bad', 'bad');
		expect(auto.phase).toBe('saved');
	});
});
