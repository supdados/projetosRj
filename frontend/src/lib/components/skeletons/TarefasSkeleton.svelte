<script lang="ts">
	/**
	 * Skeleton do Hub de Tarefas (modo lista), espelho EXATO da area de dados de
	 * routes/(app)/tarefas/+page.svelte: o card header + filtros ficam FORA deste
	 * componente (nao dependem do fetch, seguem renderizados). Aqui so o miolo —
	 * grupos de projeto/etapa/tarefa (mesma grade `.task-hub-grid` das linhas
	 * reais, para as colunas baterem) + a barra de paginacao.
	 */
	import Skeleton from '$lib/components/Skeleton.svelte';
</script>

<div aria-hidden="true" class="contents">
	<div class="flex flex-col gap-4">
		<div class="flex flex-col gap-5">
			<!-- Grupo de projeto 1: 2 etapas (3 + 2 tarefas). -->
			<section class="overflow-hidden rounded-lg border border-border-subtle bg-surface shadow-sm">
				<div class="flex w-full items-center gap-1.5 px-5 py-4">
					<Skeleton class="h-4 w-4 rounded" />
					<Skeleton class="h-4 w-8 rounded" />
					<Skeleton class="h-4 w-64 rounded" />
					<span class="ml-auto flex shrink-0 items-center gap-2">
						<Skeleton class="h-3 w-16 rounded" />
						<Skeleton class="h-3 w-16 rounded" />
					</span>
				</div>
				<div class="border-t border-border-subtle">
					<div class="flex flex-col gap-3 p-3">
						<div class="overflow-hidden rounded-lg border border-border-subtle">
							<div class="task-hub-grid w-full items-center bg-wash-neutral px-3 py-2">
								<span class="flex min-w-0 items-center gap-2">
									<Skeleton class="h-2.5 w-2.5 rounded" />
									<Skeleton class="h-3 w-10 rounded" />
									<Skeleton class="h-3 w-32 rounded" />
								</span>
								<Skeleton class="h-2.5 w-12 justify-self-center rounded" />
								<Skeleton class="h-2.5 w-8 justify-self-center rounded" />
								<Skeleton class="h-2.5 w-10 justify-self-center rounded" />
								<Skeleton class="h-2.5 w-16 justify-self-center rounded" />
								<Skeleton class="h-2.5 w-10 justify-self-center rounded" />
							</div>
							{#each { length: 3 } as _, r (r)}
								<div class="task-hub-grid items-center border-b border-border-subtle px-3 py-2 last:border-b-0">
									<Skeleton class="h-3.5 w-4/5 rounded" />
									<Skeleton class="h-6 w-full rounded-md" />
									<Skeleton class="h-6 w-full rounded-md" />
									<Skeleton class="h-6 w-full rounded-md" />
									<Skeleton class="h-6 w-24 justify-self-center rounded-full" />
									<span class="flex items-center justify-center gap-1">
										<Skeleton class="h-5 w-5 rounded" />
										<Skeleton class="h-5 w-5 rounded" />
										<Skeleton class="h-5 w-5 rounded" />
									</span>
								</div>
							{/each}
						</div>
						<div class="overflow-hidden rounded-lg border border-border-subtle">
							<div class="task-hub-grid w-full items-center bg-wash-neutral px-3 py-2">
								<span class="flex min-w-0 items-center gap-2">
									<Skeleton class="h-2.5 w-2.5 rounded" />
									<Skeleton class="h-3 w-10 rounded" />
									<Skeleton class="h-3 w-24 rounded" />
								</span>
								<Skeleton class="h-2.5 w-12 justify-self-center rounded" />
								<Skeleton class="h-2.5 w-8 justify-self-center rounded" />
								<Skeleton class="h-2.5 w-10 justify-self-center rounded" />
								<Skeleton class="h-2.5 w-16 justify-self-center rounded" />
								<Skeleton class="h-2.5 w-10 justify-self-center rounded" />
							</div>
							{#each { length: 2 } as _, r (r)}
								<div class="task-hub-grid items-center border-b border-border-subtle px-3 py-2 last:border-b-0">
									<Skeleton class="h-3.5 w-3/5 rounded" />
									<Skeleton class="h-6 w-full rounded-md" />
									<Skeleton class="h-6 w-full rounded-md" />
									<Skeleton class="h-6 w-full rounded-md" />
									<Skeleton class="h-6 w-24 justify-self-center rounded-full" />
									<span class="flex items-center justify-center gap-1">
										<Skeleton class="h-5 w-5 rounded" />
										<Skeleton class="h-5 w-5 rounded" />
										<Skeleton class="h-5 w-5 rounded" />
									</span>
								</div>
							{/each}
						</div>
					</div>
				</div>
			</section>

			<!-- Grupo de projeto 2: 1 etapa (2 tarefas). -->
			<section class="overflow-hidden rounded-lg border border-border-subtle bg-surface shadow-sm">
				<div class="flex w-full items-center gap-1.5 px-5 py-4">
					<Skeleton class="h-4 w-4 rounded" />
					<Skeleton class="h-4 w-8 rounded" />
					<Skeleton class="h-4 w-48 rounded" />
					<span class="ml-auto flex shrink-0 items-center gap-2">
						<Skeleton class="h-3 w-16 rounded" />
						<Skeleton class="h-3 w-16 rounded" />
					</span>
				</div>
				<div class="border-t border-border-subtle">
					<div class="flex flex-col gap-3 p-3">
						<div class="overflow-hidden rounded-lg border border-border-subtle">
							<div class="task-hub-grid w-full items-center bg-wash-neutral px-3 py-2">
								<span class="flex min-w-0 items-center gap-2">
									<Skeleton class="h-2.5 w-2.5 rounded" />
									<Skeleton class="h-3 w-10 rounded" />
									<Skeleton class="h-3 w-28 rounded" />
								</span>
								<Skeleton class="h-2.5 w-12 justify-self-center rounded" />
								<Skeleton class="h-2.5 w-8 justify-self-center rounded" />
								<Skeleton class="h-2.5 w-10 justify-self-center rounded" />
								<Skeleton class="h-2.5 w-16 justify-self-center rounded" />
								<Skeleton class="h-2.5 w-10 justify-self-center rounded" />
							</div>
							{#each { length: 2 } as _, r (r)}
								<div class="task-hub-grid items-center border-b border-border-subtle px-3 py-2 last:border-b-0">
									<Skeleton class="h-3.5 w-2/3 rounded" />
									<Skeleton class="h-6 w-full rounded-md" />
									<Skeleton class="h-6 w-full rounded-md" />
									<Skeleton class="h-6 w-full rounded-md" />
									<Skeleton class="h-6 w-24 justify-self-center rounded-full" />
									<span class="flex items-center justify-center gap-1">
										<Skeleton class="h-5 w-5 rounded" />
										<Skeleton class="h-5 w-5 rounded" />
										<Skeleton class="h-5 w-5 rounded" />
									</span>
								</div>
							{/each}
						</div>
					</div>
				</div>
			</section>
		</div>

		<!-- Barra de paginacao: mesmo chrome do PaginationBar pronto. -->
		<div
			class="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border-subtle bg-surface px-3 py-2 shadow-sm"
		>
			<Skeleton class="h-4 w-40 rounded" />
			<div class="flex items-center gap-1">
				{#each { length: 7 } as _, i (i)}
					<Skeleton class="h-8 w-9 rounded-md" />
				{/each}
			</div>
		</div>
	</div>
</div>
