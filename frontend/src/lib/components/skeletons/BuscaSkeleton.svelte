<script lang="ts">
	/**
	 * Skeleton da Busca Global, espelho do estado pronto de
	 * routes/(app)/busca/+page.svelte: mesmo chrome de secao (card rounded-lg +
	 * cabecalho com icone/titulo) e mesma linha de item (titulo + meta, separadas
	 * por border-b). A quebra por tipo real so e conhecida apos o fetch, entao
	 * aqui mostra uma unica secao generica com linhas suficientes para cobrir a
	 * maioria das respostas sem salto de layout.
	 */
	import Skeleton from '$lib/components/Skeleton.svelte';

	// Larguras variadas dos titulos — quebra a monotonia das linhas.
	const titleWidths = ['w-2/5', 'w-3/5', 'w-1/3', 'w-1/2', 'w-2/5', 'w-1/3'];
</script>

<div aria-hidden="true" class="contents">
	<div class="flex flex-col gap-4">
		<section class="overflow-hidden rounded-lg border border-border-subtle bg-surface shadow-sm">
			<div class="flex items-center gap-2 border-b border-border-subtle px-5 py-4">
				<Skeleton class="h-[1.125rem] w-[1.125rem] rounded" />
				<Skeleton class="h-6 w-28 rounded-md" />
			</div>
			<ul class="m-0 flex list-none flex-col p-0">
				{#each { length: 6 } as _, i (i)}
					<li class="border-b border-border-subtle last:border-b-0">
						<span class="flex min-w-0 flex-col gap-1 px-5 py-3">
							<Skeleton class="h-6 {titleWidths[i]} rounded" />
							<Skeleton class="h-4 w-2/5 rounded" />
						</span>
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
