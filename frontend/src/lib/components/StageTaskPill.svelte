<script lang="ts">
	/**
	 * Pílula "Tarefas" de uma etapa — contagem done/total, estado vazio (tracejado)
	 * e bloqueio quando a etapa está concluída. Fonte única do estilo: usada na
	 * tabela de etapas do projeto (StageRow) e nos cards de Projetos Pendentes.
	 */
	import '$lib/styles/stage-chips.css';

	interface Props {
		done: number;
		total: number;
		/** Etapa concluída: pílula esmaecida e sem ação. */
		stageDone?: boolean;
		title: string;
		ariaLabel?: string;
		onclick: () => void;
	}

	let { done, total, stageDone = false, title, ariaLabel, onclick }: Props = $props();
</script>

<button
	type="button"
	class="etapa-task-pill"
	class:is-empty={total === 0}
	class:is-stage-done={stageDone}
	aria-disabled={stageDone ? 'true' : undefined}
	aria-label={ariaLabel}
	{title}
	onclick={() => !stageDone && onclick()}
>
	<span class="etapa-task-pill-has">
		<span class="etapa-task-pill-count">{done}/{total}</span>
	</span>
	<span class="etapa-task-pill-add">
		<i class="fas fa-plus" aria-hidden="true"></i>
		<span>Tarefas</span>
	</span>
</button>

<style>
	/* Pílula de tarefas — paridade com 05-stage-task-quick-add.css */
	.etapa-task-pill {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		gap: 0.34rem;
		width: 116px;
		height: 32px;
		padding: 0 0.7rem;
		border-radius: 8px;
		border: 1px solid var(--stage-chip-started-border);
		background: var(--stage-chip-started-bg);
		color: var(--stage-chip-started-text);
		font-size: 0.8125rem;
		font-weight: 600;
		line-height: 1;
		cursor: pointer;
		transition:
			background-color 0.16s ease,
			border-color 0.16s ease,
			color 0.16s ease;
	}
	.etapa-task-pill:hover,
	.etapa-task-pill:focus-visible {
		background: var(--stage-chip-started-bg-hover);
		border-color: var(--stage-chip-started-border-hover);
		color: var(--stage-chip-started-text-hover);
		outline: none;
	}
	.etapa-task-pill-has,
	.etapa-task-pill-add {
		display: inline-flex;
		align-items: center;
		gap: 0.32rem;
		line-height: 1;
	}
	.etapa-task-pill-count {
		font-weight: 700;
	}
	.etapa-task-pill i {
		font-size: 0.875rem;
	}
	.etapa-task-pill-add {
		display: none;
	}
	.etapa-task-pill.is-empty {
		background: transparent;
		border-style: dashed;
		border-color: var(--ds-color-border-strong);
		color: var(--ds-color-text-muted);
	}
	.etapa-task-pill.is-empty:hover,
	.etapa-task-pill.is-empty:focus-visible {
		background: var(--stage-chip-started-bg);
		border-color: var(--stage-chip-started-border);
		color: var(--stage-chip-started-text);
	}
	.etapa-task-pill.is-empty .etapa-task-pill-has {
		display: none;
	}
	.etapa-task-pill.is-empty .etapa-task-pill-add {
		display: inline-flex;
	}
	.etapa-task-pill.is-stage-done {
		opacity: 0.4;
		cursor: not-allowed;
	}
</style>
