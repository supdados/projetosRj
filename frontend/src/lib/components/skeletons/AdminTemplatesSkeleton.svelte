<script lang="ts">
	/**
	 * Skeleton da lista de "Admin > Modelos de Etapas", espelho do estado pronto
	 * de admin/templates/+page.svelte (view === 'list'): mesmo chrome de tabela
	 * (cabecalho + linhas) e rodape de paginacao, sem salto de layout.
	 */
	import Skeleton from '$lib/components/Skeleton.svelte';

	// Larguras variadas do nome do modelo — quebra a monotonia das linhas.
	const nameWidths = ['w-40', 'w-32', 'w-48', 'w-28', 'w-36', 'w-44'];
</script>

<div aria-hidden="true" class="contents">
	<div class="overflow-hidden rounded-xl border border-border-subtle bg-surface shadow-sm">
		<div class="overflow-x-auto">
			<table class="w-full border-collapse text-sm">
				<thead>
					<tr class="border-b border-border-subtle bg-surface-muted text-left">
						<th class="px-4 py-3"><Skeleton class="h-2.5 w-16 rounded" /></th>
						<th class="px-4 py-3"><Skeleton class="h-2.5 w-12 rounded" /></th>
						<th class="px-4 py-3"><Skeleton class="h-2.5 w-14 rounded" /></th>
						<th class="hidden px-4 py-3 lg:table-cell"><Skeleton class="h-2.5 w-14 rounded" /></th>
						<th class="px-4 py-3"><Skeleton class="h-2.5 w-14 rounded" /></th>
						<th class="px-4 py-3"><Skeleton class="h-2.5 w-20 rounded" /></th>
						<th class="px-4 py-3 pr-5"><span class="sr-only">Ações</span></th>
					</tr>
				</thead>
				<tbody>
					{#each { length: 6 } as _, i (i)}
						<tr class="border-b border-border-subtle last:border-0">
							<td class="min-w-[280px] px-4 py-3 align-middle">
								<div class="flex items-center gap-3">
									<Skeleton class="h-[38px] w-[38px] shrink-0 rounded-lg" />
									<div class="flex min-w-0 flex-col gap-1.5">
										<Skeleton class="h-3.5 {nameWidths[i]} rounded" />
										<Skeleton class="h-2.5 w-24 rounded" />
									</div>
								</div>
							</td>
							<td class="px-4 py-3 align-middle"><Skeleton class="h-3.5 w-6 rounded" /></td>
							<td class="px-4 py-3 align-middle"><Skeleton class="h-3.5 w-10 rounded" /></td>
							<td class="hidden px-4 py-3 align-middle lg:table-cell">
								<Skeleton class="h-7 w-16 rounded" />
							</td>
							<td class="px-4 py-3 align-middle"><Skeleton class="h-3.5 w-14 rounded" /></td>
							<td class="min-w-[160px] px-4 py-3 align-middle">
								<Skeleton class="h-3.5 w-20 rounded" />
								<Skeleton class="mt-1 h-2.5 w-16 rounded" />
							</td>
							<td class="px-4 py-3 pr-5 align-middle">
								<div class="flex items-center justify-end gap-1">
									<Skeleton class="h-8 w-8 rounded-md" />
									<Skeleton class="h-8 w-8 rounded-md" />
								</div>
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	</div>

	<footer class="flex flex-wrap items-center justify-between gap-3 px-1 pt-3">
		<Skeleton class="h-3.5 w-48 rounded" />
		<div class="flex items-center gap-1">
			<Skeleton class="h-8 w-8 rounded-md" />
			<Skeleton class="h-8 w-8 rounded-md" />
			<Skeleton class="h-8 w-8 rounded-md" />
			<Skeleton class="h-8 w-8 rounded-md" />
		</div>
	</footer>
</div>
