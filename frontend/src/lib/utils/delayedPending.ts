/**
 * Indicador de "carregando" com histerese: só aparece se a espera passar de
 * `showAfterMs` e, uma vez visível, fica no mínimo `minVisibleMs` — mata tanto o
 * flash de spinner em resposta rápida quanto o piscar de meio quadro.
 */
import { writable, type Readable } from 'svelte/store';

/** Agenda `callback` para daqui a `ms` e devolve o cancelador. */
export type ScheduleTimer = (callback: () => void, ms: number) => () => void;

export interface DelayedPendingOptions {
	/** Espera antes de revelar o indicador (default 150ms). */
	showAfterMs?: number;
	/** Tempo mínimo em que o indicador permanece visível (default 350ms). */
	minVisibleMs?: number;
	/** Relógio injetável (os testes usam um contador fake). */
	now?: () => number;
	/** Agendador injetável (os testes usam uma fila fake). */
	schedule?: ScheduleTimer;
}

/** Store booleana de visibilidade + controles do ciclo de espera. */
export interface DelayedPending extends Readable<boolean> {
	/** Marca o início da operação (o indicador ainda não aparece). */
	start(): void;
	/** Marca o fim da operação, respeitando o tempo mínimo visível. */
	stop(): void;
	/** Esconde e cancela tudo imediatamente (desmontagem do componente). */
	reset(): void;
}

const defaultSchedule: ScheduleTimer = (callback, ms) => {
	const id = setTimeout(callback, ms);
	return () => clearTimeout(id);
};

/**
 * Cria um controlador isolado de pendência atrasada (um por operação).
 *
 * @example
 * const pendente = delayedPending({ showAfterMs: 150, minVisibleMs: 350 });
 * pendente.start();
 * await importar();
 * pendente.stop();
 */
export function delayedPending(options: DelayedPendingOptions = {}): DelayedPending {
	const showAfterMs = options.showAfterMs ?? 150;
	const minVisibleMs = options.minVisibleMs ?? 350;
	const now = options.now ?? (() => Date.now());
	const schedule = options.schedule ?? defaultSchedule;

	const store = writable(false);
	let cancelTimer: (() => void) | null = null;
	let visible = false;
	let visibleSince = 0;
	let running = false;

	function clearTimer(): void {
		if (cancelTimer === null) return;
		cancelTimer();
		cancelTimer = null;
	}

	function setVisible(next: boolean): void {
		visible = next;
		store.set(next);
	}

	function start(): void {
		if (running) return;
		running = true;
		clearTimer();
		if (visible) return;
		cancelTimer = schedule(() => {
			cancelTimer = null;
			visibleSince = now();
			setVisible(true);
		}, showAfterMs);
	}

	function stop(): void {
		if (!running) return;
		running = false;
		clearTimer();
		if (!visible) return;
		const restante = minVisibleMs - (now() - visibleSince);
		if (restante <= 0) {
			setVisible(false);
			return;
		}
		cancelTimer = schedule(() => {
			cancelTimer = null;
			setVisible(false);
		}, restante);
	}

	function reset(): void {
		running = false;
		clearTimer();
		setVisible(false);
	}

	return { subscribe: store.subscribe, start, stop, reset };
}
