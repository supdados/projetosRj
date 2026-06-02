<script lang="ts">
	/**
	 * Card minimo da marca. Superficie semantica (troca no dark via vars).
	 * `title` opcional renderiza um cabecalho; o slot e o corpo.
	 */
	import type { Snippet } from 'svelte';

	interface Props {
		title?: string;
		/** id opcional para vincular aria-labelledby do conteudo. */
		labelId?: string;
		children: Snippet;
		header?: Snippet;
		/** Rodape opcional do card, separado por borda (acoes/resumo). */
		footer?: Snippet;
	}

	let { title, labelId, children, header, footer }: Props = $props();
</script>

<section
	class="rounded-lg border border-border-subtle bg-surface shadow-sm"
	aria-labelledby={labelId}
>
	{#if header || title}
		<header class="flex items-center justify-between gap-3 border-b border-border-subtle px-5 py-4">
			{#if title}
				<h2 id={labelId} class="font-heading text-lg font-semibold text-text-primary">
					{title}
				</h2>
			{/if}
			{#if header}{@render header()}{/if}
		</header>
	{/if}
	<div class="p-5">
		{@render children()}
	</div>
	{#if footer}
		<footer class="flex items-center justify-end gap-3 border-t border-border-subtle px-5 py-4">
			{@render footer()}
		</footer>
	{/if}
</section>
