/**
 * Tipos do import/export de projetos: análise prévia do CSV
 * (`POST /api/projetos/importar-csv/analise`) e resultado da importação
 * (`POST /api/projetos/importar-csv`). Os nomes dos campos são os do backend
 * (português), já desempacotados do envelope por `client.ts`.
 */

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
	colunas: ColunaDetectada[];
	campos: CampoImportacao[];
}

/** Carga de `POST /api/projetos/importar-csv` (contadores do lote). */
export interface ImportProjectsResultV2 {
	imported_count: number;
	/** Linhas descartadas por não terem título. */
	ignored_count: number;
	/** Linhas em que algum valor não reconhecido caiu no padrão do formulário. */
	adjusted_count: number;
}
