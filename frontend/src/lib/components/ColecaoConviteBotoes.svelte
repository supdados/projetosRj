<script lang="ts">
	/**
	 * Par "Recusar / Aceitar" de um convite de coleção — o mesmo no card do
	 * índice e no estado pendente da página interna. Roda o fluxo de
	 * `conviteColecao.ts`, mostra o toast do desfecho, tira o convite do resumo
	 * do sino (o ponto apaga na hora) e devolve o desfecho a quem chamou, que
	 * decide o resto (re-buscar o índice, abrir a coleção, voltar).
	 *
	 * Os dois botões travam juntos: aceitar e recusar ao mesmo tempo daria 404
	 * no segundo. `mantemAcesso` (banner de quem já participa) troca os textos
	 * da recusa e do aceite: a pessoa não perde nem "entra" na coleção.
	 */
	import Button from '$lib/components/Button.svelte';
	import { flash } from '$lib/stores/flash';
	import { notificationSummary } from '$lib/stores/notificationSummary';
	import {
		aceitarConviteColecao,
		avisoDoDesfecho,
		recusarConviteColecao,
		type DesfechoConvite
	} from '$lib/utils/conviteColecao';
	import type { ConviteColecao } from '$lib/types/collections';

	interface Props {
		convite: ConviteColecao;
		/** `sm` no card do índice, `md` no estado pendente da página. */
		size?: 'sm' | 'md';
		/** Quem responde já participa da coleção (convite de papel novo). */
		mantemAcesso?: boolean;
		onRespondido: (desfecho: DesfechoConvite) => void;
	}

	let { convite, size = 'sm', mantemAcesso = false, onRespondido }: Props = $props();

	let ocupado = $state<'aceitar' | 'recusar' | null>(null);

	async function responder(acao: 'aceitar' | 'recusar'): Promise<void> {
		if (ocupado) return;
		if (acao === 'aceitar') ocupado = 'aceitar';
		const desfecho =
			acao === 'aceitar'
				? await aceitarConviteColecao(convite)
				: await recusarConviteColecao(convite, undefined, {
						aoConfirmar: () => (ocupado = 'recusar'),
						mantemAcesso
					});
		ocupado = null;
		const aviso = avisoDoDesfecho(desfecho, convite.nome, mantemAcesso);
		if (aviso) flash.show(aviso.texto, aviso.categoria);
		// Respondido (ou sumido): o convite sai do sino já, e a consulta real corrige o resto.
		if (desfecho.tipo !== 'cancelado' && desfecho.tipo !== 'erro') {
			notificationSummary.removerConvite(convite.id);
			notificationSummary.atualizar();
		}
		onRespondido(desfecho);
	}
</script>

<div class="flex shrink-0 items-center gap-2">
	<Button
		variant="secondary"
		{size}
		disabled={ocupado !== null}
		aria-label={`Recusar o convite para ${convite.nome}`}
		onclick={() => void responder('recusar')}
	>
		{ocupado === 'recusar' ? 'Recusando…' : 'Recusar'}
	</Button>
	<Button
		{size}
		disabled={ocupado !== null}
		aria-label={`Aceitar o convite para ${convite.nome}`}
		onclick={() => void responder('aceitar')}
	>
		{ocupado === 'aceitar' ? 'Aceitando…' : 'Aceitar'}
	</Button>
</div>
