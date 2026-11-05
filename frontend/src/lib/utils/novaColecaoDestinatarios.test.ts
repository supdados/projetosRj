import { describe, expect, it } from 'vitest';
import {
	compartilhamentosDaCriacao,
	destinatarioDeArea,
	destinatarioDePessoa,
	reciboDeVisibilidade
} from './novaColecaoDestinatarios';

const ANA = destinatarioDePessoa({ id: 7, name: 'Ana', orgao_sigla: 'SETD' }, 'viewer');
const SUPEST = destinatarioDeArea(
	{ id: 3, sigla: 'SUPEST', nome: 'Superintendência de Estratégia', pai_id: null },
	'editor'
);

describe('destinatários', () => {
	it('pessoa e área viram chaves distintas e XOR de ids', () => {
		expect(ANA).toMatchObject({ chave: 'u:7', tipo: 'pessoa', user_id: 7, orgao_id: null });
		expect(ANA.detalhe).toBe('Pessoa · SETD');
		expect(SUPEST).toMatchObject({ chave: 'o:3', tipo: 'area', user_id: null, orgao_id: 3 });
		expect(SUPEST.nome).toBe('SUPEST');
	});

	it('pessoa sem órgão fica só "Pessoa"; órgão sem sigla usa o nome', () => {
		const semOrgao = destinatarioDePessoa({ id: 1, name: 'Bia', orgao_sigla: null }, 'viewer');
		expect(semOrgao.detalhe).toBe('Pessoa');
		const semSigla = destinatarioDeArea({ id: 9, sigla: '', nome: 'Gabinete', pai_id: null }, 'viewer');
		expect(semSigla.nome).toBe('Gabinete');
	});
});

describe('compartilhamentosDaCriacao', () => {
	it('"Só eu" ou lista vazia não envia o campo', () => {
		expect(compartilhamentosDaCriacao(true, [ANA])).toBeUndefined();
		expect(compartilhamentosDaCriacao(false, [])).toBeUndefined();
	});

	it('monta o payload com um id só por item', () => {
		expect(compartilhamentosDaCriacao(false, [ANA, SUPEST])).toEqual([
			{ user_id: 7, papel: 'viewer' },
			{ orgao_id: 3, papel: 'editor' }
		]);
	});
});

describe('reciboDeVisibilidade', () => {
	it('coleção pessoal', () => {
		expect(reciboDeVisibilidade(true, [ANA])).toBe('Só você vê esta coleção');
		expect(reciboDeVisibilidade(false, [])).toBe('Só você vê esta coleção');
	});

	it('lista os convidados com "e" no fim e corta em três', () => {
		expect(reciboDeVisibilidade(false, [SUPEST])).toBe('Convite enviado para SUPEST');
		expect(reciboDeVisibilidade(false, [SUPEST, ANA])).toBe('Convite enviado para SUPEST e Ana');
		const cinco = ['A', 'B', 'C', 'D', 'E'].map((nome) => ({ nome }));
		expect(reciboDeVisibilidade(false, cinco)).toBe('Convite enviado para A, B, C e mais 2');
	});
});
