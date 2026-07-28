<script lang="ts">
	/**
	 * Pilha de toasts (FLASH) da SPA — equivalente visual ao `app-flash-alert` do
	 * Jinja (`base.html` + `static/js/app-shell/flash.js`): toasts fixos no topo,
	 * com ícone por categoria, auto-dismiss (no store) e fechamento manual.
	 *
	 * Montado UMA vez por tela; consome o store `flash`. `aria-live="assertive"`
	 * para erros, `polite` para os demais, espelhando a semântica do legado.
	 */
	import { flash, type FlashCategory } from '$lib/stores/flash';
	import { fly } from 'svelte/transition';

	/** Ícone FontAwesome por categoria (paridade com o flash legado). */
	const ICON: Record<FlashCategory, string> = {
		success: 'fa-check-circle',
		info: 'fa-info-circle',
		warning: 'fa-exclamation-triangle',
		danger: 'fa-exclamation-circle'
	};

	/** Classes de cor por categoria (tokens de tema da SPA). */
	const TONE: Record<FlashCategory, string> = {
		success: 'border-success text-success',
		info: 'border-brand text-brand',
		warning: 'border-warning text-warning',
		danger: 'border-danger text-danger'
	};
</script>

<div
	class="pointer-events-none fixed inset-x-0 top-4 z-toast flex flex-col items-center gap-2 px-4"
	aria-live="polite"
>
	{#each $flash as item (item.id)}
		<div
			role={item.category === 'danger' ? 'alert' : 'status'}
			transition:fly={{ y: -16, duration: 180 }}
			class="pointer-events-auto flex w-full max-w-md items-start gap-2 rounded-lg border bg-surface px-4 py-3 shadow-lg {TONE[
				item.category
			]}"
		>
			<i class="fas {ICON[item.category]} mt-0.5" aria-hidden="true"></i>
			<span class="flex-1 text-sm text-text-primary">{item.message}</span>
			<button
				type="button"
				onclick={() => flash.dismiss(item.id)}
				aria-label="Fechar aviso"
				class="shrink-0 text-text-muted hover:text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
			>
				✕
			</button>
		</div>
	{/each}
</div>
