/**
 * Confirmação imperativa da SPA — substitui `window.confirm` e o estado local
 * de diálogo espalhado pelas telas.
 *
 * Exemplo:
 *   import { confirmAction } from '$lib/stores/confirm';
 *   const ok = await confirmAction({ title: 'Excluir projeto?', confirmLabel: 'Excluir projeto' });
 *   if (!ok) return;
 *
 * `<ConfirmHost />` (montado uma vez no layout autenticado) lê a store abaixo,
 * renderiza o `ConfirmDialog` e resolve a Promise.
 */

import { get, writable, type Readable } from 'svelte/store';
import type { FeedbackIconId } from '$lib/icons/feedbackIcons';

export type ConfirmTone = 'danger' | 'brand' | 'warning';

export interface ConfirmRequest {
	/** Pergunta direta com verbo + objeto: "Excluir projeto?". */
	title: string;
	/** Consequência concreta, 1–2 frases. */
	description?: string;
	tone?: ConfirmTone;
	icon?: FeedbackIconId;
	/** Verbo + objeto ("Excluir projeto"), nunca "OK"/"Sim". */
	confirmLabel: string;
	cancelLabel?: string;
	/** Rótulo em progresso ("Excluindo…") enquanto `run` está no ar. */
	busyLabel?: string;
	/** Frase exigida no campo mono para liberar o botão. */
	typeToConfirm?: string;
	/**
	 * Executa a ação com o diálogo aberto em `busy`. Se lançar, a mensagem vira
	 * banner de erro dentro do diálogo e ele NÃO fecha; só resolve `true` no fim.
	 */
	run?: () => Promise<void>;
}

/** O que o host consome: a solicitação com identidade estável. */
export interface PendingConfirm extends ConfirmRequest {
	id: number;
}

const pending = writable<PendingConfirm | null>(null);
let activeResolve: ((accepted: boolean) => void) | null = null;
let sequence = 0;

/** Solicitação corrente (ou `null` quando não há diálogo aberto). */
export const confirmRequest: Readable<PendingConfirm | null> = { subscribe: pending.subscribe };

function settle(accepted: boolean): void {
	const resolve = activeResolve;
	activeResolve = null;
	resolve?.(accepted);
}

/** Abre o diálogo e resolve `true` na confirmação, `false` no cancelamento. */
export function confirmAction(request: ConfirmRequest): Promise<boolean> {
	// Uma por vez: pedir outra com uma aberta descarta a anterior como recusada.
	settle(false);
	sequence += 1;
	const id = sequence;
	return new Promise<boolean>((resolve) => {
		activeResolve = resolve;
		pending.set({ ...request, id });
	});
}

/**
 * Fecha a solicitação corrente resolvendo a Promise. `requestId` protege contra
 * resposta atrasada de uma solicitação que já foi substituída por outra.
 */
export function resolveConfirm(accepted: boolean, requestId?: number): void {
	const current = get(pending);
	if (!current) return;
	if (requestId !== undefined && requestId !== current.id) return;
	settle(accepted);
	pending.set(null);
}
