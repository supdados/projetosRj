/**
 * Tipos da visualização de Órgãos (árvore read-only) do Admin + integração
 * SIORG. A estrutura organizacional é sincronizada do SIORG-RJ; o ProjetosRJ
 * não edita mais unidades. Espelham `serialize_orgao_node`
 * (`routes/api/serializers.py`), a carga de `GET /api/admin/orgaos` e os
 * contratos de `GET /api/admin/siorg/status` / `POST /api/admin/siorg/sync`.
 */

/** Nó recursivo da árvore (serialize_orgao_node). */
export interface OrgaoNode {
	id: number;
	sigla: string | null;
	nome: string | null;
	tipo: string | null;
	tipo_id: number | null;
	pai_id: number | null;
	ordem: number | null;
	ativo: boolean;
	/** Código SIORG; null = unidade local não oficial (ex.: ECENTRAL). */
	codigo_externo: string | null;
	filhos: OrgaoNode[];
}

/** Carga de GET /api/admin/orgaos (árvore de visualização). */
export interface OrgaoTreeData {
	arvore: OrgaoNode[];
	max_depth: number;
	total: number;
}

/** Última sincronização registrada (SiorgSyncLog serializado). */
export interface SiorgSyncInfo {
	id: number;
	status: string;
	iniciado_em: string | null;
	finalizado_em: string | null;
	versao_global: string | null;
	criadas: number;
	atualizadas: number;
	desativadas: number;
	erro: string | null;
	disparado_por_nome: string | null;
}

/** Carga de GET /api/admin/siorg/status. */
export interface SiorgStatusData {
	configurado: boolean;
	ultima_sincronizacao: SiorgSyncInfo | null;
}

/** Carga de POST /api/admin/siorg/sync (200). */
export interface SiorgSyncResult {
	status: 'sucesso';
	criadas: number;
	atualizadas: number;
	desativadas: number;
	versao_global: string | null;
}
