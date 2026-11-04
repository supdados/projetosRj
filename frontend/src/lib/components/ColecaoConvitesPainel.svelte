<script lang="ts">
	/**
	 * Painel "Convites" no topo do índice de Coleções: uma linha por convite
	 * PENDENTE com Recusar/Aceitar. Só metadados (nome, ícone, cor, descrição,
	 * dono, papel, data) — antes do aceite não há projeto, contagem nem
	 * progresso. Os convites ficam FORA do grid e das contagens do índice.
	 *
	 * Lista em vez de cards no grid: o par de botões + data não cabe com folga
	 * num card de 4 colunas, e a lista separa à primeira vista "o que pede
	 * resposta" de "o que já é meu". Mesmo chrome do painel "Projetos da coleção"
	 * da página interna. O nome leva à página do convite (mesmo estado pendente).
	 */
	import { base } from '$app/paths';
	import { slide } from 'svelte/transition';
	import { prefersReducedMotion } from 'svelte/motion';
	import ColecaoIconTile from '$lib/components/ColecaoIconTile.svelte';
	import CountBadge from '$lib/components/CountBadge.svelte';
	import ColecaoConviteBotoes from '$lib/components/ColecaoConviteBotoes.svelte';
	import { procedenciaDoConvite } from '$lib/utils/colecaoShares';
	import { formatIsoDateBRLocalTz } from '$lib/utils/dateFormat';
	import type { DesfechoConvite } from '$lib/utils/conviteColecao';
	import type { ConviteColecao } from '$lib/types/collections';

	interface Props {
		convites: ConviteColecao[];
		onRespondido: (convite: ConviteColecao, desfecho: DesfechoConvite) => void;
	}

	let { convites, onRespondido }: Props = $props();

	const duracao = (ms: number): number => (prefersReducedMotion.current ? 0 : ms);
</script>

<section
	aria-labelledby="colecoes-convites-title"
	class="overflow-hidden rounded-lg border border-brand-soft bg-surface shadow-sm"
	transition:slide={{ duration: duracao(200) }}
>
	<div class="flex items-center px-4 py-3">
		<h2 id="colecoes-convites-title" class="m-0 text-base font-bold text-text-primary">Convites</h2>
		<CountBadge class="ml-2">
			{convites.length} aguardando resposta
		</CountBadge>
	</div>
	<ul class="m-0 list-none p-0">
		{#each convites as convite (convite.id)}
			{@const data = formatIsoDateBRLocalTz(convite.convidado_em)}
			<li
				class="flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-border-subtle px-4 py-3"
				transition:slide={{ duration: duracao(180) }}
			>
				<div class="flex min-w-0 flex-1 basis-64 items-center gap-3">
					<ColecaoIconTile icone={convite.icone} cor={convite.cor} size={36} />
					<div class="flex min-w-0 flex-1 flex-col">
						<a
							href={`${base}/colecoes/${convite.id}`}
							title={convite.nome}
							class="min-w-0 self-start truncate rounded-sm text-md font-semibold text-text-primary no-underline transition-colors duration-fast hover:text-brand focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
						>
							{convite.nome}
						</a>
						<span class="min-w-0 truncate text-xs text-text-muted">
							{procedenciaDoConvite(convite)}{convite.descricao ? ` · ${convite.descricao}` : ''}
						</span>
					</div>
				</div>
				<div class="ml-auto flex items-center gap-4">
					{#if data}
						<time
							datetime={convite.convidado_em ?? undefined}
							title={`Convite recebido em ${data}`}
							class="shrink-0 font-mono text-xs text-text-muted"
						>
							{data}
						</time>
					{/if}
					<ColecaoConviteBotoes {convite} onRespondido={(d) => onRespondido(convite, d)} />
				</div>
			</li>
		{/each}
	</ul>
</section>
