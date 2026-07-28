<script lang="ts">
	/**
	 * Skeleton de "Projetos Pendentes", espelho do estado pronto de
	 * routes/(app)/projetos/pendentes/+page.svelte: mesmo chrome de Card por
	 * projeto (header + tabela de etapas) e mesma grade fixa de colunas — sem
	 * salto de layout na troca loading -> pronto. Cobre só a área de listagem
	 * (header/filtros já renderizam fora do skeleton).
	 */
	import Skeleton from '$lib/components/Skeleton.svelte';

	// Larguras variadas dos títulos de projeto/descrição de etapa — quebra a
	// monotonia das linhas, como conteúdo real de tamanhos diferentes.
	const titleWidths = ['w-2/5', 'w-1/3', 'w-1/2'];
	const etapaWidths = ['w-4/5', 'w-3/5', 'w-2/3'];
</script>

<div aria-hidden="true" class="contents">
	<div class="flex flex-col gap-4">
		{#each { length: 3 } as _, cardIndex (cardIndex)}
			<section class="flex flex-col gap-4 rounded-xl border border-border-subtle bg-surface p-5 shadow-sm">
				<!-- Header: título/órgão (esq) + resumo de janelas (dir), como no PendingProjectCard. -->
				<header class="flex flex-col gap-2 border-b border-border-subtle pb-4 sm:flex-row sm:items-start sm:justify-between">
					<div class="flex min-w-0 flex-col gap-1.5">
						<Skeleton class="h-4 {titleWidths[cardIndex]} rounded" />
						<Skeleton class="h-3 w-32 rounded" />
					</div>
					<Skeleton class="h-3 w-40 rounded" />
				</header>

				<!-- Tabela de etapas: mesma grade fixa de colunas (skel-stage-grid). -->
				<div class="flex flex-col gap-2.5">
					<div class="skel-stage-grid items-center border-b border-border-subtle bg-wash-neutral">
						<span class="px-2 py-2.5"><Skeleton class="h-2.5 w-16 rounded" /></span>
						<span class="flex justify-center px-2 py-2.5"><Skeleton class="h-2.5 w-14 rounded" /></span>
						<span class="flex justify-center px-2 py-2.5"><Skeleton class="h-2.5 w-14 rounded" /></span>
						<span class="flex justify-center px-2 py-2.5"><Skeleton class="h-2.5 w-14 rounded" /></span>
						<span class="flex justify-center px-2 py-2.5"><Skeleton class="h-2.5 w-12 rounded" /></span>
						<span class="flex justify-center px-2 py-2.5"><Skeleton class="h-2.5 w-12 rounded" /></span>
					</div>
					{#each { length: 3 } as _, rowIndex (rowIndex)}
						<div class="skel-stage-grid items-center border-b border-border-subtle last:border-0">
							<span class="px-2 py-2.5"><Skeleton class="h-4 {etapaWidths[rowIndex]} rounded" /></span>
							<span class="flex justify-center px-2 py-2.5"><Skeleton class="h-4 w-16 rounded" /></span>
							<span class="flex justify-center px-2 py-2.5"><Skeleton class="h-4 w-14 rounded" /></span>
							<span class="flex justify-center px-2 py-2.5"><Skeleton class="h-4 w-14 rounded" /></span>
							<span class="flex justify-center px-2 py-2.5"><Skeleton class="h-8 w-[7.25rem] rounded-lg" /></span>
							<span class="flex justify-center px-2 py-2.5"><Skeleton class="h-8 w-[6.5rem] rounded-full" /></span>
						</div>
					{/each}
				</div>
			</section>
		{/each}

		<!-- Pager: mesma faixa horizontal do PaginationBar. -->
		<div class="flex items-center justify-between gap-3 px-1">
			<Skeleton class="h-3.5 w-32 rounded" />
			<div class="flex items-center gap-1.5">
				{#each { length: 5 } as _, i (i)}
					<Skeleton class="h-8 w-8 rounded-lg" />
				{/each}
			</div>
		</div>
	</div>
</div>

<style>
	/* Mesmas larguras fixas de colunas do <colgroup> de stageColumns (scoped no
	   PendingProjectCard, replicado aqui): descrição (1fr) | responsável | início
	   | fim | tarefas | status. */
	.skel-stage-grid {
		display: grid;
		grid-template-columns: minmax(0, 1fr) 18% 7.5rem 7.5rem 8.75rem 9rem;
	}
</style>
