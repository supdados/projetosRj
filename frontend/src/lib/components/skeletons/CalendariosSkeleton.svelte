<script lang="ts">
	/**
	 * Skeleton do hub de Calendario, espelho aproximado do estado pronto de
	 * routes/(app)/calendarios/+page.svelte: mesma barra de navegacao de
	 * periodo, mesmo card de grade (chrome cal-nav-bar/cal-grid-wrap) e mesma
	 * coluna lateral (toggle de visao + 3 paineis do CalendarRightPanel:
	 * mini-mes, "Esta semana" e "Time"). A visao real alterna entre
	 * mes/semana/dia (persistida em localStorage, so conhecida apos o mount) —
	 * este skeleton usa uma grade generica de 7 colunas que aproxima tanto a
	 * grade mensal quanto o time-grid, priorizando o chrome (bordas, larguras,
	 * altura aproximada) para reduzir o salto de layout.
	 */
	import Skeleton from '$lib/components/Skeleton.svelte';

	const weekRows = Array.from({ length: 5 });
	const dayCols = Array.from({ length: 7 });
	const miniWeeks = Array.from({ length: 6 });
	const weekListItems = Array.from({ length: 4 });
	const teamItems = Array.from({ length: 4 });
</script>

<div aria-hidden="true" class="contents">
	<div class="cal-skel-layout">
		<div class="cal-skel-main-col">
			<!-- Barra de navegacao de periodo (‹ Mês Ano › + Hoje). -->
			<div class="cal-skel-nav-bar">
				<div class="cal-skel-month-nav">
					<Skeleton class="h-[1.9rem] w-[1.9rem] rounded-md" />
					<Skeleton class="h-4 w-28 rounded-md" />
					<Skeleton class="h-[1.9rem] w-[1.9rem] rounded-md" />
				</div>
				<Skeleton class="cal-skel-today-btn h-[1.7rem] w-14 rounded-md" />
			</div>

			<!-- Grade (aproxima mes/semana): cabecalho de dias + N linhas x 7 cols. -->
			<div class="cal-skel-grid-wrap">
				<div class="cal-skel-grid-headers">
					{#each dayCols as _, i (i)}
						<div class="cal-skel-day-header">
							<Skeleton class="h-2.5 w-5 rounded" />
						</div>
					{/each}
				</div>
				{#each weekRows as _, wi (wi)}
					<div class="cal-skel-week">
						{#each dayCols as _, di (di)}
							<div class="cal-skel-cell">
								<Skeleton class="h-6 w-6 shrink-0 self-center rounded-full" />
								<Skeleton class="h-[1.05rem] w-full rounded" />
								{#if (wi + di) % 3 !== 0}
									<Skeleton class="h-[1.05rem] w-4/5 rounded" />
								{/if}
							</div>
						{/each}
					</div>
				{/each}
			</div>
		</div>

		<!-- Coluna direita: toggle de visao + 3 cards (mini-mes / semana / time). -->
		<div class="cal-skel-side-col">
			<div class="cal-skel-view-toggle">
				{#each { length: 3 } as _, i (i)}
					<Skeleton class="h-[1.9rem] flex-1 rounded" />
				{/each}
			</div>

			<!-- Mini calendario mensal. -->
			<div class="cal-skel-card">
				<div class="mb-2 flex items-center justify-between px-1">
					<Skeleton class="h-6 w-6 rounded" />
					<Skeleton class="h-3 w-20 rounded" />
					<Skeleton class="h-6 w-6 rounded" />
				</div>
				<div class="mb-1 grid grid-cols-7">
					{#each dayCols as _, i (i)}
						<span class="flex justify-center"><Skeleton class="h-2 w-2.5 rounded" /></span>
					{/each}
				</div>
				{#each miniWeeks as _, wi (wi)}
					<div class="grid grid-cols-7 py-[1px]">
						{#each dayCols as _, di (di)}
							<span class="flex items-center justify-center py-[1px]">
								<Skeleton class="h-6 w-6 rounded-full" />
							</span>
						{/each}
					</div>
				{/each}
			</div>

			<!-- "Esta semana": titulo + lista de eventos. -->
			<div class="cal-skel-card">
				<Skeleton class="mb-3 h-2.5 w-24 rounded" />
				<div class="flex flex-col gap-2.5">
					{#each weekListItems as _, i (i)}
						<div class="flex items-start gap-2.5 px-1 py-1">
							<Skeleton class="mt-1 h-2 w-2 shrink-0 rounded-full" />
							<div class="flex min-w-0 flex-1 flex-col gap-1">
								<Skeleton class="h-3 w-4/5 rounded" />
								<Skeleton class="h-2.5 w-3/5 rounded" />
							</div>
						</div>
					{/each}
				</div>
			</div>

			<!-- "Time": titulo + lista de membros. -->
			<div class="cal-skel-card">
				<Skeleton class="mb-2 h-2.5 w-12 rounded" />
				<div class="flex flex-col gap-1">
					{#each teamItems as _, i (i)}
						<div class="flex items-center gap-2 px-1 py-1">
							<Skeleton class="h-6 w-6 shrink-0 rounded-full" />
							<Skeleton class="h-3.5 w-2/5 rounded" />
						</div>
					{/each}
				</div>
			</div>
		</div>
	</div>
</div>

<style>
	/* Espelha .cal-layout / .cal-main-col / .cal-side-col (scoped na pagina). */
	.cal-skel-layout {
		display: flex;
		gap: 1.25rem;
		align-items: flex-start;
	}
	.cal-skel-main-col {
		flex: 1 1 0;
		min-width: 0;
	}
	.cal-skel-side-col {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
		width: 20rem;
		flex-shrink: 0;
	}
	@media (max-width: 1024px) {
		.cal-skel-side-col {
			width: 100%;
		}
		.cal-skel-layout {
			flex-direction: column;
		}
	}

	/* Espelha .cal-nav-bar. */
	.cal-skel-nav-bar {
		position: relative;
		display: flex;
		justify-content: center;
		align-items: center;
		padding: 0.5rem 0.75rem;
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: 12px 12px 0 0;
	}
	.cal-skel-month-nav {
		display: flex;
		align-items: center;
		gap: 0.4rem;
	}
	/* :global porque a classe é aplicada dentro do componente filho Skeleton. */
	:global(.cal-skel-today-btn) {
		position: absolute;
		right: 0.75rem;
		top: 50%;
		transform: translateY(-50%);
	}

	/* Espelha .cal-grid-wrap / .cal-grid-headers / .cal-week / .cal-cell. */
	.cal-skel-grid-wrap {
		border: 1px solid var(--color-border);
		border-top: none;
		border-radius: 0 0 12px 12px;
		overflow: hidden;
		background: var(--color-surface);
		min-height: clamp(30rem, calc(100vh - 16rem), 52rem);
		display: flex;
		flex-direction: column;
	}
	.cal-skel-grid-headers {
		display: grid;
		grid-template-columns: repeat(7, minmax(0, 1fr));
		flex-shrink: 0;
	}
	.cal-skel-day-header {
		display: flex;
		justify-content: center;
		padding: 0.5rem 0.2rem;
		border-bottom: 1px solid var(--color-border);
		background: var(--color-surface-muted);
	}
	.cal-skel-week {
		display: grid;
		grid-template-columns: repeat(7, minmax(0, 1fr));
		flex: 1;
		min-height: 0;
	}
	.cal-skel-cell {
		display: flex;
		flex-direction: column;
		gap: 0.3rem;
		border-right: 1px solid var(--color-border);
		border-bottom: 1px solid var(--color-border);
		padding: 0.3rem 0.3rem 0.4rem;
		min-height: 0;
		overflow: hidden;
	}
	.cal-skel-week .cal-skel-cell:nth-child(7n) {
		border-right: none;
	}

	/* Espelha .cal-view-toggle. */
	.cal-skel-view-toggle {
		display: flex;
		width: 100%;
		gap: 1px;
		border: 1px solid var(--color-border);
		border-radius: 8px;
		overflow: hidden;
		background: var(--color-surface);
		padding: 2px;
	}

	/* Espelha os 3 cards de CalendarRightPanel (rounded-xl border p-4 shadow-sm). */
	.cal-skel-card {
		border-radius: 12px;
		border: 1px solid var(--color-border);
		background: var(--color-surface);
		padding: 1rem;
		box-shadow: var(--ds-shadow-sm);
	}
</style>
