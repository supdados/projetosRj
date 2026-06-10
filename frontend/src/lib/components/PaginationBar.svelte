<script lang="ts">
	/**
	 * Barra de paginação compartilhada (Projetos Pendentes, Hub de Tarefas).
	 * Controlada por callback: o pai guarda a página e re-busca no `onChange`.
	 * Some quando há 0/1 página; "Página X de Y" com `aria-live` anuncia a troca.
	 * Mesmo desenho do pager original de Pendentes (centrado, botões ghost).
	 */
	interface Props {
		page: number;
		totalPages: number;
		/** Rótulo do `<nav>` (ex.: "Paginação de projetos"). */
		label?: string;
		/** Desabilita os botões durante o re-fetch. */
		disabled?: boolean;
		onChange: (page: number) => void;
	}

	let { page, totalPages, label = 'Paginação', disabled = false, onChange }: Props = $props();

	const BTN =
		'rounded-md border border-border-subtle bg-surface px-4 py-2 text-sm font-medium text-text-primary transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:cursor-not-allowed disabled:opacity-50';
</script>

{#if totalPages > 1}
	<nav class="flex items-center justify-center gap-3" aria-label={label}>
		<button
			type="button"
			class={BTN}
			disabled={disabled || page <= 1}
			onclick={() => onChange(page - 1)}
		>
			Anterior
		</button>
		<span class="text-sm tabular-nums text-text-secondary" aria-live="polite">
			Página {page} de {totalPages}
		</span>
		<button
			type="button"
			class={BTN}
			disabled={disabled || page >= totalPages}
			onclick={() => onChange(page + 1)}
		>
			Próxima
		</button>
	</nav>
{/if}
