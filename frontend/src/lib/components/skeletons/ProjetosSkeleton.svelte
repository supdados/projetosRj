<script lang="ts">
	/**
	 * Skeleton da tela "Todos os Projetos", espelho EXATO do estado pronto de
	 * routes/(app)/projetos/+page.svelte: mesmo chrome de card, cabecalho de
	 * tabela e linhas — a transicao loading -> pronto acontece sem salto de
	 * layout. So aparece na 1a visita (sem cache SWR para os filtros correntes).
	 */
	import Skeleton from '$lib/components/Skeleton.svelte';

	// Larguras variadas dos titulos — quebra a monotonia das linhas.
	const titleWidths = ['w-3/5', 'w-2/5', 'w-4/5', 'w-1/2', 'w-3/4', 'w-2/5'];
</script>

<div aria-hidden="true" class="contents">
	<!-- Tabela-card: mesma estrutura de bordas/sombra/cabecalho da tela pronta. -->
	<div class="overflow-hidden rounded-lg border border-border-subtle bg-surface shadow-sm">
		<div class="overflow-x-auto">
			<table class="m-0 w-full min-w-[980px] border-separate border-spacing-0 text-sm">
				<thead>
					<tr class="text-left text-text-muted">
						<th class="w-16 border-b border-border-subtle bg-surface-muted px-2.5 py-2"
							><span class="flex justify-center"><Skeleton class="h-2.5 w-5 rounded" /></span
							></th
						>
						<th class="min-w-[220px] border-b border-border-subtle bg-surface-muted px-2.5 py-2"
							><Skeleton class="h-2.5 w-14 rounded" /></th
						>
						<th class="border-b border-border-subtle bg-surface-muted px-2.5 py-2"
							><span class="flex justify-center"><Skeleton class="h-2.5 w-10 rounded" /></span
							></th
						>
						<th class="border-b border-border-subtle bg-surface-muted px-2.5 py-2"
							><span class="flex justify-center"><Skeleton class="h-2.5 w-14 rounded" /></span
							></th
						>
						<th class="border-b border-border-subtle bg-surface-muted px-2.5 py-2"
							><span class="flex justify-center"><Skeleton class="h-2.5 w-10 rounded" /></span
							></th
						>
						<th class="border-b border-border-subtle bg-surface-muted px-2.5 py-2"
							><span class="flex justify-center"><Skeleton class="h-2.5 w-16 rounded" /></span
							></th
						>
						<th class="border-b border-border-subtle bg-surface-muted px-2.5 py-2"
							><Skeleton class="h-2.5 w-16 rounded" /></th
						>
						<th class="border-b border-border-subtle bg-surface-muted px-2.5 py-2"
							><Skeleton class="h-2.5 w-14 rounded" /></th
						>
						<th class="border-b border-border-subtle bg-surface-muted px-2.5 py-2"
							><span class="flex justify-center"><Skeleton class="h-2.5 w-10 rounded" /></span
							></th
						>
						<th class="w-28 border-b border-border-subtle bg-surface-muted px-2.5 py-2"
							><span class="flex justify-center"><Skeleton class="h-2.5 w-10 rounded" /></span
							></th
						>
					</tr>
				</thead>
				<tbody>
					{#each { length: 8 } as _, i (i)}
						<tr>
							<td class="border-t border-border-subtle px-2.5 py-2.5 text-center align-middle">
								<span class="inline-flex justify-center"><Skeleton class="h-3.5 w-5 rounded" /></span>
							</td>
							<td class="border-t border-border-subtle px-2.5 py-2.5 align-middle">
								<Skeleton class="h-4 {titleWidths[i % titleWidths.length]} rounded" />
							</td>
							<td class="border-t border-border-subtle px-2.5 py-2.5 text-center align-middle">
								<span class="inline-flex justify-center"><Skeleton class="h-3 w-10 rounded" /></span>
							</td>
							<td class="border-t border-border-subtle px-2.5 py-2.5 text-center align-middle">
								<span class="inline-flex justify-center"><Skeleton class="h-3 w-14 rounded" /></span>
							</td>
							<td class="border-t border-border-subtle px-2.5 py-2.5 text-center align-middle">
								<span class="inline-flex justify-center"><Skeleton class="h-3 w-16 rounded" /></span>
							</td>
							<td class="border-t border-border-subtle px-2.5 py-2.5 text-center align-middle">
								<span class="inline-flex justify-center"><Skeleton class="h-3 w-16 rounded" /></span>
							</td>
							<td class="border-t border-border-subtle px-2.5 py-2.5 align-middle">
								<Skeleton class="h-3.5 w-16 rounded" />
							</td>
							<td class="border-t border-border-subtle px-2.5 py-2.5 align-middle">
								<Skeleton class="h-3.5 w-16 rounded" />
							</td>
							<td class="border-t border-border-subtle px-2.5 py-2.5 text-center align-middle">
								<span class="inline-flex justify-center"><Skeleton class="h-3 w-8 rounded" /></span>
							</td>
							<td class="border-t border-border-subtle px-2.5 py-2.5 text-center align-middle">
								<span class="inline-flex items-center justify-center gap-1.5">
									<Skeleton class="h-8 w-8 rounded-md" />
									<Skeleton class="h-8 w-8 rounded-md" />
								</span>
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	</div>

	<!-- Paginacao: mesma faixa de altura/posicao do PaginationBar pronto. -->
	<div class="flex items-center justify-between gap-3 px-1 py-1">
		<Skeleton class="h-3.5 w-32 rounded" />
		<div class="flex items-center gap-1.5">
			{#each { length: 5 } as _, i (i)}
				<Skeleton class="h-8 w-8 rounded-md" />
			{/each}
		</div>
	</div>
</div>
