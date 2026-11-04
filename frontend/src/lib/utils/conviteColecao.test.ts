/**
 * Testes do fluxo de responder convite de coleção com uma porta FAKE (API +
 * confirmação): aceite, recusa confirmada/desistida, 404 de convite que sumiu
 * (revogado, já respondido, corrida) e o toast de cada desfecho. Mais o convite
 * de quem JÁ participa (banner da página interna): gatilho pelo resumo do
 * sino, recusa que não sugere perda de acesso e o que a tela faz depois.
 */
import { describe, expect, it } from 'vitest';
import { ApiClientError } from '$lib/api/client';
import type { ConfirmRequest } from '$lib/stores/confirm';
import type { ColecaoResumo } from '$lib/types/collections';
import type { NotificacoesResumo } from '$lib/types/notifications';
import {
	aceitarConviteColecao,
	avisoDoDesfecho,
	confirmacaoDeRecusa,
	deveProcurarConviteExtra,
	indiceRecarregaApos,
	reacaoAoConviteExtra,
	recusarConviteColecao,
	type DesfechoConvite,
	type PortaDeConvite
} from './conviteColecao';

const CARD = { id: 4, nome: 'Obras', papel: 'viewer' } as unknown as ColecaoResumo;
const CONVITE = { id: 4, nome: 'Obras', owner: { id: 2, nome: 'Ana' } };

/** Porta fake: registra as chamadas e responde o que o teste mandar. */
class PortaFalsa implements PortaDeConvite {
	readonly chamadas: string[] = [];
	readonly confirmacoes: ConfirmRequest[] = [];
	constructor(
		private readonly opcoes: { falha?: unknown; confirma?: boolean } = {}
	) {}

	async aceitar(id: number): Promise<ColecaoResumo> {
		this.chamadas.push(`aceitar:${id}`);
		if (this.opcoes.falha) throw this.opcoes.falha;
		return CARD;
	}

	async recusar(id: number): Promise<void> {
		this.chamadas.push(`recusar:${id}`);
		if (this.opcoes.falha) throw this.opcoes.falha;
	}

	async confirmar(request: ConfirmRequest): Promise<boolean> {
		this.confirmacoes.push(request);
		return this.opcoes.confirma ?? true;
	}
}

const NAO_ENCONTRADO = new ApiClientError('not_found', 'Recurso não encontrado.', 404);

describe('aceitarConviteColecao', () => {
	it('devolve o card novo', async () => {
		const porta = new PortaFalsa();
		expect(await aceitarConviteColecao(CONVITE, porta)).toEqual({ tipo: 'aceito', colecao: CARD });
		expect(porta.chamadas).toEqual(['aceitar:4']);
	});

	it('404 (revogado, já respondido, corrida) vira "indisponível", nunca erro', async () => {
		const porta = new PortaFalsa({ falha: NAO_ENCONTRADO });
		expect(await aceitarConviteColecao(CONVITE, porta)).toEqual({ tipo: 'indisponivel' });
	});

	it('falha comum leva a mensagem do servidor; erro desconhecido, a genérica', async () => {
		const falha = new ApiClientError('internal', 'Erro interno.', 500);
		expect(await aceitarConviteColecao(CONVITE, new PortaFalsa({ falha }))).toEqual({
			tipo: 'erro',
			mensagem: 'Erro interno.'
		});
		expect(await aceitarConviteColecao(CONVITE, new PortaFalsa({ falha: new TypeError('x') }))).toEqual({
			tipo: 'erro',
			mensagem: 'Não foi possível responder ao convite.'
		});
	});
});

describe('recusarConviteColecao', () => {
	it('confirma antes e só então recusa', async () => {
		const porta = new PortaFalsa();
		expect(await recusarConviteColecao(CONVITE, porta)).toEqual({ tipo: 'recusado' });
		expect(porta.confirmacoes[0].title).toBe('Recusar o convite para "Obras"?');
		expect(porta.chamadas).toEqual(['recusar:4']);
	});

	it('desistir na confirmação não chama a API nem liga o "ocupado"', async () => {
		const porta = new PortaFalsa({ confirma: false });
		let ocupado = false;
		expect(
			await recusarConviteColecao(CONVITE, porta, { aoConfirmar: () => (ocupado = true) })
		).toEqual({ tipo: 'cancelado' });
		expect(porta.chamadas).toEqual([]);
		expect(ocupado).toBe(false);
	});

	it('o "ocupado" liga entre o sim e a chamada', async () => {
		const porta = new PortaFalsa();
		const ordem: string[] = [];
		await recusarConviteColecao(CONVITE, porta, {
			aoConfirmar: () => ordem.push(`ocupado:${porta.chamadas.length}`)
		});
		expect(ordem).toEqual(['ocupado:0']);
		expect(porta.chamadas).toEqual(['recusar:4']);
	});

	it('convite que sumiu entre abrir e confirmar vira "indisponível"', async () => {
		const porta = new PortaFalsa({ falha: NAO_ENCONTRADO });
		expect(await recusarConviteColecao(CONVITE, porta)).toEqual({ tipo: 'indisponivel' });
	});

	it('a confirmação avisa que o dono fica sabendo e só ele reconvida', () => {
		const pedido = confirmacaoDeRecusa(CONVITE);
		expect(pedido.description).toBe(
			'Ana recebe um aviso. Só quem convidou pode convidar você de novo.'
		);
		expect(pedido.confirmLabel).toBe('Recusar convite');
		expect(confirmacaoDeRecusa({ ...CONVITE, owner: null }).description).toMatch(/^Quem convidou/);
	});

	it('quem já participa lê que o acesso continua (nada de "perder" a coleção)', () => {
		const pedido = confirmacaoDeRecusa(CONVITE, true);
		expect(pedido.description).toBe(
			'Ana recebe um aviso. Você continua na coleção com o acesso que já tem. Só quem convidou pode convidar você de novo.'
		);
		expect(pedido.description).not.toMatch(/deixa de ver|perde/);
		expect(confirmacaoDeRecusa(CONVITE).description).not.toContain('continua');
	});

	it('a recusa do banner usa o texto de quem mantém o acesso', async () => {
		const porta = new PortaFalsa();
		await recusarConviteColecao(CONVITE, porta, { mantemAcesso: true });
		expect(porta.confirmacoes[0].description).toContain('Você continua na coleção');
	});
});

describe('avisoDoDesfecho', () => {
	it('traduz cada desfecho em toast (e silencia a desistência)', () => {
		expect(avisoDoDesfecho({ tipo: 'aceito', colecao: CARD }, 'Obras')).toEqual({
			categoria: 'success',
			texto: 'Você entrou na coleção "Obras".'
		});
		expect(avisoDoDesfecho({ tipo: 'recusado' }, 'Obras')?.texto).toBe('Convite recusado.');
		expect(avisoDoDesfecho({ tipo: 'indisponivel' }, 'Obras')?.categoria).toBe('warning');
		expect(avisoDoDesfecho({ tipo: 'erro', mensagem: 'Falhou.' }, 'Obras')).toEqual({
			categoria: 'danger',
			texto: 'Falhou.'
		});
		expect(avisoDoDesfecho({ tipo: 'cancelado' }, 'Obras')).toBeNull();
	});

	it('quem já participava não "entra": o toast diz o papel que ficou', () => {
		const editor = { ...CARD, papel: 'editor' } as ColecaoResumo;
		expect(avisoDoDesfecho({ tipo: 'aceito', colecao: editor }, 'Obras', true)?.texto).toBe(
			'Convite aceito. Seu papel em "Obras" agora é Editor.'
		);
	});
});

/** Resumo do sino com convites para as coleções dadas. */
function resumoCom(...ids: number[]): NotificacoesResumo {
	return {
		unread_count: 0,
		convites_pendentes: ids.length,
		convites: ids.map((id) => ({ collection_id: id, nome: `C${id}` }))
	};
}

describe('convite de quem já participa (banner da página interna)', () => {
	it('procura o convite quando o sino lista ESTA coleção e o papel não é dono', () => {
		expect(deveProcurarConviteExtra('viewer', 4, resumoCom(4))).toBe(true);
		expect(deveProcurarConviteExtra('editor', 4, resumoCom(9, 4))).toBe(true);
	});

	it('não procura para o dono, sem resumo, ou com convite só de outra coleção', () => {
		expect(deveProcurarConviteExtra('dono', 4, resumoCom(4))).toBe(false);
		expect(deveProcurarConviteExtra('viewer', 4, null)).toBe(false);
		expect(deveProcurarConviteExtra('viewer', 4, resumoCom(9))).toBe(false);
		expect(deveProcurarConviteExtra(undefined, 4, resumoCom(4))).toBe(false);
	});

	it('aceito recarrega tudo; recusado/sumido só fecha o banner; desistência mantém', () => {
		const aceito: DesfechoConvite = { tipo: 'aceito', colecao: CARD };
		expect(reacaoAoConviteExtra(aceito)).toBe('recarregar');
		expect(reacaoAoConviteExtra({ tipo: 'recusado' })).toBe('fechar');
		expect(reacaoAoConviteExtra({ tipo: 'indisponivel' })).toBe('fechar');
		expect(reacaoAoConviteExtra({ tipo: 'cancelado' })).toBe('manter');
		expect(reacaoAoConviteExtra({ tipo: 'erro', mensagem: 'x' })).toBe('manter');
	});
});

describe('indiceRecarregaApos', () => {
	it('o índice re-busca no aceite e no 404 (pode ser o aceite de outra aba)', () => {
		expect(indiceRecarregaApos({ tipo: 'aceito', colecao: CARD })).toBe(true);
		expect(indiceRecarregaApos({ tipo: 'indisponivel' })).toBe(true);
		expect(indiceRecarregaApos({ tipo: 'recusado' })).toBe(false);
		expect(indiceRecarregaApos({ tipo: 'cancelado' })).toBe(false);
	});
});
