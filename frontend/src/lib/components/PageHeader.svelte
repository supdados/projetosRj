<script lang="ts">
	/**
	 * HEADER-CARD padrao de TODAS as telas. Reproduz EXATAMENTE o "chrome" do
	 * hero atual do dashboard (routes/(app)/dashboard/+page.svelte):
	 *   rounded-xl border border-border-subtle bg-surface px-4 py-3 shadow-sm
	 *   flex flex-wrap items-center justify-between gap-4
	 *   titulo: font-heading text-3xl font-bold leading-tight text-primary-700
	 *
	 * Objetivo: telas ficam UNIFORMES (mesmo tamanho, posicao, radius, peso de
	 * fonte, cor e sombra) — so o titulo muda. A `min-h` garante que telas
	 * so-com-titulo tenham a MESMA altura do hero do home (que carrega titulo +
	 * subtitulo + acoes). Tudo via tokens semanticos => dark mode automatico.
	 *
	 * Uso tipico:
	 *   <PageHeader title="Projetos" subtitle="Todos os cadastros" />
	 *   <PageHeader title="Tarefas" labelId="tarefas-title">
	 *     {#snippet actions()}<Button>...</Button>{/snippet}
	 *   </PageHeader>
	 *   <PageHeader labelId="home-title">       <!-- saudacao em duas cores -->
	 *     {#snippet titleContent()}
	 *       <span class="mr-1 font-semibold text-text-secondary">Ola,</span>
	 *       <span>{nome}</span>
	 *     {/snippet}
	 *   </PageHeader>
	 */
	import type { Snippet } from 'svelte';

	interface Props {
		/** Titulo da tela, renderizado no estilo padrao do hero. Opcional apenas
		 *  quando `titleContent` for usado; caso contrario, deve ser fornecido. */
		title?: string;
		/** Conteudo customizado do titulo (ex.: saudacao em duas cores). Quando
		 *  presente, substitui o texto de `title` dentro do mesmo <h1> padrao. */
		titleContent?: Snippet;
		/** Texto de contexto/secundario abaixo do titulo. */
		subtitle?: string;
		/** id opcional para vincular aria-labelledby da regiao da tela. */
		labelId?: string;
		/** Acoes alinhadas a direita (ex.: data + botao "Novo Projeto"). */
		actions?: Snippet;
		/** Variante FINA (titulo menor, sem piso de altura) — usada pelo modo
		 *  expandido do Kanban de tarefas para devolver altura ao quadro. */
		compact?: boolean;
	}

	let { title, titleContent, subtitle, labelId, actions, compact = false }: Props = $props();
</script>

<!--
	min-h-[5.25rem]: piso de altura igual ao hero do home com 1 linha de titulo +
	subtitulo dentro do py-3 — titulo text-3xl/leading-tight (~2.25rem) + mt-1
	(0.25rem) + subtitulo text-sm (~1.25rem) + 2x py-3 (1.5rem). Garante que
	telas so-com-titulo fiquem do MESMO tamanho do hero. flex-wrap espelha o
	hero original (empilha acoes em telas estreitas).
-->
<header
	class="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-border-subtle bg-surface px-4 shadow-sm motion-safe:transition-[padding,min-height] motion-safe:duration-300 motion-safe:ease-out {compact
		? 'min-h-0 py-1.5'
		: 'min-h-[5.25rem] py-3'}"
>
	<div class="min-w-0 flex-1">
		<h1
			id={labelId}
			class="truncate font-heading font-bold leading-tight text-primary-700 motion-safe:transition-[font-size] motion-safe:duration-300 motion-safe:ease-out {compact
				? 'text-xl'
				: 'text-3xl'}"
		>
			{#if titleContent}{@render titleContent()}{:else}{title}{/if}
		</h1>
		{#if subtitle}
			<!-- No compact o subtítulo COLAPSA (max-height + opacity) em vez de
			     desmontar — a transição de altura do header fica contínua. -->
			<p
				class="truncate text-sm font-medium text-text-muted motion-safe:transition-[max-height,opacity,margin] motion-safe:duration-300 motion-safe:ease-out {compact
					? 'mt-0 max-h-0 overflow-hidden opacity-0'
					: 'mt-1 max-h-6 opacity-100'}"
			>
				{subtitle}
			</p>
		{/if}
	</div>
	{#if actions}
		<!--
			max-w-full + flex-wrap: no desktop as ações cabem numa linha (largura =
			conteúdo) e ficam à direita via o justify-between do header. Em telas
			estreitas, o header quebra as ações para a própria linha; o max-w-full
			limita a largura ao container e o flex-wrap quebra os controles internos
			(em vez de estourar horizontalmente). justify-end mantém o alinhamento à
			direita quando quebram.
		-->
		<div class="flex max-w-full flex-wrap items-center justify-end gap-4">
			{@render actions()}
		</div>
	{/if}
</header>
