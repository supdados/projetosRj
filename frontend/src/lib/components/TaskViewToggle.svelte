<script lang="ts">
	/**
	 * Alternância Lista ⇄ Kanban — segmented control clean.
	 *
	 * Trilho `surface-muted` com um indicador (thumb) no azul de marca
	 * (`bg-primary-600`, o mesmo dos botões primários) que DESLIZA entre os dois
	 * lados via `transform: translateX` (compositor-only → fluido e barato), com o
	 * rótulo ativo em branco. Substitui o toggle SVG pesado anterior
	 * (divisor em curva-S morfando + gradientes) por algo coerente com o resto da
	 * UI. Respeita `prefers-reduced-motion` (sem transição). A página continua dona
	 * do estado `view`; o componente só reflete o valor e chama `onSelect`.
	 */
	type ViewMode = 'list' | 'kanban';

	interface Props {
		/** Modo atual (dono = página). */
		view: ViewMode;
		/** Disparado ao clicar num dos lados. */
		onSelect: (mode: ViewMode) => void;
	}

	let { view, onSelect }: Props = $props();

	const segmentClass =
		'relative z-10 inline-flex flex-1 items-center justify-center rounded-md px-4 text-xs font-semibold transition-colors duration-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500';
</script>

<div
	class="relative inline-flex h-8 w-40 items-stretch rounded-lg border border-border-subtle bg-surface-muted"
	role="group"
	aria-label="Alternar visualização de tarefas"
>
	<!-- Indicador deslizante: na Lista fica à esquerda; no Kanban desliza 100% da
		 própria largura (= metade do trilho) para a direita. -->
	<span
		aria-hidden="true"
		class="pointer-events-none absolute inset-y-1 left-1 w-[calc(50%-0.25rem)] rounded-md bg-primary-600 shadow-sm transition-transform duration-300 ease-[cubic-bezier(0.4,0,0.2,1)] motion-reduce:transition-none {view ===
		'kanban'
			? 'translate-x-full'
			: 'translate-x-0'}"
	></span>

	<button
		type="button"
		class="{segmentClass} {view === 'list'
			? 'text-primary-fg'
			: 'text-text-muted hover:text-text-secondary'}"
		aria-pressed={view === 'list'}
		onclick={() => onSelect('list')}
	>
		Lista
	</button>
	<button
		type="button"
		class="{segmentClass} {view === 'kanban'
			? 'text-primary-fg'
			: 'text-text-muted hover:text-text-secondary'}"
		aria-pressed={view === 'kanban'}
		onclick={() => onSelect('kanban')}
	>
		Kanban
	</button>
</div>
