<script lang="ts">
	/**
	 * Estado de erro de carregamento de tela (full-width). Bloco `role="alert"`
	 * com a mensagem + botão "Tentar novamente".
	 *
	 * Extraído da duplicação literal que existia em dashboard/busca/projetos/
	 * pendentes/tarefas/calendarios (débito #5 / C1). Mantém EXATAMENTE a mesma
	 * marcação/classes Tailwind das telas originais para paridade visual.
	 *
	 * Contrato de autorização (S5, §6.3): quem passa `kind` distingue os casos —
	 * 404 (`not_found`, mensagem única que não revela se o recurso existe) e 403
	 * (`forbidden`) não oferecem "Tentar novamente", porque repetir a requisição
	 * não muda o resultado; no lugar sai o link de saída (`backHref`). A mensagem
	 * já vem pronta do chamador (ver `$lib/utils/accessErrorMessages`).
	 *
	 * Uso:
	 *   <LoadErrorState message={errorMessage} onRetry={() => load()} />
	 *   <LoadErrorState
	 *     message={errorMessage}
	 *     kind={errorKind}
	 *     onRetry={load}
	 *     backHref={`${base}/projetos`}
	 *     backLabel="Voltar aos projetos"
	 *   />
	 */
	import type { AccessErrorKind } from '$lib/utils/accessErrorMessages';

	interface Props {
		message: string;
		onRetry: () => void;
		/** Rótulo do botão (default: "Tentar novamente"). */
		retryLabel?: string;
		/** Caso do contrato 404/403; default "generic" (só o retry). */
		kind?: AccessErrorKind;
		/** Destino do link de saída, exibido quando `kind` não é "generic". */
		backHref?: string;
		/** Rótulo do link de saída (default: "Voltar"). */
		backLabel?: string;
	}

	let {
		message,
		onRetry,
		retryLabel = 'Tentar novamente',
		kind = 'generic',
		backHref,
		backLabel = 'Voltar'
	}: Props = $props();
</script>

<div
	role="alert"
	class="flex flex-col items-start gap-3 rounded-lg border border-danger bg-surface px-5 py-4"
>
	<p class="text-text-primary">{message}</p>
	{#if kind === 'generic'}
		<button
			type="button"
			onclick={onRetry}
			class="rounded-md border border-border-subtle bg-surface px-4 py-2 text-sm font-medium text-text-primary transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
		>
			{retryLabel}
		</button>
	{:else if backHref}
		<a
			href={backHref}
			class="rounded-md border border-border-subtle bg-surface px-4 py-2 text-sm font-medium text-text-primary no-underline transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
		>
			{backLabel}
		</a>
	{/if}
</div>
