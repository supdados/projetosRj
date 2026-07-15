<script lang="ts">
	/**
	 * Skeleton da Busca Global, espelho do estado pronto de
	 * routes/(app)/busca/+page.svelte: mesmo chrome de secao (card + cabecalho
	 * com pilula de contagem) e mesma estrutura de item de lista (pilula de
	 * tipo + titulo + linha de meta). A quebra por tipo real so e conhecida
	 * apos o fetch, entao aqui mostra uma unica secao generica com linhas
	 * suficientes para cobrir a maioria das respostas sem salto de layout.
	 */
	import Skeleton from '$lib/components/Skeleton.svelte';

	// Larguras variadas dos titulos — quebra a monotonia das linhas.
	const titleWidths = ['w-2/5', 'w-3/5', 'w-1/3', 'w-1/2', 'w-2/5', 'w-1/3'];
</script>

<div aria-hidden="true" class="contents">
	<div class="flex flex-col gap-4">
		<section class="overflow-hidden rounded-xl border border-border-subtle bg-surface shadow-token">
			<div class="flex items-center justify-between gap-3 border-b border-border-subtle px-5 py-4">
				<Skeleton class="h-[1.125rem] w-28 rounded-md" />
				<Skeleton class="h-5 w-8 rounded-md" />
			</div>
			<ul class="flex flex-col">
				{#each { length: 6 } as _, i (i)}
					<li class="mx-1.5 my-1 flex items-start justify-between gap-3 rounded-md border border-border-subtle px-3 py-3">
						<span class="flex min-w-0 flex-1 flex-col gap-1.5">
							<span class="flex min-w-0 items-center gap-1.5">
								<Skeleton class="h-5 w-16 rounded-full" />
								<Skeleton class="h-4 {titleWidths[i]} rounded" />
							</span>
							<Skeleton class="h-3 w-2/5 rounded" />
						</span>
						<Skeleton class="h-4 w-4 shrink-0 rounded" />
					</li>
				{/each}
			</ul>
		</section>

		<!-- Barra de paginacao (aparece so com >1 pagina no estado pronto; mantida
			 aqui para nao dar salto quando a busca tiver muitos resultados). -->
		<div class="flex items-center justify-between gap-3 rounded-lg border border-border-subtle bg-surface px-3 py-2 shadow-sm">
			<Skeleton class="h-4 w-40 rounded" />
			<Skeleton class="h-8 w-52 rounded-md" />
		</div>
	</div>
</div>
