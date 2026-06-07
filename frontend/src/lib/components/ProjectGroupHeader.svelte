<script lang="ts">
	/**
	 * Header do card de PROJETO: chevron colapsável + código (id) integrado ao
	 * nome ("42 – Nome do Projeto"), sigla do órgão e, à direita, as contagens de
	 * tarefas e etapas. O header inteiro é clicável e alterna o colapso do card.
	 */
	interface Props {
		titulo: string;
		/** Código do projeto (id) exibido antes do nome; `null` se sem projeto. */
		code: string | null;
		orgaoSigla: string | null;
		taskCount: number;
		stagesCount: number;
		open: boolean;
		onToggle: () => void;
		/** id do corpo colapsável, para `aria-controls`. */
		controlsId?: string;
	}

	let { titulo, code, orgaoSigla, taskCount, stagesCount, open, onToggle, controlsId }: Props =
		$props();
</script>

<button
	type="button"
	onclick={onToggle}
	aria-expanded={open}
	aria-controls={controlsId}
	class="flex w-full items-center gap-2.5 px-5 py-4 text-left transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary-500"
>
	<i
		class="fas fa-chevron-right shrink-0 text-xs text-text-muted transition-transform duration-fast motion-reduce:transition-none {open
			? 'rotate-90'
			: ''}"
		aria-hidden="true"
	></i>

	<h2 class="flex min-w-0 items-baseline gap-1.5 font-heading text-lg font-semibold text-text-primary">
		{#if code}
			<span class="shrink-0 font-mono text-base font-normal text-text-muted">{code}</span>
			<span class="shrink-0 text-text-muted" aria-hidden="true">–</span>
		{/if}
		<span class="truncate">{titulo}</span>
	</h2>

	{#if orgaoSigla}
		<span class="shrink-0 text-xs font-medium text-text-secondary">{orgaoSigla}</span>
	{/if}

	<span class="ml-auto flex shrink-0 items-center gap-2 text-xs text-text-secondary">
		<span><b class="font-mono font-semibold text-text-primary">{taskCount}</b> {taskCount === 1 ? 'tarefa' : 'tarefas'}</span>
		<span class="text-text-muted" aria-hidden="true">·</span>
		<span><b class="font-mono font-semibold text-text-primary">{stagesCount}</b> {stagesCount === 1 ? 'etapa' : 'etapas'}</span>
	</span>
</button>
