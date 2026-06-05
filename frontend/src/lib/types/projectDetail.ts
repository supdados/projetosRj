/**
 * Tipos da carga do Detalhe de Projeto (Fase 5a) consumidos pela SPA.
 *
 * Espelham os serializers do backend (routes/api/serializers.py:
 * serialize_project_detail / serialize_etapa_detail / serialize_task_card) e o
 * payload montado por routes/api/project_detail.py (_serialize_detail) — a MESMA
 * fonte de verdade da tela Jinja (templates/projects/detail.html,
 * _project_stages_section.html, _stage_tasks_panel.html), respeitando o
 * orgao_scope server-side.
 *
 * Princípios:
 *   - CAMPOS REAIS; sem aliases legados. NUNCA segredos.
 *   - Derivados (datas do projeto, contagens, cascata de datas em dias úteis)
 *     são computados no backend e chegam prontos; o cliente NÃO recalcula.
 *   - Tarefas das etapas são SOMENTE LEITURA na Fase 5a (contagem + lista
 *     simples). Mutação de tarefas/drawer fica para a Fase 5b; reuniões Google
 *     para a Fase 6 (renderizadas read-only quando presentes).
 *
 * O envelope `{ok, data}` é desempacotado por `client.ts`; os tipos abaixo
 * descrevem apenas `data`.
 */

import type { Project } from './entities';
import type { ValueLabelOption, AbepIndicadorOption } from './projects';

/**
 * Projeto no formato "detalhe" (serialize_project_detail). Reusa o card
 * (`Project`) e soma os campos editáveis inline que NÃO estão no card.
 */
export interface ProjectDetail extends Project {
	observacao: string | null;
	sei_process: string | null;
	delivery_type: string | null;
	abep_indicator: string | null;
	github_link: string | null;
	documentation_link: string | null;
	product_link: string | null;
	objetivo_id: number | null;
	resultado_esperado_id: number | null;
	indicadores_ids: number[];
	// Descrições EEGG (somente leitura) — o cliente só tem os IDs.
	objetivo_descricao: string | null;
	resultado_esperado_descricao: string | null;
	indicadores_descricoes: string[];
}

/** Contagem read-only de tarefas por etapa (serialize_etapa_detail.task_count). */
export interface EtapaTaskCount {
	total: number;
	done: number;
}

/**
 * Bloco read-only da reunião Google de uma etapa (Fase 6). Espelha
 * `meeting_payload_block` (services/etapas_dates.py) — a MESMA fonte usada pelos
 * endpoints de criar/editar reunião. NUNCA contém tokens OAuth; `owner_email` é
 * o e-mail já público do evento. `can_*` vêm calculados no backend.
 */
export interface EtapaMeeting {
	time_summary: string;
	title: string | null;
	description: string;
	starts_at: string; // input datetime (YYYY-MM-DDTHH:mm) ou ''
	ends_at: string;
	start_time_display: string;
	end_time_display: string;
	is_all_day: boolean;
	sync_status: string;
	sync_error: string;
	location: string;
	meet_link: string;
	owner_email: string;
	can_manage: boolean;
	can_edit: boolean;
	can_edit_dates: boolean;
}

/**
 * Uma etapa na tela de Detalhe (serialize_etapa_detail). Inclui `iniciada`,
 * `comentarios` e a contagem read-only de tarefas. `is_google_meeting` marca as
 * reuniões Google (Fase 6); quando verdadeiro, `meeting` traz o bloco read-only
 * do evento Google.
 */
export interface EtapaDetail {
	id: number;
	descricao: string | null;
	data_inicio: string | null; // ISO 8601 (YYYY-MM-DD) ou null
	data_fim: string | null; // ISO 8601 (YYYY-MM-DD) ou null
	responsavel: string | null;
	ordem: number | null;
	iniciada: boolean;
	done: boolean;
	comentarios: string | null;
	project_id: number;
	entry_type: string | null;
	is_google_meeting: boolean;
	task_count: EtapaTaskCount;
	/** Presente apenas em etapas-reunião Google (Fase 6). */
	meeting?: EtapaMeeting;
}

/** Derivados read-only do projeto computados no backend (_serialize_detail.derived). */
export interface ProjectDetailDerived {
	data_inicio_projeto: string | null; // ISO 8601
	data_fim_projeto: string | null; // ISO 8601
	total_workflow_etapas: number;
	todas_etapas_concluidas: boolean;
}

/** Opções dos seletores de edição inline (_serialize_detail.options). */
export interface ProjectDetailOptions {
	status: ValueLabelOption[];
	prioridade: ValueLabelOption[];
	special_project: string[];
	delivery_type: string[];
	abep_indicator: AbepIndicadorOption[];
}

/** Permissões da tela de detalhe (_serialize_detail.permissions). */
export interface ProjectDetailPermissions {
	can_edit: boolean;
}

/** Carga completa de GET /api/projetos/<id>/detalhe (já desempacotada). */
export interface ProjectDetailData {
	project: ProjectDetail;
	etapas: EtapaDetail[];
	derived: ProjectDetailDerived;
	options: ProjectDetailOptions;
	permissions: ProjectDetailPermissions;
}

/**
 * Tarefa no formato "card" SOMENTE LEITURA da etapa (serialize_task_card).
 * Fase 5a: contagem + lista simples; sem mutação (Fase 5b cobre drawer/CRUD).
 */
export interface EtapaTask {
	id: number;
	descricao: string;
	status: string;
	responsavel: string | null;
	prioridade: string | null;
	tipo_pedido: string | null;
	ordem: number;
	project_id: number | null;
	etapa_id: number | null;
	created_by_id: number;
	created_at: string | null; // ISO 8601
	is_archived: boolean;
	archived_at: string | null; // ISO 8601
}

/** Resposta de GET /api/projetos/<id>/tarefas-etapa (SOMENTE LEITURA). */
export interface EtapaTasksData {
	etapa_id: number;
	tasks: EtapaTask[];
}

// ── Payloads de mutação (entrada) ────────────────────────────────────────────

/** Corpo de POST /api/projetos/<id>/inline (campos parciais do projeto). */
export interface ProjectInlinePayload {
	[field: string]: string | number | number[] | null;
}

/** Resposta de POST /api/projetos/<id>/inline. */
export interface ProjectInlineResult {
	project: ProjectDetail;
	changed: string[];
}

/** Corpo de POST /api/projetos/<id>/etapas (adicionar etapa). */
export interface EtapaAddPayload {
	descricao: string;
	data_inicio?: string | null; // YYYY-MM-DD
	data_fim?: string | null; // YYYY-MM-DD
	responsavel?: string | null;
	comentarios?: string | null;
	iniciada?: boolean;
	done?: boolean;
	/** Confirma a reativação quando o projeto está Finalizado. */
	reactivate?: boolean;
}

/** Resposta de POST /api/projetos/<id>/etapas. */
export interface EtapaAddResult {
	etapa: EtapaDetail;
	project_status: string;
	project_reactivated: boolean;
}

/** Corpo de POST /api/etapas/<id> (editar etapa regular completa). */
export interface EtapaEditPayload {
	descricao?: string | null;
	responsavel?: string | null;
	comentarios?: string | null;
	data_inicio?: string | null; // YYYY-MM-DD
	data_fim?: string | null; // YYYY-MM-DD
	iniciada?: boolean;
	done?: boolean;
}

/** Resposta com a etapa atualizada (edit/comentario/toggle*). */
export interface EtapaResult {
	etapa: EtapaDetail;
}

/** Resposta de POST /api/etapas/<id>/delete. */
export interface EtapaDeleteResult {
	deleted_id: number;
	project_id: number;
	total_etapas: number;
}

/** Campos aceitos pela edição inline de etapa (update-field). */
export type EtapaInlineField = 'descricao' | 'data_inicio' | 'data_fim' | 'responsavel';

/**
 * `field_update` devolvido por update_regular_field (services/etapas_mutation.py).
 * Ao mudar `data_inicio`, o backend normaliza para dia útil e pode propagar a
 * `data_fim` da própria etapa (`updatedEndDate*`) — o cliente NÃO recalcula.
 */
export interface EtapaFieldUpdate {
	success: boolean;
	newValue: string | null;
	displayValue: string | null;
	daysDiff?: number;
	updatedEndDate?: string;
	updatedEndDateDisplay?: string;
}

/** Resposta de POST /api/etapas/<id>/update-field. */
export interface EtapaFieldUpdateResult {
	field: EtapaInlineField;
	field_update: EtapaFieldUpdate;
	etapa: EtapaDetail;
}

/** Resposta de POST /api/etapas/<id>/comentario. */
export interface EtapaComentarioResult {
	message: string;
	etapa: EtapaDetail;
}

/**
 * Pedido opcional de cascata embutido na reordenação. O backend desloca as
 * etapas após a etapa base em `days_diff` dias úteis (server-side).
 */
export interface CascadeRequest {
	etapa_id: number;
	days_diff: number;
}

/** Resposta de reordenar/cascade — lista de etapas RE-BUSCADA do servidor. */
export interface EtapasResult {
	etapas: EtapaDetail[];
}

/** Corpo de POST /api/projetos/<id>/importar-modelo. */
export interface ImportModelPayload {
	template_id: number;
	start_date: string; // YYYY-MM-DD
}

/** Resposta de POST /api/projetos/<id>/importar-modelo. */
export interface ImportModelResult {
	etapas_criadas: number;
	etapas: EtapaDetail[];
}

/**
 * Linha de modelo de etapas para o ImportModelModal (GET /api/templates,
 * routes/api/legacy.py:get_templates). NÃO é envelope — array cru.
 */
export interface StageTemplateOption {
	id: number;
	name: string;
	stage_count: number;
	total_duration_days: number;
}

/**
 * Resposta de POST /api/projetos/<id>/concluir (envelope desempacotado).
 * `redirect_to` aponta para a rota SPA do detalhe; o front toca o chime +
 * confetes + overlay e navega via router (goto).
 */
export interface ConcludeProjectResult {
	message: string;
	redirect_to: string;
	status: string;
}

/**
 * Corpo de criação/edição de reunião Google de etapa
 * (POST /api/projetos/<id>/reunioes | POST /api/etapas/<id>/reuniao).
 * Espelha o `_event_payload_from_json` do backend.
 */
export interface MeetingPayload {
	title: string;
	description?: string;
	location?: string;
	starts_at?: string; // YYYY-MM-DDTHH:mm
	ends_at?: string;
	is_all_day?: boolean;
	create_conference?: boolean;
}

/**
 * Resposta de criar/editar reunião (envelope desempacotado). `warning != null`
 * quando o sync com o Google falhou (a etapa/evento persistem). `message` é o
 * texto PT pronto para o toast de sucesso.
 */
export interface MeetingMutationResult {
	etapa: EtapaMeetingPayload;
	warning: string | null;
	message: string;
}

/**
 * Payload de etapa devolvido pelos endpoints de reunião — shape do serializer
 * LEGADO (`_serialize_etapa_payload`), distinto de `EtapaDetail`. Após a
 * mutação a página RE-BUSCA o detalhe completo, então só usamos `id`/`meeting`
 * para feedback imediato; os campos restantes existem por compatibilidade.
 */
export interface EtapaMeetingPayload {
	id: number;
	descricao: string | null;
	entry_type: string | null;
	meeting?: EtapaMeeting;
}
