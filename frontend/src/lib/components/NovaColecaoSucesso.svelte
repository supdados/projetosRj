<script lang="ts">
	/**
	 * Tela de sucesso do modal Nova coleção (design "Coleções 3a"): a capa da
	 * coleção recém-criada "cai" na mesa levemente girada, com o selo de visto
	 * na cor da família, e embaixo os números (projetos · áreas · etapas), quem
	 * enxerga e os dois caminhos — criar outra ou abrir a coleção.
	 *
	 * Os números vêm do `ColecaoResumo` devolvido pelo POST (rollup do backend,
	 * só projetos visíveis); o recibo de visibilidade é montado pelo modal antes
	 * de limpar o formulário. Animações só sem `prefers-reduced-motion`.
	 */
	import { onMount, tick } from 'svelte';
	import Button from '$lib/components/Button.svelte';
	import ColecaoAndamento from '$lib/components/ColecaoAndamento.svelte';
	import ColecaoAreasPill from '$lib/components/ColecaoAreasPill.svelte';
	import ColecaoCapa from '$lib/components/ColecaoCapa.svelte';
	import { tomDaCapa } from '$lib/icons/collectionIdentity';
	import { plural, quantasAreas } from '$lib/utils/colecaoCapa';
	import type { ColecaoResumo } from '$lib/types/collections';

	interface Props {
		titleId: string;
		colecao: ColecaoResumo;
		/** "Só você vê esta coleção" / "Convite enviado para …". */
		recibo: string;
		pessoal: boolean;
		/** Destino de "Abrir coleção". */
		href: string;
		onFechar: () => void;
		onCriarOutra: () => void;
	}

	let { titleId, colecao, recibo, pessoal, href, onFechar, onCriarOutra }: Props = $props();

	const tom = $derived(tomDaCapa(colecao.cor));
	const areas = $derived(colecao.areas ?? []);
	const rotulo = (n: number, singular: string): string => (n === 1 ? singular : `${singular}s`);
	const numeros = $derived.by(() => {
		const totalAreas = quantasAreas(areas);
		return [
			{ chave: 'projetos', valor: colecao.projetos, rotulo: rotulo(colecao.projetos, 'projeto') },
			{ chave: 'areas', valor: totalAreas, rotulo: rotulo(totalAreas, 'área') },
			{ chave: 'etapas', valor: colecao.etapas_total, rotulo: rotulo(colecao.etapas_total, 'etapa') }
		];
	});

	let tituloEl = $state<HTMLHeadingElement | null>(null);

	// O botão "Criar coleção" que tinha o foco saiu do DOM: o título o recebe,
	// e o leitor de tela anuncia "Coleção criada".
	onMount(() => {
		void tick().then(() => tituloEl?.focus());
	});
</script>

<div class="relative flex justify-center overflow-hidden bg-surface-muted pb-[34px] pt-10">
	<button
		type="button"
		onclick={onFechar}
		aria-label="Fechar"
		class="absolute right-4 top-3.5 grid h-8 w-8 place-items-center rounded-full text-text-secondary transition-colors duration-fast hover:bg-border-hairline hover:text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
	>
		<svg viewBox="0 0 20 20" class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true">
			<path d="m5 5 10 10M15 5 5 15" stroke-linecap="round" />
		</svg>
	</button>

	<div class="capa-pop relative w-[264px] -rotate-[2.5deg]" aria-hidden="true">
		<div class="overflow-hidden rounded-xl border border-border-subtle bg-surface shadow-lg">
			<ColecaoCapa
				icone={colecao.icone}
				cor={colecao.cor}
				nome={colecao.nome}
				meta={plural(colecao.projetos, 'projeto')}
			>
				{#snippet acoes()}
					{#if areas.length > 0}
						<ColecaoAreasPill {areas} cor={colecao.cor} />
					{/if}
				{/snippet}
			</ColecaoCapa>
			<div class="px-4 pb-4 pt-3.5">
				<ColecaoAndamento etapas={colecao} />
			</div>
		</div>
		<span
			class="selo absolute -right-3.5 -top-3.5 grid h-10 w-10 place-items-center rounded-full text-white ring-4 ring-surface-muted {tom.selo}"
		>
			<svg viewBox="0 0 24 24" class="h-6 w-6" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
				<path d="M5 12.5l4.5 4.5L19 7.5" />
			</svg>
		</span>
	</div>
</div>

<div class="sucesso-texto flex flex-col items-center px-6 pb-7 pt-6 text-center sm:px-8">
	<h2
		id={titleId}
		bind:this={tituloEl}
		tabindex="-1"
		class="m-0 font-heading text-xl font-bold text-text-primary focus:outline-none"
	>
		Coleção criada
	</h2>
	<p class="m-0 mt-1.5 max-w-[380px] text-md leading-relaxed text-text-secondary [text-wrap:pretty]">
		{colecao.nome} já está nas suas coleções.
	</p>

	<dl class="m-0 mt-5 grid w-full grid-cols-3 rounded-lg border border-border-subtle">
		{#each numeros as numero, i (numero.chave)}
			<div class="flex flex-col gap-0.5 px-2 py-3 {i > 0 ? 'border-l border-border-subtle' : ''}">
				<dt class="order-2 text-sm text-text-muted">{numero.rotulo}</dt>
				<dd class="order-1 m-0 text-2xl font-bold tabular-nums {tom.tinta}">{numero.valor}</dd>
			</div>
		{/each}
	</dl>

	<p class="m-0 mt-3.5 flex items-center gap-1.5 text-sm text-text-muted">
		<i class="fas {pessoal ? 'fa-lock' : 'fa-user-group'} text-xs" aria-hidden="true"></i>
		{recibo}
	</p>

	<div class="mt-5 grid w-full grid-cols-2 gap-2.5">
		<Button variant="secondary" block onclick={onCriarOutra}>Criar outra</Button>
		<Button block {href}>
			Abrir coleção
			<i class="fas fa-arrow-right ml-1.5 text-xs" aria-hidden="true"></i>
		</Button>
	</div>
</div>

<style>
	@media (prefers-reduced-motion: no-preference) {
		.capa-pop {
			animation: capa-pop 0.55s cubic-bezier(0.2, 1.3, 0.4, 1) 0.12s both;
		}
		.selo {
			animation: selo-in 0.35s cubic-bezier(0.2, 1.6, 0.4, 1) 0.5s both;
		}
		.sucesso-texto {
			animation: sucesso-fade 0.4s ease-out 0.35s both;
		}
	}

	@keyframes capa-pop {
		0% {
			opacity: 0;
			transform: scale(0.6) rotate(-10deg);
		}
		60% {
			opacity: 1;
		}
		100% {
			opacity: 1;
			transform: scale(1) rotate(-2.5deg);
		}
	}

	@keyframes selo-in {
		from {
			transform: scale(0);
		}
		to {
			transform: scale(1);
		}
	}

	@keyframes sucesso-fade {
		from {
			opacity: 0;
			transform: translateY(8px);
		}
		to {
			opacity: 1;
			transform: none;
		}
	}
</style>
