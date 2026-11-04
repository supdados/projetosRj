/**
 * Testes do cliente de coleções na parte do convite com aceite: URLs das rotas
 * novas, piso de 2 caracteres da busca de pessoas e a política de cache —
 * escrita que muda QUAIS projetos o ator vê derruba também a Lista de Projetos,
 * e o 404 ("não está mais disponível") de aceitar/recusar/sair também derruba.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('./client', () => ({
	get: vi.fn(),
	post: vi.fn(),
	put: vi.fn(),
	del: vi.fn(),
	// Mesma forma do erro real: o cliente decide pelo `status`/`code`.
	ApiClientError: class ErroDeApiFalso extends Error {
		constructor(
			readonly code: string,
			message: string,
			readonly status: number
		) {
			super(message);
		}
	}
}));
vi.mock('./projects', () => ({ invalidateProjects: vi.fn() }));

import { ApiClientError, del, get, post } from './client';
import { invalidateProjects } from './projects';
import {
	aceitarConvite,
	adicionarProjeto,
	buscarDestinatarios,
	fetchConvites,
	fetchShares,
	peekConvites,
	recusarConvite,
	reenviarShare,
	revogarShare,
	sairDaColecao
} from './collections';

const CONVITE = {
	id: 4,
	nome: 'Obras',
	descricao: null,
	icone: 'camadas',
	cor: 'primary',
	owner: { id: 2, nome: 'Ana' },
	papel: 'viewer',
	convidado_em: null
};

beforeEach(() => {
	vi.mocked(get).mockReset();
	vi.mocked(post).mockReset();
	vi.mocked(del).mockReset();
	vi.mocked(invalidateProjects).mockReset();
});

describe('convites', () => {
	it('lista os convites e guarda no cache SWR', async () => {
		vi.mocked(get).mockResolvedValueOnce({ convites: [CONVITE] });
		expect(await fetchConvites()).toEqual([CONVITE]);
		expect(get).toHaveBeenCalledWith('/api/colecoes/convites', undefined);
		expect(peekConvites()).toEqual([CONVITE]);
	});

	it('aceitar devolve o card e derruba convites + Lista de Projetos', async () => {
		vi.mocked(get).mockResolvedValueOnce({ convites: [CONVITE] });
		await fetchConvites();
		const card = { id: 4, nome: 'Obras' };
		vi.mocked(post).mockResolvedValueOnce({ status: 'aceito', colecao: card });
		expect(await aceitarConvite(4)).toBe(card);
		expect(post).toHaveBeenCalledWith('/api/colecoes/4/convite/aceitar');
		expect(peekConvites()).toBeNull();
		expect(invalidateProjects).toHaveBeenCalledTimes(1);
	});

	it('recusar e sair usam as rotas por coleção e invalidam a Lista de Projetos', async () => {
		vi.mocked(post).mockResolvedValueOnce({ status: 'recusado' });
		await recusarConvite(4);
		expect(post).toHaveBeenLastCalledWith('/api/colecoes/4/convite/recusar');
		vi.mocked(post).mockResolvedValueOnce({ status: 'saiu', itens_removidos: 2 });
		expect(await sairDaColecao(4)).toBe(2);
		expect(post).toHaveBeenLastCalledWith('/api/colecoes/4/sair');
		expect(invalidateProjects).toHaveBeenCalledTimes(2);
	});
});

describe('404 de aceitar/recusar/sair (convite ou acesso que sumiu)', () => {
	const NAO_ENCONTRADO = new ApiClientError('not_found', 'Recurso não encontrado.', 404);
	const ACOES: [string, () => Promise<unknown>][] = [
		['aceitar', () => aceitarConvite(4)],
		['recusar', () => recusarConvite(4)],
		['sair', () => sairDaColecao(4)]
	];

	it.each(ACOES)('%s: relança o 404 e derruba convites + Lista de Projetos', async (_, acao) => {
		vi.mocked(get).mockResolvedValueOnce({ convites: [CONVITE] });
		await fetchConvites();
		vi.mocked(post).mockRejectedValueOnce(NAO_ENCONTRADO);
		await expect(acao()).rejects.toBe(NAO_ENCONTRADO);
		// Sem isso o índice remontaria com o convite morto (peek) e Aceitar ativo.
		expect(peekConvites()).toBeNull();
		expect(invalidateProjects).toHaveBeenCalledTimes(1);
	});

	it('falha comum (500) NÃO derruba o cache: nada mudou no servidor', async () => {
		vi.mocked(get).mockResolvedValueOnce({ convites: [CONVITE] });
		await fetchConvites();
		vi.mocked(post).mockRejectedValueOnce(new ApiClientError('internal', 'Erro.', 500));
		await expect(aceitarConvite(4)).rejects.toBeInstanceOf(ApiClientError);
		expect(peekConvites()).toEqual([CONVITE]);
		expect(invalidateProjects).not.toHaveBeenCalled();
	});
});

describe('gestão do dono e curadoria', () => {
	it('compartilhamentos trazem os itens órfãos; backend sem o campo conta 0', async () => {
		const share = { id: 3 };
		vi.mocked(get).mockResolvedValueOnce({ compartilhamentos: [share], itens_orfaos: 2 });
		expect(await fetchShares(7)).toEqual({ compartilhamentos: [share], itens_orfaos: 2 });
		expect(get).toHaveBeenCalledWith('/api/colecoes/7/compartilhamentos', undefined);
		vi.mocked(get).mockResolvedValueOnce({ compartilhamentos: [share] });
		expect((await fetchShares(7)).itens_orfaos).toBe(0);
	});

	it('revogar derruba a Lista de Projetos (a poda tira itens)', async () => {
		vi.mocked(del).mockResolvedValueOnce(undefined);
		await revogarShare(7, 3);
		expect(del).toHaveBeenCalledWith('/api/colecoes/7/compartilhamentos/3');
		expect(invalidateProjects).toHaveBeenCalledTimes(1);
	});

	it('reenviar não mexe na visibilidade de projetos', async () => {
		const share = { id: 3 };
		vi.mocked(post).mockResolvedValueOnce({ reconvidados: 1, compartilhamento: share });
		expect(await reenviarShare(7, 3)).toEqual({ reconvidados: 1, compartilhamento: share });
		expect(post).toHaveBeenCalledWith('/api/colecoes/7/compartilhamentos/3/reenviar');
		expect(invalidateProjects).not.toHaveBeenCalled();
	});

	it('incluir projeto não muda o que quem inclui já vê', async () => {
		vi.mocked(post).mockResolvedValueOnce(undefined);
		await adicionarProjeto(7, 42);
		expect(invalidateProjects).not.toHaveBeenCalled();
	});
});

describe('buscarDestinatarios', () => {
	it('termo com menos de 2 caracteres nem sai para a rede', async () => {
		expect(await buscarDestinatarios(' m ')).toEqual([]);
		expect(get).not.toHaveBeenCalled();
	});

	it('codifica o termo e devolve as pessoas', async () => {
		const pessoas = [{ id: 5, name: 'Maria José', orgao_sigla: 'SEPLAG' }];
		vi.mocked(get).mockResolvedValueOnce({ usuarios: pessoas });
		expect(await buscarDestinatarios('  maria josé ')).toEqual(pessoas);
		expect(get).toHaveBeenCalledWith(
			'/api/colecoes/destinatarios?q=maria%20jos%C3%A9',
			undefined
		);
	});
});
