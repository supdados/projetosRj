<script lang="ts">
	/**
	 * Skeleton do índice de Coleções, espelho do estado pronto de
	 * routes/(app)/colecoes/+page.svelte: grid 2/4 colunas de cards no mesmo
	 * chrome do ColecaoCard (tile + título, descrição, barra + meta) — a
	 * transição loading → pronto acontece sem salto de layout. Só aparece na
	 * 1ª visita (sem cache SWR).
	 */
	import Skeleton from '$lib/components/Skeleton.svelte';

	// Larguras variadas dos títulos — quebra a monotonia dos cards.
	const titleWidths = ['w-2/5', 'w-3/5', 'w-1/2', 'w-2/3', 'w-2/5', 'w-3/5', 'w-1/2', 'w-2/5'];
</script>

<div aria-hidden="true" class="grid grid-cols-2 gap-4 lg:grid-cols-4">
	{#each titleWidths as width, i (i)}
		<div
			class="flex h-full flex-col gap-3 rounded-lg border border-border-subtle bg-surface p-4 shadow-sm"
		>
			<div class="flex items-center gap-3">
				<Skeleton class="h-10 w-10 shrink-0 rounded-md" />
				<Skeleton class="h-4 {width} rounded" />
			</div>
			<Skeleton class="h-3.5 w-4/5 rounded" />
			<div class="mt-auto">
				<Skeleton class="h-1.5 w-full rounded-full" />
				<div class="mt-2 flex items-center justify-between">
					<Skeleton class="h-3 w-28 rounded" />
					<Skeleton class="h-3 w-8 rounded" />
				</div>
			</div>
		</div>
	{/each}

	<!-- Card fantasma "Criar uma nova coleção" (1 coluna, tracejado, centralizado). -->
	<div
		class="flex h-full flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-border-strong bg-surface p-4"
	>
		<Skeleton class="h-10 w-10 shrink-0 rounded-md" />
		<Skeleton class="h-3.5 w-40 rounded" />
	</div>
</div>
