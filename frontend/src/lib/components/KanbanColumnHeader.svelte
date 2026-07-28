<script lang="ts">
	/**
	 * Cabeçalho de coluna: faixa tingida com a cor do status. Fundo = wash da
	 * família do status; tinta = token de texto da mesma família.
	 */
	import type { Snippet } from 'svelte';
	import type { TaskStatus } from '$lib/utils/taskStatus';

	interface Props {
		status: TaskStatus;
		headingId: string;
		label: string;
		count: number;
		trailing?: Snippet;
	}

	let { status, headingId, label, count, trailing }: Props = $props();
</script>

<header
	class="kcol-head kcol-head--{status} flex shrink-0 items-center gap-2 rounded-lg px-3 py-2"
>
	<h2 id={headingId} class="font-heading truncate text-sm font-bold">
		{label}
	</h2>
	<!-- {#key count}: remonta o contador a cada mudança p/ rodar o "pop". -->
	{#key count}
		<span class="kcol-count text-xs font-bold tabular-nums opacity-70">
			{count}
		</span>
	{/key}
	{#if trailing}
		<span class="ml-auto flex items-center self-center">{@render trailing()}</span>
	{/if}
</header>

<style>
	.kcol-head--nao_iniciada {
		background-color: var(--ds-color-wash-neutral);
		color: var(--ds-color-text-secondary);
	}
	/* Tinta = token puro e mapeamento arbitrado em plano-regua-de-cor §7.2:
	   andamento=primary, ajustes=orange (vira attention). O fundo é o wash da
	   mesma família (degrau nomeado, desloca sozinho no dark). */
	.kcol-head--em_andamento {
		background-color: var(--ds-color-wash-brand);
		color: var(--ds-color-text-brand);
	}
	.kcol-head--para_validacao {
		background-color: var(--ds-color-wash-warning);
		color: var(--ds-color-text-warning);
	}
	.kcol-head--para_ajustes {
		background-color: var(--ds-color-wash-attention);
		color: var(--ds-color-text-attention);
	}
	.kcol-head--finalizada {
		background-color: var(--ds-color-wash-success);
		color: var(--ds-color-text-success);
	}

	/* Pop da contagem quando o número muda (remontada via {#key}). */
	@keyframes kcol-count-pop {
		0% {
			transform: scale(1);
		}
		45% {
			transform: scale(1.18);
		}
		100% {
			transform: scale(1);
		}
	}
	.kcol-count {
		display: inline-block;
		animation: kcol-count-pop 0.24s ease;
	}

	@media (prefers-reduced-motion: reduce) {
		.kcol-count {
			animation: none;
		}
	}
</style>
