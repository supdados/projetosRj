/**
 * Acesso tipado ao CRUD de "Tipos de Órgão" (`/api/admin/orgaos/tipos*`).
 *
 * Leituras via `client.get`; mutações via `client.post` (que injeta o
 * X-CSRFToken — NÃO editamos `client.ts`). Todos os endpoints exigem
 * `api_admin_required` no backend: 403 (JSON) para não-admin e 401 sem sessão,
 * já tratados por `client.ts`. As respostas chegam JÁ desempacotadas do
 * envelope; falhas (422 validação / 409 conflito de hierarquia / 404)
 * viram `ApiClientError` com `code`/`message` do backend.
 *
 * Espelha os endpoints de routes/api/admin_orgaos.py e a semântica de
 * `_normalize_tipo_form` (routes/admin_orgaos.py).
 */

import { get, post, put, del } from './client';
import type {
	AdminOrgaoTiposListData,
	AdminOrgaoTipoDetailData,
	AdminOrgaoTipoMutationData,
	AdminOrgaoTipoDeleteData,
	AdminOrgaoTipoFormInput
} from '$lib/types/adminOrgaoTipos';

/**
 * Monta o corpo JSON do form de tipo.
 *
 * As flags `ativo`/`permite_raiz` seguem a detecção por presença do backend
 * (`payload.get(...) is not None`): a chave é OMITIDA quando `false` para não
 * ser interpretada como verdadeira. `slug`/`descricao` só vão quando preenchidos
 * (o backend deriva o slug do nome quando ausente).
 */
function buildTipoBody(input: AdminOrgaoTipoFormInput): Record<string, unknown> {
	const body: Record<string, unknown> = {
		nome: input.nome.trim(),
		nivel: input.nivel
	};
	const slug = input.slug?.trim();
	if (slug) body.slug = slug;
	const descricao = input.descricao?.trim();
	if (descricao) body.descricao = descricao;
	if (input.ativo) body.ativo = '1';
	if (input.permite_raiz) body.permite_raiz = '1';
	return body;
}

/** Lista o catálogo de tipos (inclui inativos) com a contagem de uso por tipo. */
export function fetchOrgaoTipos(
	signal?: AbortSignal
): Promise<AdminOrgaoTiposListData> {
	return get<AdminOrgaoTiposListData>('/api/admin/orgaos/tipos', signal);
}

/** Carrega um tipo para o form de edição; `fail(404)` vira `ApiClientError`. */
export function fetchOrgaoTipo(
	tipoId: number,
	signal?: AbortSignal
): Promise<AdminOrgaoTipoDetailData> {
	return get<AdminOrgaoTipoDetailData>(`/api/admin/orgaos/tipos/${tipoId}`, signal);
}

/** Cria um tipo (sempre `is_system=false`). `fail(422)` em validação. */
export function createOrgaoTipo(
	input: AdminOrgaoTipoFormInput,
	signal?: AbortSignal
): Promise<AdminOrgaoTipoMutationData> {
	return post<AdminOrgaoTipoMutationData>(
		'/api/admin/orgaos/tipos',
		buildTipoBody(input),
		signal
	);
}

/**
 * Edita um tipo. `fail(422)` em validação; `fail(409)` quando a alteração de
 * nível/raiz deixaria órgãos fora da regra hierárquica (ou desativa tipo em uso).
 */
export function updateOrgaoTipo(
	tipoId: number,
	input: AdminOrgaoTipoFormInput,
	signal?: AbortSignal
): Promise<AdminOrgaoTipoMutationData> {
	return put<AdminOrgaoTipoMutationData>(
		`/api/admin/orgaos/tipos/${tipoId}`,
		buildTipoBody(input),
		signal
	);
}

/**
 * Alterna ativo/inativo. `fail(409)` ao tentar desativar tipo raiz ativo ou
 * tipo em uso por órgãos.
 */
export function toggleOrgaoTipoAtivo(
	tipoId: number,
	signal?: AbortSignal
): Promise<AdminOrgaoTipoMutationData> {
	return post<AdminOrgaoTipoMutationData>(
		`/api/admin/orgaos/tipos/${tipoId}/toggle-ativo`,
		undefined,
		signal
	);
}

/**
 * Exclui um tipo. `fail(409)` quando em uso por órgãos ou permitido para raiz;
 * `fail(404)` se não existe.
 */
export function deleteOrgaoTipo(
	tipoId: number,
	signal?: AbortSignal
): Promise<AdminOrgaoTipoDeleteData> {
	return del<AdminOrgaoTipoDeleteData>(
		`/api/admin/orgaos/tipos/${tipoId}`,
		undefined,
		signal
	);
}
