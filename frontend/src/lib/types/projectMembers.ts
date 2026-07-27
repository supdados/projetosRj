/**
 * Tipos dos convites por projeto (`project_member`, S4/§6.5).
 *
 * Espelham `routes/api/project_members.py` e o modelo `models/project_member.py`
 * (papel com teto rígido `editor`, revogação soft, expiração lazy). O envelope
 * `{ok, data}` é desempacotado por `client.ts`; os tipos abaixo descrevem apenas
 * `data`.
 *
 * Nenhuma decisão de permissão acontece aqui: quem pode gerenciar vem de
 * `permissions.can_manage_members` (serializers), nunca recalculado no cliente.
 */

import type { OrgaoPapel } from './entities';

/** Papel concedível por convite. Gestor é proibido pelo teto do backend. */
export type ConvitePapel = 'leitor' | 'editor';

/** Estado de um convite direto na leitura (`is_active` lazy + `revoked_at`). */
export type ConviteStatus = 'ativo' | 'expirado' | 'revogado';

/** Membro DIRETO: uma linha de `project_member` (convite). */
export interface ProjectMemberDireto {
	/** Id da linha `project_member` (o `<mid>` das rotas PUT/DELETE). */
	id: number;
	user_id: number;
	user_name: string;
	user_username: string;
	user_orgao_sigla: string | null;
	papel: ConvitePapel;
	status: ConviteStatus;
	created_at: string | null; // ISO 8601
	expires_at: string | null; // ISO 8601 (null = sem expiração)
	revoked_at: string | null; // ISO 8601
	/** Opcional: nomes de auditoria; ausentes não quebram a UI. */
	granted_by_name?: string | null;
	revoked_by_name?: string | null;
}

/**
 * Membro HERDADO pelo vínculo de área (read-only no modal): não existe linha em
 * `project_member` para ele, então não há `id` nem ações.
 */
export interface ProjectMemberHerdado {
	user_id: number;
	user_name: string;
	user_username: string;
	papel: OrgaoPapel;
	orgao_id: number;
	orgao_sigla: string | null;
	orgao_nome: string | null;
}

/** Carga de GET /api/projetos/<id>/membros (já desempacotada). */
export interface ProjectMembersData {
	diretos: ProjectMemberDireto[];
	herdados: ProjectMemberHerdado[];
}

/** Usuário convidável devolvido por GET /api/usuarios/busca (sem dado sensível). */
export interface UsuarioConvidavel {
	id: number;
	name: string;
	username: string;
	orgao_sigla: string | null;
}

/** Carga de GET /api/usuarios/busca?q= (já desempacotada). */
export interface UsuarioBuscaData {
	usuarios: UsuarioConvidavel[];
}

/** Corpo de POST /api/projetos/<id>/membros. */
export interface ConviteCreatePayload {
	user_id: number;
	papel: ConvitePapel;
	/** ISO YYYY-MM-DD; omitido = convite sem expiração. */
	expires_at?: string | null;
}

/** Corpo de PUT /api/projetos/<id>/membros/<mid> (papel e/ou expiração). */
export interface ConviteUpdatePayload {
	papel?: ConvitePapel;
	expires_at?: string | null;
}
