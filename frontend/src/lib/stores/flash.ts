/**
 * Sistema de FLASH/TOAST da SPA (equivalente a `window.showFlash` +
 * `static/js/app-shell/flash.js` do Jinja).
 *
 * Toasts no topo da tela com auto-dismiss por categoria, teto de 5 na pilha,
 * deduplicação por chave (repetição vira contador `×N`, não empilha) e pausa
 * em hover/foco. Consumido pelo `<FlashToasts>` montado uma vez por tela.
 *
 * Exemplo:
 *   import { flash } from '$lib/stores/flash';
 *   flash.success('Tarefa criada com sucesso.');
 *   flash.warning('Finalize as tarefas pendentes.', { key: 'etapa-tarefas-pendentes' });
 */

import { writable, type Readable } from 'svelte/store';

/** Categorias espelhando as do flash legado (Flask `flash(msg, category)`). */
export type FlashCategory = 'success' | 'info' | 'warning' | 'danger';

export interface FlashOptions {
	/** Agrupa repetições cujo texto varia mas o evento é o mesmo. */
	key?: string;
	/** Override de duração (ms); ainda sujeito ao teto de 10000. */
	durationMs?: number;
}

/** Um toast ativo na pilha. */
export interface FlashMessage {
	id: number;
	message: string;
	category: FlashCategory;
	/** Chave de dedupe (explícita ou `${category}|${message}`). */
	key: string;
	/** 1 na primeira exibição; incrementa a cada repetição coalescida. */
	count: number;
	/** Epoch ms da primeira exibição — base do teto de 10 s. */
	firstShownAt: number;
}

export interface FlashStore extends Readable<FlashMessage[]> {
	show(message: string, category?: FlashCategory, options?: FlashOptions): number;
	success(message: string, options?: FlashOptions): number;
	info(message: string, options?: FlashOptions): number;
	warning(message: string, options?: FlashOptions): number;
	danger(message: string, options?: FlashOptions): number;
	dismiss(id: number): void;
	pause(id: number): void;
	resume(id: number): void;
	/** Limpa a pilha e todos os timers (uso em teste/logout). */
	clear(): void;
}

/** Teto da pilha visível; acima disso há evicção (nunca recusa o toast novo). */
const MAX_TOASTS = 3;
/** Janela de cauda: repetição logo após o sumiço é suprimida (absorve duplo-clique). */
const DEDUPE_TAIL_MS = 1000;
/** Teto absoluto de vida — impede que repetição prenda o toast na tela. */
const MAX_LIFETIME_MS = 10000;

const SEVERITY: Record<FlashCategory, number> = {
	success: 0,
	info: 1,
	warning: 2,
	danger: 3
};

const BASE_MS: Record<FlashCategory, number> = {
	success: 4000,
	info: 5000,
	warning: 6000,
	danger: 7000
};

/** Duração calculada; exportada para teste. */
export function flashDurationMs(message: string, category: FlashCategory): number {
	const palavras = message.trim().split(/\s+/).filter(Boolean).length;
	const minimo = 3000 + 1000 * Math.ceil(palavras / 3);
	return Math.min(MAX_LIFETIME_MS, Math.max(BASE_MS[category], minimo));
}

interface FlashTimer {
	key: string;
	durationMs: number;
	/** Instante limite absoluto; desloca durante a pausa (tempo pausado não conta). */
	lifetimeEndsAt: number;
	handle: ReturnType<typeof setTimeout> | null;
	expiresAt: number;
	remainingMs: number | null;
	pausedAt: number | null;
	/** Pausas simultâneas (ponteiro + foco): retomar exige zerar o contador. */
	pauseCount: number;
}

/** Fábrica exportada para teste (mesmo padrão de `createBoardStore` em board.ts). */
export function createFlashStore(now: () => number = () => Date.now()): FlashStore {
	const store = writable<FlashMessage[]>([]);
	let nextId = 1;
	const timers = new Map<number, FlashTimer>();
	const tail = new Map<string, number>();
	let items: FlashMessage[] = [];

	function commit(): void {
		store.set(items);
	}

	function clearHandle(timer: FlashTimer): void {
		if (timer.handle === null) return;
		clearTimeout(timer.handle);
		timer.handle = null;
	}

	function schedule(id: number, timer: FlashTimer, delayMs: number): void {
		clearHandle(timer);
		timer.pausedAt = null;
		timer.remainingMs = null;
		timer.expiresAt = now() + delayMs;
		timer.handle = setTimeout(() => drop(id, true), delayMs);
	}

	function drop(id: number, recordTail: boolean): void {
		const timer = timers.get(id);
		if (!timer) return;
		clearHandle(timer);
		timers.delete(id);
		if (recordTail) tail.set(timer.key, now());
		items = items.filter((item) => item.id !== id);
		commit();
	}

	function pruneTail(at: number): void {
		for (const [key, removedAt] of tail) {
			if (at - removedAt >= DEDUPE_TAIL_MS) tail.delete(key);
		}
	}

	/** Abre espaço: descarta o mais antigo de severidade ≤ à do novo, senão FIFO puro. */
	function evict(incoming: FlashCategory): void {
		const level = SEVERITY[incoming];
		const victim = items.find((item) => SEVERITY[item.category] <= level) ?? items[0];
		if (!victim) return;
		drop(victim.id, false);
	}

	/** Repetição coalescida: só contador + timer reiniciado; `message` nunca é reescrito. */
	function bump(id: number, at: number): void {
		items = items.map((item) => (item.id === id ? { ...item, count: item.count + 1 } : item));
		commit();
		const timer = timers.get(id);
		if (!timer) return;
		if (timer.pauseCount > 0 && timer.pausedAt !== null) {
			timer.remainingMs = Math.max(
				0,
				Math.min(timer.durationMs, timer.lifetimeEndsAt - timer.pausedAt)
			);
			return;
		}
		const deadline = Math.min(at + timer.durationMs, timer.lifetimeEndsAt);
		if (deadline <= at) {
			drop(id, true);
			return;
		}
		schedule(id, timer, deadline - at);
	}

	function show(
		message: string,
		category: FlashCategory = 'info',
		options: FlashOptions = {}
	): number {
		const key = options.key ?? `${category}|${message}`;
		const at = now();

		const alive = items.find((item) => item.key === key);
		if (alive) {
			bump(alive.id, at);
			return alive.id;
		}

		pruneTail(at);
		if (tail.has(key)) return -1;

		if (items.length >= MAX_TOASTS) evict(category);

		const durationMs = Math.min(
			MAX_LIFETIME_MS,
			options.durationMs ?? flashDurationMs(message, category)
		);
		const id = nextId++;
		const timer: FlashTimer = {
			key,
			durationMs,
			lifetimeEndsAt: at + MAX_LIFETIME_MS,
			handle: null,
			expiresAt: at + durationMs,
			remainingMs: null,
			pausedAt: null,
			pauseCount: 0
		};
		timers.set(id, timer);
		items = [...items, { id, message, category, key, count: 1, firstShownAt: at }];
		commit();
		schedule(id, timer, durationMs);
		return id;
	}

	function dismiss(id: number): void {
		drop(id, true);
	}

	function pause(id: number): void {
		const timer = timers.get(id);
		if (!timer) return;
		timer.pauseCount += 1;
		if (timer.pauseCount > 1) return;
		const at = now();
		clearHandle(timer);
		timer.pausedAt = at;
		timer.remainingMs = Math.max(0, timer.expiresAt - at);
	}

	function resume(id: number): void {
		const timer = timers.get(id);
		if (!timer || timer.pauseCount === 0) return;
		timer.pauseCount -= 1;
		// Ponteiro ainda sobre o toast enquanto o foco sai: o relógio segue parado.
		if (timer.pauseCount > 0) return;
		if (timer.pausedAt === null || timer.remainingMs === null) return;
		const at = now();
		timer.lifetimeEndsAt += at - timer.pausedAt;
		const deadline = Math.min(at + timer.remainingMs, timer.lifetimeEndsAt);
		if (deadline <= at) {
			drop(id, true);
			return;
		}
		schedule(id, timer, deadline - at);
	}

	function clear(): void {
		for (const timer of timers.values()) clearHandle(timer);
		timers.clear();
		tail.clear();
		items = [];
		commit();
	}

	return {
		subscribe: store.subscribe,
		show,
		success: (message: string, options?: FlashOptions) => show(message, 'success', options),
		info: (message: string, options?: FlashOptions) => show(message, 'info', options),
		warning: (message: string, options?: FlashOptions) => show(message, 'warning', options),
		danger: (message: string, options?: FlashOptions) => show(message, 'danger', options),
		dismiss,
		pause,
		resume,
		clear
	};
}

/** Store singleton de flash da SPA (uma pilha global de toasts). */
export const flash = createFlashStore();
