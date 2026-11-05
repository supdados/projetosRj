<script lang="ts">
	/**
	 * Ilustração do passo 2 da novidade de Coleções: o formulário de criação em
	 * miniatura — capa de exemplo (`ColecaoCapa`), cores da paleta real de
	 * coleção e a lista "Projetos da sua área" com dois marcados. Decorativa.
	 */
	import ColecaoCapa from '$lib/components/ColecaoCapa.svelte';
	import { COLECAO_CAPA_TOM } from '$lib/icons/collectionIdentity';
	import type { CollectionColorId } from '$lib/types/collections';

	const CORES: readonly CollectionColorId[] = [
		'primary',
		'success',
		'warning',
		'attention',
		'danger',
		'neutral'
	];
	const PROJETOS: readonly { nome: string; marcado: boolean }[] = [
		{ nome: 'Portal de dados abertos', marcado: true },
		{ nome: 'Catálogo de APIs do Estado', marcado: true },
		{ nome: 'Inventário de bases', marcado: false }
	];
</script>

<div
	class="w-[320px] overflow-hidden rounded-xl border border-border-subtle bg-surface shadow-lg"
	aria-hidden="true"
>
	<ColecaoCapa icone="dados" cor="success" nome="Dados Abertos" class="rounded-t-[15px]" />
	<div class="flex flex-col gap-3.5 p-4">
		<div class="flex flex-col gap-1.5">
			<span class="text-xs font-bold text-text-secondary">Cor</span>
			<div class="flex justify-between">
				{#each CORES as cor (cor)}
					<span
						class="h-[26px] w-[26px] rounded-full {COLECAO_CAPA_TOM[cor].selo} {cor === 'success'
							? 'ring-2 ring-success-600 ring-offset-2 ring-offset-surface'
							: ''}"
					></span>
				{/each}
			</div>
		</div>
		<div class="flex flex-col gap-1.5">
			<span class="text-xs font-bold text-text-secondary">Projetos da sua área</span>
			<div class="overflow-hidden rounded-lg border border-border-subtle">
				{#each PROJETOS as projeto, i (projeto.nome)}
					<div
						class="flex items-center gap-2.5 px-3 py-2 text-sm {i > 0
							? 'border-t border-border-subtle'
							: ''} {projeto.marcado ? 'bg-primary-50' : ''}"
					>
						{#if projeto.marcado}
							<span class="grid h-4 w-4 place-items-center rounded bg-primary-600 text-white">
								<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round"><path d="M5 12l5 5 9-10" /></svg>
							</span>
						{:else}
							<span class="h-4 w-4 rounded border-[1.5px] border-neutral-400"></span>
						{/if}
						{projeto.nome}
					</div>
				{/each}
			</div>
		</div>
	</div>
</div>
