/**
 * Testes do polling do resumo do sino com timers falsos: consulta imediata,
 * tique por intervalo, pausa em aba oculta, resposta velha descartada, erro
 * silencioso e parada por sessão expirada.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { iniciarPolling } from './summaryPolling';

/** Fonte controlável: cada chamada fica pendente até o teste resolver/rejeitar. */
class FonteControlada {
	readonly chamadas: {
		signal: AbortSignal;
		resolver: (valor: number) => void;
		rejeitar: (erro: unknown) => void;
	}[] = [];

	carregar = (signal: AbortSignal): Promise<number> =>
		new Promise<number>((resolver, rejeitar) => {
			this.chamadas.push({ signal, resolver, rejeitar });
		});
}

/** Erro de sessão expirada que o chamador manda parar. */
class SessaoExpirada extends Error {}

const INTERVALO = 60_000;

describe('iniciarPolling', () => {
	beforeEach(() => vi.useFakeTimers());
	afterEach(() => vi.useRealTimers());

	it('consulta ao iniciar e de novo a cada intervalo', async () => {
		const fonte = new FonteControlada();
		const recebidos: number[] = [];
		const polling = iniciarPolling({
			carregar: fonte.carregar,
			aoReceber: (v) => recebidos.push(v),
			documentoOculto: () => false,
			intervaloMs: INTERVALO
		});
		expect(fonte.chamadas).toHaveLength(1);
		fonte.chamadas[0].resolver(1);
		await vi.advanceTimersByTimeAsync(INTERVALO);
		expect(fonte.chamadas).toHaveLength(2);
		fonte.chamadas[1].resolver(2);
		await vi.advanceTimersByTimeAsync(0);
		expect(recebidos).toEqual([1, 2]);
		polling.parar();
	});

	it('aba oculta pula o tique', async () => {
		const fonte = new FonteControlada();
		let oculto = true;
		const polling = iniciarPolling({
			carregar: fonte.carregar,
			aoReceber: () => {},
			documentoOculto: () => oculto,
			intervaloMs: INTERVALO
		});
		await vi.advanceTimersByTimeAsync(INTERVALO * 3);
		expect(fonte.chamadas).toHaveLength(1);
		oculto = false;
		await vi.advanceTimersByTimeAsync(INTERVALO);
		expect(fonte.chamadas).toHaveLength(2);
		polling.parar();
	});

	it('consulta nova aborta a anterior e a resposta velha não vence', async () => {
		const fonte = new FonteControlada();
		const recebidos: number[] = [];
		const polling = iniciarPolling({
			carregar: fonte.carregar,
			aoReceber: (v) => recebidos.push(v),
			documentoOculto: () => false,
			intervaloMs: INTERVALO
		});
		polling.atualizarAgora();
		expect(fonte.chamadas[0].signal.aborted).toBe(true);
		fonte.chamadas[1].resolver(20);
		fonte.chamadas[0].resolver(10);
		await vi.advanceTimersByTimeAsync(0);
		expect(recebidos).toEqual([20]);
		polling.parar();
	});

	it('erro comum é silencioso e o polling segue', async () => {
		const fonte = new FonteControlada();
		const polling = iniciarPolling({
			carregar: fonte.carregar,
			aoReceber: () => {},
			documentoOculto: () => false,
			intervaloMs: INTERVALO,
			deveParar: (erro) => erro instanceof SessaoExpirada
		});
		fonte.chamadas[0].rejeitar(new Error('rede'));
		await vi.advanceTimersByTimeAsync(INTERVALO);
		expect(polling.parado).toBe(false);
		expect(fonte.chamadas).toHaveLength(2);
		polling.parar();
	});

	it('sessão expirada encerra o polling de vez', async () => {
		const fonte = new FonteControlada();
		const polling = iniciarPolling({
			carregar: fonte.carregar,
			aoReceber: () => {},
			documentoOculto: () => false,
			intervaloMs: INTERVALO,
			deveParar: (erro) => erro instanceof SessaoExpirada
		});
		fonte.chamadas[0].rejeitar(new SessaoExpirada());
		await vi.advanceTimersByTimeAsync(INTERVALO * 2);
		expect(polling.parado).toBe(true);
		expect(fonte.chamadas).toHaveLength(1);
		polling.atualizarAgora();
		expect(fonte.chamadas).toHaveLength(1);
	});

	it('parar descarta a resposta que ainda estava no ar', async () => {
		const fonte = new FonteControlada();
		const recebidos: number[] = [];
		const polling = iniciarPolling({
			carregar: fonte.carregar,
			aoReceber: (v) => recebidos.push(v),
			documentoOculto: () => false,
			intervaloMs: INTERVALO
		});
		polling.parar();
		fonte.chamadas[0].resolver(1);
		await vi.advanceTimersByTimeAsync(INTERVALO);
		expect(recebidos).toEqual([]);
		expect(fonte.chamadas[0].signal.aborted).toBe(true);
	});
});
