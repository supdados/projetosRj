<script lang="ts">
	/**
	 * Tela final da importação: check animado + contadores do lote. O modal
	 * chama `focusConcluir()` ao entrar no estado de sucesso.
	 */
	import type { ImportProjectsResultV2 } from '$lib/types/importExport';

	interface Props {
		resultado: ImportProjectsResultV2;
		/** Título já formatado por modo ("X projetos [e Y etapas] importados"). */
		rotulo: string;
		/** Copy das ignoradas por modo — no com etapas só linhas em branco são ignoradas. */
		descricaoIgnoradas: string;
		/** Classe do botão primário, herdada do modal para manter o visual. */
		classePrimario: string;
		onConcluir: () => void;
	}

	let { resultado, rotulo, descricaoIgnoradas, classePrimario, onConcluir }: Props = $props();

	let concluirEl = $state<HTMLButtonElement | null>(null);

	export function focusConcluir(): void {
		concluirEl?.focus({ preventScroll: true });
	}
</script>

<span class="import-sucesso-circulo grid h-14 w-14 place-items-center rounded-full bg-wash-success">
	<svg width="24" height="24" viewBox="0 0 24 24" class="text-success" aria-hidden="true">
		<path class="import-sucesso-check" d="M4 13 L9.5 18.5 L20 6.5" fill="none" />
	</svg>
</span>
<p class="text-xl font-bold text-text-primary" aria-hidden="true">{rotulo}</p>
{#if resultado.ignored_count > 0}
	<p class="text-sm text-text-muted">
		{resultado.ignored_count} {descricaoIgnoradas}
	</p>
{/if}
{#if resultado.adjusted_count > 0}
	<p class="text-sm text-text-muted">
		Valores não reconhecidos em {resultado.adjusted_count} linha(s) receberam os padrões escolhidos.
	</p>
{/if}
<button bind:this={concluirEl} type="button" onclick={onConcluir} class="mt-2 px-6 {classePrimario}">
	Concluir
</button>

<style>
	.import-sucesso-circulo {
		animation: import-circulo-pop 260ms cubic-bezier(0.34, 1.56, 0.64, 1) both;
	}
	@keyframes import-circulo-pop {
		from {
			transform: scale(0.8);
		}
		to {
			transform: scale(1);
		}
	}
	.import-sucesso-check {
		stroke: currentColor;
		stroke-width: 2.5;
		stroke-linecap: round;
		stroke-linejoin: round;
		stroke-dasharray: 24;
		animation: import-check-draw 400ms cubic-bezier(0.33, 1, 0.68, 1) 120ms both;
	}
	@keyframes import-check-draw {
		from {
			stroke-dashoffset: 24;
		}
		to {
			stroke-dashoffset: 0;
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.import-sucesso-circulo,
		.import-sucesso-check {
			animation-duration: 0ms;
			animation-delay: 0ms;
		}
	}
</style>
