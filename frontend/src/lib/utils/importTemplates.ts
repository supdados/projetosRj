/**
 * Modelos de CSV da importação de projetos (um por modo), com os MESMOS
 * cabeçalhos que o export gera — garantia de round-trip com os sinônimos do
 * backend (`services/import_columns.py`). Delimitador `;`, CRLF e BOM para o
 * Excel pt-BR abrir com acentos corretos.
 */
import type { ImportModo } from '$lib/types/importExport';

const BOM = '\uFEFF';

const SIMPLES_HEADERS: readonly string[] = [
	'Título',
	'Descrição',
	'Status',
	'Prioridade',
	'Tipo de entrega',
	'Projeto especial',
	'Área responsável',
	'Órgão',
	'Observação',
	'Processos SEI',
	'Data de início',
	'Data de fim'
];

const COM_ETAPAS_HEADERS: readonly string[] = [
	'Ref Projeto',
	'Título',
	'Descrição',
	'Status',
	'Prioridade',
	'Tipo de entrega',
	'Projeto especial',
	'Área responsável',
	'Órgão',
	'Observação',
	'Processos SEI',
	'Etapa',
	'Etapa Data de início',
	'Etapa Data de fim',
	'Etapa Responsável',
	'Etapa Situação',
	'Etapa Comentários'
];

const SIMPLES_EXEMPLO: readonly (readonly string[])[] = [
	[
		'Modernização do portal de serviços',
		'Nova versão do portal com foco em acessibilidade',
		'Vigente',
		'Alta',
		'',
		'',
		'SEFAZ',
		'Secretaria de Estado de Fazenda',
		'',
		'SEI-150001/000123/2026',
		'01/02/2026',
		'30/06/2026'
	]
];

// Linhas do mesmo projeto ficam contíguas; os campos de projeto valem na 1ª linha da ref.
const COM_ETAPAS_EXEMPLO: readonly (readonly string[])[] = [
	[
		'P1',
		'Modernização do portal de serviços',
		'Nova versão do portal com foco em acessibilidade',
		'Vigente',
		'Alta',
		'',
		'',
		'SEFAZ',
		'Secretaria de Estado de Fazenda',
		'',
		'SEI-150001/000123/2026',
		'Levantamento de requisitos',
		'01/02/2026',
		'28/02/2026',
		'SEFAZ',
		'Concluída',
		'Entrevistas com as áreas'
	],
	['P1', '', '', '', '', '', '', '', '', '', '', 'Desenvolvimento', '01/03/2026', '31/05/2026', 'SEFAZ', 'Em andamento', ''],
	['P1', '', '', '', '', '', '', '', '', '', '', 'Homologação', '01/06/2026', '30/06/2026', '', '', ''],
	[
		'P2',
		'Central de atendimento ao cidadão',
		'',
		'Vigente',
		'Média',
		'',
		'',
		'CASACIVIL',
		'Casa Civil',
		'',
		'',
		'Plano de implantação',
		'15/02/2026',
		'15/03/2026',
		'CASACIVIL',
		'',
		''
	],
	['P2', '', '', '', '', '', '', '', '', '', '', 'Contratação', '16/03/2026', '30/04/2026', '', '', '']
];

function csvCell(valor: string): string {
	if (!/[";\r\n]/.test(valor)) return valor;
	return `"${valor.replaceAll('"', '""')}"`;
}

/** CSV completo do modelo do `modo`, pronto para virar arquivo. */
export function buildImportTemplateCsv(modo: ImportModo): string {
	const headers = modo === 'com_etapas' ? COM_ETAPAS_HEADERS : SIMPLES_HEADERS;
	const exemplos = modo === 'com_etapas' ? COM_ETAPAS_EXEMPLO : SIMPLES_EXEMPLO;
	const registros = [headers, ...exemplos].map((linha) => linha.map(csvCell).join(';'));
	return BOM + registros.join('\r\n') + '\r\n';
}

/** Dispara o download do modelo no navegador via Blob. */
export function downloadImportTemplate(modo: ImportModo): void {
	const nome =
		modo === 'com_etapas'
			? 'modelo-importacao-projetos-com-etapas.csv'
			: 'modelo-importacao-projetos.csv';
	const blob = new Blob([buildImportTemplateCsv(modo)], { type: 'text/csv;charset=utf-8' });
	const url = URL.createObjectURL(blob);
	const link = document.createElement('a');
	link.href = url;
	link.download = nome;
	document.body.appendChild(link);
	link.click();
	link.remove();
	URL.revokeObjectURL(url);
}
