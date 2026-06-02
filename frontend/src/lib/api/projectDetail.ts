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
 * ADIADO: tarefas das etapas são SOMENTE LEITURA aqui (Fase 5b cobre o CRUD);
 * reuniões Google ficam para a Fase 6.
 */

import { get, post } from './client';
import type {
	ProjectDetailData,
	ProjectInlinePayload,
	ProjectInlineResult,
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

/** Carrega o payload completo do Detalhe de Projeto. */
export function fetchProjectDetail(
	projectId: number,
	signal?: AbortSignal
): Promise<ProjectDetailData> {
	return get<ProjectDetailData>(`/api/projetos/${projectId}/detalhe`, signal);
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
 * front toca o chime + confetes + overlay e navega via router. Erros (403/400)
 * sobem como `ApiClientError` com a mensagem do envelope.
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
 * Sem corpo. Só a conta Google dona pode excluir (403); falha remota ABORTA
 * (502). Em sucesso devolve o total de etapas para recalcular o botão concluir.
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
