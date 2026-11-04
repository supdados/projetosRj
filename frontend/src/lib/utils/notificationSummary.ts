/**
 * Regras puras do SINO com convites: o número que acende o ponto, o texto
 * acessível do botão, quais convites ainda não ganharam toast e a memória
 * (por pessoa, neste navegador) dos que já ganharam.
 *
 * O ponto soma `unread_count` e `convites_pendentes` porque o convite segue
 * aguardando resposta mesmo depois de "marcar lidas" — sem a soma, quem abre o
 * sino e não responde perde o único lembrete visível.
 *
 * Exemplo:
 *   const novos = convitesNaoAvisados(resumo.convites, avisados);
 *   const aviso = avisoDeConvitesNovos(novos, base);
 */

import type { NotificacaoConviteResumo, NotificacoesResumo } from '$lib/types/notifications';

/** Quanto acende o ponto do sino (0 = apagado; antes do 1º resumo, 0). */
export function contagemDoSino(resumo: NotificacoesResumo | null): number {
	if (!resumo) return 0;
	return Math.max(0, resumo.unread_count) + Math.max(0, resumo.convites_pendentes);
}

/** `aria-label`/`title` do sino: "Notificações (2 não lidas, 1 convite pendente)". */
export function rotuloDoSino(resumo: NotificacoesResumo | null): string {
	if (!resumo) return 'Notificações';
	const partes: string[] = [];
	if (resumo.unread_count > 0) {
		partes.push(`${resumo.unread_count} ${resumo.unread_count === 1 ? 'não lida' : 'não lidas'}`);
	}
	if (resumo.convites_pendentes > 0) {
		const n = resumo.convites_pendentes;
		partes.push(`${n} ${n === 1 ? 'convite pendente' : 'convites pendentes'}`);
	}
	return partes.length > 0 ? `Notificações (${partes.join(', ')})` : 'Notificações';
}

/** Convites do resumo que ainda não ganharam toast nesta pessoa/navegador. */
export function convitesNaoAvisados(
	convites: readonly NotificacaoConviteResumo[],
	avisados: ReadonlySet<number>
): NotificacaoConviteResumo[] {
	return convites.filter((convite) => !avisados.has(convite.collection_id));
}

/** Toast de convite novo: texto, chave de dedupe e o caminho para responder. */
export interface AvisoDeConvite {
	mensagem: string;
	key: string;
	href: string;
	acao: string;
}

/**
 * Um convite novo leva direto à página dele (Aceitar/Recusar); vários viram
 * UM toast que leva ao índice — a pilha de toasts tem teto de 3.
 */
export function avisoDeConvitesNovos(
	novos: readonly NotificacaoConviteResumo[],
	base: string
): AvisoDeConvite | null {
	if (novos.length === 0) return null;
	if (novos.length === 1) {
		const [convite] = novos;
		return {
			mensagem: `Você recebeu um convite para a coleção "${convite.nome}"`,
			key: `colecao-convite-${convite.collection_id}`,
			href: `${base}/colecoes/${convite.collection_id}`,
			acao: 'Ver convite'
		};
	}
	return {
		mensagem: `Você recebeu ${novos.length} convites para coleções`,
		key: 'colecao-convites',
		href: `${base}/colecoes`,
		acao: 'Ver convites'
	};
}

/** Subconjunto do `Storage` usado aqui — injetável no teste (classe fake). */
export interface ArmazenamentoDeAvisos {
	getItem(chave: string): string | null;
	setItem(chave: string, valor: string): void;
}

/** Chave por pessoa: dois logins no mesmo navegador não silenciam o convite do outro. */
export function chaveDosAvisos(userId: number): string {
	return `projetosrj:convites-avisados:${userId}`;
}

/**
 * Ids de coleção cujo convite já ganhou toast. Armazenamento ausente, bloqueado
 * ou com lixo devolve vazio — no pior caso o toast reaparece, nunca quebra.
 */
export function lerConvitesAvisados(
	armazenamento: ArmazenamentoDeAvisos | null,
	userId: number
): Set<number> {
	if (!armazenamento) return new Set();
	try {
		const cru: unknown = JSON.parse(armazenamento.getItem(chaveDosAvisos(userId)) ?? '[]');
		if (!Array.isArray(cru)) return new Set();
		return new Set(cru.filter((id): id is number => Number.isInteger(id)));
	} catch {
		return new Set();
	}
}

/**
 * Grava os PENDENTES atuais como avisados: convite respondido sai do conjunto,
 * e um reenvio futuro do dono volta a ganhar toast.
 */
export function gravarConvitesAvisados(
	armazenamento: ArmazenamentoDeAvisos | null,
	userId: number,
	ids: Iterable<number>
): void {
	if (!armazenamento) return;
	try {
		armazenamento.setItem(chaveDosAvisos(userId), JSON.stringify([...ids]));
	} catch {
		// Cota cheia ou storage bloqueado: só perde a memória do toast.
	}
}
