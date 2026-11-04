/**
 * Testes do `getQuiet` (GET de fundo do polling do sino): desempacota o
 * envelope como o `get`, mas sessão expirada NÃO navega para /login — sobe
 * como `unauthenticated` para o polling parar sem derrubar o rascunho aberto.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiClientError, getQuiet } from './client';

/** Resposta mínima de `fetch` com status e corpo JSON. */
class RespostaFalsa {
	constructor(
		readonly status: number,
		private readonly corpo: unknown
	) {}
	async text(): Promise<string> {
		return JSON.stringify(this.corpo);
	}
}

const assign = vi.fn();

beforeEach(() => {
	assign.mockReset();
	vi.stubGlobal('window', { location: { assign } });
});

afterEach(() => {
	vi.unstubAllGlobals();
});

describe('getQuiet', () => {
	it('devolve `data` do envelope de sucesso', async () => {
		vi.stubGlobal(
			'fetch',
			vi.fn().mockResolvedValue(new RespostaFalsa(200, { ok: true, data: { unread_count: 2 } }))
		);
		expect(await getQuiet('/api/notificacoes/resumo')).toEqual({ unread_count: 2 });
	});

	it('401 sobe como unauthenticated e NÃO redireciona para o login', async () => {
		vi.stubGlobal(
			'fetch',
			vi.fn().mockResolvedValue(
				new RespostaFalsa(401, { ok: false, error: { code: 'unauthenticated', message: 'Sessão expirada.' } })
			)
		);
		const erro = await getQuiet('/api/notificacoes/resumo').catch((e: unknown) => e);
		expect(erro).toBeInstanceOf(ApiClientError);
		expect((erro as ApiClientError).code).toBe('unauthenticated');
		expect(assign).not.toHaveBeenCalled();
	});

	it('outros erros mantêm code e status do servidor', async () => {
		vi.stubGlobal(
			'fetch',
			vi.fn().mockResolvedValue(
				new RespostaFalsa(500, { ok: false, error: { code: 'internal', message: 'Falhou.' } })
			)
		);
		const erro = (await getQuiet('/x').catch((e: unknown) => e)) as ApiClientError;
		expect(erro.code).toBe('internal');
		expect(erro.status).toBe(500);
	});
});
