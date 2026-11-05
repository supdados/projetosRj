<script lang="ts">
	/**
	 * Estado vazio do índice de Coleções (design "Coleções 2b"): só Favoritos
	 * existe. Ocupa a trilha ao lado do card de Favoritos (grade própria,
	 * `COLECOES_GRID_VAZIO_CLS`; empilha abaixo de `md`) com um leque de
	 * duas capas de EXEMPLO (decorativas, `aria-hidden`) atrás do botão
	 * "Criar primeira coleção", e o convite em texto embaixo.
	 *
	 * Os exemplos são ilustração fixa — nomes, barras e % não vêm do banco.
	 */
	import ColecaoCapa from '$lib/components/ColecaoCapa.svelte';
	import type { CollectionColorId, CollectionIconId } from '$lib/types/collections';

	interface Props {
		onCriar: () => void;
	}

	let { onCriar }: Props = $props();

	interface CapaDeExemplo {
		nome: string;
		icone: CollectionIconId;
		cor: CollectionColorId;
		meta: string;
		pct: string;
		/** Pesos dos segmentos: concluídas, vigentes, não iniciadas. */
		barra: [number, number, number];
		posicao: string;
		giro: string;
	}

	const EXEMPLOS: readonly CapaDeExemplo[] = [
		{
			nome: 'Dados Abertos',
			icone: 'dados',
			cor: 'success',
			meta: '3 projetos',
			pct: '62%',
			barra: [42, 20, 9],
			posicao: 'left-[40px]',
			giro: '-rotate-[9deg]'
		},
		{
			nome: 'Painéis de Gestão',
			icone: 'indicadores',
			cor: 'attention',
			meta: '2 projetos',
			pct: '25%',
			barra: [9, 13, 14],
			posicao: 'right-[40px]',
			giro: 'rotate-[8deg]'
		}
	];

	const SEGMENTO_CLS = ['bg-success-600', 'bg-primary-600', 'bg-border-strong'] as const;
</script>

<div
	class="flex min-w-0 flex-col items-center gap-6 overflow-hidden rounded-xl border border-border-subtle bg-surface px-6 pb-10 pt-9"
>
	<div class="relative flex h-[210px] w-full max-w-[580px] items-center justify-center">
		<div class="pointer-events-none absolute inset-0 hidden sm:block" aria-hidden="true">
			{#each EXEMPLOS as exemplo (exemplo.nome)}
				<div
					class="absolute top-[22px] w-[210px] overflow-hidden rounded-xl border border-border-subtle bg-surface shadow-md {exemplo.posicao} {exemplo.giro}"
				>
					<ColecaoCapa icone={exemplo.icone} cor={exemplo.cor} nome={exemplo.nome} tamanho="sm" />
					<div class="flex flex-col gap-2 px-3.5 pb-3 pt-2.5">
						<div class="flex h-[5px] gap-0.5">
							{#each exemplo.barra as peso, i (i)}
								<div class="rounded-sm {SEGMENTO_CLS[i]}" style:flex-grow={peso}></div>
							{/each}
						</div>
						<div class="flex justify-between text-2xs text-text-muted">
							<span>{exemplo.meta}</span>
							<span class="font-bold text-text-primary">{exemplo.pct}</span>
						</div>
					</div>
				</div>
			{/each}
		</div>

		<button
			type="button"
			onclick={onCriar}
			class="relative z-[2] flex h-[196px] w-[220px] flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed border-border-strong bg-surface shadow-lg transition-ui duration-fast hover:-translate-y-1 hover:border-brand focus:outline-none focus-visible:border-brand focus-visible:ring-2 focus-visible:ring-brand motion-reduce:hover:translate-y-0"
		>
			<span class="grid h-12 w-12 place-items-center rounded-full bg-brand text-on-brand" aria-hidden="true">
				<i class="fas fa-plus text-xl"></i>
			</span>
			<span class="text-md font-bold text-brand">Criar primeira coleção</span>
			<span class="text-xs text-text-muted">Nome, cor e projetos</span>
		</button>
	</div>

	<div class="flex flex-col items-center gap-2 text-center">
		<h2 class="m-0 font-heading text-2xl font-bold text-text-primary [text-wrap:balance]">
			Agrupe projetos do jeito que você acompanha
		</h2>
		<p class="m-0 max-w-[440px] text-md leading-relaxed text-text-secondary [text-wrap:pretty]">
			Reúna projetos de várias áreas e veja a situação de todos de uma vez.
		</p>
	</div>
</div>
