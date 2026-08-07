<script lang="ts">
	/**
	 * Skeleton da página interna da coleção (/colecoes/<id>), espelho do estado
	 * pronto: breadcrumb + header-card com linha de meta + 4 KPIs + tabela-card
	 * de projetos. Cobre também o header porque o nome da coleção só chega com o
	 * fetch. Só aparece na 1ª visita (sem cache SWR do id corrente).
	 */
	import Skeleton from '$lib/components/Skeleton.svelte';

	const titleWidths = ['w-3/5', 'w-2/5', 'w-4/5', 'w-1/2', 'w-3/4', 'w-2/5'];
</script>

<div aria-hidden="true" class="flex flex-col gap-4">
	<!-- Breadcrumb "Coleções · nome". -->
	<Skeleton class="h-3 w-56 rounded" />

	<!-- Header-card: título + botões, linha de meta embutida. -->
	<div class="rounded-xl border border-border-subtle bg-surface shadow-sm">
		<div class="flex min-h-[3.5rem] items-center gap-3 px-4 py-1.5">
			<Skeleton class="h-6 w-72 rounded" />
			<div class="ml-auto flex items-center gap-2">
				<Skeleton class="h-9 w-32 rounded-md" />
				<Skeleton class="h-9 w-40 rounded-md" />
			</div>
		</div>
		<div class="flex items-center gap-4 border-t border-border-subtle px-4 py-2.5">
			{#each { length: 4 } as _, i (i)}
				<Skeleton class="h-3.5 w-24 rounded" />
			{/each}
		</div>
	</div>

	<!-- 4 KPIs (o primeiro, Progresso geral, é mais largo). -->
	<div class="grid grid-cols-2 gap-4 xl:grid-cols-[1.3fr_1fr_1fr_1fr]">
		{#each { length: 4 } as _, i (i)}
			<div
				class="flex items-center gap-4 rounded-lg border border-border-subtle bg-surface p-4 shadow-sm"
			>
				<Skeleton class="h-9 w-16 shrink-0 rounded" />
				<div class="flex min-w-0 flex-1 flex-col gap-1.5">
					<Skeleton class="h-3.5 w-3/5 rounded" />
					<Skeleton class="h-3 w-4/5 rounded" />
				</div>
			</div>
		{/each}
	</div>

	<!-- Tabela-card: cabeçalho da seção + filtros + linhas. -->
	<div class="overflow-hidden rounded-lg border border-border-subtle bg-surface shadow-sm">
		<div class="flex items-center gap-3 px-4 py-3">
			<Skeleton class="h-4 w-44 rounded" />
			<div class="ml-auto flex items-center gap-2">
				<Skeleton class="h-9 w-16 rounded-sm" />
				<Skeleton class="h-9 w-24 rounded-sm" />
				<Skeleton class="h-9 w-48 rounded-lg" />
			</div>
		</div>
		<div class="overflow-x-auto">
			<table class="m-0 w-full min-w-[980px] border-separate border-spacing-0 text-sm">
				<thead>
					<tr>
						{#each { length: 10 } as _, i (i)}
							<th class="border-b border-border-subtle bg-surface-muted px-2.5 py-2 text-left">
								<Skeleton class="h-2.5 w-12 rounded" />
							</th>
						{/each}
					</tr>
				</thead>
				<tbody>
					{#each titleWidths as width, i (i)}
						<tr>
							<td class="border-t border-border-subtle px-2.5 py-2.5">
								<Skeleton class="h-3.5 w-10 rounded" />
							</td>
							<td class="min-w-[220px] border-t border-border-subtle px-2.5 py-2.5">
								<Skeleton class="h-4 {width} rounded" />
							</td>
							<td class="border-t border-border-subtle px-2.5 py-2.5">
								<Skeleton class="h-3.5 w-14 rounded" />
							</td>
							<td class="border-t border-border-subtle px-2.5 py-2.5">
								<Skeleton class="h-3.5 w-10 rounded" />
							</td>
							<td class="border-t border-border-subtle px-2.5 py-2.5">
								<Skeleton class="h-3.5 w-12 rounded" />
							</td>
							<td class="min-w-[120px] border-t border-border-subtle px-2.5 py-2.5">
								<div class="flex items-center gap-2">
									<Skeleton class="h-1.5 flex-1 rounded-full" />
									<Skeleton class="h-3 w-8 rounded" />
								</div>
							</td>
							<td class="border-t border-border-subtle px-2.5 py-2.5">
								<Skeleton class="h-3.5 w-20 rounded" />
							</td>
							<td class="border-t border-border-subtle px-2.5 py-2.5">
								<Skeleton class="h-3.5 w-20 rounded" />
							</td>
							<td class="border-t border-border-subtle px-2.5 py-2.5">
								<Skeleton class="h-5 w-28 rounded-sm" />
							</td>
							<td class="border-t border-border-subtle px-2.5 py-2.5">
								<Skeleton class="h-8 w-8 rounded-md" />
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	</div>
</div>
