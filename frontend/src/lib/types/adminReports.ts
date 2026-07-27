/**
 * Tipos do relatório admin de grants órfãos (S4/F3-25), espelhando
 * `OrphanGrant` de `services/authorization_reports.py`.
 */

export type GrantOrfaoMotivo = 'concedente_removido' | 'concedente_sem_gestao';

/** Convite ativo cujo concedente perdeu a gestão do projeto (revisão manual). */
export interface GrantOrfao {
	member_id: number;
	project_id: number;
	project_titulo: string;
	user_id: number;
	user_name: string;
	granted_by_id: number | null;
	granted_by_name: string | null;
	motivo: GrantOrfaoMotivo;
	created_at: string | null;
	expires_at: string | null;
}
