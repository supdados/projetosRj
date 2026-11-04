/**
 * Responder a um convite de coleção (aceitar/recusar) — o MESMO fluxo no card
 * do índice e no estado "convite pendente" da página interna.
 *
 * Desfechos possíveis, que a tela traduz em toast/navegação:
 *   - `aceito` (com o card novo) / `recusado`;
 *   - `cancelado` — desistiu na confirmação da recusa;
 *   - `indisponivel` — 404: o dono revogou, outra aba já respondeu ou o
 *     duplo clique perdeu a corrida (o backend devolve o MESMO 404 para tudo);
 *   - `erro` — falha comum, com a mensagem para o toast.
 *
 * As chamadas (API e confirmação) entram por parâmetro: o teste usa classes
 * fake em vez de mockar módulos.
 *
 * "Mantém acesso" é o convite que chega a quem JÁ participa da coleção (ex.:
 * era Leitor e a área recebeu Editor): `.../projetos` dá 200, a página mostra
 * o convite num banner e recusar não tira o acesso que a pessoa já tinha.
 *
 * Exemplo:
 *   const desfecho = await aceitarConviteColecao(convite);
 *   const aviso = avisoDoDesfecho(desfecho, convite.nome);
 */

import { ApiClientError } from '$lib/api/client';
import { aceitarConvite, recusarConvite } from '$lib/api/collections';
import { confirmAction, type ConfirmRequest } from '$lib/stores/confirm';
import type { FlashCategory } from '$lib/stores/flash';
import type { ColecaoResumo, ConviteColecao, PapelColecao } from '$lib/types/collections';
import type { NotificacoesResumo } from '$lib/types/notifications';
import { papelColecaoLabel } from '$lib/utils/colecaoShares';

export type DesfechoConvite =
	| { tipo: 'aceito'; colecao: ColecaoResumo }
	| { tipo: 'recusado' }
	| { tipo: 'cancelado' }
	| { tipo: 'indisponivel' }
	| { tipo: 'erro'; mensagem: string };

/** O que o fluxo precisa do mundo de fora (API + diálogo de confirmação). */
export interface PortaDeConvite {
	aceitar(collectionId: number): Promise<ColecaoResumo>;
	recusar(collectionId: number): Promise<void>;
	confirmar(request: ConfirmRequest): Promise<boolean>;
}

const PORTA_PADRAO: PortaDeConvite = {
	aceitar: aceitarConvite,
	recusar: recusarConvite,
	confirmar: confirmAction
};

const MSG_FALHA = 'Não foi possível responder ao convite.';

function desfechoDeErro(err: unknown): DesfechoConvite {
	if (err instanceof ApiClientError && (err.status === 404 || err.code === 'not_found')) {
		return { tipo: 'indisponivel' };
	}
	if (err instanceof ApiClientError && err.message) return { tipo: 'erro', mensagem: err.message };
	return { tipo: 'erro', mensagem: MSG_FALHA };
}

/** Aceita o convite; o card devolvido já traz o papel novo e o rollup. */
export async function aceitarConviteColecao(
	convite: Pick<ConviteColecao, 'id'>,
	porta: PortaDeConvite = PORTA_PADRAO
): Promise<DesfechoConvite> {
	try {
		return { tipo: 'aceito', colecao: await porta.aceitar(convite.id) };
	} catch (err) {
		return desfechoDeErro(err);
	}
}

/**
 * Pergunta da recusa: o dono recebe aviso e só ele pode convidar de novo. Com
 * `mantemAcesso` (quem já participa), o texto diz que o acesso atual continua
 * — recusar só desfaz o convite novo, nunca o share que a pessoa já aceitou.
 */
export function confirmacaoDeRecusa(
	convite: Pick<ConviteColecao, 'nome' | 'owner'>,
	mantemAcesso: boolean = false
): ConfirmRequest {
	const dono = convite.owner?.nome ?? 'Quem convidou';
	const continua = mantemAcesso ? ' Você continua na coleção com o acesso que já tem.' : '';
	return {
		title: `Recusar o convite para "${convite.nome}"?`,
		description: `${dono} recebe um aviso.${continua} Só quem convidou pode convidar você de novo.`,
		tone: 'danger',
		confirmLabel: 'Recusar convite',
		cancelLabel: 'Voltar'
	};
}

/** Ajustes da recusa vindos da tela. */
export interface OpcoesDaRecusa {
	/**
	 * Roda entre o "sim" e a chamada — é onde a tela liga o "Recusando…" (antes
	 * disso o botão não pode parecer ocupado com o diálogo aberto).
	 */
	aoConfirmar?: () => void;
	/** Quem recusa já participa da coleção (banner da página interna). */
	mantemAcesso?: boolean;
}

/** Confirma e recusa; desistir na confirmação não chama a API. */
export async function recusarConviteColecao(
	convite: Pick<ConviteColecao, 'id' | 'nome' | 'owner'>,
	porta: PortaDeConvite = PORTA_PADRAO,
	opcoes: OpcoesDaRecusa = {}
): Promise<DesfechoConvite> {
	const pedido = confirmacaoDeRecusa(convite, opcoes.mantemAcesso ?? false);
	if (!(await porta.confirmar(pedido))) return { tipo: 'cancelado' };
	opcoes.aoConfirmar?.();
	try {
		await porta.recusar(convite.id);
		return { tipo: 'recusado' };
	} catch (err) {
		return desfechoDeErro(err);
	}
}

/**
 * Toast de cada desfecho; `null` = nada a dizer (desistiu na confirmação).
 * Quem já participava (`mantemAcesso`) não "entra" na coleção: o aceite só
 * muda o papel, e o toast diz qual ficou.
 */
export function avisoDoDesfecho(
	desfecho: DesfechoConvite,
	nomeColecao: string,
	mantemAcesso: boolean = false
): { categoria: FlashCategory; texto: string } | null {
	switch (desfecho.tipo) {
		case 'aceito':
			return {
				categoria: 'success',
				texto: mantemAcesso
					? `Convite aceito. Seu papel em "${nomeColecao}" agora é ${papelColecaoLabel(desfecho.colecao.papel)}.`
					: `Você entrou na coleção "${nomeColecao}".`
			};
		case 'recusado':
			return { categoria: 'success', texto: 'Convite recusado.' };
		case 'indisponivel':
			return { categoria: 'warning', texto: 'Este convite não está mais disponível.' };
		case 'erro':
			return { categoria: 'danger', texto: desfecho.mensagem };
		default:
			return null;
	}
}

/**
 * A página interna procura convite pendente MESMO com acesso válido? Só para
 * quem participa sem ser dono e só quando o resumo do sino lista esta coleção:
 * o resumo já chega a cada navegação e a cada ~60 s, então o caso comum (sem
 * convite) não paga um `GET .../convite` que daria 404.
 *
 * Exemplo:
 *   const procurar = deveProcurarConviteExtra(colecao.papel, id, $notificationSummary);
 */
export function deveProcurarConviteExtra(
	papel: PapelColecao | null | undefined,
	collectionId: number,
	resumo: Pick<NotificacoesResumo, 'convites'> | null
): boolean {
	if (!papel || papel === 'dono' || !resumo) return false;
	return resumo.convites.some((convite) => convite.collection_id === collectionId);
}

/**
 * O que o banner do convite extra faz com o desfecho: aceito sobe o papel
 * (`recarregar` a página toda); recusado ou sumido só `fechar` o banner — a
 * pessoa fica na página com o acesso que já tinha; desistência ou falha
 * `manter` o banner para tentar de novo.
 */
export function reacaoAoConviteExtra(desfecho: DesfechoConvite): 'recarregar' | 'fechar' | 'manter' {
	if (desfecho.tipo === 'aceito') return 'recarregar';
	if (desfecho.tipo === 'recusado' || desfecho.tipo === 'indisponivel') return 'fechar';
	return 'manter';
}

/**
 * O índice re-busca o grid depois da resposta? Aceito entra no grid; o 404
 * ("não está mais disponível") pode ser o aceite feito em outra aba.
 */
export function indiceRecarregaApos(desfecho: DesfechoConvite): boolean {
	return desfecho.tipo === 'aceito' || desfecho.tipo === 'indisponivel';
}
