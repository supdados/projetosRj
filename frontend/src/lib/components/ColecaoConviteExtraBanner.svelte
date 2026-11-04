<script lang="ts">
	/**
	 * Convite pendente para quem JÁ participa da coleção (ex.: era Leitor e a
	 * área recebeu um share de Editor). Nesse estado `.../projetos` responde
	 * 200, então o estado "convite" da página (que nasce do 404) nunca aparece:
	 * sem este banner, o toast "Ver convite", o "Responder" do sino e a própria
	 * notificação levariam a uma página sem Aceitar/Recusar, e o ponto do sino
	 * ficaria aceso.
	 *
	 * Gatilho: o resumo do sino lista esta coleção (`deveProcurarConviteExtra`)
	 * — só então busca `GET .../convite` (404 = nada pendente, silencioso). Os
	 * projetos continuam na tela. Aceitar sobe o papel e chama `onAceito` (a
	 * página recarrega tudo); recusar ou "não está mais disponível" só fecha o
	 * banner — a pessoa fica na página com o acesso que já tinha.
	 */
	import { slide } from 'svelte/transition';
	import { prefersReducedMotion } from 'svelte/motion';
	import StateBanner from '$lib/components/StateBanner.svelte';
	import ColecaoConviteBotoes from '$lib/components/ColecaoConviteBotoes.svelte';
	import { fetchConvite } from '$lib/api/collections';
	import { notificationSummary } from '$lib/stores/notificationSummary';
	import { textoDoConviteExtra } from '$lib/utils/colecaoShares';
	import {
		deveProcurarConviteExtra,
		reacaoAoConviteExtra,
		type DesfechoConvite
	} from '$lib/utils/conviteColecao';
	import type { ConviteColecao, PapelColecao } from '$lib/types/collections';

	interface Props {
		collectionId: number;
		/** Papel válido de hoje nesta coleção (o dono nunca recebe convite). */
		papelAtual: PapelColecao;
		/** Aceitou: o papel mudou e a página precisa recarregar dados e cronograma. */
		onAceito: () => void;
	}

	let { collectionId, papelAtual, onAceito }: Props = $props();

	let convite = $state<ConviteColecao | null>(null);

	const procurar = $derived(
		deveProcurarConviteExtra(papelAtual, collectionId, $notificationSummary)
	);
	const texto = $derived(convite ? textoDoConviteExtra(convite, papelAtual) : null);
	const duracao = (ms: number): number => (prefersReducedMotion.current ? 0 : ms);

	// Re-roda só quando o gatilho ou o id mudam (o resumo novo a cada ~60 s com
	// o mesmo conteúdo não refaz o GET). Respondido em qualquer tela, o convite
	// sai do resumo e o banner some sozinho.
	$effect(() => {
		convite = null;
		if (!procurar) return;
		const controller = new AbortController();
		fetchConvite(collectionId, controller.signal)
			.then((achado) => {
				if (!controller.signal.aborted) convite = achado;
			})
			.catch(() => {
				// 404 = nada pendente para mim; outra falha deixa o painel do índice como caminho.
			});
		return () => controller.abort();
	});

	function onRespondido(desfecho: DesfechoConvite): void {
		const reacao = reacaoAoConviteExtra(desfecho);
		if (reacao === 'manter') return;
		convite = null;
		if (reacao === 'recarregar') onAceito();
	}
</script>

{#if convite && texto}
	<div transition:slide={{ duration: duracao(200) }}>
		<StateBanner tone="info" title={texto.title} description={texto.description}>
			{#snippet actions()}
				{#if convite}
					<ColecaoConviteBotoes {convite} mantemAcesso {onRespondido} />
				{/if}
			{/snippet}
		</StateBanner>
	</div>
{/if}
