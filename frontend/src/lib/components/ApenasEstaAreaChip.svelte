<script lang="ts">
	/**
	 * Segmento "Apenas a área", fundido à direita do OrgaoTreeSelect (que deve
	 * receber `attachedRight`): mesma altura, borda compartilhada, deslizando
	 * para fora do seletor quando o órgão filtrado tem filhos. Ativo, restringe
	 * o filtro ao próprio órgão, sem os descendentes (`?apenas_orgao=1`).
	 */
	import { slide } from 'svelte/transition';
	import { cubicOut } from 'svelte/easing';
	import { prefersReducedMotion } from 'svelte/motion';

	interface Props {
		ativo: boolean;
		onToggle: () => void;
	}

	let { ativo, onToggle }: Props = $props();

	const duracao = (ms: number): number => (prefersReducedMotion.current ? 0 : ms);
</script>

<div
	class="min-w-0 shrink-0"
	transition:slide={{ axis: 'x', duration: duracao(180), easing: cubicOut }}
>
	<button
		type="button"
		aria-pressed={ativo}
		onclick={onToggle}
		class="relative -ml-px inline-flex h-[var(--control-h-md)] items-center whitespace-nowrap rounded-r-lg border px-2.5 text-sm transition-colors duration-fast focus:outline-none focus-visible:z-[1] focus-visible:ring-2 focus-visible:ring-brand {ativo
			? 'z-[1] border-brand-soft bg-wash-brand font-medium text-brand'
			: 'border-border-subtle bg-surface text-text-muted hover:z-[1] hover:border-brand hover:text-brand'}"
	>
		Apenas a área
	</button>
</div>
