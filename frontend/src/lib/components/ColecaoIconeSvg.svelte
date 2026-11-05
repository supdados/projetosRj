<script lang="ts">
	/**
	 * SVG duotone de um ícone de coleção (registry `collectionIcons.ts`), na
	 * cor do texto (`currentColor`). Base do tile, da capa e da marca d'água —
	 * eram três cópias do mesmo `{#each}` de paths. Decorativo: o nome
	 * acessível vive no card/cabeçalho.
	 */
	import { COLLECTION_ICONS } from '$lib/icons/collectionIcons';
	import type { CollectionIconId } from '$lib/types/collections';

	interface Props {
		icone: CollectionIconId;
		/** Lado em px. */
		size: number;
		class?: string;
	}

	let { icone, size, class: classe = '' }: Props = $props();

	// Ícone fora do registry = drift do backend; cai no padrão em vez de sumir.
	const paths = $derived(COLLECTION_ICONS[icone] ?? COLLECTION_ICONS.camadas);
</script>

<svg
	width={size}
	height={size}
	viewBox="0 0 24 24"
	fill="currentColor"
	class={classe}
	aria-hidden="true"
	focusable="false"
>
	{#each paths as p (p.d)}
		<path d={p.d} opacity={p.opacity} fill-rule={p.fillRule} />
	{/each}
</svg>
