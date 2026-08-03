/**
 * Sistema de FLASH/TOAST da SPA (equivalente a `window.showFlash` +
 * `static/js/app-shell/flash.js` do Jinja).
 *
 * Toasts no canto superior direito com auto-dismiss por categoria, teto de 3 na
 * pilha, deduplicação por chave e pausa em hover/foco. `danger` não expira
 * sozinho — só sai por X, Esc ou evicção. Consumido pelo `<FlashToasts>`
 * montado uma vez por tela.
 *
 * Dedupe por `key` tem dois desfechos:
 * - repetição IDÊNTICA (mesma `message` e `category`): só incrementa `count` e
 *   reinicia o timer, sem cartão novo;
 * - texto ou categoria DIFERENTES sob a mesma `key`: o cartão vivo é REESCRITO
 *   no lugar (mesmo `id` e mesma posição), `count` volta a 1, o timer reinicia
 *   pela categoria nova e `revision` incrementa para o leitor de tela
 *   reanunciar. Sem isso a 2ª mensagem de uma `key` compartilhada nunca
 *   apareceria — e com `danger` eterno ficaria presa para sempre.
 *
 * Exemplo:
 *   import { flash } from '$lib/stores/flash';
 *   flash.success('Tarefa criada com sucesso.');
 *   flash.success('Projeto criado', { description: 'Já está na sua lista.' });
 *   flash.warning('Finalize as tarefas pendentes.', { key: 'etapa-tarefas-pendentes' });
 */

import { writable, type Readable } from 'svelte/store';

/** Categorias espelhando as do flash legado (Flask `flash(msg, category)`). */
export type FlashCategory = 'success' | 'info' | 'warning' | 'danger';

export interface FlashOptions {
	/** Agrupa repetições cujo texto varia mas o evento é o mesmo. */
	key?: string;
	/** Segunda linha do cartão: consequência ou detalhe do que aconteceu. */
	description?: string;
	/** Override de duração (ms), com teto de 10000. IGNORADO em `danger`. */
	durationMs?: number;
}

/** Um toast ativo na pilha. */
export interface FlashMessage {
	id: number;
	message: string;
	category: FlashCategory;
	/** Texto secundário opcional (o título é `message`). */
	description?: string;
	/** Chave de dedupe (explícita ou `${category}|${message}`). */
	key: string;
	/** 1 na primeira exibição do texto atual; incrementa a cada repetição coalescida. */
	count: number;
	/** Epoch ms em que o texto atual entrou — base do teto de vida (não se aplica a `danger`). */
	firstShownAt: number;
	/** 0 no nascimento; incrementa a cada reescrita — sinal de re-anúncio (o `id` não muda). */
	revision: number;
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

/**
 * Teto da pilha visível; acima disso há evicção (nunca recusa o toast novo).
 * Teto SOFT: se não há vítima elegível (pilha só de `danger` e o novo não é
 * `danger`), a pilha passa de 3 em vez de sacrificar um erro não lido.
 */
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
	info: 4000,
	warning: 7000,
	danger: Number.POSITIVE_INFINITY
};

/** `danger` não tem teto: erro sem leitura vira trabalho perdido. */
function lifetimeCapMs(category: FlashCategory): number {
	return category === 'danger' ? Number.POSITIVE_INFINITY : MAX_LIFETIME_MS;
}

/** Duração calculada; `Infinity` em `danger` (só sai por X, Esc ou evicção). */
export function flashDurationMs(message: string, category: FlashCategory): number {
	if (category === 'danger') return Number.POSITIVE_INFINITY;
	const palavras = message.trim().split(/\s+/).filter(Boolean).length;
	const minimo = 3000 + 1000 * Math.ceil(palavras / 3);
	return Math.min(MAX_LIFETIME_MS, Math.max(BASE_MS[category], minimo));
}

/**
 * Duração efetiva do toast. O override do chamador NÃO vale para `danger`:
 * `Math.min` contra um teto infinito deixaria o valor passar e devolveria o
 * auto-dismiss que o erro não pode ter.
 */
function resolveDurationMs(
	message: string,
	category: FlashCategory,
	override: number | undefined
): number {
	if (category === 'danger') return Number.POSITIVE_INFINITY;
	return Math.min(MAX_LIFETIME_MS, override ?? flashDurationMs(message, category));
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
		// Prazo infinito (danger): fica na tela sem timer até fechamento manual.
		if (!Number.isFinite(delayMs)) return;
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

	/**
	 * Abre espaço: descarta o mais antigo de severidade ≤ à do novo. Sem vítima
	 * elegível não há FIFO de consolo — `danger` só é despejado por outro
	 * `danger`, senão um "Salvo." derrubaria o erro que ninguém leu.
	 */
	function evict(incoming: FlashCategory): void {
		const level = SEVERITY[incoming];
		const victim = items.find((item) => SEVERITY[item.category] <= level);
		if (!victim) return;
		drop(victim.id, false);
	}

	/** Repetição idêntica coalescida: só contador + timer reiniciado, sem cartão novo. */
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

	/**
	 * Reescrita no lugar: a `key` já está viva, mas com outro texto/categoria. O
	 * cartão mantém `id` e posição; o relógio recomeça pela categoria nova e
	 * `revision` sobe para o anúncio ao leitor de tela sair de novo.
	 */
	function rewrite(
		id: number,
		message: string,
		category: FlashCategory,
		options: FlashOptions,
		at: number
	): void {
		items = items.map((item) =>
			item.id === id
				? {
						...item,
						message,
						category,
						description: options.description,
						count: 1,
						firstShownAt: at,
						revision: item.revision + 1
					}
				: item
		);
		commit();
		const timer = timers.get(id);
		if (!timer) return;
		timer.durationMs = resolveDurationMs(message, category, options.durationMs);
		timer.lifetimeEndsAt = at + lifetimeCapMs(category);
		// Sob o ponteiro: o texto novo já vale, mas o relógio só volta a correr no resume.
		if (timer.pauseCount > 0 && timer.pausedAt !== null) {
			timer.remainingMs = timer.durationMs;
			return;
		}
		schedule(id, timer, timer.durationMs);
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
			if (alive.message === message && alive.category === category) bump(alive.id, at);
			else rewrite(alive.id, message, category, options, at);
			return alive.id;
		}

		pruneTail(at);
		if (tail.has(key)) return -1;

		if (items.length >= MAX_TOASTS) evict(category);

		const cap = lifetimeCapMs(category);
		const durationMs = resolveDurationMs(message, category, options.durationMs);
		const id = nextId++;
		const timer: FlashTimer = {
			key,
			durationMs,
			lifetimeEndsAt: at + cap,
			handle: null,
			expiresAt: at + durationMs,
			remainingMs: null,
			pausedAt: null,
			pauseCount: 0
		};
		timers.set(id, timer);
		items = [
			...items,
			{
				id,
				message,
				category,
				description: options.description,
				key,
				count: 1,
				firstShownAt: at,
				revision: 0
			}
		];
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
