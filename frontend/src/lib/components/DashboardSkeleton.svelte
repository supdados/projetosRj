<script lang="ts">
	/**
	 * Skeleton do Dashboard, espelho EXATO do estado pronto de
	 * routes/(app)/dashboard/+page.svelte: mesmos wrappers de grid, mesmo chrome
	 * de Card/painel e mesmas dimensoes aproximadas do conteudo — a transicao
	 * loading -> pronto acontece sem salto de layout. Aparece apenas no primeiro
	 * carregamento (ou escopo de orgao sem cache); revisitas usam o cache SWR.
	 */
	import Skeleton from '$lib/components/Skeleton.svelte';

	// Larguras variadas dos titulos de projeto — quebra a monotonia das linhas,
	// como titulos reais de tamanhos diferentes.
	const projectTitleWidths = ['w-3/5', 'w-2/5', 'w-4/5', 'w-1/2', 'w-3/4', 'w-2/5', 'w-3/5'];
</script>

<div aria-hidden="true" class="contents">
	<!-- KPI cards: mesma grade 2x2 / 4 colunas e shell dos StatCards. -->
	<section>
		<div class="grid grid-cols-2 gap-3 lg:grid-cols-4">
			{#each { length: 4 } as _, i (i)}
				<div
					class="flex h-full items-center gap-3 rounded-lg border border-border-subtle bg-surface px-5 py-3 shadow-sm"
				>
					<Skeleton class="h-11 w-11 rounded-xl" />
					<div class="flex min-w-0 flex-col gap-1.5">
						<Skeleton class="h-7 w-12 rounded-md" />
						<Skeleton class="h-3.5 w-20 rounded" />
						<Skeleton class="hidden h-3 w-36 rounded sm:block" />
					</div>
				</div>
			{/each}
		</div>
	</section>

	<!-- Split 2+1: projetos recentes (esq) + tarefas (dir), como no estado pronto. -->
	<div class="grid grid-cols-1 items-stretch gap-4 lg:min-h-0 lg:flex-1 lg:grid-cols-3">
		<!-- Painel Projetos Recentes: chrome + cabecalho de tabela + 7 linhas. -->
		<div class="lg:col-span-2 lg:min-h-0">
			<section
				class="flex h-full flex-col overflow-hidden rounded-xl border border-border-subtle bg-surface shadow-sm"
			>
				<header class="flex shrink-0 items-center gap-2 border-b border-border-subtle px-5 py-4">
					<Skeleton class="h-[1.125rem] w-44 rounded-md" />
				</header>
				<div class="flex min-h-0 flex-1 flex-col overflow-hidden">
					<div class="skel-rp-grid items-center border-b border-border-subtle bg-surface-muted">
						<span class="flex justify-center px-3 py-2.5"><Skeleton class="h-2.5 w-6 rounded" /></span>
						<span class="px-3 py-2.5"><Skeleton class="h-2.5 w-16 rounded" /></span>
						<span class="flex justify-center px-3 py-2.5"><Skeleton class="h-2.5 w-12 rounded" /></span>
						<span class="flex justify-center px-3 py-2.5"><Skeleton class="h-2.5 w-16 rounded" /></span>
					</div>
					{#each { length: 7 } as _, i (i)}
						<div class="skel-rp-grid items-center border-b border-border-subtle">
							<span class="flex justify-center px-3 py-3"><Skeleton class="h-4 w-6 rounded" /></span>
							<span class="px-3 py-3"><Skeleton class="h-4 {projectTitleWidths[i]} rounded" /></span>
							<span class="flex justify-center px-3 py-3"><Skeleton class="h-4 w-14 rounded" /></span>
							<span class="flex justify-center px-3 py-3"><Skeleton class="h-4 w-16 rounded" /></span>
						</div>
					{/each}
				</div>
			</section>
		</div>

		<!-- Card Tarefas: hero do anel + legenda, chips "Por tipo" e recentes. -->
		<aside class="flex flex-col lg:col-span-1 lg:min-h-0">
			<section
				class="flex h-full flex-col rounded-xl border border-border-subtle bg-surface shadow-sm"
			>
				<header class="flex items-center justify-between gap-3 border-b border-border-subtle px-5 py-4">
					<Skeleton class="h-[1.125rem] w-20 rounded-md" />
					<Skeleton class="h-3 w-16 rounded" />
				</header>
				<div class="flex min-h-0 flex-1 flex-col p-5">
					<div class="flex flex-col gap-4 lg:min-h-0 lg:flex-1">
						<!-- Hero: circulo no lugar do donut + numero + 5 linhas de legenda. -->
						<section
							class="skel-tasks-hero flex shrink-0 items-center gap-4 rounded-xl border border-border-subtle px-4 py-3"
						>
							<Skeleton class="skel-tasks-ring rounded-full" />
							<div class="min-w-0 flex-1">
								<div class="mb-2 flex items-baseline gap-1.5">
									<Skeleton class="h-6 w-9 rounded-md" />
									<Skeleton class="h-3 w-24 rounded" />
								</div>
								<ul class="flex flex-col gap-2">
									{#each { length: 5 } as _, i (i)}
										<li class="flex items-center gap-2 leading-none">
											<Skeleton class="h-2 w-2 rounded-full" />
											<span class="min-w-0 flex-1"><Skeleton class="h-2.5 w-3/5 rounded" /></span>
											<Skeleton class="h-2.5 w-4 rounded" />
										</li>
									{/each}
								</ul>
							</div>
						</section>

						<!-- Chips "Por tipo": rotulo + 3 pilulas. -->
						<section class="flex shrink-0 flex-col gap-2">
							<Skeleton class="h-2.5 w-14 rounded" />
							<div class="flex flex-wrap gap-1.5">
								<Skeleton class="h-7 w-20 rounded-lg" />
								<Skeleton class="h-7 w-24 rounded-lg" />
								<Skeleton class="h-7 w-28 rounded-lg" />
							</div>
						</section>

						<!-- Recentes: rotulo + 4 linhas (icone, titulo+meta, avatar). -->
						<section class="flex flex-col gap-2 overflow-hidden lg:min-h-0 lg:flex-1">
							<Skeleton class="h-2.5 w-14 rounded" />
							<div class="flex flex-col gap-1.5 overflow-hidden lg:min-h-0 lg:flex-1">
								{#each { length: 4 } as _, i (i)}
									<div
										class="flex items-center gap-2.5 rounded-xl border border-border-subtle px-3 py-1.5"
									>
										<Skeleton class="h-5 w-5 rounded-md" />
										<span class="flex min-w-0 flex-1 flex-col gap-1">
											<Skeleton class="h-3.5 w-4/5 rounded" />
											<Skeleton class="h-2.5 w-3/5 rounded" />
										</span>
										<Skeleton class="h-6 w-6 rounded-full" />
									</div>
								{/each}
							</div>
						</section>
					</div>
				</div>
			</section>
		</aside>
	</div>
</div>

<style>
	/* Mesmo template de colunas do .rp-grid do RecentProjectsPanel (estilo
	   scoped la, replicado aqui): 64px | 1fr | 170px | 185px. */
	.skel-rp-grid {
		display: grid;
		grid-template-columns: 64px minmax(0, 1fr) 170px 185px;
	}

	/* Mesmo gradiente do .dashboard-tasks-hero da pagina (scoped la). */
	.skel-tasks-hero {
		background: linear-gradient(180deg, var(--ds-color-surface-muted), var(--ds-color-surface-base));
	}

	/* Mesmo dimensionamento responsivo do .dashboard-tasks-ring. */
	:global(.skel-tasks-ring) {
		width: clamp(80px, 30%, 128px);
		aspect-ratio: 1 / 1;
	}
</style>
