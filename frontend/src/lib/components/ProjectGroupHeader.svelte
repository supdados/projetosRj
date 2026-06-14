<script lang="ts">
	/**
	 * Header do card de PROJETO: chevron que COLAPSA o card + código (id) integrado
	 * ao nome ("42 – Nome do Projeto"), sigla do órgão e, à direita, as contagens de
	 * tarefas e etapas. O nome LINKA para a página do projeto; a expansão acontece
	 * só ao clicar no chevron (setinha).
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
		/** Link para a página do projeto; `null` quando o grupo não tem projeto. */
		href?: string | null;
	}

	let {
		titulo,
		code,
		orgaoSigla,
		taskCount,
		stagesCount,
		open,
		onToggle,
		controlsId,
		href = null
	}: Props = $props();
</script>

<div class="flex w-full items-center gap-1.5 px-5 py-4">
	<button
		type="button"
		onclick={onToggle}
		aria-expanded={open}
		aria-controls={controlsId}
		aria-label={open ? 'Recolher projeto' : 'Expandir projeto'}
		class="-ml-1 inline-flex shrink-0 items-center rounded-md p-1 text-text-muted transition-colors duration-fast hover:bg-surface-muted hover:text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
	>
		<i
			class="fas fa-chevron-right text-xs transition-transform duration-fast motion-reduce:transition-none {open
				? 'rotate-90'
				: ''}"
			aria-hidden="true"
		></i>
	</button>

	<h2 class="flex min-w-0 items-baseline gap-1.5 font-heading text-lg font-semibold text-text-primary">
		{#if code}
			<span class="shrink-0 font-mono text-base font-normal text-text-muted">{code}</span>
			<span class="shrink-0 text-text-muted" aria-hidden="true">–</span>
		{/if}
		{#if href}
			<a
				{href}
				class="truncate text-text-primary no-underline transition-colors duration-fast hover:text-primary-700 hover:underline focus:outline-none focus-visible:rounded-sm focus-visible:ring-2 focus-visible:ring-primary-500"
			>
				{titulo}
			</a>
		{:else}
			<span class="truncate">{titulo}</span>
		{/if}
	</h2>

	{#if orgaoSigla}
		<span class="shrink-0 text-xs font-medium text-text-secondary">{orgaoSigla}</span>
	{/if}

	<span class="ml-auto flex shrink-0 items-center gap-2 text-xs text-text-secondary">
		<span><b class="font-mono font-semibold text-text-primary">{taskCount}</b> {taskCount === 1 ? 'tarefa' : 'tarefas'}</span>
		<span class="text-text-muted" aria-hidden="true">·</span>
		<span><b class="font-mono font-semibold text-text-primary">{stagesCount}</b> {stagesCount === 1 ? 'etapa' : 'etapas'}</span>
	</span>
</div>
