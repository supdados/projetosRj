/**
 * Tipos das notificações da SPA (sino da topnav).
 *
 * Espelham `routes/notifications.py` (`_serialize_notification` +
 * `api_notificacoes_list`): a MESMA query/escopo do dropdown legado, agora no
 * envelope canônico. `created_at` em ISO 8601 (ou `null`).
 */

/** Item da lista de notificações (GET /api/notificacoes -> data.items[]). */
export interface Notificacao {
	id: number;
	event_type: string;
	title: string;
	message: string;
	created_at: string | null; // ISO 8601
	actor_name: string; // "" quando sem ator
	is_unread: boolean;
	target_url: string | null;
}

/** Carga de GET /api/notificacoes (já desempacotada do envelope). */
export interface NotificacaoListResult {
	items: Notificacao[];
	unread_count: number;
}

/** Carga de POST /api/notificacoes/marcar-lidas. */
export interface NotificacaoMarcarLidasResult {
	marked: number;
	unread_count: number; // sempre 0 após marcar
}

/** Convite pendente citado no resumo do sino (só o necessário para o toast). */
export interface NotificacaoConviteResumo {
	collection_id: number;
	nome: string;
}

/**
 * Carga de GET /api/notificacoes/resumo — o polling leve do sino.
 *
 * `unread_count` conta só as não lidas VISÍVEIS (mesmo filtro da lista);
 * `convites_pendentes` independe de `is_read`: o ponto do sino acende pela
 * soma dos dois. `convites` alimenta o toast de convite novo.
 */
export interface NotificacoesResumo {
	unread_count: number;
	convites_pendentes: number;
	convites: NotificacaoConviteResumo[];
}
