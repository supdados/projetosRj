/**
 * Saves das seções do CriarProjetoModal v2, aplicados a um projeto JÁ CRIADO
 * (o POST /api/projetos acontece ao fim da fase essencial; o hub só faz update).
 *
 * NENHUM endpoint novo: são wrappers tipados sobre `updateProjectInline`
 * (POST /api/projetos/<id>/inline) e `importStageModel`
 * (POST /api/projetos/<id>/importar-modelo).
 *
 * CADA SEÇÃO É AUTORITATIVA: todas as chaves da seção vão em todo save, porque o
 * backend trata string vazia / lista vazia como "limpar o campo". Omitir uma
 * chave mantém o valor antigo — enviar `''` é o que apaga.
 *
 * Normalizações que o servidor aplica e o caller deve esperar de volta:
 * URL sem scheme ganha `https://`; `380001/000664/2026` vira
 * `SEI-380001/000664/2026`; strings vazias voltam como `null`; `start_date` em
 * fim de semana é empurrado para a segunda-feira seguinte.
 */

import { importStageModel, updateProjectInline } from './projectDetail';
import type {
	ImportModelResult,
	ProjectInlinePayload,
	ProjectInlineResult
} from '$lib/types/projectDetail';

/** Link personalizado do projeto (máx. 3 por projeto — o backend valida). */
export interface CustomLinkInput {
	label: string;
	url: string;
}

/** Passos 1-3 reeditados depois da criação (lápis do hub). */
export interface EssentialsPayload {
	titulo: string;
	short_description: string;
	prioridade: string;
	orgao_id: number;
}

/** Seção 1 do hub. `objetivo_id: null` limpa a cascata inteira. */
export interface GoalsSectionPayload {
	objetivo_id: number | null;
	resultado_esperado_id: number | null;
	indicadores_ids: number[];
	abep_indicator: string;
}

/** Seção 2 do hub. */
export interface DetailsSectionPayload {
	orgao: string;
	delivery_type: string;
	special_project: string;
	sei_processes: string[];
	observacao: string;
}

/** Seção 3 do hub. */
export interface LinksSectionPayload {
	github_link: string;
	documentation_link: string;
	product_link: string;
	custom_links: CustomLinkInput[];
}

type SectionPayload =
	| EssentialsPayload
	| GoalsSectionPayload
	| DetailsSectionPayload
	| LinksSectionPayload;

// Os payloads acima são estruturalmente `ProjectInlinePayload` válidos, mas TS
// não faz widening de tipo fechado para index signature (mesmo cast de
// `saveProjectGoals`); o boundary é seguro porque as chaves espelham 1:1 as
// aceitas por `apply_project_inline_changes`.
function postSection(
	projectId: number,
	payload: SectionPayload,
	signal?: AbortSignal
): Promise<ProjectInlineResult> {
	return updateProjectInline(projectId, payload as unknown as ProjectInlinePayload, signal);
}

/**
 * Reedita os essenciais do projeto criado. O backend NÃO rejeita `titulo` vazio
 * — o guard de `titulo.trim()` no cliente é a única proteção.
 */
export function saveEssentials(
	projectId: number,
	payload: EssentialsPayload,
	signal?: AbortSignal
): Promise<ProjectInlineResult> {
	return postSection(projectId, payload, signal);
}

/**
 * Seção 1 — objetivo → resultado → ≤4 indicadores + indicador ABEP. Erros de
 * cascata voltam como 422 com a mensagem genérica "Erro ao atualizar projeto."
 * (o backend não propaga o motivo específico).
 */
export function saveGoalsSection(
	projectId: number,
	payload: GoalsSectionPayload,
	signal?: AbortSignal
): Promise<ProjectInlineResult> {
	return postSection(projectId, payload, signal);
}

/** Seção 2 — órgão (texto livre), tipo de entrega, projeto especial, SEI, observação. */
export function saveDetailsSection(
	projectId: number,
	payload: DetailsSectionPayload,
	signal?: AbortSignal
): Promise<ProjectInlineResult> {
	return postSection(projectId, payload, signal);
}

/** Seção 3 — links fixos + personalizados (422 se >3 ou URL inválida). */
export function saveLinksSection(
	projectId: number,
	payload: LinksSectionPayload,
	signal?: AbortSignal
): Promise<ProjectInlineResult> {
	return postSection(projectId, payload, signal);
}

/**
 * Seção 4 — aplica o modelo ao projeto já criado (etapas em dias ÚTEIS,
 * calculadas server-side). `startDate` é OBRIGATÓRIO (422 se ausente).
 *
 * ACRESCENTA etapas: a `ordem` continua da última existente, então chamar duas
 * vezes duplica o modelo — o caller precisa travar o reenvio após o sucesso.
 */
export function applyStageTemplate(
	projectId: number,
	templateId: number,
	startDate: string,
	signal?: AbortSignal
): Promise<ImportModelResult> {
	return importStageModel(projectId, { template_id: templateId, start_date: startDate }, signal);
}
