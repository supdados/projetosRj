<script lang="ts">
	/**
	 * Header estático do card de PROJETO: código (id) integrado ao nome
	 * ("42 - Nome do Projeto"), sigla do órgão e, à direita, as contagens de
	 * tarefas e etapas. O nome LINKA para a página do projeto. Tipografia/cores
	 * de id/título/órgão seguem o padrão de Projetos e Projetos Pendentes.
	 * Com finalizadas no grupo e `onArchive`, um ícone ao lado do nome abre o
	 * card de arquivamento só deste projeto.
	 */
	import FeedbackIcon from './FeedbackIcon.svelte';

	interface Props {
		titulo: string;
		/** Código do projeto (id) exibido antes do nome; `null` se sem projeto. */
		code: string | null;
		orgaoSigla: string | null;
		taskCount: number;
		stagesCount: number;
		/** Link para a página do projeto; `null` quando o grupo não tem projeto. */
		href?: string | null;
		/** Finalizadas visíveis no grupo; 0 esconde o ícone de arquivar. */
		finalizadasCount?: number;
		archiveDisabled?: boolean;
		onArchive?: () => void;
	}

	let {
		titulo,
		code,
		orgaoSigla,
		taskCount,
		stagesCount,
		href = null,
		finalizadasCount = 0,
		archiveDisabled = false,
		onArchive
	}: Props = $props();

	const archiveHint = $derived(
		finalizadasCount === 1
			? 'Arquivar 1 tarefa concluída'
			: `Arquivar ${finalizadasCount} tarefas concluídas`
	);
</script>

<div class="flex w-full items-center gap-1.5 px-5 py-4">
	<!-- Tipografia/cor do "ID - Nome" espelham a coluna Título da lista de
		 Projetos e o card de Pendentes (link text-base medium primary-700 + hover
		 underline; ID em xs bold muted). -->
	<h2 class="flex min-w-0 items-baseline gap-1.5 text-base font-medium">
		{#if code}
			<span class="shrink-0 text-xs font-bold text-text-muted">{code}</span>
			<span class="shrink-0 text-text-muted" aria-hidden="true">-</span>
		{/if}
		{#if href}
			<a
				{href}
				class="truncate text-brand no-underline transition-colors duration-fast hover:underline focus:outline-none focus-visible:rounded-sm focus-visible:ring-2 focus-visible:ring-brand"
			>
				{titulo}
			</a>
		{:else}
			<span class="truncate text-text-primary">{titulo}</span>
		{/if}
	</h2>

	{#if onArchive && finalizadasCount > 0}
		<button
			type="button"
			onclick={onArchive}
			disabled={archiveDisabled}
			title={archiveHint}
			aria-label="{archiveHint} de {titulo}"
			class="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-text-muted transition-colors duration-fast hover:bg-surface-muted hover:text-brand focus:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:opacity-50"
		>
			<FeedbackIcon id="archive" size={16} />
		</button>
	{/if}

	{#if orgaoSigla}
		<span class="shrink-0 text-xs text-text-muted">
			Área responsável: <strong class="font-medium text-text-secondary">{orgaoSigla}</strong>
		</span>
	{/if}

	<span class="ml-auto flex shrink-0 items-center gap-2 text-xs text-text-secondary">
		<span><b class="font-mono font-semibold text-text-primary">{taskCount}</b> {taskCount === 1 ? 'tarefa' : 'tarefas'}</span>
		<span class="text-text-muted" aria-hidden="true">·</span>
		<span><b class="font-mono font-semibold text-text-primary">{stagesCount}</b> {stagesCount === 1 ? 'etapa' : 'etapas'}</span>
	</span>
</div>
