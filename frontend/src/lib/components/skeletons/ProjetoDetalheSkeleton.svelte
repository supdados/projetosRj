<script lang="ts">
	/**
	 * Skeleton do Detalhe de Projeto, espelho EXATO do estado pronto de
	 * routes/(app)/projetos/[id]/+page.svelte: mesmo cabecalho glass, card de
	 * "Detalhes do Projeto" (campos + EEGG + informacoes adicionais) e tabela de
	 * etapas — a transicao loading -> pronto acontece sem salto de layout.
	 * So aparece na 1a visita deste id (sem cache SWR); revisitas reabrem com o
	 * dado antigo instantaneo.
	 */
	import Skeleton from '$lib/components/Skeleton.svelte';
	import { CALENDAR_ENABLED } from '$lib/config/features';

	const stageDescWidths = ['w-4/5', 'w-3/5', 'w-2/3', 'w-1/2', 'w-3/4'];
</script>

<div aria-hidden="true" class="contents">
	<!-- Cabecalho (paridade ProjectHeader): mesma caixa/padding/gap, sem o
	     gradiente azul (so a forma importa para nao saltar o layout). -->
	<div class="rounded-xl border border-border-subtle bg-surface-muted px-6 py-5 shadow-sm">
		<div class="flex items-start justify-between gap-2">
			<div class="flex min-w-0 flex-1 flex-col gap-2">
				<Skeleton class="h-7 w-3/5 rounded-md" />
				<Skeleton class="h-4 w-2/5 rounded" />
			</div>
			<Skeleton class="h-9 w-24 shrink-0 rounded-lg" />
		</div>
		<div class="mt-4 flex flex-wrap items-end gap-2">
			<Skeleton class="h-8 w-28 rounded-md" />
			<Skeleton class="h-8 w-24 rounded-md" />
			<Skeleton class="h-8 w-32 rounded-md" />
			<Skeleton class="h-8 w-32 rounded-md" />
			<Skeleton class="h-8 w-40 rounded-md" />
		</div>
	</div>

	<!-- Card "Detalhes do Projeto": mesmo chrome header/body/footer do Card.svelte. -->
	<section class="rounded-xl border border-border-subtle bg-surface shadow-sm">
		<header class="flex items-center justify-between gap-3 border-b border-border-subtle px-5 py-4">
			<Skeleton class="h-[1.125rem] w-48 rounded-md" />
			<div class="flex items-center gap-2">
				<Skeleton class="h-8 w-32 rounded-md" />
				<Skeleton class="h-8 w-40 rounded-md" />
			</div>
		</header>
		<div class="flex flex-col gap-6 p-5">
			<!-- Grid de campos (Area Responsavel / Orgao / Processo SEI). -->
			<div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
				{#each { length: 3 } as _, i (i)}
					<div
						class="flex flex-col gap-1.5 rounded-md border border-border-subtle bg-surface px-4 py-2 shadow-sm"
					>
						<Skeleton class="h-2.5 w-24 rounded" />
						<Skeleton class="h-4 w-32 rounded" />
					</div>
				{/each}
			</div>

			<!-- EEGD: titulo + editor cascata. -->
			<div class="flex flex-col gap-3">
				<Skeleton class="h-4 w-72 rounded" />
				<div class="flex flex-col gap-2 rounded-md border border-border-subtle bg-surface p-4 shadow-sm">
					<Skeleton class="h-4 w-3/5 rounded" />
					<Skeleton class="h-4 w-2/5 rounded" />
					<Skeleton class="h-4 w-1/3 rounded" />
				</div>
			</div>

			<!-- Informacoes adicionais: links + observacao. -->
			<div class="flex flex-col gap-3">
				<Skeleton class="h-4 w-52 rounded" />
				<div class="rounded-md border border-border-subtle bg-surface p-5 shadow-sm">
					<div class="flex flex-col gap-3">
						{#each { length: 3 } as _, i (i)}
							<div class="flex items-center gap-2">
								<Skeleton class="h-4 w-4 rounded" />
								<Skeleton class="h-3.5 w-24 rounded" />
								<Skeleton class="h-3.5 w-40 rounded" />
							</div>
						{/each}
					</div>
					<div class="my-4 border-t border-border-subtle"></div>
					<div class="flex items-start justify-between gap-4">
						<div class="flex min-w-0 flex-1 flex-col gap-2">
							<Skeleton class="h-3.5 w-24 rounded" />
							<Skeleton class="h-4 w-4/5 rounded" />
						</div>
						<Skeleton class="h-8 w-36 shrink-0 rounded-md" />
					</div>
				</div>
			</div>
		</div>
		<footer class="flex items-center justify-end gap-3 border-t border-border-subtle px-5 py-4">
			<Skeleton class="h-8 w-32 rounded-md" />
			<Skeleton class="h-8 w-40 rounded-md" />
		</footer>
	</section>

	<!-- Divisor de secao "Etapas do Projeto" (mesmo padrao da pagina pronta). -->
	<div class="skel-section-divider">
		<Skeleton class="h-[1.125rem] w-52 rounded-md" />
	</div>

	<!-- Acoes (Importar Modelo / Adicionar reuniao). -->
	<div class="flex flex-wrap items-center justify-end gap-2">
		<Skeleton class="h-9 w-36 rounded-md" />
		{#if CALENDAR_ENABLED}
			<Skeleton class="h-9 w-40 rounded-md" />
		{/if}
	</div>

	<!-- Tabela de etapas: mesmo cartao/cabecalho de colunas do StageList pronto.
	     table-layout fixed + larguras no <colgroup> reproduzem exatamente as
	     colunas col-drag..col-actions (fixadas via thead th no componente real). -->
	<div class="overflow-hidden rounded-[14px] border border-border-subtle bg-surface shadow-sm">
		<div class="overflow-x-auto">
			<table class="skel-stage-table m-0 w-full min-w-[1100px] border-separate border-spacing-0">
				<colgroup>
					<col style="width: 44px" />
					<col style="width: 64px" />
					<col style="width: 306px" />
					<col style="width: 130px" />
					<col style="width: 130px" />
					<col style="width: 170px" />
					<col style="width: 140px" />
					<col style="width: 150px" />
					<col style="width: 72px" />
				</colgroup>
				<thead>
					<tr>
						<th class="border-b border-border-subtle bg-surface-muted px-2.5 py-2.5"></th>
						<th class="border-b border-border-subtle bg-surface-muted px-2.5 py-2.5">
							<span class="flex justify-center"><Skeleton class="h-2.5 w-6 rounded" /></span>
						</th>
						<th class="border-b border-border-subtle bg-surface-muted px-2.5 py-2.5">
							<Skeleton class="h-2.5 w-16 rounded" />
						</th>
						<th class="border-b border-border-subtle bg-surface-muted px-2.5 py-2.5">
							<span class="flex justify-center"><Skeleton class="h-2.5 w-16 rounded" /></span>
						</th>
						<th class="border-b border-border-subtle bg-surface-muted px-2.5 py-2.5">
							<span class="flex justify-center"><Skeleton class="h-2.5 w-14 rounded" /></span>
						</th>
						<th class="border-b border-border-subtle bg-surface-muted px-2.5 py-2.5">
							<span class="flex justify-center"><Skeleton class="h-2.5 w-20 rounded" /></span>
						</th>
						<th class="border-b border-border-subtle bg-surface-muted px-2.5 py-2.5">
							<span class="flex justify-center"><Skeleton class="h-2.5 w-14 rounded" /></span>
						</th>
						<th class="border-b border-border-subtle bg-surface-muted px-2.5 py-2.5">
							<span class="flex justify-center"><Skeleton class="h-2.5 w-14 rounded" /></span>
						</th>
						<th class="border-b border-border-subtle bg-surface-muted px-2.5 py-2.5">
							<span class="flex justify-center"><Skeleton class="h-2.5 w-8 rounded" /></span>
						</th>
					</tr>
				</thead>
				<tbody>
					{#each { length: 5 } as _, i (i)}
						<tr>
							<td class="border-t border-border-subtle px-2.5 py-3 text-center">
								<span class="inline-flex justify-center"><Skeleton class="h-3.5 w-3.5 rounded" /></span>
							</td>
							<td class="border-t border-border-subtle px-2.5 py-3 text-center">
								<span class="inline-flex justify-center"><Skeleton class="h-3.5 w-8 rounded" /></span>
							</td>
							<td class="border-t border-border-subtle px-2.5 py-3">
								<Skeleton class="h-4 {stageDescWidths[i % stageDescWidths.length]} rounded" />
							</td>
							<td class="border-t border-border-subtle px-2.5 py-3 text-center">
								<span class="inline-flex justify-center"><Skeleton class="h-3.5 w-16 rounded" /></span>
							</td>
							<td class="border-t border-border-subtle px-2.5 py-3 text-center">
								<span class="inline-flex justify-center"><Skeleton class="h-3.5 w-16 rounded" /></span>
							</td>
							<td class="border-t border-border-subtle px-2.5 py-3 text-center">
								<span class="inline-flex justify-center"><Skeleton class="h-3.5 w-20 rounded" /></span>
							</td>
							<td class="border-t border-border-subtle px-2.5 py-3 text-center">
								<span class="inline-flex justify-center"><Skeleton class="h-3.5 w-12 rounded" /></span>
							</td>
							<td class="border-t border-border-subtle px-2.5 py-3 text-center">
								<span class="inline-flex justify-center"><Skeleton class="h-6 w-20 rounded-full" /></span>
							</td>
							<td class="border-t border-border-subtle px-2.5 py-3 text-center">
								<span class="inline-flex justify-center"><Skeleton class="h-7 w-7 rounded-md" /></span>
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	</div>
</div>

<style>
	/* Mesmo padrao visual de .section-divider da pagina pronta (linha + titulo). */
	.skel-section-divider {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		margin-top: 0.5rem;
	}
	.skel-section-divider::after {
		content: '';
		flex: 1;
		height: 1px;
		background: var(--ds-color-border-base);
	}

	.skel-stage-table {
		table-layout: fixed;
	}
</style>
