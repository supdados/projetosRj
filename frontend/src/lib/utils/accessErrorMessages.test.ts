/**
 * Testes unitários do contrato de erro de autorização (S5, §6.3): 404
 * anti-enumeração (mensagem única, sem revelar existência) × 403 de ação.
 */
import { describe, it, expect } from 'vitest';
import { ApiClientError } from '$lib/api/client';
import {
	MSG_ACAO_SEM_PERMISSAO,
	MSG_PROJETO_INACESSIVEL,
	accessErrorKind,
	accessErrorMessage
} from './accessErrorMessages';

describe('accessErrorKind', () => {
	it('classifica 404 e 403 por status ou por code', () => {
		expect(accessErrorKind(new ApiClientError('not_found', 'x', 404))).toBe('not_found');
		expect(accessErrorKind(new ApiClientError('forbidden', 'x', 403))).toBe('forbidden');
		expect(accessErrorKind(new ApiClientError('not_found', 'x', 200))).toBe('not_found');
		expect(accessErrorKind(new ApiClientError('forbidden', 'x', 200))).toBe('forbidden');
	});

	it('trata validação, erro de rede e não-erro como genérico', () => {
		expect(accessErrorKind(new ApiClientError('validation', 'x', 400))).toBe('generic');
		expect(accessErrorKind(new Error('offline'))).toBe('generic');
		expect(accessErrorKind(null)).toBe('generic');
	});
});

describe('accessErrorMessage', () => {
	it('404 ignora a mensagem do servidor (anti-enumeração)', () => {
		const err = new ApiClientError('not_found', 'Recurso não encontrado.', 404);
		expect(accessErrorMessage(err, MSG_PROJETO_INACESSIVEL, 'fallback')).toBe(
			MSG_PROJETO_INACESSIVEL
		);
	});

	it('403 usa a mensagem de ação', () => {
		const err = new ApiClientError('forbidden', 'Sem permissão.', 403);
		expect(accessErrorMessage(err, MSG_PROJETO_INACESSIVEL, 'fallback')).toBe(
			MSG_ACAO_SEM_PERMISSAO
		);
	});

	it('genérico preserva a mensagem do erro e cai no fallback sem ela', () => {
		expect(accessErrorMessage(new Error('Falha de rede'), MSG_PROJETO_INACESSIVEL, 'fb')).toBe(
			'Falha de rede'
		);
		expect(accessErrorMessage(null, MSG_PROJETO_INACESSIVEL, 'fb')).toBe('fb');
	});
});
