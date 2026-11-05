<script lang="ts">
	/**
	 * Pílula "N áreas" da capa (ícone de órgão + rótulo). Com `detalhe`, vira
	 * botão: hover OU foco abre a lista "SIGLA · N projetos" (tooltip escuro do
	 * design 2b) — por teclado e por toque também (o toque foca o botão). Fica
	 * acima do link sobreposto do card, então clicar nela não navega.
	 * Fundo: `.bg-capa-veu` (`app.css`), a superfície a 75% sobre o wash.
	 */
	import ColecaoIconeSvg from '$lib/components/ColecaoIconeSvg.svelte';
	import { tomDaCapa } from '$lib/icons/collectionIdentity';
	import { nomeDaArea, plural, rotuloAreas } from '$lib/utils/colecaoCapa';
	import type { AreaColecao, CollectionColorId } from '$lib/types/collections';

	interface Props {
		areas: readonly AreaColecao[];
		cor: CollectionColorId;
		/** Abre a lista de áreas no hover/foco (card do índice). */
		detalhe?: boolean;
	}

	let { areas, cor, detalhe = false }: Props = $props();

	const tom = $derived(tomDaCapa(cor));
	const rotulo = $derived(rotuloAreas(areas));
	let aberta = $state(false);

	const pilulaCls =
		'bg-capa-veu inline-flex h-6 items-center gap-1 rounded-full px-2.5 text-xs font-semibold text-text-primary';
</script>

{#if detalhe}
	<div
		class="relative"
		role="presentation"
		onmouseenter={() => (aberta = true)}
		onmouseleave={() => (aberta = false)}
	>
		<button
			type="button"
			class="{pilulaCls} focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
			aria-expanded={aberta}
			aria-label={`${rotulo}: ver projetos por área`}
			onfocus={() => (aberta = true)}
			onblur={() => (aberta = false)}
		>
			<ColecaoIconeSvg icone="orgao" size={15} class={tom.tinta} />
			{rotulo}
		</button>
		{#if aberta}
			<ul
				class="absolute right-0 top-[calc(100%+6px)] z-30 m-0 flex min-w-[190px] list-none flex-col gap-1.5 rounded-lg bg-neutral-900 px-3 py-2.5 shadow-popover"
			>
				{#each areas as area (area.sigla ?? '∅')}
					<li class="flex justify-between gap-4 text-xs">
						<span class="font-semibold text-white">{nomeDaArea(area)}</span>
						<span class="text-neutral-300">{plural(area.projetos, 'projeto')}</span>
					</li>
				{/each}
			</ul>
		{/if}
	</div>
{:else}
	<span class={pilulaCls}>
		<ColecaoIconeSvg icone="orgao" size={15} class={tom.tinta} />
		{rotulo}
	</span>
{/if}
