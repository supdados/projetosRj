<script lang="ts">
	/**
	 * Estado de erro de carregamento: substitui o conteúdo que falhou, na
	 * mesma caixa que ele ocuparia. Ícone neutro (erro de sistema, não do
	 * usuário) + explicação + ação. Duas variantes (Grupo 6 do spec):
	 *   - 'screen' (default): tela cheia, centralizado, par de botões.
	 *   - 'block': escala reduzida dentro de um painel, um único botão.
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
	 *   <LoadErrorState variant="block" title="Cronograma indisponível" message={msg} onRetry={reload} />
	 */
	import type { AccessErrorKind } from '$lib/utils/accessErrorMessages';
	import FeedbackIcon from './FeedbackIcon.svelte';

	interface Props {
		message: string;
		onRetry: () => void;
		/** Rótulo do botão (default: "Tentar novamente" em 'screen', "Recarregar bloco" em 'block'). */
		retryLabel?: string;
		/** Caso do contrato 404/403; default "generic" (só o retry). */
		kind?: AccessErrorKind;
		/** Destino do link de saída, exibido quando `kind` não é "generic". */
		backHref?: string;
		/** Rótulo do link de saída (default: "Voltar"). */
		backLabel?: string;
		/** 'screen': tela cheia centralizada. 'block': encaixado num painel. */
		variant?: 'screen' | 'block';
		/** Título opcional acima da mensagem. */
		title?: string;
		/** Código já formatado pelo chamador (ex.: "erro 504 · req 8f31c2"). */
		errorCode?: string;
	}

	let {
		message,
		onRetry,
		retryLabel,
		kind = 'generic',
		backHref,
		backLabel = 'Voltar',
		variant = 'screen',
		title,
		errorCode
	}: Props = $props();

	const canRetry = $derived(kind === 'generic');
	const effectiveRetryLabel = $derived(retryLabel ?? (variant === 'block' ? 'Recarregar bloco' : 'Tentar novamente'));

	const secondaryActionClass =
		'inline-flex items-center gap-1.5 rounded-md border border-border-subtle bg-surface px-3.5 py-2 text-xs font-semibold text-text-primary no-underline transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-brand';
</script>

{#if variant === 'screen'}
	<div
		role="alert"
		class="flex min-h-[20rem] flex-col items-center justify-center gap-4 px-5 py-8 text-center"
	>
		<FeedbackIcon id="cloudoff" size={46} class="text-text-faint" />
		<div class="flex max-w-[26.25rem] flex-col gap-2">
			{#if title}
				<h3 class="text-2xl font-semibold text-text-primary">{title}</h3>
			{/if}
			<p class="text-md text-text-secondary">{message}</p>
		</div>
		<div class="flex gap-2 pt-1">
			{#if canRetry}
				<button
					type="button"
					onclick={onRetry}
					class="inline-flex items-center gap-2 rounded-md bg-brand px-4 py-2.5 text-sm font-semibold text-on-brand transition-colors duration-fast hover:bg-brand-hover focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
				>
					<FeedbackIcon id="retry" size={17} />
					{effectiveRetryLabel}
				</button>
			{/if}
			{#if backHref}
				<a
					href={backHref}
					class="inline-flex items-center gap-2 rounded-md border border-border-subtle bg-surface px-4 py-2.5 text-sm font-semibold text-text-primary no-underline transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
				>
					<FeedbackIcon id="back" size={17} />
					{backLabel}
				</a>
			{/if}
		</div>
		{#if errorCode}
			<span class="font-mono text-2xs text-text-faint">{errorCode}</span>
		{/if}
	</div>
{:else}
	<div
		role="alert"
		class="flex min-h-[14.75rem] flex-col items-center justify-center gap-3 rounded-md border border-border-subtle bg-surface-muted px-5 py-6 text-center"
	>
		<FeedbackIcon id="cloudoff" size={32} class="text-text-faint" />
		{#if title}
			<span class="text-base font-semibold text-text-primary">{title}</span>
		{/if}
		<p class="max-w-[17.5rem] text-sm text-text-secondary">{message}</p>
		{#if canRetry}
			<button type="button" onclick={onRetry} class={secondaryActionClass}>
				<FeedbackIcon id="retry" size={16} />
				{effectiveRetryLabel}
			</button>
		{:else if backHref}
			<a href={backHref} class={secondaryActionClass}>
				<FeedbackIcon id="back" size={16} />
				{backLabel}
			</a>
		{/if}
		{#if errorCode}
			<span class="font-mono text-2xs text-text-faint">{errorCode}</span>
		{/if}
	</div>
{/if}
