/**
 * Testes das regras puras do sino com convites: soma do ponto, rótulo
 * acessível, detecção de convite novo, texto/rota do toast e a memória por
 * pessoa dos convites já avisados (com storage fake e storage quebrado).
 */
import { describe, expect, it } from 'vitest';
import type { NotificacoesResumo } from '$lib/types/notifications';
import {
	avisoDeConvitesNovos,
	chaveDosAvisos,
	contagemDoSino,
	convitesNaoAvisados,
	gravarConvitesAvisados,
	lerConvitesAvisados,
	rotuloDoSino,
	type ArmazenamentoDeAvisos
} from './notificationSummary';

/** Storage em memória, com a mesma interface mínima do `localStorage`. */
class ArmazenamentoEmMemoria implements ArmazenamentoDeAvisos {
	readonly itens = new Map<string, string>();
	getItem(chave: string): string | null {
		return this.itens.get(chave) ?? null;
	}
	setItem(chave: string, valor: string): void {
		this.itens.set(chave, valor);
	}
}

/** Storage bloqueado (modo privado / site data bloqueado): toda chamada lança. */
class ArmazenamentoBloqueado implements ArmazenamentoDeAvisos {
	getItem(): string | null {
		throw new DOMException('bloqueado', 'SecurityError');
	}
	setItem(): void {
		throw new DOMException('bloqueado', 'SecurityError');
	}
}

function resumo(extra: Partial<NotificacoesResumo> = {}): NotificacoesResumo {
	return { unread_count: 0, convites_pendentes: 0, convites: [], ...extra };
}

describe('ponto e rótulo do sino', () => {
	it('soma não lidas e convites pendentes; sem resumo fica apagado', () => {
		expect(contagemDoSino(null)).toBe(0);
		expect(contagemDoSino(resumo({ unread_count: 2, convites_pendentes: 1 }))).toBe(3);
		expect(contagemDoSino(resumo({ convites_pendentes: 1 }))).toBe(1);
	});

	it('o rótulo explica por que o ponto acende', () => {
		expect(rotuloDoSino(null)).toBe('Notificações');
		expect(rotuloDoSino(resumo())).toBe('Notificações');
		expect(rotuloDoSino(resumo({ unread_count: 1 }))).toBe('Notificações (1 não lida)');
		expect(rotuloDoSino(resumo({ unread_count: 3, convites_pendentes: 2 }))).toBe(
			'Notificações (3 não lidas, 2 convites pendentes)'
		);
	});
});

describe('toast de convite novo', () => {
	const convites = [
		{ collection_id: 4, nome: 'Obras' },
		{ collection_id: 9, nome: 'Saúde' }
	];

	it('só conta como novo o convite ainda não avisado', () => {
		expect(convitesNaoAvisados(convites, new Set([4]))).toEqual([convites[1]]);
		expect(convitesNaoAvisados(convites, new Set([4, 9]))).toEqual([]);
	});

	it('um convite leva à página dele, com a chave por coleção', () => {
		expect(avisoDeConvitesNovos([convites[0]], '/app')).toEqual({
			mensagem: 'Você recebeu um convite para a coleção "Obras"',
			key: 'colecao-convite-4',
			href: '/app/colecoes/4',
			acao: 'Ver convite'
		});
	});

	it('vários convites viram um toast só, que leva ao índice', () => {
		const aviso = avisoDeConvitesNovos(convites, '');
		expect(aviso?.mensagem).toBe('Você recebeu 2 convites para coleções');
		expect(aviso?.href).toBe('/colecoes');
		expect(avisoDeConvitesNovos([], '')).toBeNull();
	});
});

describe('memória dos convites avisados', () => {
	it('grava e lê por pessoa', () => {
		const armazenamento = new ArmazenamentoEmMemoria();
		gravarConvitesAvisados(armazenamento, 7, [4, 9]);
		expect(lerConvitesAvisados(armazenamento, 7)).toEqual(new Set([4, 9]));
		expect(lerConvitesAvisados(armazenamento, 8)).toEqual(new Set());
		expect(armazenamento.itens.has(chaveDosAvisos(7))).toBe(true);
	});

	it('lixo no storage vira conjunto vazio, sem lançar', () => {
		const armazenamento = new ArmazenamentoEmMemoria();
		armazenamento.setItem(chaveDosAvisos(7), '{não é json');
		expect(lerConvitesAvisados(armazenamento, 7)).toEqual(new Set());
		armazenamento.setItem(chaveDosAvisos(7), JSON.stringify({ a: 1 }));
		expect(lerConvitesAvisados(armazenamento, 7)).toEqual(new Set());
		armazenamento.setItem(chaveDosAvisos(7), JSON.stringify([3, 'x', 2.5]));
		expect(lerConvitesAvisados(armazenamento, 7)).toEqual(new Set([3]));
	});

	it('storage ausente ou bloqueado não quebra o sino', () => {
		expect(lerConvitesAvisados(null, 7)).toEqual(new Set());
		expect(lerConvitesAvisados(new ArmazenamentoBloqueado(), 7)).toEqual(new Set());
		expect(() => gravarConvitesAvisados(new ArmazenamentoBloqueado(), 7, [1])).not.toThrow();
		expect(() => gravarConvitesAvisados(null, 7, [1])).not.toThrow();
	});
});
