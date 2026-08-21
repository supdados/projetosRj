/**
 * Acesso tipado às ações da própria conta do usuário logado (tela Ajustes).
 *
 *   GET  /api/conta               -> { name, username, orgao_sigla, govbr }
 *   POST /api/conta/nome          -> { name }
 *   POST /api/conta/govbr         -> { govbr }   (vincular CPF)
 *   POST /api/conta/govbr/remover -> { govbr }   (remover vínculo)
 *   POST /api/conta/senha         -> { changed: true }
 *
 * O CPF completo NUNCA chega ao cliente: `cpf_mascarado` traz só os 3 primeiros
 * dígitos (estado `cpf_pendente`); no estado `vinculado` nem a máscara vem.
 * A troca de senha não exige a senha atual: o corpo é só nova + confirmação.
 * A régua de força da senha é do backend (`services/password_policy.py`): em
 * falha, `client.ts` lança `ApiClientError` com a mensagem já legível em PT-BR
 * — `validation` (400). O 401 já vira navegação top-level para /login dentro
 * do client.
 */

import { get, post } from './client';

/** Estado do vínculo gov.br da conta. */
export type GovbrStatus = 'nenhum' | 'cpf_pendente' | 'vinculado';

export interface GovbrVinculo {
	status: GovbrStatus;
	/** Só presente no estado `cpf_pendente`: 3 primeiros dígitos + `*`. */
	cpf_mascarado: string | null;
}

export interface ContaData {
	name: string;
	username: string;
	/** Sigla do órgão do usuário; null quando não há órgão vinculado. */
	orgao_sigla: string | null;
	govbr: GovbrVinculo;
}

/** Corpo do POST de troca de senha (nomes iguais aos do backend). */
export interface TrocaSenhaPayload {
	nova_senha: string;
	confirmacao: string;
}

interface TrocaSenhaData {
	changed: boolean;
}

/** Dados da conta logada para a tela de Ajustes. */
export function fetchConta(signal?: AbortSignal): Promise<ContaData> {
	return get<ContaData>('/api/conta', signal);
}

/** Troca o nome de exibição (nunca o username). Resolve com o nome salvo. */
export async function trocarNome(name: string, signal?: AbortSignal): Promise<string> {
	const data = await post<{ name: string }>('/api/conta/nome', { name }, signal);
	return data.name;
}

/** Vincula um CPF gov.br à conta. Resolve com o estado novo do vínculo. */
export async function vincularGovbr(
	cpf: string,
	signal?: AbortSignal
): Promise<GovbrVinculo> {
	const data = await post<{ govbr: GovbrVinculo }>('/api/conta/govbr', { cpf }, signal);
	return data.govbr;
}

/** Remove o vínculo gov.br (CPF e login gov.br). Resolve com o estado novo. */
export async function removerGovbr(signal?: AbortSignal): Promise<GovbrVinculo> {
	const data = await post<{ govbr: GovbrVinculo }>('/api/conta/govbr/remover', {}, signal);
	return data.govbr;
}

/** Troca a senha da conta logada. Resolve quando a senha foi trocada. */
export async function trocarSenha(
	payload: TrocaSenhaPayload,
	signal?: AbortSignal
): Promise<boolean> {
	const data = await post<TrocaSenhaData>('/api/conta/senha', payload, signal);
	return data.changed;
}
