<script lang="ts">
	/**
	 * Skeleton do índice de Coleções, espelho do estado pronto de
	 * routes/(app)/colecoes/+page.svelte: a MESMA grade de colunas automáticas
	 * (`COLECOES_GRID_CLS`) com cards no chrome do ColecaoCard em formato capa
	 * (faixa de 124px com ícone e nome, barra + três números embaixo) — a
	 * transição loading → pronto acontece sem salto de layout. Só aparece na 1ª
	 * visita (sem cache SWR).
	 */
	import Skeleton from '$lib/components/Skeleton.svelte';
	import { COLECOES_GRID_CLS } from '$lib/utils/colecoesGrid';

	// Larguras variadas dos títulos — quebra a monotonia dos cards.
	const titleWidths = ['w-2/5', 'w-3/5', 'w-1/2', 'w-2/3', 'w-2/5', 'w-3/5', 'w-1/2', 'w-2/5'];
</script>

<div aria-hidden="true" class={COLECOES_GRID_CLS}>
	{#each titleWidths as width, i (i)}
		<div class="flex h-full flex-col rounded-xl border border-border-subtle bg-surface shadow-sm">
			<div
				class="flex h-[124px] flex-col justify-between rounded-t-[15px] bg-surface-muted p-4"
			>
				<Skeleton class="h-[26px] w-[26px] rounded-md" />
				<div class="flex flex-col gap-1.5">
					<Skeleton class="h-4 {width} rounded" />
					<Skeleton class="h-3 w-16 rounded" />
				</div>
			</div>
			<div class="flex flex-col gap-2.5 px-4 pb-4 pt-3.5">
				<Skeleton class="h-1.5 w-full rounded-full" />
				<div class="grid grid-cols-3 gap-1.5">
					{#each [0, 1, 2] as j (j)}
						<div class="flex flex-col gap-1">
							<Skeleton class="h-4 w-6 rounded" />
							<Skeleton class="h-2.5 w-14 rounded" />
						</div>
					{/each}
				</div>
			</div>
		</div>
	{/each}

	<!-- Card fantasma "Nova coleção" (tracejado, centralizado). -->
	<div
		class="flex h-full min-h-[186px] flex-col items-center justify-center gap-2.5 rounded-xl border-2 border-dashed border-border-strong p-5"
	>
		<Skeleton class="h-[52px] w-[52px] shrink-0 rounded-full" />
		<Skeleton class="h-3.5 w-24 rounded" />
	</div>
</div>
