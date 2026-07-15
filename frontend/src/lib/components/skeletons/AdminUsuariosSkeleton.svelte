<script lang="ts">
	/**
	 * Skeleton da lista de Admin > Usuários, espelho do cartao de tabela
	 * (.rounded-xl border bg-surface) do estado pronto de admin/usuarios/+page.svelte:
	 * mesmo cabecalho de colunas e 6 linhas com a mesma grade de celulas — a
	 * transicao loading -> pronto acontece sem salto de layout.
	 */
	import Skeleton from '$lib/components/Skeleton.svelte';
</script>

<div aria-hidden="true" class="overflow-hidden rounded-xl border border-border-subtle bg-surface">
	<div class="overflow-x-auto">
		<table class="w-full border-collapse align-middle text-sm">
			<thead>
				<tr class="border-b border-border-subtle bg-surface-muted text-left">
					<th class="whitespace-nowrap px-3 py-2.5"><Skeleton class="h-2.5 w-6 rounded" /></th>
					<th class="whitespace-nowrap px-3 py-2.5"><Skeleton class="h-2.5 w-24 rounded" /></th>
					<th class="whitespace-nowrap px-3 py-2.5"><Skeleton class="h-2.5 w-14 rounded" /></th>
					<th class="whitespace-nowrap px-3 py-2.5"><Skeleton class="h-2.5 w-14 rounded" /></th>
					<th class="w-[160px] whitespace-nowrap px-3 py-2.5"><Skeleton class="h-2.5 w-20 rounded" /></th>
					<th class="whitespace-nowrap px-3 py-2.5"><Skeleton class="h-2.5 w-16 rounded" /></th>
					<th class="whitespace-nowrap px-3 py-2.5 text-center"><Skeleton class="mx-auto h-2.5 w-10 rounded" /></th>
					<th class="whitespace-nowrap px-3 py-2.5 text-center"><Skeleton class="mx-auto h-2.5 w-10 rounded" /></th>
				</tr>
			</thead>
			<tbody>
				{#each { length: 6 } as _, i (i)}
					<tr class="border-t border-border-subtle">
						<td class="px-3 py-2.5 align-middle"><Skeleton class="h-4 w-5 rounded" /></td>
						<td class="px-3 py-2.5 align-middle"><Skeleton class="h-4 w-32 rounded" /></td>
						<td class="px-3 py-2.5 align-middle"><Skeleton class="h-4 w-24 rounded" /></td>
						<td class="px-3 py-2.5 align-middle"><Skeleton class="h-4 w-20 rounded" /></td>
						<td class="max-w-[160px] px-3 py-2.5 align-middle"><Skeleton class="h-4 w-28 rounded" /></td>
						<td class="px-3 py-2.5 align-middle"><Skeleton class="h-5 w-32 rounded-full" /></td>
						<td class="px-3 py-2.5 text-center align-middle"><Skeleton class="mx-auto h-6 w-16 rounded-md" /></td>
						<td class="px-3 py-2.5 text-center align-middle">
							<div class="inline-flex items-center gap-1">
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
