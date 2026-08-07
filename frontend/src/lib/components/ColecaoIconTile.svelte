<script lang="ts">
	/**
	 * Tile quadrado da identidade visual de uma coleção: wash da família + ícone
	 * duotone na tinta da mesma família (dark mode grátis — o token desloca o
	 * degrau sozinho). Decorativo: o nome acessível vive no card/cabeçalho.
	 *
	 * As classes vêm de um mapa ESTÁTICO por cor porque o Tailwind não compila
	 * classe montada em runtime (`bg-wash-{cor}` não existe).
	 */
	import { COLLECTION_ICONS } from '$lib/icons/collectionIcons';
	import type { CollectionColorId, CollectionIconId } from '$lib/types/collections';

	interface Props {
		icone: CollectionIconId;
		cor: CollectionColorId;
		/** Lado do tile em px (40 no card, 52 no cabeçalho do modal). */
		size?: number;
	}

	let { icone, cor, size = 40 }: Props = $props();

	const toneClass: Record<CollectionColorId, string> = {
		primary: 'bg-wash-brand text-brand',
		success: 'bg-wash-success text-success',
		warning: 'bg-wash-warning text-warning',
		attention: 'bg-wash-attention text-attention',
		danger: 'bg-wash-danger text-danger',
		neutral: 'bg-wash-neutral text-text-secondary'
	};

	// Ícone/cor fora do registry = drift do backend; cai no padrão em vez de sumir.
	const paths = $derived(COLLECTION_ICONS[icone] ?? COLLECTION_ICONS.camadas);
	const tone = $derived(toneClass[cor] ?? toneClass.primary);
	const iconSize = $derived(Math.round(size * 0.55));
</script>

<span
	class="grid shrink-0 place-items-center rounded-md {tone}"
	style:width="{size}px"
	style:height="{size}px"
	aria-hidden="true"
>
	<svg width={iconSize} height={iconSize} viewBox="0 0 24 24" fill="currentColor">
		{#each paths as p (p.d)}
			<path d={p.d} opacity={p.opacity} fill-rule={p.fillRule} />
		{/each}
	</svg>
</span>
