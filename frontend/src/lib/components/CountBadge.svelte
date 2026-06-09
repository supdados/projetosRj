<script lang="ts">
	/**
	 * Pílula de CONTAGEM padronizada do header (meta-pill). Mesmo visual nas três
	 * telas que têm esse contador: Projetos, Tarefas e Projetos Pendentes — chip
	 * "quadrado" (rounded-md), borda/fundo da marca, texto xs semibold primary.
	 *
	 * O conteúdo (rótulo + número) vem como children; `class` recebe só espaçamento
	 * contextual (ex.: `ml-2` quando fica ao lado do título). NÃO mude as classes de
	 * aparência aqui sem refletir nas três telas — a padronização é o objetivo.
	 */
	import type { Snippet } from 'svelte';

	interface Props {
		/** Rótulo + contagem (ex.: "12 projetos"). */
		children: Snippet;
		/** Classes contextuais de espaçamento/posição (ex.: "ml-2"). */
		class?: string;
	}

	let { children, class: extra = '' }: Props = $props();
</script>

<span
	class="inline-flex items-center whitespace-nowrap rounded-md border border-primary-500/40 bg-primary-100 px-2.5 py-1 align-middle text-xs font-semibold text-primary-700 {extra}"
>
	{@render children()}
</span>
