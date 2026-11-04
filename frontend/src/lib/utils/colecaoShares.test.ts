/**
 * Testes dos utils PUROS da coleção compartilhada com aceite: rótulos de papel
 * e status, marcador/detalhe de share de área, gatilho do "Reenviar", textos
 * das confirmações (revogar, rebaixar, sair — com os itens órfãos), banner do
 * convite de quem já participa, pilha do card e chip "Incluído por".
 */
import { describe, expect, it } from 'vitest';
import type {
	ColecaoShare,
	ConviteColecao,
	DestinatarioColecao,
	ResumoShareOrgao
} from '$lib/types/collections';
import {
	PAPEIS_COMPARTILHAMENTO,
	destinatarioSemAcesso,
	detalheDoShareDeArea,
	fraseDeItensOrfaos,
	fraseDeItensQueSaem,
	marcadorDoShare,
	nomeDoShare,
	papelColecaoLabel,
	permissaoDoConvite,
	pilhaDestinatarios,
	podeReenviarShare,
	procedenciaDoConvite,
	rotuloDestinatario,
	rotuloIncluidoPor,
	rotuloStatusConvite,
	textoDeRebaixamento,
	textoDeRevogacao,
	textoDeSaida,
	textoDoConviteExtra
} from './colecaoShares';

/** Share de pessoa com os campos do contrato; `extra` sobrescreve o necessário. */
function sharePessoa(extra: Partial<ColecaoShare> = {}): ColecaoShare {
	return {
		id: 1,
		user_id: 5,
		orgao_id: null,
		papel: 'viewer',
		created_at: '2026-10-01T12:00:00Z',
		user: { id: 5, nome: 'Maria' },
		orgao: null,
		exige_aceite: true,
		status: 'pendente',
		resumo: null,
		itens_incluidos: 0,
		...extra
	};
}

function resumoArea(extra: Partial<ResumoShareOrgao> = {}): ResumoShareOrgao {
	return { membros: 4, aceitos: 0, pendentes: 4, recusados: 0, sairam: 0, ...extra };
}

function shareArea(resumo: ResumoShareOrgao, extra: Partial<ColecaoShare> = {}): ColecaoShare {
	return sharePessoa({
		user_id: null,
		orgao_id: 3,
		user: null,
		orgao: { id: 3, nome: 'Secretaria de Planejamento', sigla: 'SEPLAG' },
		status: null,
		resumo,
		...extra
	});
}

function destinatario(extra: Partial<DestinatarioColecao> = {}): DestinatarioColecao {
	return { tipo: 'user', id: 9, nome: 'João', sigla: null, papel: 'viewer', status: 'aceito', ...extra };
}

describe('papéis e status', () => {
	it('oferece leitor e editor com o texto do que cada papel permite', () => {
		expect(PAPEIS_COMPARTILHAMENTO.map((p) => p.id)).toEqual(['viewer', 'editor']);
		expect(PAPEIS_COMPARTILHAMENTO[0].hint).toBe('Vê a coleção e lê os projetos');
		expect(PAPEIS_COMPARTILHAMENTO[1].hint).toContain('até o nível de quem os incluiu');
	});

	it('rotula papel e cai em Leitor quando o valor é desconhecido', () => {
		expect(papelColecaoLabel('dono')).toBe('Dono');
		expect(papelColecaoLabel('editor')).toBe('Editor');
		expect(papelColecaoLabel('x' as never)).toBe('Leitor');
	});

	it('mapeia cada status de convite para rótulo e tinta', () => {
		expect(rotuloStatusConvite('pendente')).toEqual({ rotulo: 'Pendente', tom: 'warning' });
		expect(rotuloStatusConvite('aceito')).toEqual({ rotulo: 'Aceito', tom: 'success' });
		expect(rotuloStatusConvite('legado')).toEqual({ rotulo: 'Com acesso', tom: 'neutral' });
		expect(rotuloStatusConvite('recusado')).toEqual({ rotulo: 'Recusou', tom: 'danger' });
		expect(rotuloStatusConvite('saiu')).toEqual({ rotulo: 'Saiu', tom: 'neutral' });
	});
});

describe('marcador e detalhe do share', () => {
	it('nome do share: pessoa pelo nome, área pela sigla (ou nome sem sigla)', () => {
		expect(nomeDoShare(sharePessoa())).toBe('Maria');
		expect(nomeDoShare(shareArea(resumoArea()))).toBe('SEPLAG');
		expect(nomeDoShare({ user: null, orgao: { id: 1, nome: 'Casa Civil', sigla: '' } })).toBe(
			'Casa Civil'
		);
		expect(nomeDoShare({ user: null, orgao: null })).toBe('Destinatário');
	});

	it('share de pessoa usa o status dela', () => {
		expect(marcadorDoShare(sharePessoa({ status: 'recusado' }))?.rotulo).toBe('Recusou');
	});

	it('share de área marca só quantos estão pendentes', () => {
		expect(marcadorDoShare(shareArea(resumoArea({ pendentes: 1 })))?.rotulo).toBe('1 pendente');
		expect(marcadorDoShare(shareArea(resumoArea({ pendentes: 3 })))?.rotulo).toBe('3 pendentes');
		expect(marcadorDoShare(shareArea(resumoArea({ pendentes: 0, aceitos: 4 })))).toBeNull();
	});

	it('detalhe da área resume aceites, recusas e saídas', () => {
		expect(detalheDoShareDeArea(resumoArea({ aceitos: 2, pendentes: 1, recusados: 1 }))).toBe(
			'2 de 4 com acesso · 1 recusou'
		);
		expect(detalheDoShareDeArea(resumoArea({ aceitos: 1, recusados: 2, sairam: 1 }))).toBe(
			'1 de 4 com acesso · 2 recusaram · 1 saiu'
		);
		expect(detalheDoShareDeArea(resumoArea({ membros: 0, pendentes: 0 }))).toBe(
			'Nenhuma pessoa lotada na área'
		);
	});

	it('Reenviar só aparece onde alguém recusou ou saiu', () => {
		expect(podeReenviarShare(sharePessoa({ status: 'recusado' }))).toBe(true);
		expect(podeReenviarShare(sharePessoa({ status: 'saiu' }))).toBe(true);
		expect(podeReenviarShare(sharePessoa({ status: 'pendente' }))).toBe(false);
		expect(podeReenviarShare(sharePessoa({ status: 'aceito' }))).toBe(false);
		expect(podeReenviarShare(shareArea(resumoArea({ sairam: 1 })))).toBe(true);
		expect(podeReenviarShare(shareArea(resumoArea()))).toBe(false);
	});
});

describe('textos de confirmação', () => {
	it('frase do que sai concorda em número e some quando nada sai', () => {
		expect(fraseDeItensQueSaem(0, 'Maria')).toBe('');
		expect(fraseDeItensQueSaem(1, 'Maria')).toBe(' 1 projeto incluído por Maria sai da coleção.');
		expect(fraseDeItensQueSaem(3, 'você')).toBe(' 3 projetos incluídos por você saem da coleção.');
	});

	it('convite pendente vira "cancelar convite", sem falar em perda de acesso', () => {
		const texto = textoDeRevogacao(sharePessoa(), 'Maria');
		expect(texto.title).toBe('Cancelar o convite de Maria?');
		expect(texto.confirmLabel).toBe('Cancelar convite');
		expect(texto.description).not.toContain('deixa de ver');
		expect(texto.sucesso).toBe('Convite de Maria cancelado.');
	});

	it('quem aceitou perde só o que vê pela coleção, e os itens dele saem junto', () => {
		const texto = textoDeRevogacao(sharePessoa({ status: 'aceito', itens_incluidos: 2 }), 'Maria');
		expect(texto.title).toBe('Revogar o acesso de Maria?');
		expect(texto.sucesso).toBe('Acesso de Maria revogado.');
		expect(texto.description).toContain('o que vê pela própria área continua');
		expect(texto.description).toContain('2 projetos incluídos por Maria saem da coleção.');
	});

	it('share de área com alguém dentro fala das pessoas da área', () => {
		const share = shareArea(resumoArea({ aceitos: 2, pendentes: 2 }), { itens_incluidos: 1 });
		const texto = textoDeRevogacao(share, 'SEPLAG');
		expect(texto.description).toMatch(/^Quem é da área deixa de ver/);
		expect(texto.description).toContain('1 projeto incluído por pessoas da área sai da coleção.');
	});

	it('rebaixar só pede confirmação quando algum projeto sai', () => {
		expect(textoDeRebaixamento(sharePessoa({ papel: 'editor' }), 'Maria')).toBeNull();
		const texto = textoDeRebaixamento(sharePessoa({ papel: 'editor', itens_incluidos: 1 }), 'Maria');
		expect(texto?.title).toBe('Mudar o papel de Maria para Leitor?');
		expect(texto?.confirmLabel).toBe('Mudar para Leitor');
		expect(texto?.description).toContain('1 projeto incluído por Maria sai da coleção.');
	});

	it('sair conta os projetos que o próprio ator incluiu', () => {
		const texto = textoDeSaida('Obras 2026', 2);
		expect(texto.title).toBe('Sair da coleção "Obras 2026"?');
		expect(texto.description).toContain('2 projetos incluídos por você saem da coleção.');
		expect(textoDeSaida('Obras 2026', 0).description).not.toContain('incluído');
	});

	it('sair usa a mesma forma neutra da recusa para o reconvite', () => {
		const texto = textoDeSaida('Obras 2026', 0);
		expect(texto.description).toContain('Só quem convidou pode convidar você de novo.');
		expect(texto.description).not.toContain('o dono');
	});
});

describe('itens órfãos (de quem já não é editor) nas confirmações', () => {
	it('frase dos órfãos concorda em número, encadeia com "também" e some no zero', () => {
		expect(fraseDeItensOrfaos(0, true)).toBe('');
		expect(fraseDeItensOrfaos(1, true)).toBe(' 1 projeto de quem já não é editor também sai.');
		expect(fraseDeItensOrfaos(3, true)).toBe(' 3 projetos de quem já não é editor também saem.');
		expect(fraseDeItensOrfaos(2, false)).toBe(
			' 2 projetos de quem já não é editor saem da coleção.'
		);
	});

	it('revogar soma os órfãos depois dos itens do alvo (sem dupla contagem)', () => {
		const share = sharePessoa({ status: 'aceito', itens_incluidos: 2 });
		expect(textoDeRevogacao(share, 'Maria', 1).description).toMatch(
			/2 projetos incluídos por Maria saem da coleção\. 1 projeto de quem já não é editor também sai\.$/
		);
		expect(textoDeRevogacao(share, 'Maria').description).not.toContain('já não é editor');
	});

	it('cancelar um convite pendente também avisa dos órfãos (a poda roda igual)', () => {
		const texto = textoDeRevogacao(sharePessoa(), 'Maria', 2);
		expect(texto.description).toContain('2 projetos de quem já não é editor saem da coleção.');
	});

	it('rebaixar sem itens do alvo mas com órfão AINDA pede confirmação', () => {
		const share = sharePessoa({ papel: 'editor', itens_incluidos: 0 });
		const texto = textoDeRebaixamento(share, 'Maria', 1);
		expect(texto).not.toBeNull();
		expect(texto?.description).toBe(
			'A leitura da coleção continua. 1 projeto de quem já não é editor sai da coleção.'
		);
		expect(textoDeRebaixamento(share, 'Maria', 0)).toBeNull();
	});

	it('sair conta os meus itens e os órfãos', () => {
		const texto = textoDeSaida('Obras', 1, 2);
		expect(texto.description).toContain(
			'1 projeto incluído por você sai da coleção. 2 projetos de quem já não é editor também saem.'
		);
		expect(textoDeSaida('Obras', 0, 1).description).toContain(
			'1 projeto de quem já não é editor sai da coleção.'
		);
	});
});

describe('convite, pilha do card e autoria', () => {
	it('procedência do convite cita o dono e o NOME do papel (sem flexão de gênero)', () => {
		const convite: ConviteColecao = {
			id: 7,
			nome: 'Obras',
			descricao: null,
			icone: 'camadas',
			cor: 'primary',
			owner: { id: 2, nome: 'Ana' },
			papel: 'editor',
			convidado_em: null
		};
		expect(procedenciaDoConvite(convite)).toBe('Ana convidou você com o papel de Editor');
		expect(procedenciaDoConvite({ ...convite, owner: null })).toBe(
			'Alguém convidou você com o papel de Editor'
		);
		expect(procedenciaDoConvite({ ...convite, papel: 'viewer' })).toBe(
			'Ana convidou você com o papel de Leitor'
		);
	});

	it('banner do convite de quem já participa: papel de hoje e recusa sem perda', () => {
		const convite = { owner: { id: 2, nome: 'Ana' }, papel: 'editor' as const };
		const sobe = textoDoConviteExtra(convite, 'viewer');
		expect(sobe.title).toBe('Ana convidou você com o papel de Editor');
		expect(sobe.description).toBe(
			'Seu papel atual é Leitor: aceite para passar a Editor. Recusar mantém o acesso que você já tem.'
		);
		const igual = textoDoConviteExtra({ ...convite, papel: 'viewer' }, 'editor');
		expect(igual.description).toBe('Aceitar ou recusar não muda o seu papel atual (Editor).');
		expect(`${sobe.description} ${igual.description}`).not.toMatch(/deixa de ver|perde/);
	});

	it('a permissão do convite se sustenta sozinha (sem o "Também" do seletor)', () => {
		expect(permissaoDoConvite('viewer')).toBe('Você vê a coleção e lê os projetos.');
		expect(permissaoDoConvite('editor')).toMatch(/^Você vê a coleção, inclui projetos/);
		expect(permissaoDoConvite('x' as never)).toBe('Você vê a coleção e lê os projetos.');
	});

	it('o "+N" vem do total do servidor, não da lista já cortada', () => {
		const lista = [1, 2, 3, 4, 5].map((id) => destinatario({ id }));
		const pilha = pilhaDestinatarios(lista, 8);
		expect(pilha.visiveis).toHaveLength(5);
		expect(pilha.excedente).toBe(3);
		expect(pilhaDestinatarios(lista.slice(0, 2), 2).excedente).toBe(0);
		expect(pilhaDestinatarios(lista, 5, 3)).toEqual({ visiveis: lista.slice(0, 3), excedente: 2 });
	});

	it('tooltip do avatar mostra papel para quem tem acesso e status para o resto', () => {
		expect(rotuloDestinatario(destinatario({ papel: 'editor' }))).toBe('João · Editor');
		expect(rotuloDestinatario(destinatario({ status: 'dono', papel: 'dono' }))).toBe('João · Dono');
		expect(
			rotuloDestinatario(
				destinatario({ tipo: 'orgao', nome: 'Planejamento', sigla: 'SEPLAG', status: 'pendente' })
			)
		).toBe('SEPLAG (Planejamento) · Pendente');
	});

	it('pendente, recusado e saiu não têm acesso; aceito, legado e dono têm', () => {
		expect(destinatarioSemAcesso(destinatario({ status: 'pendente' }))).toBe(true);
		expect(destinatarioSemAcesso(destinatario({ status: 'saiu' }))).toBe(true);
		expect(destinatarioSemAcesso(destinatario({ status: 'legado' }))).toBe(false);
		expect(destinatarioSemAcesso(destinatario({ status: 'dono' }))).toBe(false);
	});

	it('chip "Incluído por" some para o dono e para item legado', () => {
		const ids = { meuId: 5, donoId: 2 };
		expect(rotuloIncluidoPor({ adicionado_por: null }, ids)).toBeNull();
		expect(rotuloIncluidoPor({ adicionado_por: { id: 2, name: 'Ana' } }, ids)).toBeNull();
		expect(rotuloIncluidoPor({ adicionado_por: { id: 5, name: 'Maria' } }, ids)).toBe(
			'Incluído por você'
		);
		expect(rotuloIncluidoPor({ adicionado_por: { id: 8, name: 'Rui' } }, ids)).toBe(
			'Incluído por Rui'
		);
	});
});
