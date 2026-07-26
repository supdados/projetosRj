/**
 * Testes unitários dos utils PUROS de papel por vínculo de área (S2).
 *
 * Cobre a conversão entre o shape da API (`orgaos: [{id, papel}]`) e o do form
 * (`orgaos: [{orgao_id, papel}]`), o default `gestor` do backend e a detecção
 * de descendência que alimenta o aviso do `max()`.
 */
import { describe, it, expect } from 'vitest';
import {
	PAPEL_PADRAO,
	mergeVinculosComSelecao,
	normalizePapel,
	papelLabel,
	setVinculoPapel,
	vinculosFromRefs
} from './orgaoPapel';
import { buildOrgaoTree, computeCoveringAncestors } from './orgaoTree';
import type { AdminUserOrgaoRef } from '$lib/types/adminUsers';

const ref = (id: number, papel: string): AdminUserOrgaoRef =>
	({ id, sigla: `O${id}`, nome: `Órgão ${id}`, papel }) as AdminUserOrgaoRef;

describe('papelLabel / normalizePapel', () => {
	it('traduz os três papéis para PT-BR', () => {
		expect(papelLabel('gestor')).toBe('Gestor');
		expect(papelLabel('editor')).toBe('Editor');
		expect(papelLabel('leitor')).toBe('Leitor');
	});

	it('papel ausente ou desconhecido cai no default gestor', () => {
		expect(papelLabel(null)).toBe('Gestor');
		expect(papelLabel('chefe')).toBe('Gestor');
		expect(normalizePapel(undefined)).toBe(PAPEL_PADRAO);
		expect(normalizePapel('chefe')).toBe('gestor');
	});
});

describe('vinculosFromRefs', () => {
	it('converte os refs da API em pares (orgao_id, papel)', () => {
		const vinculos = vinculosFromRefs([ref(3, 'editor'), ref(7, 'leitor')], new Set([3, 7]));
		expect(vinculos).toEqual([
			{ orgao_id: 3, papel: 'editor' },
			{ orgao_id: 7, papel: 'leitor' }
		]);
	});

	it('descarta vínculos fora das opções (órgãos inativos, preservados no backend)', () => {
		expect(vinculosFromRefs([ref(3, 'gestor'), ref(99, 'gestor')], new Set([3]))).toEqual([
			{ orgao_id: 3, papel: 'gestor' }
		]);
	});
});

describe('mergeVinculosComSelecao', () => {
	it('preserva o papel das áreas que continuam selecionadas', () => {
		const atuais = [
			{ orgao_id: 3, papel: 'editor' as const },
			{ orgao_id: 7, papel: 'leitor' as const }
		];
		expect(mergeVinculosComSelecao(atuais, [7, 3])).toEqual([
			{ orgao_id: 7, papel: 'leitor' },
			{ orgao_id: 3, papel: 'editor' }
		]);
	});

	it('área nova nasce com o papel default e área removida some', () => {
		const atuais = [{ orgao_id: 3, papel: 'leitor' as const }];
		expect(mergeVinculosComSelecao(atuais, [9])).toEqual([{ orgao_id: 9, papel: 'gestor' }]);
	});
});

describe('setVinculoPapel', () => {
	it('troca só o papel do vínculo alvo, sem mutar a lista original', () => {
		const atuais = [
			{ orgao_id: 3, papel: 'gestor' as const },
			{ orgao_id: 7, papel: 'gestor' as const }
		];
		const next = setVinculoPapel(atuais, 7, 'leitor');
		expect(next).toEqual([
			{ orgao_id: 3, papel: 'gestor' },
			{ orgao_id: 7, papel: 'leitor' }
		]);
		expect(atuais[1].papel).toBe('gestor');
	});
});

describe('computeCoveringAncestors', () => {
	// GOVRJ(1) › SETD(2) › SUPDADOS(3); GOVRJ › SEPLAG(4)
	const tree = buildOrgaoTree([
		{ value: 1, pai_id: null },
		{ value: 2, pai_id: 1 },
		{ value: 3, pai_id: 2 },
		{ value: 4, pai_id: 1 }
	]);

	it('aponta o ancestral vinculado mais próximo, mesmo quando o nó também está vinculado', () => {
		const covering = computeCoveringAncestors(tree, new Set([1, 3]));
		expect(covering.get(1)).toBeNull();
		expect(covering.get(2)).toBe(1);
		expect(covering.get(3)).toBe(1);
		expect(covering.get(4)).toBe(1);
	});

	it('vínculo em nó intermediário vira o ancestral mais próximo dos descendentes', () => {
		const covering = computeCoveringAncestors(tree, new Set([1, 2]));
		expect(covering.get(3)).toBe(2);
		expect(covering.get(4)).toBe(1);
	});

	it('sem vínculos, ninguém tem ancestral cobrindo', () => {
		const covering = computeCoveringAncestors(tree, new Set<number>());
		expect([...covering.values()].every((v) => v === null)).toBe(true);
	});
});
