/**
 * Regras de APRESENTAÇÃO da coleção compartilhada com aceite: rótulos de papel
 * e de status, textos das confirmações (revogar, rebaixar, sair) e a pilha de
 * destinatários do card. Nada aqui decide acesso — status, `pode_remover` e a
 * lista de quem vê chegam prontos do backend; este módulo só os põe em texto,
 * para o modal, o card e a página interna dizerem a MESMA coisa.
 *
 * Exemplo:
 *   const { rotulo, tom } = rotuloStatusConvite('pendente'); // 'Pendente', 'warning'
 *   const texto = textoDeRevogacao(share, 'Maria', dados.itens_orfaos);
 */

import type {
	ColecaoShare,
	ConviteColecao,
	DestinatarioColecao,
	PapelColecao,
	PapelCompartilhamento,
	ProjetoColecaoRow,
	ResumoShareOrgao,
	StatusConvite,
	StatusDestinatario
} from '$lib/types/collections';

/** Tinta do marcador de status (mapeada para classes estáticas no componente). */
export type TomStatusShare = 'warning' | 'success' | 'danger' | 'neutral';

export interface RotuloStatusShare {
	rotulo: string;
	tom: TomStatusShare;
}

/** Texto de um `confirmAction` (título-pergunta, consequência e verbo do botão). */
export interface TextoConfirmacaoColecao {
	title: string;
	description: string;
	confirmLabel: string;
}

/** Revogação: a pergunta + o recibo que a tela mostra depois de confirmada. */
export interface TextoDeRevogacao extends TextoConfirmacaoColecao {
	sucesso: string;
}

/** Opção de papel concedível, com a frase que explica o que ele permite. */
export interface OpcaoPapelColecao {
	id: PapelCompartilhamento;
	label: string;
	hint: string;
}

/** Papéis do compartilhamento, na ordem do seletor (o texto é o da spec). */
export const PAPEIS_COMPARTILHAMENTO: readonly OpcaoPapelColecao[] = [
	{ id: 'viewer', label: 'Leitor', hint: 'Vê a coleção e lê os projetos' },
	{
		id: 'editor',
		label: 'Editor',
		hint: 'Também inclui projetos, remove os que incluiu e edita os projetos (até o nível de quem os incluiu)'
	}
];

const PAPEL_LABEL: Record<PapelColecao, string> = {
	dono: 'Dono',
	viewer: 'Leitor',
	editor: 'Editor'
};

const STATUS_CONVITE: Record<StatusConvite, RotuloStatusShare> = {
	pendente: { rotulo: 'Pendente', tom: 'warning' },
	aceito: { rotulo: 'Aceito', tom: 'success' },
	legado: { rotulo: 'Com acesso', tom: 'neutral' },
	recusado: { rotulo: 'Recusou', tom: 'danger' },
	saiu: { rotulo: 'Saiu', tom: 'neutral' }
};

/** `'Leitor'`/`'Editor'`/`'Dono'`; papel desconhecido (drift) cai em Leitor. */
export function papelColecaoLabel(papel: PapelColecao): string {
	return PAPEL_LABEL[papel] ?? PAPEL_LABEL.viewer;
}

/** Nome de exibição do destinatário de um share: pessoa pelo nome, área pela sigla. */
export function nomeDoShare(share: Pick<ColecaoShare, 'user' | 'orgao'>): string {
	if (share.user) return share.user.nome;
	return share.orgao ? share.orgao.sigla || share.orgao.nome : 'Destinatário';
}

/** Rótulo + tinta da situação de UMA pessoa num share. */
export function rotuloStatusConvite(status: StatusConvite): RotuloStatusShare {
	return STATUS_CONVITE[status] ?? STATUS_CONVITE.pendente;
}

function contagem(n: number, singular: string, plural: string): string {
	return `${n} ${n === 1 ? singular : plural}`;
}

/**
 * Marcador ao lado do papel na lista do dono: status da pessoa, ou "N pendentes"
 * num share de área (o resto do agregado vai na linha de detalhe). `null` = sem
 * marcador.
 */
export function marcadorDoShare(share: ColecaoShare): RotuloStatusShare | null {
	if (share.user_id !== null) return share.status ? rotuloStatusConvite(share.status) : null;
	const pendentes = share.resumo?.pendentes ?? 0;
	if (pendentes === 0) return null;
	return { rotulo: contagem(pendentes, 'pendente', 'pendentes'), tom: 'warning' };
}

/** Linha de detalhe de um share de área: "3 de 12 com acesso · 1 recusou". */
export function detalheDoShareDeArea(resumo: ResumoShareOrgao): string {
	if (resumo.membros === 0) return 'Nenhuma pessoa lotada na área';
	const partes = [`${resumo.aceitos} de ${resumo.membros} com acesso`];
	if (resumo.recusados > 0) partes.push(`${resumo.recusados} ${resumo.recusados === 1 ? 'recusou' : 'recusaram'}`);
	if (resumo.sairam > 0) partes.push(`${resumo.sairam} ${resumo.sairam === 1 ? 'saiu' : 'saíram'}`);
	return partes.join(' · ');
}

/** "Reenviar" só faz sentido onde alguém recusou ou saiu (senão o backend dá 422). */
export function podeReenviarShare(share: ColecaoShare): boolean {
	if (share.user_id !== null) return share.status === 'recusado' || share.status === 'saiu';
	const resumo = share.resumo;
	return resumo !== null && resumo.recusados + resumo.sairam > 0;
}

/** Ninguém do share tem acesso ainda (pessoa pendente ou área sem nenhum aceite). */
function shareSemAcesso(share: ColecaoShare): boolean {
	if (share.user_id !== null) return share.status !== 'aceito' && share.status !== 'legado';
	return (share.resumo?.aceitos ?? 0) === 0;
}

/** " 2 projetos incluídos por Maria saem da coleção." — vazio quando nada sai. */
export function fraseDeItensQueSaem(itens: number, porQuem: string): string {
	if (itens <= 0) return '';
	const projetos = itens === 1 ? '1 projeto incluído' : `${itens} projetos incluídos`;
	return ` ${projetos} por ${porQuem} ${itens === 1 ? 'sai' : 'saem'} da coleção.`;
}

/**
 * " 2 projetos de quem já não é editor também saem." — itens ÓRFÃOS
 * (`itens_orfaos`): quem os incluiu já perdeu o papel editor, e qualquer poda
 * (revogar, sair, recusar, rebaixar) os tira, seja qual for o share mexido.
 * `tambem` = já há uma frase de itens antes; sem ela, a frase se sustenta só.
 */
export function fraseDeItensOrfaos(itens: number, tambem: boolean): string {
	if (itens <= 0) return '';
	const projetos = itens === 1 ? '1 projeto' : `${itens} projetos`;
	const verbo = itens === 1 ? 'sai' : 'saem';
	return tambem
		? ` ${projetos} de quem já não é editor também ${verbo}.`
		: ` ${projetos} de quem já não é editor ${verbo} da coleção.`;
}

/** Tudo o que sai numa poda: os itens do alvo e, em seguida, os órfãos. */
function fraseDoQueSai(itensDoAlvo: number, porQuem: string, itensOrfaos: number): string {
	return (
		fraseDeItensQueSaem(itensDoAlvo, porQuem) + fraseDeItensOrfaos(itensOrfaos, itensDoAlvo > 0)
	);
}

/**
 * Confirmação de revogar um share. Quem ainda não tem acesso perde só o
 * convite; quem tem perde o que vê SÓ pela coleção (o que vê pela própria área
 * continua) e os projetos que incluiu saem junto — e, como toda poda, os
 * órfãos (`itensOrfaos`, contados à parte pelo backend) também.
 */
export function textoDeRevogacao(
	share: ColecaoShare,
	nome: string,
	itensOrfaos: number = 0
): TextoDeRevogacao {
	const ehArea = share.user_id === null;
	const porQuem = ehArea ? 'pessoas da área' : nome;
	const itens = fraseDoQueSai(share.itens_incluidos, porQuem, itensOrfaos);
	if (shareSemAcesso(share)) {
		return {
			title: `Cancelar o convite de ${nome}?`,
			description: `O convite deixa de valer.${itens} Dá para convidar de novo depois.`,
			confirmLabel: 'Cancelar convite',
			sucesso: `Convite de ${nome} cancelado.`
		};
	}
	const quem = ehArea ? 'Quem é da área' : nome;
	return {
		title: `Revogar o acesso de ${nome}?`,
		description: `${quem} deixa de ver a coleção e os projetos que só vê por ela; o que vê pela própria área continua.${itens}`,
		confirmLabel: 'Revogar acesso',
		sucesso: `Acesso de ${nome} revogado.`
	};
}

/**
 * Confirmação de rebaixar editor → leitor; `null` só quando NADA sai da
 * coleção (nem itens do alvo nem órfãos) — aí a troca de papel é silenciosa.
 */
export function textoDeRebaixamento(
	share: ColecaoShare,
	nome: string,
	itensOrfaos: number = 0
): TextoConfirmacaoColecao | null {
	if (share.itens_incluidos <= 0 && itensOrfaos <= 0) return null;
	const porQuem = share.user_id === null ? 'pessoas da área' : nome;
	return {
		title: `Mudar o papel de ${nome} para Leitor?`,
		description: `A leitura da coleção continua.${fraseDoQueSai(share.itens_incluidos, porQuem, itensOrfaos)}`,
		confirmLabel: 'Mudar para Leitor'
	};
}

/** Confirmação de "Sair da coleção" com a contagem do que sai junto (meus + órfãos). */
export function textoDeSaida(
	nomeColecao: string,
	itensMeus: number,
	itensOrfaos: number = 0
): TextoConfirmacaoColecao {
	return {
		title: `Sair da coleção "${nomeColecao}"?`,
		description: `Você deixa de ver a coleção e os projetos que só vê por ela.${fraseDoQueSai(itensMeus, 'você', itensOrfaos)} Só quem convidou pode convidar você de novo.`,
		confirmLabel: 'Sair da coleção'
	};
}

const PERMISSAO_DO_CONVITE: Record<PapelCompartilhamento, string> = {
	viewer: 'Você vê a coleção e lê os projetos.',
	editor:
		'Você vê a coleção, inclui projetos, remove os que incluiu e edita os projetos (até o nível de quem os incluiu).'
};

/**
 * O que o papel do convite permite, em frase que se sustenta sozinha (o
 * `hint` do seletor começa em "Também…", que só faz sentido ao lado do Leitor).
 */
export function permissaoDoConvite(papel: PapelCompartilhamento): string {
	return PERMISSAO_DO_CONVITE[papel] ?? PERMISSAO_DO_CONVITE.viewer;
}

/**
 * "Maria convidou você com o papel de Editor" — linha de procedência do
 * convite. O papel vai como NOME do papel (sem flexão de gênero do destinatário).
 */
export function procedenciaDoConvite(convite: Pick<ConviteColecao, 'owner' | 'papel'>): string {
	const quem = convite.owner?.nome ?? 'Alguém';
	return `${quem} convidou você com o papel de ${papelColecaoLabel(convite.papel)}`;
}

const RANK_DO_PAPEL: Record<PapelColecao, number> = { viewer: 1, editor: 2, dono: 3 };

/**
 * Banner do convite que chega a quem JÁ participa (ex.: era Leitor e a área
 * recebeu Editor): diz o papel de hoje e que recusar não tira o acesso.
 */
export function textoDoConviteExtra(
	convite: Pick<ConviteColecao, 'owner' | 'papel'>,
	papelAtual: PapelColecao
): { title: string; description: string } {
	const atual = papelColecaoLabel(papelAtual);
	const sobe = (RANK_DO_PAPEL[convite.papel] ?? 0) > (RANK_DO_PAPEL[papelAtual] ?? 0);
	return {
		title: procedenciaDoConvite(convite),
		description: sobe
			? `Seu papel atual é ${atual}: aceite para passar a ${papelColecaoLabel(convite.papel)}. Recusar mantém o acesso que você já tem.`
			: `Aceitar ou recusar não muda o seu papel atual (${atual}).`
	};
}

/** Pilha do card: os avatares a desenhar e quantos ficam no "+N". */
export interface PilhaDestinatarios {
	visiveis: DestinatarioColecao[];
	excedente: number;
}

/**
 * Corta a lista em `limite` avatares; o "+N" vem do TOTAL do servidor (a lista
 * já chega cortada em 5, então não dá para contar os escondidos no cliente).
 */
export function pilhaDestinatarios(
	destinatarios: readonly DestinatarioColecao[],
	total: number,
	limite = 5
): PilhaDestinatarios {
	const visiveis = destinatarios.slice(0, limite);
	return { visiveis, excedente: Math.max(0, total - visiveis.length) };
}

const STATUS_DESTINATARIO: Record<StatusDestinatario, string> = {
	dono: 'Dono',
	pendente: 'Pendente',
	aceito: '',
	legado: '',
	recusado: 'Recusou',
	saiu: 'Saiu'
};

/** Tooltip do avatar: "Maria · Editor", "SEPLAG · Pendente", "João · Dono". */
export function rotuloDestinatario(destinatario: DestinatarioColecao): string {
	const nome =
		destinatario.tipo === 'orgao' && destinatario.sigla
			? `${destinatario.sigla} (${destinatario.nome})`
			: destinatario.nome;
	const situacao = STATUS_DESTINATARIO[destinatario.status] || papelColecaoLabel(destinatario.papel);
	return `${nome} · ${situacao}`;
}

/** Sem acesso hoje (convite em aberto, recusado ou saiu) — avatar esmaecido no card do dono. */
export function destinatarioSemAcesso(destinatario: DestinatarioColecao): boolean {
	return (
		destinatario.status === 'pendente' ||
		destinatario.status === 'recusado' ||
		destinatario.status === 'saiu'
	);
}

/**
 * Chip "Incluído por X" de uma linha da página interna; `null` = item do dono
 * (o caso comum não ganha chip) ou legado sem autoria.
 */
export function rotuloIncluidoPor(
	row: Pick<ProjetoColecaoRow, 'adicionado_por'>,
	ids: { meuId: number | null; donoId: number | null }
): string | null {
	const incluidor = row.adicionado_por;
	if (!incluidor || incluidor.id === ids.donoId) return null;
	if (incluidor.id === ids.meuId) return 'Incluído por você';
	return `Incluído por ${incluidor.name}`;
}
