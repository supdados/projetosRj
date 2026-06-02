/**
 * Tipos do CRUD de Modelos de Etapas (Admin) consumido pela SPA.
 *
 * Espelham os serializers do backend (routes/api/serializers.py:
 * `serialize_template_row`, `serialize_template_detail`,
 * `serialize_template_stage_item`) e os envelopes de
 * `routes/api/admin_templates.py` — a MESMA fonte de verdade das rotas Jinja
 * (`templates/admin/template_list.html` / `template_form.html`).
 *
 * Datas em ISO 8601 (ou `null`). NÃO há `created_by_id`/`updated_by_id`
 * expostos — apenas `editor_name`. As métricas agregadas
 * (`usage_count`/`stage_count`/`total_duration`) chegam JÁ calculadas no
 * backend; o cliente NÃO recalcula.
 */

/** Etapa de um modelo (serialize_template_stage_item). */
export interface TemplateStage {
	id: number;
	name: string;
	duration_days: number;
	order: number;
}

/** Linha da lista de modelos (serialize_template_row). */
export interface TemplateRow {
	id: number;
	name: string;
	description: string | null;
	/** Iniciais derivadas do nome (avatar), calculadas no backend. */
	initials: string;
	stage_count: number;
	total_duration: number;
	/**
	 * Pares `[altura_px, duracao_dias]` (serialize_template_row -> _silhouette_bars)
	 * que a coluna Silhueta renderiza como mini-gráfico de barras.
	 */
	silhouette: Array<[number, number]>;
	usage_count: number;
	updated_at: string | null; // ISO 8601
	/** Tempo relativo em pt-BR ("há 2 dias"), pré-formatado no backend. */
	updated_relative: string | null;
	editor_name: string | null;
	/** True quando o modelo foi criado recentemente. */
	is_new: boolean;
}

/** Modelo completo com etapas (serialize_template_detail). */
export interface TemplateDetail {
	id: number;
	name: string;
	description: string | null;
	stage_count: number;
	total_duration: number;
	created_at: string | null; // ISO 8601
	updated_at: string | null; // ISO 8601
	editor_name: string | null;
	stages: TemplateStage[];
}

/** Chave de ordenação aceita por `?order=` (espelha `ORDER_OPTIONS`). */
export type TemplateOrder =
	| 'mais_usados'
	| 'nome'
	| 'mais_etapas'
	| 'maior_duracao'
	| 'edicao_recente';

/** Filtros aceitos pela listagem (espelham os query params). */
export interface TemplateListQuery {
	q?: string;
	order?: TemplateOrder;
	page?: number;
}

/** Metadados de paginação devolvidos em `meta` por GET /api/admin/templates. */
export interface TemplateListMeta {
	page: number;
	per_page: number;
	total: number;
	total_pages: number;
	order: TemplateOrder;
	q: string;
}

/** Carga + meta da listagem (já desempacotada do envelope). */
export interface TemplateListResult {
	templates: TemplateRow[];
	order_options: TemplateOrder[];
	meta: TemplateListMeta;
}

/** Carga de GET /api/admin/templates/<id> (form de edição). */
export interface TemplateDetailResult {
	template: TemplateDetail;
	usage_count: number;
}

/** Etapa enviada ao criar/editar (sem `id`/`order` — o backend recalcula). */
export interface TemplateStageInput {
	name: string;
	duration_days: number;
}

/** Payload de criação/edição de modelo (JSON com `stages`). */
export interface TemplatePayload {
	name: string;
	description?: string | null;
	stages: TemplateStageInput[];
}
