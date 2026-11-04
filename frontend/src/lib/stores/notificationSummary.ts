/**
 * Resumo do sino (`GET /api/notificacoes/resumo`) compartilhado pela SPA.
 *
 * O sino (`NotificationBell`) é quem consulta — polling de ~60 s — e registra
 * aqui o seu "consultar já". As telas que mudam o estado de um convite
 * (aceitar, recusar, sair) tiram o convite na hora (`removerConvite`, o ponto
 * apaga sem esperar o próximo tique) e pedem a consulta real (`atualizar`),
 * que também corrige `unread_count` (o aviso de uma coleção recusada some).
 *
 * Exemplo:
 *   import { notificationSummary } from '$lib/stores/notificationSummary';
 *   await aceitarConvite(id);
 *   notificationSummary.removerConvite(id);
 *   notificationSummary.atualizar();
 */

import { writable, type Readable } from 'svelte/store';
import type { NotificacoesResumo } from '$lib/types/notifications';

export interface NotificationSummaryStore extends Readable<NotificacoesResumo | null> {
	/** Grava o resumo vindo do servidor. */
	definir(resumo: NotificacoesResumo): void;
	/** Depois de "marcar lidas": o servidor devolve o `unread_count` novo. */
	definirNaoLidas(total: number): void;
	/** Convite respondido nesta aba: some do resumo antes da próxima consulta. */
	removerConvite(collectionId: number): void;
	/** Pede ao sino uma consulta imediata (no-op se o sino não está montado). */
	atualizar(): void;
	/** O sino registra (ou desfaz, com `null`) a sua consulta imediata. */
	registrarAtualizador(atualizador: (() => void) | null): void;
	/** Volta ao estado inicial (logout/teste). */
	limpar(): void;
}

/** Fábrica exportada para teste (mesmo padrão de `createFlashStore`). */
export function createNotificationSummaryStore(): NotificationSummaryStore {
	const store = writable<NotificacoesResumo | null>(null);
	let atualizador: (() => void) | null = null;

	function removerConvite(collectionId: number): void {
		store.update((resumo) => {
			if (!resumo) return resumo;
			const convites = resumo.convites.filter((c) => c.collection_id !== collectionId);
			if (convites.length === resumo.convites.length) return resumo;
			return { ...resumo, convites, convites_pendentes: convites.length };
		});
	}

	return {
		subscribe: store.subscribe,
		definir: (resumo) => store.set(resumo),
		definirNaoLidas: (total) =>
			store.update((resumo) => (resumo ? { ...resumo, unread_count: Math.max(0, total) } : resumo)),
		removerConvite,
		atualizar: () => atualizador?.(),
		registrarAtualizador: (novo) => {
			atualizador = novo;
		},
		limpar: () => {
			atualizador = null;
			store.set(null);
		}
	};
}

/** Store singleton do resumo do sino. */
export const notificationSummary = createNotificationSummaryStore();
