<script lang="ts">
	/**
	 * Ilustração do passo 1 da novidade de Coleções: uma coleção de EXEMPLO em
	 * destaque (capa real — `ColecaoCapa` + `ColecaoAndamento`, as mesmas peças
	 * do índice) sobre duas cartas inclinadas, e a lista de áreas que a pílula
	 * abre no hover. Decorativa (`aria-hidden`): o texto ao lado diz o mesmo.
	 */
	import ColecaoAndamento from '$lib/components/ColecaoAndamento.svelte';
	import ColecaoCapa from '$lib/components/ColecaoCapa.svelte';

	const ETAPAS = {
		etapas_total: 34,
		etapas_concluidas: 14,
		etapas_em_andamento: 11,
		etapas_atrasadas: 3
	};
	const AREAS: readonly (readonly [string, number])[] = [
		['SETD', 4],
		['SUBEDD', 3],
		['ASSTEC', 2]
	];
</script>

<div class="relative h-[330px] w-[300px]" aria-hidden="true">
	<div
		class="absolute left-[-26px] top-[46px] h-[210px] w-[250px] -rotate-[8deg] overflow-hidden rounded-xl border border-border-subtle bg-surface shadow-md"
	>
		<div class="h-24 bg-wash-success"></div>
	</div>
	<div
		class="absolute right-[-26px] top-[46px] h-[210px] w-[250px] rotate-[8deg] overflow-hidden rounded-xl border border-border-subtle bg-surface shadow-md"
	>
		<div class="h-24 bg-wash-attention"></div>
	</div>

	<div
		class="absolute left-[10px] top-6 w-[280px] overflow-hidden rounded-xl border border-border-subtle bg-surface shadow-lg"
	>
		<ColecaoCapa
			icone="camadas"
			cor="primary"
			nome="Transformação Digital"
			meta="9 projetos"
			class="rounded-t-[15px]"
		>
			{#snippet acoes()}
				<span
					class="bg-capa-veu inline-flex h-6 items-center rounded-full px-2.5 text-xs font-semibold text-text-primary ring-2 ring-primary-600"
				>
					3 áreas
				</span>
			{/snippet}
		</ColecaoCapa>
		<div class="px-4 pb-4 pt-3.5">
			<ColecaoAndamento etapas={ETAPAS} />
		</div>
	</div>

	<!-- Popover da pílula (o que o hover abre no índice): logo abaixo dela. -->
	<div
		class="absolute right-[-60px] top-[74px] flex w-40 flex-col gap-1.5 rounded-lg bg-neutral-900 px-3 py-2.5 text-xs text-white shadow-lg"
	>
		{#each AREAS as [sigla, projetos] (sigla)}
			<div class="flex justify-between">
				<span class="font-bold">{sigla}</span>
				<span class="text-neutral-300">{projetos} projetos</span>
			</div>
		{/each}
	</div>
</div>
