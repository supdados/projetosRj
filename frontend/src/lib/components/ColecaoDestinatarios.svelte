<script lang="ts">
	/**
	 * Linha "Compartilhada com" do ColecaoCard: pilha de avatares sobrepostos
	 * (pessoa = círculo de iniciais, área = quadrado com a sigla), "+N" com o
	 * total do servidor e, SÓ para o dono, o marcador de convites pendentes.
	 *
	 * A lista chega pronta de `destinatarios_por_colecao` (regra de quem vê já
	 * aplicada): o dono recebe todos com status; quem participa recebe o dono e
	 * os outros aceitos. Para o dono, pendente ganha ponto âmbar e quem recusou
	 * ou saiu fica em cinza — continua listado (o dono decide se reenvia), mas
	 * sem parecer que tem acesso. O texto completo vai no `title` e no rótulo
	 * acessível da lista.
	 *
	 * Sem rótulo visível de propósito: num card de 4 colunas em tela de
	 * notebook sobram ~220px, e rótulo + 5 avatares + "Pendente" estouravam.
	 * O PRIMEIRO avatar fica por cima (z-index decrescente): as iniciais e o
	 * ponto de pendente (canto inferior direito) não somem sob o vizinho.
	 */
	import AssigneeAvatar from '$lib/components/AssigneeAvatar.svelte';
	import {
		destinatarioSemAcesso,
		pilhaDestinatarios,
		rotuloDestinatario
	} from '$lib/utils/colecaoShares';
	import type { DestinatarioColecao } from '$lib/types/collections';

	interface Props {
		destinatarios: DestinatarioColecao[];
		/** `destinatarios_total` do card (base do "+N"). */
		total: number;
		/** O ator é o dono: vê status (pendente/recusou/saiu) e o marcador. */
		souDono: boolean;
	}

	let { destinatarios, total, souDono }: Props = $props();

	const pilha = $derived(pilhaDestinatarios(destinatarios, total));
	const pendentes = $derived(
		souDono ? pilha.visiveis.filter((d) => d.status === 'pendente').length : 0
	);
	const rotuloLista = $derived.by(() => {
		const nomes = pilha.visiveis.map(rotuloDestinatario).join(', ');
		const resto = pilha.excedente > 0 ? ` e mais ${pilha.excedente}` : '';
		return `${souDono ? 'Compartilhada com' : 'Com acesso'}: ${nomes}${resto}`;
	});
</script>

<!-- flex-wrap: em card estreito o "Pendente" desce em vez de estourar a borda. -->
<div class="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
	<ul class="m-0 flex min-w-0 list-none items-center p-0" aria-label={rotuloLista}>
		{#each pilha.visiveis as destinatario, indice (`${destinatario.tipo}:${destinatario.id}`)}
			{@const inativo = souDono && destinatarioSemAcesso(destinatario) && destinatario.status !== 'pendente'}
			<li
				class="relative flex ring-2 ring-surface {indice > 0 ? '-ml-0.5' : ''} {destinatario.tipo ===
				'orgao'
					? 'rounded-md'
					: 'rounded-full'} {inativo ? 'grayscale' : ''}"
				style:z-index={pilha.visiveis.length - indice}
				title={rotuloDestinatario(destinatario)}
			>
				{#if destinatario.tipo === 'orgao'}
					<!-- Área = retângulo com a sigla inteira (pessoa = círculo de iniciais). -->
					<span
						class="block h-6 min-w-6 max-w-[3.75rem] truncate rounded-md bg-wash-brand px-1.5 text-center text-[9px] font-bold leading-6 text-brand ring-1 ring-border-subtle"
						aria-hidden="true"
					>
						{(destinatario.sigla || destinatario.nome).toUpperCase()}
					</span>
				{:else}
					<AssigneeAvatar name={destinatario.nome} size="sm" title={rotuloDestinatario(destinatario)} />
				{/if}
				{#if souDono && destinatario.status === 'pendente'}
					<span
						class="absolute -bottom-0.5 -right-0.5 h-2 w-2 rounded-full bg-warning ring-2 ring-surface"
						aria-hidden="true"
					></span>
				{/if}
			</li>
		{/each}
		{#if pilha.excedente > 0}
			<li class="ml-1 flex rounded-full" aria-hidden="true">
				<span
					class="grid h-6 min-w-6 place-items-center rounded-full bg-surface-muted px-1 text-[10px] font-semibold leading-none text-text-secondary ring-1 ring-border-subtle"
				>
					+{pilha.excedente}
				</span>
			</li>
		{/if}
	</ul>
	{#if pendentes > 0}
		<span
			class="shrink-0 rounded-sm border border-warning-soft bg-wash-warning px-1.5 py-0.5 text-2xs font-medium text-warning"
		>
			{pendentes === 1 ? 'Pendente' : `${pendentes} pendentes`}
		</span>
	{/if}
</div>
