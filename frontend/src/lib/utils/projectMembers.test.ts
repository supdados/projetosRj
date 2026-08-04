/**
 * Testes unitários dos utils PUROS dos convites por projeto (S4).
 *
 * Cobre o teto de papéis (gestor nunca é opção), os rótulos de status, os
 * períodos de expiração do formulário (§7), o gatilho do badge "Convidado" e a
 * tradução do contrato anti-enumeração (404/403) das rotas novas.
 */
import { describe, it, expect } from 'vitest';
import type { ProjectMemberDireto, ProjectMemberHerdado } from '$lib/types/projectMembers';
import { MSG_PROJETO_INACESSIVEL } from './accessErrorMessages';
import {
	CONVITE_EXPIRACAO_DIAS,
	CONVITE_PAPEL_OPTIONS,
	CONVITE_PAPEL_PADRAO,
	CONVITE_PERIODO_OPTIONS,
	CONVITE_PERIODO_PADRAO_DIAS,
	contarAreasHerdadas,
	conviteErrorMessage,
	conviteLoteResumo,
	convitePapelLabel,
	convitePeriodoDias,
	convitePeriodoValue,
	expiracaoDoPeriodo,
	expiracaoPadraoIso,
	filtrarConcessoes,
	isAcessoPorConvite,
	normalizeConvitePapel
} from './projectMembers';

describe('papéis concedíveis por convite', () => {
	it('oferece apenas editor e leitor (teto rígido: gestor fora)', () => {
		expect(CONVITE_PAPEL_OPTIONS.map((o) => o.value)).toEqual(['editor', 'leitor']);
	});

	it('normaliza papel ausente, desconhecido ou gestor para o padrão leitor', () => {
		expect(CONVITE_PAPEL_PADRAO).toBe('leitor');
		expect(normalizeConvitePapel('gestor')).toBe('leitor');
		expect(normalizeConvitePapel(undefined)).toBe('leitor');
		expect(normalizeConvitePapel('editor')).toBe('editor');
	});

	it('traduz o papel para PT-BR', () => {
		expect(convitePapelLabel('editor')).toBe('Editor');
		expect(convitePapelLabel('leitor')).toBe('Leitor');
		expect(convitePapelLabel(null)).toBe('Leitor');
	});
});

describe('expiracaoPadraoIso', () => {
	it('sugere 90 dias à frente em ISO (YYYY-MM-DD)', () => {
		expect(CONVITE_EXPIRACAO_DIAS).toBe(90);
		expect(expiracaoPadraoIso(new Date('2026-01-01T12:00:00Z'))).toBe('2026-04-01');
	});

	it('atravessa a virada de ano sem estourar o mês', () => {
		expect(expiracaoPadraoIso(new Date('2026-12-15T00:00:00Z'), 30)).toBe('2027-01-14');
	});
});

describe('períodos do formulário de convite', () => {
	it('oferece 15/30/45 dias e indeterminado, com 30 como padrão', () => {
		expect(CONVITE_PERIODO_OPTIONS.map((o) => o.value)).toEqual([
			'15',
			'30',
			'45',
			'indeterminado'
		]);
		expect(CONVITE_PERIODO_OPTIONS.map((o) => o.dias)).toEqual([15, 30, 45, null]);
		expect(CONVITE_PERIODO_PADRAO_DIAS).toBe(30);
	});

	it('converte dias ⇄ valor da opção (null = indeterminado)', () => {
		expect(convitePeriodoValue(45)).toBe('45');
		expect(convitePeriodoValue(null)).toBe('indeterminado');
		expect(convitePeriodoDias('15')).toBe(15);
		expect(convitePeriodoDias('indeterminado')).toBeNull();
	});

	it('cai no padrão quando o valor é ausente ou desconhecido', () => {
		expect(convitePeriodoDias(null)).toBe(CONVITE_PERIODO_PADRAO_DIAS);
		expect(convitePeriodoDias('7')).toBe(CONVITE_PERIODO_PADRAO_DIAS);
	});

	it('deriva expires_at do período (indeterminado ⇒ null = sem expiração)', () => {
		expect(expiracaoDoPeriodo(30, new Date('2026-01-01T12:00:00Z'))).toBe('2026-01-31');
		expect(expiracaoDoPeriodo(null, new Date('2026-01-01T12:00:00Z'))).toBeNull();
	});
});

describe('conviteLoteResumo (compartilhar com área)', () => {
	it('junta só as contagens não-zeradas, na ordem convidados › reativados › pulados', () => {
		expect(conviteLoteResumo({ convidados: 12, reativados: 0, pulados: 3 })).toBe(
			'12 pessoas convidadas · 3 já tinham acesso'
		);
		expect(conviteLoteResumo({ convidados: 2, reativados: 4, pulados: 1 })).toBe(
			'2 pessoas convidadas · 4 convites reativados · 1 já tinha acesso'
		);
	});

	it('flexiona o singular', () => {
		expect(conviteLoteResumo({ convidados: 1, reativados: 1, pulados: 0 })).toBe(
			'1 pessoa convidada · 1 convite reativado'
		);
	});

	it('órgão sem elegíveis (tudo zerado) vira frase própria, não "0 · 0 · 0"', () => {
		expect(conviteLoteResumo({ convidados: 0, reativados: 0, pulados: 0 })).toBe(
			'Ninguém novo para convidar nesta área.'
		);
	});
});

describe('isAcessoPorConvite (badge "Convidado")', () => {
	it('liga em convite e ambos, desliga em área/admin/ausente', () => {
		expect(isAcessoPorConvite('convite')).toBe(true);
		expect(isAcessoPorConvite('ambos')).toBe(true);
		expect(isAcessoPorConvite('area')).toBe(false);
		expect(isAcessoPorConvite('admin')).toBe(false);
		expect(isAcessoPorConvite(undefined)).toBe(false);
	});
});

/** Concessão direta mínima; cada teste sobrescreve só o que importa. */
function direto(over: Partial<ProjectMemberDireto> = {}): ProjectMemberDireto {
	return {
		id: 1,
		user_id: 1,
		user_name: 'Jose Silva',
		user_username: 'jsilva',
		user_orgao_sigla: 'SEFAZ',
		papel: 'leitor',
		status: 'ativo',
		created_at: null,
		expires_at: null,
		revoked_at: null,
		...over
	};
}

/** Membro herdado mínimo (só `orgao_id` importa para a contagem de áreas). */
function herdado(over: Partial<ProjectMemberHerdado> = {}): ProjectMemberHerdado {
	return {
		user_id: 1,
		user_name: 'Ana Lima',
		user_username: 'alima',
		papel: 'leitor',
		orgao_id: 10,
		orgao_sigla: 'SEFAZ',
		orgao_nome: 'Secretaria de Fazenda',
		...over
	};
}

describe('filtrarConcessoes (busca da tela Gerenciar acesso)', () => {
	const maria = direto({
		id: 2,
		user_id: 2,
		user_name: 'Maria Antônia',
		user_username: 'mantonia',
		user_orgao_sigla: 'SEEDUC'
	});
	const revogado = direto({
		id: 3,
		user_id: 3,
		user_name: 'Carlos Dias',
		user_username: 'cdias',
		user_orgao_sigla: null,
		status: 'revogado'
	});
	const expirado = direto({ id: 4, user_id: 4, user_name: 'Bruno Reis', status: 'expirado' });
	const todos = [direto(), maria, revogado, expirado];

	it('acha por nome ignorando acento e caixa nos DOIS sentidos', () => {
		expect(filtrarConcessoes(todos, 'josé', 'todos').map((d) => d.id)).toEqual([1]);
		expect(filtrarConcessoes(todos, 'JOSE', 'todos').map((d) => d.id)).toEqual([1]);
		expect(filtrarConcessoes(todos, 'antonia', 'todos').map((d) => d.id)).toEqual([2]);
		expect(filtrarConcessoes(todos, 'ANTÔNIA', 'todos').map((d) => d.id)).toEqual([2]);
	});

	it('acha por username e por sigla do órgão', () => {
		expect(filtrarConcessoes(todos, 'mantonia', 'todos').map((d) => d.id)).toEqual([2]);
		expect(filtrarConcessoes(todos, 'seeduc', 'todos').map((d) => d.id)).toEqual([2]);
		// 3 fica DE FORA: `revogado` é o único fixture com `user_orgao_sigla: null`
		// (usado logo abaixo para cobrir sigla ausente), então não casa por sigla.
		expect(filtrarConcessoes(todos, 'sefaz', 'todos').map((d) => d.id)).toEqual([1, 4]);
	});

	it('sigla ausente não quebra a busca', () => {
		expect(filtrarConcessoes([revogado], 'carlos', 'todos')).toHaveLength(1);
	});

	it('termo vazio (ou só espaços) não filtra por texto', () => {
		expect(filtrarConcessoes(todos, '', 'todos')).toHaveLength(4);
		expect(filtrarConcessoes(todos, '   ', 'todos')).toHaveLength(4);
	});

	it('segmenta por status — expirado conta como ativo', () => {
		expect(filtrarConcessoes(todos, '', 'ativos').map((d) => d.id)).toEqual([1, 2, 4]);
		expect(filtrarConcessoes(todos, '', 'revogados').map((d) => d.id)).toEqual([3]);
	});

	it('combina texto e status (sem casar, devolve vazio)', () => {
		expect(filtrarConcessoes(todos, 'carlos', 'ativos')).toEqual([]);
		expect(filtrarConcessoes(todos, 'carlos', 'revogados').map((d) => d.id)).toEqual([3]);
	});

	it('preserva a ordem de entrada e não muta a lista original', () => {
		const entrada = [...todos];
		expect(filtrarConcessoes(entrada, '', 'todos').map((d) => d.id)).toEqual([1, 2, 3, 4]);
		expect(entrada).toEqual(todos);
	});
});

describe('contarAreasHerdadas', () => {
	it('conta áreas DISTINTAS, não pessoas', () => {
		const herdados = [herdado(), herdado({ user_id: 2 }), herdado({ user_id: 3, orgao_id: 20 })];
		expect(contarAreasHerdadas(herdados)).toBe(2);
	});

	it('sem herdados devolve 0 (rodapé omite o trecho de áreas)', () => {
		expect(contarAreasHerdadas([])).toBe(0);
	});
});

describe('conviteErrorMessage', () => {
	it('separa 404 (não vê o projeto OU flag off) de 403 (vê mas não gerencia)', () => {
		expect(conviteErrorMessage(404, 'not_found')).toBe(MSG_PROJETO_INACESSIVEL);
		expect(conviteErrorMessage(403, 'forbidden')).toBe(
			'Você não pode gerenciar os membros deste projeto.'
		);
	});

	it('cobre validação e o genérico (503 não existe no contrato: flag off => 404)', () => {
		expect(conviteErrorMessage(400, 'validation')).toBe('Dados do convite inválidos.');
		expect(conviteErrorMessage(503, 'unavailable')).toBe(
			'Não foi possível concluir a operação.'
		);
		expect(conviteErrorMessage(500, 'server')).toBe('Não foi possível concluir a operação.');
	});
});
