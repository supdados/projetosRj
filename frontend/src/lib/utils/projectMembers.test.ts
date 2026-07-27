/**
 * Testes unitários dos utils PUROS dos convites por projeto (S4).
 *
 * Cobre o teto de papéis (gestor nunca é opção), os rótulos de status, a janela
 * padrão de 90 dias do formulário (§7), o gatilho do badge "Convidado" e a
 * tradução do contrato anti-enumeração (404/403) das rotas novas.
 */
import { describe, it, expect } from 'vitest';
import { MSG_PROJETO_INACESSIVEL } from './accessErrorMessages';
import {
	CONVITE_EXPIRACAO_DIAS,
	CONVITE_PAPEL_OPTIONS,
	CONVITE_PAPEL_PADRAO,
	conviteErrorMessage,
	conviteStatusLabel,
	conviteStatusTone,
	convitePapelLabel,
	expiracaoPadraoIso,
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

describe('status do convite', () => {
	it('rotula os três estados e trata o desconhecido como revogado', () => {
		expect(conviteStatusLabel('ativo')).toBe('Ativo');
		expect(conviteStatusLabel('expirado')).toBe('Expirado');
		expect(conviteStatusLabel('revogado')).toBe('Revogado');
		expect(conviteStatusLabel('vencido')).toBe('Revogado');
	});

	it('mapeia o tom do badge por status', () => {
		expect(conviteStatusTone('ativo')).toBe('success');
		expect(conviteStatusTone('expirado')).toBe('warning');
		expect(conviteStatusTone('revogado')).toBe('neutral');
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

describe('isAcessoPorConvite (badge "Convidado")', () => {
	it('liga em convite e ambos, desliga em área/admin/ausente', () => {
		expect(isAcessoPorConvite('convite')).toBe(true);
		expect(isAcessoPorConvite('ambos')).toBe(true);
		expect(isAcessoPorConvite('area')).toBe(false);
		expect(isAcessoPorConvite('admin')).toBe(false);
		expect(isAcessoPorConvite(undefined)).toBe(false);
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
