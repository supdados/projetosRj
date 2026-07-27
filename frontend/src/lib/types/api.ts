/**
 * Contrato de envelope da API JSON do backend Flask.
 *
 * Espelha `routes/api/envelope.py`:
 *   sucesso -> { "ok": true,  "data": <T>, "meta"?: PageMeta }
 *   falha   -> { "ok": false, "error": { "code", "message" } }
 *
 * `client.ts` desempacota o envelope: em sucesso devolve `data`; em falha
 * lanca `ApiClientError`. Os tipos abaixo descrevem o JSON cru na rede.
 */

/** Metadados de paginacao (presentes apenas em respostas paginadas). */
export interface PageMeta {
	page: number;
	page_size: number;
	total: number;
}

/** Envelope de sucesso. `meta` so aparece em listas paginadas. */
export interface ApiEnvelope<T> {
	ok: true;
	data: T;
	meta?: PageMeta;
}

/**
 * Codigos de erro padronizados pelo backend (`routes/api/negotiation.py`).
 *
 * Contrato de autorizacao S5 (`services/authorization.py::project_access_verdict`
 * + `routes/api/envelope.py::fail_not_found`):
 *   - `not_found` (404): o recurso NAO EXISTE **ou** o usuario nao tem acesso a
 *     ele. Os dois casos respondem o MESMO corpo (anti-enumeracao) — a UI mostra
 *     "não existe ou você não tem acesso" e nunca tenta distinguir.
 *   - `forbidden` (403): o usuario ve o recurso mas nao pode ESTA acao (rank
 *     abaixo do exigido, autoria, dono da conta Google).
 *   - Rotas `/admin/*` (`api_admin_required`) ficam so em 403 — nao migraram.
 */
export type ApiErrorCode =
	| 'unauthenticated'
	| 'forbidden'
	| 'not_found'
	| 'validation'
	| 'server'
	| string;

/** Envelope de falha. */
export interface ApiError {
	ok: false;
	error: {
		code: ApiErrorCode;
		message: string;
	};
}

/** Uniao discriminada pelo campo `ok` — formato cru de qualquer resposta da API. */
export type ApiResult<T> = ApiEnvelope<T> | ApiError;
