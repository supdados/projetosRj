/**
 * Acesso tipado ao endpoint "Lista de Projetos" (GET /api/projetos).
 *
 * Devolve a `ProjectsListData` já desempacotada do envelope (`client.ts`),
 * respeitando o `orgao_scope` aplicado no servidor. Os query params
 * (`?status`/`?prioridade`/`?special_project`/`?abep_indicator`/`?q`/`?orgao`/
 * `?page`...) espelham os filtros da tela Jinja; `?q` é o alias JSON de
 * `?search`. Um filtro de órgão fora do escopo do usuário faz o backend
 * devolver `fail(422,'validation')`, que `client.ts` converte em
 * `ApiClientError`.
 *
 * Aceita um `AbortSignal` para cancelar a requisição anterior (busca textual
 * com debounce / troca rápida de filtros), evitando respostas fora de ordem.
 *
 * Exemplo:
 *   const data = await fetchProjects({ status: 'Vigente', q: 'painel' });
 */

import { get, post, del, postForm } from './client';
import { createSwrCache } from './swrCache';
import type { ProjectsListData, ProjectsListQuery } from '$lib/types/projects';

// Ultimo payload bom por chave de filtros (querystring de `buildQuery`). SWR:
// a tela reabre com o dado antigo e revalida em silencio (ver dashboard.ts).
const projectsCache = createSwrCache<ProjectsListData>();

/** Ultima lista carregada para os filtros, ou null (sincrono, 1o render). */
export function peekProjects(query: ProjectsListQuery = {}): ProjectsListData | null {
	return projectsCache.peek(buildQuery(query));
}

/** Resultado da importação de projetos via CSV (`POST /api/projetos/importar-csv`). */
export interface ImportProjectsResult {
	imported_count: number;
}

/**
 * Importa projetos em lote de um CSV (Admin). Envia `multipart/form-data` com o
 * arquivo em `arquivo` e os atributos comuns (`orgao_id`, `status`,
 * `special_project`, `delivery_type`). Sucessor da rota Jinja `/projects/import`.
 */
export function importProjectsCsv(formData: FormData): Promise<ImportProjectsResult> {
	return postForm<ImportProjectsResult>('/api/projetos/importar-csv', formData);
}
import type { Project } from '$lib/types/entities';

/** Monta a querystring a partir dos filtros, omitindo valores vazios/nulos. */
function buildQuery(query: ProjectsListQuery): string {
	const params = new URLSearchParams();
	if (query.status) params.set('status', query.status);
	if (query.prioridade) params.set('prioridade', query.prioridade);
	if (query.atraso) params.set('atraso', query.atraso);
	if (query.special_project) params.set('special_project', query.special_project);
	if (query.delivery_type) params.set('delivery_type', query.delivery_type);
	if (query.abep_indicator) params.set('abep_indicator', query.abep_indicator);
	if (query.objetivo) params.set('objetivo', query.objetivo);
	if (query.q) params.set('q', query.q);
	if (query.orgao !== undefined && query.orgao !== null) {
		params.set('orgao', String(query.orgao));
	}
	if (query.page && query.page > 1) params.set('page', String(query.page));
	const qs = params.toString();
	return qs ? `?${qs}` : '';
}

/**
 * Busca a "Lista de Projetos" do usuário autenticado, respeitando o escopo de
 * órgão server-side. Sem `status` explícito o backend assume "Vigente".
 */
export async function fetchProjects(
	query: ProjectsListQuery = {},
	signal?: AbortSignal
): Promise<ProjectsListData> {
	const qs = buildQuery(query);
	const data = await get<ProjectsListData>(`/api/projetos${qs}`, signal);
	projectsCache.store(qs, data);
	return data;
}

/** Etapa do Quick Create (espelha `etapa_descricao[]`/`etapa_duration[]`). */
export interface CreateProjectStage {
	descricao: string;
	duration: number;
}

/**
 * Payload de criação de projeto (Quick Create). Espelha o form
 * `templates/projects/add_form.html` e o contrato `POST /api/projetos`
 * (routes/api/projects_write.py). Apenas `titulo` e `orgao_id` são
 * obrigatórios; os demais campos são opcionais.
 */
export interface CreateProjectInput {
	titulo: string;
	orgao_id: string | number;
	orgao?: string;
	prioridade?: string;
	objetivo?: string | number | null;
	resultado?: string | number | null;
	indicadores?: (string | number)[];
	observacao?: string;
	special_project?: string;
	sei_processes?: string[];
	short_description?: string;
	delivery_type?: string;
	abep_indicator?: string;
	github_link?: string;
	documentation_link?: string;
	product_link?: string;
	custom_links?: { label: string; url: string }[];
	etapas?: CreateProjectStage[];
	start_date?: string; // YYYY-MM-DD
	template_id?: number | null;
}

/** Sucesso de `POST /api/projetos` (já desempacotado do envelope). */
export interface CreateProjectResult {
	id: number;
	redirect_to: string;
	message: string;
	project: Project;
}

/**
 * Cria um projeto (Quick Create) via `POST /api/projetos`, reusando o pipeline
 * de envelope/CSRF de `client.ts`. Em falha de validação/permissão o backend
 * devolve `{ok:false}` e `client.ts` lança `ApiClientError` (422 validation,
 * 403 forbidden, 500 server) — o chamador exibe a mensagem como flash.
 *
 * Exemplo:
 *   const { redirect_to, message } = await createProject({
 *     titulo: 'Painel X', orgao_id: 12
 *   });
 */
export function createProject(input: CreateProjectInput): Promise<CreateProjectResult> {
	return post<CreateProjectResult>('/api/projetos', input);
}

/** Sucesso de `DELETE /api/projetos/<id>` (já desempacotado do envelope). */
export interface DeleteProjectResult {
	deleted: boolean;
	id: number;
}

/**
 * Exclui um projeto DE VERDADE via `DELETE /api/projetos/<id>`, espelhando a
 * regra do Jinja (`routes/projects/crud.delete_project`): permissão por escopo
 * de órgão (403 fora do escopo), 404 inexistente, exclusão em cascata. Em falha
 * o backend devolve `{ok:false}` e `client.ts` lança `ApiClientError` — o
 * chamador deve manter a linha na UI e exibir a mensagem como flash.
 *
 * Exemplo:
 *   await deleteProject(42); // remove a linha só após sucesso
 */
export function deleteProject(projectId: number): Promise<DeleteProjectResult> {
	return del<DeleteProjectResult>(`/api/projetos/${projectId}`);
}

/** Objetivo EEGD (catálogo `GET /api/catalogos/objetivos`). */
export interface ObjetivoCatalogo {
	id: number;
	descricao: string;
}

/**
 * Catálogo de objetivos EEGD para o select inicial do modal de criação
 * (`GET /api/catalogos/objetivos`, envelope).
 */
export function fetchObjetivosCatalogo(signal?: AbortSignal): Promise<ObjetivoCatalogo[]> {
	return get<ObjetivoCatalogo[]>('/api/catalogos/objetivos', signal);
}

/** Resultado EEGD (legado `GET /api/resultados/<id>`). */
export interface ResultadoCatalogo {
	id: number;
	descricao: string;
}

/** Indicador EEGD (legado `GET /api/indicadores/<id>`). */
export interface IndicadorCatalogo {
	id: number;
	descricao: string;
}

/** Etapa de um modelo (legado `GET /api/templates/<id>`). */
export interface TemplateStage {
	name: string;
	order: number;
	duration: number;
}

/** Modelo de etapas (legado `GET /api/templates`). */
export interface TemplateOption {
	id: number;
	name: string;
	stage_count: number;
	total_duration_days: number;
}

/**
 * Lê uma resposta JSON CRUA (sem envelope) das rotas legadas de catálogo.
 *
 * As rotas `/api/resultados/<id>`, `/api/indicadores/<id>`, `/api/templates`
 * e `/api/templates/<id>` (routes/api/legacy.py) devolvem um ARRAY puro, NÃO o
 * envelope `{ok,data}` — por isso não podem passar pelo `get<T>` de `client.ts`.
 * Mantemos `credentials:'include'` para o cookie de sessão; sem corpo => `[]`.
 */
async function fetchLegacyArray<T>(path: string, signal?: AbortSignal): Promise<T[]> {
	const res = await fetch(path, {
		method: 'GET',
		credentials: 'include',
		headers: { Accept: 'application/json' },
		signal
	});
	if (!res.ok) return [];
	const text = await res.text();
	if (!text) return [];
	const parsed = JSON.parse(text) as unknown;
	return Array.isArray(parsed) ? (parsed as T[]) : [];
}

/** Resultados de um objetivo EEGD (cascata objetivo→resultado). */
export function fetchResultados(
	objetivoId: number | string,
	signal?: AbortSignal
): Promise<ResultadoCatalogo[]> {
	return fetchLegacyArray<ResultadoCatalogo>(`/api/resultados/${objetivoId}`, signal);
}

/** Indicadores de um resultado EEGD (cascata resultado→indicadores). */
export function fetchIndicadores(
	resultadoId: number | string,
	signal?: AbortSignal
): Promise<IndicadorCatalogo[]> {
	return fetchLegacyArray<IndicadorCatalogo>(`/api/indicadores/${resultadoId}`, signal);
}

/** Lista de modelos de etapas disponíveis para importar. */
export function fetchTemplates(signal?: AbortSignal): Promise<TemplateOption[]> {
	return fetchLegacyArray<TemplateOption>('/api/templates', signal);
}

/** Etapas de um modelo (para o preview read-only de importação). */
export function fetchTemplateStages(
	templateId: number | string,
	signal?: AbortSignal
): Promise<TemplateStage[]> {
	return fetchLegacyArray<TemplateStage>(`/api/templates/${templateId}`, signal);
}
