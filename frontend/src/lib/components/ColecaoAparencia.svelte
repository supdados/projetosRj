<script lang="ts">
	/**
	 * Bloco "Aparência" da coleção (design "Coleções 3a"): as 6 famílias de cor
	 * em círculos e os 12 ícones numa grade 6×2, num só quadro. Usado no modal
	 * Nova coleção (onde a capa acima reage na hora) e no Editar coleção.
	 *
	 * Ícone ativo em azul da marca, independente da cor escolhida — quem mostra
	 * a cor é a capa; a grade só diz qual ícone está marcado.
	 */
	import ColecaoIconeSvg from '$lib/components/ColecaoIconeSvg.svelte';
	import { COLECAO_COR_OPTIONS, COLECAO_ICONE_OPTIONS } from '$lib/icons/collectionIdentity';
	import type { CollectionColorId, CollectionIconId } from '$lib/types/collections';

	interface Props {
		icone: CollectionIconId;
		cor: CollectionColorId;
		/** Prefixo dos ids (dois modais podem coexistir no DOM). */
		idPrefix: string;
	}

	let { icone = $bindable(), cor = $bindable(), idPrefix }: Props = $props();

	const focoCls =
		'focus:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-1';
</script>

<div class="flex flex-col gap-2">
	<span id="{idPrefix}-aparencia" class="text-sm font-semibold text-text-secondary">Aparência</span>
	<div
		class="flex flex-col gap-3 rounded-lg border border-border-subtle p-3"
		role="group"
		aria-labelledby="{idPrefix}-aparencia"
	>
		<div role="group" aria-label="Cor" class="flex justify-between">
			{#each COLECAO_COR_OPTIONS as opcao (opcao.id)}
				{@const ativo = cor === opcao.id}
				<button
					type="button"
					aria-pressed={ativo}
					aria-label={opcao.label}
					title={opcao.label}
					onclick={() => (cor = opcao.id)}
					class="grid h-9 w-9 place-items-center rounded-full border-2 transition-colors duration-fast {focoCls} {ativo
						? opcao.ativo
						: 'border-transparent hover:border-border-subtle'}"
				>
					<span class="h-6 w-6 rounded-full {opcao.dot}" aria-hidden="true"></span>
				</button>
			{/each}
		</div>

		<div class="h-px bg-border-hairline" aria-hidden="true"></div>

		<div role="group" aria-label="Ícone" class="grid grid-cols-6 gap-1.5">
			{#each COLECAO_ICONE_OPTIONS as opcao (opcao.id)}
				{@const ativo = icone === opcao.id}
				<button
					type="button"
					aria-pressed={ativo}
					aria-label={opcao.label}
					title={opcao.label}
					onclick={() => (icone = opcao.id)}
					class="grid h-10 place-items-center rounded-md transition-colors duration-fast {focoCls} {ativo
						? 'bg-wash-brand text-brand'
						: 'text-text-secondary hover:bg-surface-muted hover:text-text-primary'}"
				>
					<ColecaoIconeSvg icone={opcao.id} size={21} />
				</button>
			{/each}
		</div>
	</div>
</div>
