<script lang="ts">
	/**
	 * Estado de erro de carregamento de tela (full-width). Bloco `role="alert"`
	 * com a mensagem + botão "Tentar novamente".
	 *
	 * Extraído da duplicação literal que existia em dashboard/busca/projetos/
	 * pendentes/tarefas/calendarios (débito #5 / C1). Mantém EXATAMENTE a mesma
	 * marcação/classes Tailwind das telas originais para paridade visual.
	 *
	 * As telas com erro multi-branch (not_found/forbidden com links próprios,
	 * ex.: detalhe do projeto e histórico) NÃO usam este componente.
	 *
	 * Uso:
	 *   <LoadErrorState message={errorMessage} onRetry={() => load()} />
	 */
	interface Props {
		message: string;
		onRetry: () => void;
		/** Rótulo do botão (default: "Tentar novamente"). */
		retryLabel?: string;
	}

	let { message, onRetry, retryLabel = 'Tentar novamente' }: Props = $props();
</script>

<div
	role="alert"
	class="flex flex-col items-start gap-3 rounded-lg border border-danger bg-surface px-5 py-4"
>
	<p class="text-text-primary">{message}</p>
	<button
		type="button"
		onclick={onRetry}
		class="rounded-md border border-border-subtle bg-surface px-4 py-2 text-sm font-medium text-text-primary transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
	>
		{retryLabel}
	</button>
</div>
