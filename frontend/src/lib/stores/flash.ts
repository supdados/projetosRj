/**
 * Sistema de FLASH/TOAST da SPA (equivalente a `window.showFlash` +
 * `static/js/app-shell/flash.js` do Jinja).
 *
 * Toasts no topo da tela com auto-dismiss (~2.2s para sucesso) e categorias
 * `success`/`info`/`warning`/`danger` (mapeadas dos `flash()`/`showFlash()` do
 * Flask), consumidos pelo `<FlashToasts>` montado uma vez por tela.
 *
 * Exemplo:
 *   import { flash } from '$lib/stores/flash';
 *   flash.success('Tarefa criada com sucesso.');
 *   flash.show('Não foi possível atualizar a etapa.', 'danger');
 */

import { writable, type Readable } from 'svelte/store';

/** Categorias espelhando as do flash legado (Flask `flash(msg, category)`). */
export type FlashCategory = 'success' | 'info' | 'warning' | 'danger';

/** Um toast ativo na fila. */
export interface FlashMessage {
	id: number;
	message: string;
	category: FlashCategory;
}

/** Duração (ms) por categoria — sucesso some rápido (paridade com o legado). */
const AUTO_DISMISS_MS: Record<FlashCategory, number> = {
	success: 2200,
	info: 3200,
	warning: 4200,
	danger: 5200
};

let nextId = 1;

interface FlashStore extends Readable<FlashMessage[]> {
	show(message: string, category?: FlashCategory): number;
	success(message: string): number;
	info(message: string): number;
	warning(message: string): number;
	danger(message: string): number;
	dismiss(id: number): void;
}

function createFlashStore(): FlashStore {
	const store = writable<FlashMessage[]>([]);

	function dismiss(id: number): void {
		store.update((items) => items.filter((item) => item.id !== id));
	}

	function show(message: string, category: FlashCategory = 'info'): number {
		const id = nextId++;
		store.update((items) => [...items, { id, message, category }]);
		// Auto-dismiss espelhando o comportamento do flash legado.
		if (typeof window !== 'undefined') {
			window.setTimeout(() => dismiss(id), AUTO_DISMISS_MS[category]);
		}
		return id;
	}

	return {
		subscribe: store.subscribe,
		show,
		success: (message: string) => show(message, 'success'),
		info: (message: string) => show(message, 'info'),
		warning: (message: string) => show(message, 'warning'),
		danger: (message: string) => show(message, 'danger'),
		dismiss
	};
}

/** Store singleton de flash da SPA (uma fila global de toasts). */
export const flash = createFlashStore();
