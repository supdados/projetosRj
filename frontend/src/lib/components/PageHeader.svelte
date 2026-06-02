<script lang="ts">
	/**
	 * Cabecalho de tela: titulo grande a esquerda + acoes a direita.
	 * Fiel ao padrao .dashboard-welcome-* do original (static/css/index.css):
	 * titulo em fonte 3xl, peso bold, line-height tight, cor primaria da marca;
	 * subtitulo/contexto em texto secundario; bloco de acoes encostado a direita.
	 *
	 * `title` e a unica prop obrigatoria. `subtitle` e o slot `actions` sao
	 * opcionais. Usa heading semantico (h1) com id opcional para aria-labelledby.
	 */
	import type { Snippet } from 'svelte';

	interface Props {
		title: string;
		/** Texto de contexto/secundario abaixo do titulo. */
		subtitle?: string;
		/** id opcional para vincular aria-labelledby da regiao da tela. */
		labelId?: string;
		/** Acoes alinhadas a direita (botoes, etc.). */
		actions?: Snippet;
	}

	let { title, subtitle, labelId, actions }: Props = $props();
</script>

<header class="flex items-center justify-between gap-4">
	<div class="min-w-0 flex-1">
		<h1
			id={labelId}
			class="truncate font-heading text-3xl font-bold leading-tight text-primary-700"
		>
			{title}
		</h1>
		{#if subtitle}
			<p class="mt-1 truncate text-sm font-medium text-text-secondary">{subtitle}</p>
		{/if}
	</div>
	{#if actions}
		<div class="flex shrink-0 items-center gap-2">
			{@render actions()}
		</div>
	{/if}
</header>
