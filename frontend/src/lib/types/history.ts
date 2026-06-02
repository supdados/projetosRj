/**
 * Tipos da carga de Historico de projeto (GET /api/projetos/<id>/historico).
 *
 * Espelha `serialize_project_history_entry` / `serialize_project_card`
 * (routes/api/serializers.py): cada entrada usa os CAMPOS REAIS de
 * `ProjectHistory` (`action_type`, `action_description`, `old_value`,
 * `new_value`, `timestamp`) mais um vinculo minimo do autor (`user`) com apenas
 * `id`/`name`/`username` — NUNCA segredos. O cabecalho do projeto chega no
 * formato "card" (reuso de `Project`). Derivados NAO sao recalculados no
 * cliente.
 */

import type { Project } from './entities';

/** Autor de uma entrada de historico (vinculo minimo; sem segredos). */
export interface HistoryAuthor {
	id: number;
	name: string;
	username: string;
}

/** Uma entrada do historico do projeto (instancia de `ProjectHistory`). */
export interface HistoryEntry {
	id: number;
	project_id: number;
	action_type: string;
	action_description: string | null;
	old_value: string | null;
	new_value: string | null;
	timestamp: string | null; // ISO 8601
	user: HistoryAuthor | null;
}

/** Carga completa da tela de historico (cabecalho + lista de eventos). */
export interface ProjectHistoryData {
	project: Project;
	history: HistoryEntry[];
}
