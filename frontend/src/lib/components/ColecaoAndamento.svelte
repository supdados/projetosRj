<script lang="ts">
	/**
	 * Corpo da capa: barra segmentada das etapas por situação (concluídas,
	 * vigentes, atrasadas, não iniciadas) + os três números com bolinha. As
	 * contas vivem em `utils/colecaoCapa.ts` (testadas); aqui só o desenho.
	 *
	 * A barra é decorativa para leitor de tela — os números logo abaixo dizem
	 * o mesmo em texto. Cada segmento tem `title` para quem passa o mouse.
	 */
	import {
		numerosDoAndamento,
		segmentosDaBarra,
		type EtapasDaColecao
	} from '$lib/utils/colecaoCapa';

	interface Props {
		etapas: EtapasDaColecao;
	}

	let { etapas }: Props = $props();

	const segmentos = $derived(segmentosDaBarra(etapas));
	const numeros = $derived(numerosDoAndamento(etapas));
</script>

<div class="flex flex-col gap-2.5">
	<div class="flex h-1.5 gap-0.5 overflow-hidden rounded-full bg-progress-track" aria-hidden="true">
		{#each segmentos as segmento (segmento.faixa)}
			<div
				class="rounded-sm {segmento.classe}"
				style:flex-grow={segmento.valor}
				title={segmento.rotulo}
			></div>
		{/each}
	</div>
	<dl class="m-0 grid grid-cols-3 gap-1.5">
		{#each numeros as numero (numero.faixa)}
			<div class="flex min-w-0 flex-col">
				<dt class="order-2 truncate text-2xs text-text-muted">{numero.rotulo}</dt>
				<dd
					class="order-1 m-0 flex items-center gap-1.5 text-md font-bold tabular-nums text-text-primary"
				>
					<span class="h-[7px] w-[7px] shrink-0 rounded-full {numero.pontoClasse}" aria-hidden="true"
					></span>
					{numero.valor}
				</dd>
			</div>
		{/each}
	</dl>
</div>
