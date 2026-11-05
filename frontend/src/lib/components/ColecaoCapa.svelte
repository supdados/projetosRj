<script lang="ts">
	/**
	 * CAPA de uma coleção (design "Coleções 2b"): faixa no wash da família com o
	 * ícone no canto, a marca d'água do mesmo ícone em 13% e o nome embaixo.
	 * Mesma peça no card do índice, no leque do estado vazio e na tela de
	 * sucesso do modal Nova coleção. O topo do modal é a versão EDITÁVEL desta
	 * capa (`ColecaoCapaEditavel`), não esta.
	 *
	 * `acoes` ocupa o canto superior direito (pílula de áreas, kebab, badge) e
	 * fica acima do link sobreposto do card (`z-20`). Só a marca d'água é
	 * recortada (camada própria com `overflow-hidden`): o tooltip da pílula
	 * precisa vazar pela borda da capa. `class` arredonda o topo no card.
	 */
	import type { Snippet } from 'svelte';
	import ColecaoIconeSvg from '$lib/components/ColecaoIconeSvg.svelte';
	import { tomDaCapa } from '$lib/icons/collectionIdentity';
	import type { CollectionColorId, CollectionIconId } from '$lib/types/collections';

	interface Props {
		icone: CollectionIconId;
		cor: CollectionColorId;
		nome: string;
		/** Linha sob o nome (ex.: "6 projetos"); ausente = só o nome. */
		meta?: string;
		/** `md` = card do índice (124px); `sm` = cartas do leque do estado vazio. */
		tamanho?: 'md' | 'sm';
		acoes?: Snippet;
		/** Arredondamento do topo (ex.: `rounded-t-[15px]` dentro do card). */
		class?: string;
	}

	let { icone, cor, nome, meta, tamanho = 'md', acoes, class: classe = '' }: Props = $props();

	const tom = $derived(tomDaCapa(cor));
	const md = $derived(tamanho === 'md');
</script>

<div
	class="relative flex shrink-0 flex-col justify-between {tom.wash} {classe} {md
		? 'h-[124px] p-4'
		: 'h-24 p-3.5'}"
>
	<!-- Marca d'água: o mesmo ícone, grande e vazando pelo canto (recortado). -->
	<div class="pointer-events-none absolute inset-0 overflow-hidden {classe}">
		<ColecaoIconeSvg
			{icone}
			size={md ? 130 : 100}
			class="absolute opacity-[.13] {tom.tinta} {md
				? '-bottom-[26px] -right-[14px]'
				: '-bottom-[22px] -right-[12px]'}"
		/>
	</div>
	<ColecaoIconeSvg {icone} size={md ? 26 : 22} class="relative {tom.tinta}" />
	<div class="relative flex max-w-[85%] flex-col gap-0.5">
		<span
			class="line-clamp-2 font-bold leading-tight text-text-primary [text-wrap:balance] {md
				? 'text-[1.0625rem]'
				: 'text-md'}"
			title={nome}
		>
			{nome}
		</span>
		{#if meta}
			<span class="truncate text-xs text-text-secondary">{meta}</span>
		{/if}
	</div>
	{#if acoes}
		<div class="absolute right-3.5 top-3.5 z-20 flex items-center gap-1.5">
			{@render acoes()}
		</div>
	{/if}
</div>
