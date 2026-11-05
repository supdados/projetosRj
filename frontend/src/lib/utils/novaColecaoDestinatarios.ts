/**
 * Destinatários escolhidos em "Quem enxerga" do modal Nova coleção, ANTES de a
 * coleção existir: viram `compartilhamentos` do POST atômico e a linha de
 * visibilidade da tela de sucesso. Cada um nasce CONVITE pendente no backend
 * (nada é visto antes do aceite) — por isso o recibo diz "Convite enviado".
 *
 * Exemplo:
 *   const alvo = destinatarioDePessoa({ id: 7, name: 'Ana', orgao_sigla: 'SETD' }, 'viewer');
 *   compartilhamentosDaCriacao(false, [alvo]); // → [{ user_id: 7, papel: 'viewer' }]
 */

import type { AreaOption } from '$lib/api/areas';
import type {
	ColecaoShareCreatePayload,
	PapelCompartilhamento,
	PessoaDestinavel
} from '$lib/types/collections';

/** Um destinatário da lista: pessoa XOR órgão exato (sem subárvore). */
export interface DestinatarioNovo {
	/** "u:12"/"o:3" — chave do `{#each}` e trava de duplicata. */
	chave: string;
	tipo: 'pessoa' | 'area';
	nome: string;
	/** "Pessoa · SETD" ou o nome por extenso do órgão. */
	detalhe: string;
	user_id: number | null;
	orgao_id: number | null;
	papel: PapelCompartilhamento;
}

export function destinatarioDePessoa(
	pessoa: PessoaDestinavel,
	papel: PapelCompartilhamento
): DestinatarioNovo {
	return {
		chave: `u:${pessoa.id}`,
		tipo: 'pessoa',
		nome: pessoa.name,
		detalhe: pessoa.orgao_sigla ? `Pessoa · ${pessoa.orgao_sigla}` : 'Pessoa',
		user_id: pessoa.id,
		orgao_id: null,
		papel
	};
}

export function destinatarioDeArea(orgao: AreaOption, papel: PapelCompartilhamento): DestinatarioNovo {
	return {
		chave: `o:${orgao.id}`,
		tipo: 'area',
		nome: orgao.sigla || orgao.nome,
		detalhe: orgao.nome,
		user_id: null,
		orgao_id: orgao.id,
		papel
	};
}

/** "Só eu" ligado (ou lista vazia) = coleção pessoal: o campo nem vai no POST. */
export function compartilhamentosDaCriacao(
	soEu: boolean,
	destinatarios: readonly DestinatarioNovo[]
): ColecaoShareCreatePayload[] | undefined {
	if (soEu || destinatarios.length === 0) return undefined;
	return destinatarios.map((d) =>
		d.user_id !== null
			? { user_id: d.user_id, papel: d.papel }
			: { orgao_id: d.orgao_id ?? 0, papel: d.papel }
	);
}

/** Até 3 nomes por extenso; o resto vira "+N" para a linha caber no recibo. */
const NOMES_NO_RECIBO = 3;

/**
 * Linha de visibilidade da tela de sucesso. Exemplos:
 * `"Só você vê esta coleção"`, `"Convite enviado para SUPEST e Ana"`,
 * `"Convite enviado para A, B, C e mais 2"`.
 */
export function reciboDeVisibilidade(
	soEu: boolean,
	destinatarios: readonly Pick<DestinatarioNovo, 'nome'>[]
): string {
	if (soEu || destinatarios.length === 0) return 'Só você vê esta coleção';
	const nomes = destinatarios.slice(0, NOMES_NO_RECIBO).map((d) => d.nome);
	const resto = destinatarios.length - nomes.length;
	if (resto > 0) return `Convite enviado para ${nomes.join(', ')} e mais ${resto}`;
	if (nomes.length === 1) return `Convite enviado para ${nomes[0]}`;
	return `Convite enviado para ${nomes.slice(0, -1).join(', ')} e ${nomes[nomes.length - 1]}`;
}
