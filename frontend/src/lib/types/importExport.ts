/**
 * Tipos do import/export de projetos: análise prévia do CSV
 * (`POST /api/projetos/importar-csv/analise`) e resultado da importação
 * (`POST /api/projetos/importar-csv`). Os nomes dos campos são os do backend
 * (português), já desempacotados do envelope por `client.ts`.
 */

/** Modo do lote: 1 linha = 1 projeto (`simples`) ou 1 linha = 1 etapa (`com_etapas`). */
export type ImportModo = 'simples' | 'com_etapas';

/** Coluna do CSV com o campo sugerido pelo matching do backend. */
export interface ColunaDetectada {
	indice: number;
	cabecalho: string;
	/** Campo sugerido (`titulo`, `descricao`, ...) ou `null` quando não reconhecida. */
	campo: string | null;
	confianca: 'exato' | 'sinonimo' | 'aproximado' | null;
	/** Primeiro valor não-vazio da coluna (pode ser `''`). */
	amostra: string;
}

/** Campo importável oferecido no select de mapeamento. */
export interface CampoImportacao {
	campo: string;
	rotulo: string;
	obrigatorio: boolean;
}

/** Carga de `POST /api/projetos/importar-csv/analise` (stateless, nada persiste). */
export interface AnaliseImportacao {
	delimitador: string;
	/** Linhas de dados, já sem o cabeçalho. */
	total_linhas: number;
	/** Modo pedido no form — campos e sugestões vêm restritos a ele. */
	modo: ImportModo;
	colunas: ColunaDetectada[];
	campos: CampoImportacao[];
}

/** Linha ajustada na importação: nº na planilha (1 = cabeçalho) e o que caiu no padrão. */
export interface LinhaAjustada {
	linha: number;
	titulo: string;
	motivos: string[];
}

/** Carga de `POST /api/projetos/importar-csv` (contadores do lote). */
export interface ImportProjectsResultV2 {
	imported_count: number;
	/** Linhas descartadas por não terem título. */
	ignored_count: number;
	/** Linhas em que algum valor não reconhecido caiu no padrão do formulário. */
	adjusted_count: number;
	/** Etapas persistidas (no modo simples, nº de etapas default criadas). */
	etapas_criadas: number;
	/** Detalhe das linhas ajustadas, na ordem da planilha. */
	adjusted_rows: LinhaAjustada[];
}
