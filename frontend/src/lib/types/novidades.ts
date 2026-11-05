/**
 * Contrato de `routes/api/novidades.py` (onboarding "Novidades").
 *
 * O backend só sabe QUAIS novidades existem, se estão ativas e quem já viu; o
 * conteúdo de cada uma (passos, textos, ilustrações) vem do registro do front,
 * `lib/novidades/conteudo.ts`, pelo `slug`.
 */

/** Uma novidade ativa do ponto de vista de quem está logado (`GET /api/novidades`). */
export interface NovidadeResumo {
	slug: string;
	titulo: string;
	/** ISO 8601 (UTC). Ordena: mais recente primeiro. */
	publicada_em: string;
	vista: boolean;
}

/** Uma novidade na tela de administração (`GET /api/admin/novidades`). */
export interface NovidadeAdmin {
	slug: string;
	titulo: string;
	ativa: boolean;
	publicada_em: string;
	/** Pessoas que já fecharam (concluindo ou dispensando). */
	vistas: number;
	/** Pessoas que chegaram ao último passo. */
	concluidas: number;
}

export interface NovidadesAdminData {
	novidades: NovidadeAdmin[];
	/** Usuários não excluídos — base do "N de M viram". */
	usuarios_ativos: number;
}
