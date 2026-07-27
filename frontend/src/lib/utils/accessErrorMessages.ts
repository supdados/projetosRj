/**
 * Mensagens PT-BR do contrato de erro de autorizacao (S5, §6.3 do doc
 * `docs/sugestao-tipos-usuario.md`).
 *
 * Contrato:
 *   - 404 `not_found` — o recurso nao existe OU o usuario nao o enxerga (rank 0).
 *     Os dois casos respondem o MESMO envelope (anti-enumeracao), entao a tela
 *     nunca revela qual dos dois e nunca reusa a mensagem do servidor
 *     (deliberadamente sem entidade: "Recurso nao encontrado.").
 *   - 403 `forbidden` — o usuario ve o recurso mas nao pode executar a acao.
 *   - 401 ja redireciona para /login em `client.ts`.
 *
 * Uso:
 *   const kind = accessErrorKind(err);
 *   const msg = accessErrorMessage(err, MSG_PROJETO_INACESSIVEL, 'Falha ao carregar.');
 */

import { ApiClientError } from '$lib/api/client';

/** Caso do contrato ao qual um erro de carregamento pertence. */
export type AccessErrorKind = 'not_found' | 'forbidden' | 'generic';

/** 404: nunca dizer se o projeto nao existe ou se e invisivel para o usuario. */
export const MSG_PROJETO_INACESSIVEL = 'Este projeto não existe ou você não tem acesso.';

/** 404 de tarefa — mesma regra do projeto. */
export const MSG_TAREFA_INACESSIVEL = 'Esta tarefa não existe ou você não tem acesso.';

/** 403: o usuario ve o recurso, a acao e que esta acima do seu papel. */
export const MSG_ACAO_SEM_PERMISSAO = 'Você não tem permissão para esta ação.';

/** Classifica um erro da API nos tres casos do contrato (status ou `code`). */
export function accessErrorKind(err: unknown): AccessErrorKind {
	if (!(err instanceof ApiClientError)) return 'generic';
	if (err.status === 404 || err.code === 'not_found') return 'not_found';
	if (err.status === 403 || err.code === 'forbidden') return 'forbidden';
	return 'generic';
}

/**
 * Mensagem de painel de erro por caso: 404 usa a mensagem unica da entidade,
 * 403 usa a mensagem de acao e o resto cai na mensagem do erro / fallback.
 */
export function accessErrorMessage(
	err: unknown,
	notFoundMessage: string,
	fallback: string
): string {
	const kind = accessErrorKind(err);
	if (kind === 'not_found') return notFoundMessage;
	if (kind === 'forbidden') return MSG_ACAO_SEM_PERMISSAO;
	if (err instanceof Error && err.message) return err.message;
	return fallback;
}
