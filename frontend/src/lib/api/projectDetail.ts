/**
 * Acesso tipado aos endpoints do Detalhe de Projeto (Fase 5a).
 *
 * Cada função desempacota o envelope `{ok, data}` via `client.ts` e devolve o
 * estado atualizado para o caller (a página) re-renderizar. As mutações usam
 * `post` (espelhando o Flask, com X-CSRFToken e tratamento de 401 no client).
 *
 * CASCATA DE DATAS É SERVER-SIDE: ao reordenar etapas ou editar uma data, o
 * backend recalcula dias úteis e RE-BUSCA o estado; o front NUNCA reimplementa
 * dias úteis nem recalcula datas — apenas envia o pedido e renderiza a resposta.
 *
 * Contrato S5 de autorização, válido para TODAS as funções deste módulo:
 *   - 404 `not_found`: o projeto/etapa não existe OU o usuário não tem acesso a
 *     ele. Os dois casos devolvem o MESMO corpo (anti-enumeração) e a tela
 *     mostra "não existe ou você não tem acesso", sem revelar qual dos dois.
 *   - 403 `forbidden`: ele VÊ o projeto (rank ≥ leitor) mas não pode ESTA ação —
 *     as leituras (`fetchProjectDetail`, `fetchEtapaTasks`) portanto nunca dão
 *     403, só as mutações (que exigem editor/gestor).
 */

import { get, post } from './client';
import { createSwrCache } from './swrCache';
import type {
	ProjectDetailData,
	ProjectInlinePayload,
	ProjectInlineResult,
	ProjectGoalsSelection,
	EtapaAddPayload,
	EtapaAddResult,
	EtapaEditPayload,
	EtapaResult,
	EtapaDeleteResult,
	EtapaInlineField,
	EtapaFieldUpdateResult,
	EtapaComentarioResult,
	CascadeRequest,
	EtapasResult,
	ImportModelPayload,
	ImportModelResult,
	EtapaTasksData,
	StageTemplateOption,
	ConcludeProjectResult,
	MeetingPayload,
	MeetingMutationResult
} from '$lib/types/projectDetail';

// Ultimo payload bom por id de projeto. SWR: a tela reabre com o dado antigo e
// revalida em silencio (ver dashboard.ts). Mutations do detalhe (inline/etapas/
// reunioes) RE-BUSCAM o estado via seus proprios endpoints — nao passam por
// este cache; a proxima chamada a fetchProjectDetail e que atualiza a entrada.
const projectDetailCache = createSwrCache<ProjectDetailData>();

/** Ultimo detalhe carregado do projeto, ou null (sincrono, para o 1o render). */
export function peekProjectDetail(projectId: number): ProjectDetailData | null {
	return projectDetailCache.peek(String(projectId));
}

/** Carrega o payload completo do Detalhe de Projeto. */
export async function fetchProjectDetail(
	projectId: number,
	signal?: AbortSignal
): Promise<ProjectDetailData> {
	const data = await get<ProjectDetailData>(`/api/projetos/${projectId}/detalhe`, signal);
	projectDetailCache.store(String(projectId), data);
	return data;
}

/** Lista SOMENTE LEITURA as tarefas de uma etapa (Fase 5a). */
export function fetchEtapaTasks(
	projectId: number,
	etapaId: number,
	signal?: AbortSignal
): Promise<EtapaTasksData> {
	return get<EtapaTasksData>(
		`/api/projetos/${projectId}/tarefas-etapa?etapa_id=${etapaId}`,
		signal
	);
}

/** Edita campos do projeto inline; devolve o projeto atualizado + `changed`. */
export function updateProjectInline(
	projectId: number,
	changes: ProjectInlinePayload,
	signal?: AbortSignal
): Promise<ProjectInlineResult> {
	return post<ProjectInlineResult>(`/api/projetos/${projectId}/inline`, changes, signal);
}

/**
 * Salva a cascata EEGG (objetivo → resultado → ≤4 indicadores) como UNIDADE
 * coesa, reusando `updateProjectInline` (mesmo endpoint /inline) — não há rota
 * dedicada. O backend valida a cascata (`normalize_goal_selection`) e devolve o
 * projeto RE-SERIALIZADO com as descrições EEGG atualizadas; a página
 * re-renderiza com `result.project`. `objetivo_id === null` limpa tudo.
 *
 * Exemplo:
 *   const { project } = await saveProjectGoals(42, {
 *     objetivo_id: 1, resultado_esperado_id: 3, indicadores_ids: [7, 9]
 *   });
 */
export function saveProjectGoals(
	projectId: number,
	selection: ProjectGoalsSelection,
	signal?: AbortSignal
): Promise<ProjectInlineResult> {
	// `ProjectGoalsSelection` é estruturalmente um `ProjectInlinePayload` válido
	// (chaves string → number | number[] | null), mas TS não widen um tipo
	// fechado para a index signature; o cast é seguro no boundary.
	return updateProjectInline(projectId, selection as unknown as ProjectInlinePayload, signal);
}

/**
 * Catálogo de metas EEGG reexportado de `$lib/api/projects` para que o
 * editor inline da cascata (EeggInlineEditor) importe tudo de um único módulo.
 * São EXATAMENTE os mesmos endpoints/funções usados pelo CriarProjetoModal:
 *   - fetchObjetivosCatalogo() → GET /api/catalogos/objetivos (envelope)
 *   - fetchResultados(objetivoId) → GET /api/resultados/<id> (array cru)
 *   - fetchIndicadores(resultadoId) → GET /api/indicadores/<id> (array cru)
 * NÃO há reimplementação aqui — apenas reexport, para não divergir do modal.
 */
export {
	fetchObjetivosCatalogo,
	fetchResultados,
	fetchIndicadores
} from './projects';
export type {
	ObjetivoCatalogo,
	ResultadoCatalogo,
	IndicadorCatalogo
} from './projects';

/** Adiciona uma etapa ao projeto; devolve a etapa criada e o status do projeto. */
export function addEtapa(
	projectId: number,
	payload: EtapaAddPayload,
	signal?: AbortSignal
): Promise<EtapaAddResult> {
	return post<EtapaAddResult>(`/api/projetos/${projectId}/etapas`, payload, signal);
}

/** Edita uma etapa regular (completa); devolve a etapa atualizada. */
export function editEtapa(
	etapaId: number,
	payload: EtapaEditPayload,
	signal?: AbortSignal
): Promise<EtapaResult> {
	return post<EtapaResult>(`/api/etapas/${etapaId}`, payload, signal);
}

/** Exclui uma etapa regular; devolve o total de etapas do projeto. */
export function deleteEtapa(
	etapaId: number,
	signal?: AbortSignal
): Promise<EtapaDeleteResult> {
	return post<EtapaDeleteResult>(`/api/etapas/${etapaId}/delete`, undefined, signal);
}

/**
 * Edita um campo inline da etapa. Ao mudar `data_inicio`, o backend normaliza
 * para dia útil e pode propagar a `data_fim` (server-side); a resposta traz a
 * etapa RE-BUSCADA e o `field_update`. O front NÃO recalcula datas.
 */
export function updateEtapaField(
	etapaId: number,
	field: EtapaInlineField,
	value: string | null,
	signal?: AbortSignal
): Promise<EtapaFieldUpdateResult> {
	return post<EtapaFieldUpdateResult>(
		`/api/etapas/${etapaId}/update-field`,
		{ field, value },
		signal
	);
}

/** Salva/atualiza o comentário da etapa; devolve a etapa atualizada. */
export function saveEtapaComentario(
	etapaId: number,
	comentario: string,
	signal?: AbortSignal
): Promise<EtapaComentarioResult> {
	return post<EtapaComentarioResult>(
		`/api/etapas/${etapaId}/comentario`,
		{ comentario },
		signal
	);
}

/** Alterna `iniciada` da etapa; devolve a etapa atualizada. */
export function toggleEtapaIniciada(
	etapaId: number,
	signal?: AbortSignal
): Promise<EtapaResult> {
	return post<EtapaResult>(`/api/etapas/${etapaId}/toggle-iniciada`, undefined, signal);
}

/** Alterna `done` (concluída) da etapa; devolve a etapa atualizada. */
export function toggleEtapaDone(
	etapaId: number,
	signal?: AbortSignal
): Promise<EtapaResult> {
	return post<EtapaResult>(`/api/etapas/${etapaId}/toggle`, undefined, signal);
}

/**
 * Persiste a nova ordem das etapas e, opcionalmente, dispara a cascata de datas
 * (server-side). RE-BUSCA e devolve as etapas atualizadas para re-renderização.
 *
 * @param etapaIds IDs das etapas na ordem desejada.
 * @param cascade  Pedido opcional de cascata (`etapa_id` base + `days_diff`).
 */
export function reorderEtapas(
	projectId: number,
	etapaIds: number[],
	cascade?: CascadeRequest,
	signal?: AbortSignal
): Promise<EtapasResult> {
	const body: Record<string, unknown> = { etapa_ids: etapaIds };
	if (cascade) {
		body.etapa_id = cascade.etapa_id;
		body.days_diff = cascade.days_diff;
	}
	return post<EtapasResult>(`/api/projetos/${projectId}/etapas/reordenar`, body, signal);
}

/**
 * Recalcula datas em cascata (server-side): desloca as etapas após a etapa base
 * em `days_diff` dias úteis. RE-BUSCA e devolve as etapas atualizadas.
 */
export function cascadeDates(
	projectId: number,
	cascade: CascadeRequest,
	signal?: AbortSignal
): Promise<EtapasResult> {
	return post<EtapasResult>(`/api/projetos/${projectId}/cascade`, cascade, signal);
}

/** Aplica um modelo de etapas ao projeto; devolve as etapas RE-BUSCADAS. */
export function importStageModel(
	projectId: number,
	payload: ImportModelPayload,
	signal?: AbortSignal
): Promise<ImportModelResult> {
	return post<ImportModelResult>(
		`/api/projetos/${projectId}/importar-modelo`,
		payload,
		signal
	);
}

/**
 * Conclui o projeto (POST /api/projetos/<id>/concluir). Sem corpo. Em sucesso
 * devolve a mensagem de celebração e o `redirect_to` da rota SPA do detalhe; o
 * front toca o chime + confetes + overlay e navega via router. Erros sobem como
 * `ApiClientError`: 400/422 (regra de negócio), 403 (vê o projeto mas não é
 * gestor), 404 (não existe ou sem acesso).
 */
export function concludeProject(
	projectId: number,
	signal?: AbortSignal
): Promise<ConcludeProjectResult> {
	return post<ConcludeProjectResult>(
		`/api/projetos/${projectId}/concluir`,
		undefined,
		signal
	);
}

/**
 * Cria uma reunião Google de etapa (POST /api/projetos/<id>/reunioes). Devolve
 * a etapa (shape legado com `meeting`), `warning` (sync Google falhou) e a
 * `message` de sucesso. A página RE-BUSCA o detalhe após o sucesso.
 */
export function createStageMeeting(
	projectId: number,
	payload: MeetingPayload,
	signal?: AbortSignal
): Promise<MeetingMutationResult> {
	return post<MeetingMutationResult>(
		`/api/projetos/${projectId}/reunioes`,
		payload,
		signal
	);
}

/**
 * Edita uma reunião Google de etapa (POST /api/etapas/<id>/reuniao). Mesmo
 * shape de retorno de `createStageMeeting`.
 */
export function updateStageMeeting(
	etapaId: number,
	payload: MeetingPayload,
	signal?: AbortSignal
): Promise<MeetingMutationResult> {
	return post<MeetingMutationResult>(`/api/etapas/${etapaId}/reuniao`, payload, signal);
}

/**
 * Exclui uma reunião Google de etapa (POST /api/etapas/<id>/reuniao/excluir).
 * Sem corpo. Só a conta Google dona pode excluir — 403 mesmo para quem tem rank
 * de escrita no projeto; falha remota ABORTA (502). Em sucesso devolve o total
 * de etapas para recalcular o botão concluir.
 */
export function deleteStageMeeting(
	etapaId: number,
	signal?: AbortSignal
): Promise<EtapaDeleteResult & { message: string }> {
	return post<EtapaDeleteResult & { message: string }>(
		`/api/etapas/${etapaId}/reuniao/excluir`,
		undefined,
		signal
	);
}

/**
 * Lista os modelos de etapas para o ImportModelModal.
 *
 * Usa o endpoint enveloped GET /api/etapas/templates (envelope canônico
 * `{ok, data}`) via `client.get`, que desempacota `data` e trata 401/CSRF.
 */
export async function fetchStageTemplates(
	signal?: AbortSignal
): Promise<StageTemplateOption[]> {
	const data = await get<StageTemplateOption[]>('/api/etapas/templates', signal);
	return Array.isArray(data) ? data : [];
}
