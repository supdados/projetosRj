/**
 * Ícone do redesign por `event_type` de notificação (13 grupos do doc do sino).
 * Extraído de `AppTopnav.svelte` junto com o sino (`NotificationBell`).
 *
 * A ordem importa: comentário/anexo/etapa/reunião vêm ANTES do `_deleted`
 * genérico, e os eventos de coleção compartilhada (`colecao_*`: convite,
 * aceite, recusa, saída e o histórico `colecao_compartilhada`) caem todos no
 * ícone de convite.
 *
 * Exemplo:
 *   notificationIcon('colecao_convite'); // 'convite'
 */

import type { AppIconId } from '$lib/icons/appIcons';

const EVENTOS_DE_CONVITE = new Set([
	'projeto_convite',
	'colecao_compartilhada',
	'colecao_convite',
	'colecao_convite_aceito',
	'colecao_convite_recusado',
	'colecao_participante_saiu'
]);

function iconeDeAtividade(t: string): AppIconId | null {
	if (t.startsWith('task_comment_') || t.startsWith('task_item_comment_')) return 'comentario';
	if (t.startsWith('task_attachment_')) return 'anexo';
	if (t.includes('google_meeting')) return 'reuniao';
	const etapa = ['add_etapa', 'edit_etapa', 'delete_etapa'].some((p) => t.startsWith(p));
	if (etapa || t === 'import_model') return 'etapa';
	return null;
}

function iconeDeEstado(t: string): AppIconId | null {
	const conclusao = ['finalize', 'reactivate', 'toggle_done'].some((s) => t.endsWith(s));
	if (t === 'task_finalized' || conclusao) return 'conclusao';
	if (t === 'task_archived' || t === 'task_unarchived') return 'arquivo';
	if (t === 'task_assignment' || t === 'task_item_assignment') return 'atribuicao';
	if (EVENTOS_DE_CONVITE.has(t)) return 'convite';
	return null;
}

const STATUS_EVENTS = new Set([
	'task_status_updated',
	'task_priority_updated',
	'task_type_updated'
]);

function iconeDeMudanca(t: string): AppIconId {
	if (t === 'task_created' || t.endsWith('create')) return 'criacao';
	if (STATUS_EVENTS.has(t) || t.endsWith('toggle_iniciada')) return 'status';
	if (t === 'task_deleted' || t === 'project_delete' || t.endsWith('_deleted')) return 'exclusao';
	if (t === 'task_updated' || t.endsWith('edit')) return 'edicao';
	return 'sino';
}

/** Ícone do item do sino; tipo desconhecido cai no próprio sino. */
export function notificationIcon(eventType: string | null | undefined): AppIconId {
	const t = (eventType ?? '').toString().trim().toLowerCase();
	return iconeDeAtividade(t) ?? iconeDeEstado(t) ?? iconeDeMudanca(t);
}
