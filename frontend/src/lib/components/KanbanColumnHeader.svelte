<script lang="ts">
	/**
	 * Cabeçalho de coluna: faixa tingida com a cor do status. Tintas via
	 * color-mix no bloco de estilo (Tailwind 3 não gera bg-info/10 de var sem
	 * alpha-value).
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
		background-color: color-mix(in srgb, var(--color-text-muted) 8%, var(--color-surface));
		color: var(--color-text-secondary);
	}
	.kcol-head--em_andamento {
		background-color: color-mix(in srgb, var(--ds-color-info-600) 9%, var(--color-surface));
		color: color-mix(in srgb, var(--ds-color-info-600) 62%, var(--color-text-primary));
	}
	.kcol-head--para_validacao {
		background-color: color-mix(in srgb, var(--ds-color-warning-600) 10%, var(--color-surface));
		color: color-mix(in srgb, var(--ds-color-warning-600) 62%, var(--color-text-primary));
	}
	.kcol-head--para_ajustes {
		background-color: color-mix(in srgb, var(--ds-color-danger-600) 8%, var(--color-surface));
		color: color-mix(in srgb, var(--ds-color-danger-600) 62%, var(--color-text-primary));
	}
	.kcol-head--finalizada {
		background-color: color-mix(in srgb, var(--ds-color-success-600) 8%, var(--color-surface));
		color: color-mix(in srgb, var(--ds-color-success-600) 62%, var(--color-text-primary));
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
