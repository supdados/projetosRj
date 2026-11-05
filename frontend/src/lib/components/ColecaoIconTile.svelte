<script lang="ts">
	/**
	 * Tile quadrado da identidade visual de uma coleção: wash da família + ícone
	 * duotone na tinta da mesma família (dark mode grátis — o token desloca o
	 * degrau sozinho). Decorativo: o nome acessível vive no card/cabeçalho.
	 *
	 * As classes vêm do mapa ESTÁTICO `COLECAO_CAPA_TOM` (o mesmo da capa)
	 * porque o Tailwind não compila classe montada em runtime.
	 */
	import ColecaoIconeSvg from '$lib/components/ColecaoIconeSvg.svelte';
	import { tomDaCapa } from '$lib/icons/collectionIdentity';
	import type { CollectionColorId, CollectionIconId } from '$lib/types/collections';

	interface Props {
		icone: CollectionIconId;
		cor: CollectionColorId;
		/** Lado do tile em px (40 no card, 52 no cabeçalho do modal). */
		size?: number;
	}

	let { icone, cor, size = 40 }: Props = $props();

	const tom = $derived(tomDaCapa(cor));
	const iconSize = $derived(Math.round(size * 0.55));
</script>

<span
	class="grid shrink-0 place-items-center rounded-md {tom.wash} {tom.tinta}"
	style:width="{size}px"
	style:height="{size}px"
	aria-hidden="true"
>
	<ColecaoIconeSvg {icone} size={iconSize} />
</span>
