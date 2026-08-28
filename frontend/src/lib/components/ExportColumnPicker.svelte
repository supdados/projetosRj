<script lang="ts">
	/**
	 * Bloco de seleção de colunas do modal de exportação: contador, ações em lote
	 * (todas/limpar) e grid de chips. Usado para as colunas de projeto e as de etapa.
	 */
	import { untrack } from 'svelte';
	import { fade } from 'svelte/transition';
	import { prefersReducedMotion } from 'svelte/motion';
	import type { ExportColumn } from '$lib/utils/exportColumns';

	interface Props {
		titulo: string;
		registro: readonly ExportColumn[];
		selecao: readonly string[];
		/** `false` suprime o pop dos checks (abertura do modal e ações em lote). */
		pop: boolean;
		aviso: string;
		alternar: (slug: string) => void;
		todas: () => void;
		limpar: () => void;
	}

	let { titulo, registro, selecao, pop, aviso, alternar, todas, limpar }: Props = $props();

	const ativos = $derived(new Set(selecao));

	/** Lido via `untrack` de propósito: aplicar a classe reativamente faria a seleção já
	 * persistida dar pop na abertura — o pop só deve responder a um clique do usuário. */
	const classePop = (): string => untrack(() => (pop ? 'export-check-pop' : ''));
</script>

<div class="flex items-baseline justify-between">
	<span class="text-2xs font-bold uppercase tracking-caps text-text-label">{titulo}</span>
	<span class="font-mono text-xs tabular-nums text-text-muted" aria-live="polite">
		<span aria-hidden="true">{selecao.length} de {registro.length}</span>
		<span class="sr-only">{selecao.length} de {registro.length} colunas selecionadas</span>
	</span>
</div>
<div class="flex items-center gap-2">
	<button
		type="button"
		onclick={todas}
		class="rounded-sm text-xs text-brand hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
	>
		Selecionar todas
	</button>
	<span class="text-xs text-text-faint" aria-hidden="true">·</span>
	<button
		type="button"
		onclick={limpar}
		class="rounded-sm text-xs text-brand hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
	>
		Limpar
	</button>
</div>
<div class="grid grid-cols-3 gap-1.5">
	{#each registro as coluna (coluna.slug)}
		{@const ativa = ativos.has(coluna.slug)}
		<button
			type="button"
			aria-pressed={ativa}
			onclick={() => alternar(coluna.slug)}
			class="inline-flex h-8 items-center gap-1.5 rounded-sm border px-2.5 text-xs font-medium transition-ui active:scale-[0.97] focus:outline-none focus-visible:ring-2 focus-visible:ring-brand {ativa
				? 'border-brand-soft bg-wash-brand text-brand'
				: 'border-border-subtle bg-surface text-text-secondary hover:border-brand hover:text-brand'}"
		>
			<span class="grid h-2.5 w-2.5 shrink-0 place-items-center" aria-hidden="true">
				{#if ativa}
					<svg
						class={classePop()}
						width="10"
						height="10"
						viewBox="0 0 10 10"
						fill="none"
						out:fade={{ duration: prefersReducedMotion.current ? 0 : 100 }}
					>
						<path
							d="M1.5 5.5 4 8l4.5-6"
							stroke="currentColor"
							stroke-width="1.8"
							stroke-linecap="round"
							stroke-linejoin="round"
						/>
					</svg>
				{/if}
			</span>
			<span class="truncate">{coluna.label}</span>
		</button>
	{/each}
</div>
<p class="min-h-4 text-xs text-text-muted" aria-live="polite">{aviso}</p>

<style>
	.export-check-pop {
		animation: export-check-pop 200ms cubic-bezier(0.34, 1.56, 0.64, 1) both;
	}
	@keyframes export-check-pop {
		from {
			transform: scale(0.6);
			opacity: 0;
		}
		to {
			transform: scale(1);
			opacity: 1;
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.export-check-pop {
			animation-duration: 0ms;
		}
	}
</style>
