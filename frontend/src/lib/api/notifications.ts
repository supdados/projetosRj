/**
 * Acesso tipado às notificações do sino da topnav.
 *
 * Espelha `routes/notifications.py`:
 *   - GET  /api/notificacoes            -> NotificacaoListResult (items + unread_count)
 *   - GET  /api/notificacoes/resumo     -> NotificacoesResumo (polling do sino)
 *   - POST /api/notificacoes/marcar-lidas -> NotificacaoMarcarLidasResult
 *
 * O comportamento do v4.5 era: ao ABRIR o sino, carregava a lista E marcava
 * como lidas (o badge zerava). Aqui mantemos a mesma UX: `openNotifications`
 * busca os itens e em seguida marca-lidas, devolvendo `unread_count` de antes
 * (para mostrar quantas eram novas) junto da lista para render.
 *
 * O client (`get`/`post`) já desempacota o envelope canônico e devolve `data`.
 */

import { get, getQuiet, post } from './client';
import type {
	NotificacaoListResult,
	NotificacaoMarcarLidasResult,
	NotificacoesResumo
} from '$lib/types/notifications';

/** Lista as notificações do usuário (sem alterar o estado de leitura). */
export function fetchNotificacoes(signal?: AbortSignal): Promise<NotificacaoListResult> {
	return get<NotificacaoListResult>('/api/notificacoes', signal);
}

/** Marca todas as notificações como lidas (badge volta a zero). */
export function marcarNotificacoesLidas(
	signal?: AbortSignal
): Promise<NotificacaoMarcarLidasResult> {
	return post<NotificacaoMarcarLidasResult>('/api/notificacoes/marcar-lidas', undefined, signal);
}

/**
 * Contadores do sino (não lidas visíveis + convites pendentes) para o polling.
 * GET de fundo: sessão expirada sobe como `ApiClientError('unauthenticated')`
 * SEM navegar para /login — quem chama para de consultar.
 */
export function fetchNotificacoesResumo(signal?: AbortSignal): Promise<NotificacoesResumo> {
	return getQuiet<NotificacoesResumo>('/api/notificacoes/resumo', signal);
}
