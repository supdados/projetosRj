/**
 * Testes do ícone por `event_type` do sino: os eventos de coleção com aceite
 * (convite, aceite, recusa, saída) e a ordem de precedência herdada do
 * `AppTopnav` (atividade específica antes do `_deleted`/`create` genéricos).
 */
import { describe, expect, it } from 'vitest';
import { notificationIcon } from './notificationIcon';

describe('notificationIcon', () => {
	it('todos os eventos de coleção compartilhada usam o ícone de convite', () => {
		for (const tipo of [
			'colecao_convite',
			'colecao_convite_aceito',
			'colecao_convite_recusado',
			'colecao_participante_saiu',
			'colecao_compartilhada',
			'projeto_convite'
		]) {
			expect(notificationIcon(tipo)).toBe('convite');
		}
	});

	it('atividade específica vence o sufixo genérico', () => {
		expect(notificationIcon('task_comment_deleted')).toBe('comentario');
		expect(notificationIcon('task_attachment_deleted')).toBe('anexo');
		expect(notificationIcon('delete_etapa')).toBe('etapa');
		expect(notificationIcon('google_meeting_create')).toBe('reuniao');
	});

	it('mantém os demais grupos', () => {
		expect(notificationIcon('task_finalized')).toBe('conclusao');
		expect(notificationIcon('task_archived')).toBe('arquivo');
		expect(notificationIcon('task_assignment')).toBe('atribuicao');
		expect(notificationIcon('project_create')).toBe('criacao');
		expect(notificationIcon('task_status_updated')).toBe('status');
		expect(notificationIcon('project_delete')).toBe('exclusao');
		expect(notificationIcon('project_edit')).toBe('edicao');
	});

	it('normaliza caixa/espaços e cai no sino quando não conhece o tipo', () => {
		expect(notificationIcon('  COLECAO_CONVITE ')).toBe('convite');
		expect(notificationIcon('algo_novo')).toBe('sino');
		expect(notificationIcon(null)).toBe('sino');
	});
});
