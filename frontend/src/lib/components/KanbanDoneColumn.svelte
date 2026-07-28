<script lang="ts">
	/**
	 * Coluna "Finalizada" como trilho colapsável. Sempre nasce recolhida — a
	 * preferência NÃO é persistida, então ao sair e voltar à página o trilho
	 * volta ao estado retraído. Fechado continua drop target. O toggle liga o
	 * sinal KANBAN_COLUMN_MOTION durante o morph de largura — ver
	 * kanbanColumnMotion.ts.
	 */
	import { getContext } from 'svelte';
	import KanbanColumnHeader from '$lib/components/KanbanColumnHeader.svelte';
	import KanbanDropzone from '$lib/components/KanbanDropzone.svelte';
	import type { BoardColumn } from '$lib/types/board';
	import type { KanbanDndProps } from '$lib/types/kanbanDnd';
	import {
		KANBAN_COLUMN_MOTION,
		type KanbanColumnMotionSignal
	} from '$lib/utils/kanbanColumnMotion';

	interface Props extends KanbanDndProps {
		column: BoardColumn;
	}

	let { column, ...dnd }: Props = $props();

	const requestArchive = getContext<(() => void) | undefined>('requestArchiveFinalizadas');

	// Sempre recolhida ao montar — sem persistência (volta retraída a cada visita).
	let open = $state<boolean>(false);

	const count = $derived(column.tasks.length);
	const view = $derived(dnd.zoneView('finalizada'));

	// Curvas M3 por direção — strings estáticas (Tailwind não gera classe de valor computado).
	const RAIL_MOTION_OPEN =
		'motion-safe:duration-[360ms] motion-safe:[transition-timing-function:cubic-bezier(0.05,0.7,0.1,1)]';
	const RAIL_MOTION_CLOSE =
		'motion-safe:duration-[280ms] motion-safe:[transition-timing-function:cubic-bezier(0.3,0,0.8,0.15)]';
	const railMotion = $derived(open ? RAIL_MOTION_OPEN : RAIL_MOTION_CLOSE);

	const columnMotion = getContext<KanbanColumnMotionSignal | undefined>(KANBAN_COLUMN_MOTION);
	const REDUCED_MOTION =
		typeof window !== 'undefined' &&
		window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
	// Fallback p/ transitionend perdido (aba em background).
	const RELEASE_MS = 360 + 80;
	let releaseTimer: ReturnType<typeof setTimeout> | null = null;

	function releaseColumnMotion(): void {
		if (releaseTimer) {
			clearTimeout(releaseTimer);
			releaseTimer = null;
		}
		if (columnMotion) columnMotion.active = false;
	}

	function toggleOpen(): void {
		open = !open;
		if (REDUCED_MOTION || !columnMotion) return;
		if (releaseTimer) clearTimeout(releaseTimer);
		columnMotion.active = true;
		releaseTimer = setTimeout(releaseColumnMotion, RELEASE_MS);
	}

	function onWidthTransitionEnd(event: TransitionEvent): void {
		// transitionend borbulha dos filhos: só a width do próprio section conta.
		if (event.target !== event.currentTarget) return;
		if (event.propertyName !== 'width') return;
		releaseColumnMotion();
	}
</script>

<!-- Larguras explícitas dos dois lados: flex-1 não anima width. -->
<section
	class="flex h-full min-h-0 shrink-0 flex-col gap-2 [contain:layout] motion-safe:transition-[width] {railMotion} {open
		? 'w-[280px] rounded-xl border border-border-subtle'
		: 'w-[52px]'}"
	aria-labelledby={open ? 'kanban-col-finalizada' : undefined}
	aria-label={open ? undefined : `Coluna ${column.label} recolhida (${count} tarefas)`}
	ontransitionend={onWidthTransitionEnd}
>
	{#if !open}
		<div
			data-status="finalizada"
			role="group"
			aria-label={`Coluna ${column.label} recolhida (${count} tarefas). Aceita soltar um card para finalizar.`}
			class="kdone-rail flex min-h-0 flex-1 flex-col items-center gap-2 rounded-xl border border-border-subtle py-3 shadow-sm transition-[box-shadow,border-color,opacity] duration-fast hover:border-border-strong hover:shadow-md {view.isOver &&
			view.canDrop
				? 'is-rail-over'
				: ''} {view.isOver && !view.canDrop ? 'cursor-not-allowed opacity-60' : ''}"
			ondragenter={(event) => dnd.onZoneDragEnter(event, 'finalizada')}
			ondragover={(event) => dnd.onZoneDragOver(event, 'finalizada')}
			ondragleave={(event) => dnd.onZoneDragLeave(event, 'finalizada')}
			ondrop={(event) => dnd.onZoneDrop(event, 'finalizada')}
		>
			<button
				type="button"
				onclick={toggleOpen}
				aria-expanded="false"
				aria-label={`Expandir coluna ${column.label} (${count} tarefas)`}
				class="flex min-h-0 flex-1 flex-col items-center gap-3 rounded-lg px-1 pt-0.5 text-text-muted transition-colors duration-fast hover:text-text-secondary focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
			>
				<svg
					viewBox="0 0 24 24"
					class="h-3.5 w-3.5 shrink-0"
					fill="none"
					stroke="currentColor"
					stroke-width="2"
					stroke-linecap="round"
					stroke-linejoin="round"
					aria-hidden="true"
				>
					<path d="M15 18l-6-6 6-6" />
				</svg>
				{#key count}
					<span class="kdone-count shrink-0 text-xs font-bold tabular-nums">
						{count}
					</span>
				{/key}
				<span
					class="font-heading text-sm font-bold tracking-wide text-text-secondary [writing-mode:vertical-rl]"
				>
					{column.label}
				</span>
			</button>

			{#if requestArchive}
				<button
					type="button"
					onclick={requestArchive}
					disabled={count === 0}
					title="Arquivar tarefas finalizadas do escopo atual"
					aria-label="Arquivar finalizados"
					class="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-text-muted transition-colors duration-fast hover:bg-surface-muted hover:text-text-secondary focus:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:opacity-40 disabled:hover:bg-transparent disabled:hover:text-text-muted"
				>
					<i class="fas fa-box-archive text-xs" aria-hidden="true"></i>
				</button>
			{/if}
		</div>
	{:else}
		<KanbanColumnHeader status="finalizada" headingId="kanban-col-finalizada" label={column.label} {count}>
			{#snippet trailing()}
				<button
					type="button"
					onclick={toggleOpen}
					aria-expanded="true"
					aria-label={`Recolher coluna ${column.label}`}
					title="Recolher coluna"
					class="inline-flex h-6 w-6 items-center justify-center rounded-md text-text-muted transition-colors duration-fast hover:bg-surface-muted hover:text-text-secondary focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
				>
					<svg
						viewBox="0 0 24 24"
						class="h-3.5 w-3.5"
						fill="none"
						stroke="currentColor"
						stroke-width="2"
						stroke-linecap="round"
						stroke-linejoin="round"
						aria-hidden="true"
					>
						<path d="M9 18l6-6-6-6" />
					</svg>
				</button>
			{/snippet}
		</KanbanColumnHeader>

		<KanbanDropzone status="finalizada" label={column.label} tasks={column.tasks} {...dnd} />

		{#if requestArchive}
			<div class="shrink-0 px-1 pb-1">
				<button
					type="button"
					onclick={requestArchive}
					disabled={count === 0}
					title="Arquivar tarefas finalizadas do escopo atual"
					class="inline-flex w-full items-center justify-center gap-2 rounded-lg border border-border-subtle px-3 py-2 text-sm font-medium text-text-muted transition-colors duration-fast hover:border-border-strong hover:bg-surface-muted hover:text-text-secondary focus:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:opacity-50 disabled:hover:border-border-subtle disabled:hover:bg-transparent disabled:hover:text-text-muted"
				>
					<i class="fas fa-box-archive" aria-hidden="true"></i>
					Arquivar finalizados
				</button>
			</div>
		{/if}
	{/if}
</section>

<style>
	/* Recolhida: verde bem fraquinho para sinalizar "finalizada" sem peso visual. */
	.kdone-rail {
		background-color: var(--ds-color-wash-success);
	}

	/* Trilho realçado quando é alvo válido do drag em curso (eco do is-zone-over). */
	.is-rail-over {
		border-color: var(--ds-color-border-brand-soft);
		background-color: var(--ds-color-wash-brand);
		box-shadow: inset 0 0 0 1px var(--ds-color-border-brand-soft);
	}

	/* Pop da contagem do trilho quando o número muda (remontada via {#key}). */
	@keyframes kdone-count-pop {
		0% {
			transform: scale(1);
		}
		45% {
			transform: scale(1.18);
		}
		100% {
			transform: scale(1);
		}
	}
	.kdone-count {
		display: inline-block;
		animation: kdone-count-pop 0.24s ease;
	}

	@media (prefers-reduced-motion: reduce) {
		.kdone-count {
			animation: none;
		}
	}
</style>
