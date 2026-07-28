<script lang="ts">
	/**
	 * Skeleton de Admin > Órgãos, espelho EXATO do card da árvore em
	 * routes/(app)/admin/orgaos/+page.svelte (`.orgao-tree-card`): mesma toolbar
	 * (busca + ações), mesmas linhas recuadas por profundidade (`.orgao-row` de
	 * OrgaoTreeNode) e mesmo rodapé — zero salto de layout na troca p/ pronto.
	 * O card "Última sincronização" (`.siorg-card`) fica fora do loadState e
	 * não entra aqui.
	 */
	import Skeleton from '$lib/components/Skeleton.svelte';

	// Profundidade + largura do nome variam por linha p/ imitar a hierarquia
	// real (filhos recuados, nomes de tamanhos diferentes).
	const rows = [
		{ depth: 0, nome: 'w-2/5', hasChildren: true },
		{ depth: 1, nome: 'w-1/3', hasChildren: true },
		{ depth: 2, nome: 'w-1/4', hasChildren: false },
		{ depth: 2, nome: 'w-1/3', hasChildren: false },
		{ depth: 1, nome: 'w-2/5', hasChildren: false },
		{ depth: 0, nome: 'w-1/3', hasChildren: true },
		{ depth: 1, nome: 'w-1/4', hasChildren: false }
	];
</script>

<div aria-hidden="true" class="contents">
	<div class="skel-tree-card">
		<div class="skel-toolbar">
			<Skeleton class="h-9 w-full max-w-[19rem] rounded-xl" />
			<div class="skel-toolbar-actions">
				<Skeleton class="h-3.5 w-24 rounded" />
				<Skeleton class="h-3.5 w-24 rounded" />
			</div>
		</div>

		<ul class="skel-tree">
			{#each rows as row, i (i)}
				<li class="skel-row" style={`--depth:${row.depth}`}>
					{#if row.hasChildren}
						<Skeleton class="h-3 w-3 shrink-0 rounded" />
					{:else}
						<span class="skel-toggle-empty" aria-hidden="true"></span>
					{/if}
					<Skeleton class="h-[0.55rem] w-[0.55rem] shrink-0 rounded-full" />
					<Skeleton class="h-3.5 w-10 shrink-0 rounded" />
					<Skeleton class="h-3.5 {row.nome} rounded" />
				</li>
			{/each}
		</ul>

		<div class="skel-footnote">
			<Skeleton class="h-3 w-56 rounded" />
		</div>
	</div>
</div>

<style>
	/* Espelha .orgao-tree-card (chrome do card da arvore). */
	.skel-tree-card {
		background: var(--ds-color-surface-base);
		border: 1px solid var(--ds-color-border-base);
		border-radius: 16px;
		box-shadow: var(--ds-shadow-sm);
		overflow: hidden;
	}

	/* Espelha .orgao-tree-toolbar. */
	.skel-toolbar {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 1rem;
		padding: 0.875rem 1rem;
		border-bottom: 1px solid var(--ds-color-border-base);
		background: var(--ds-color-surface-muted);
		flex-wrap: wrap;
	}
	.skel-toolbar-actions {
		display: flex;
		gap: 0.75rem;
		align-items: center;
		flex-shrink: 0;
	}

	/* Espelha .orgao-tree (lista) + .orgao-row (linha, via OrgaoTreeNode). */
	.skel-tree {
		list-style: none;
		margin: 0;
		padding: 0.5rem 0.25rem 0.5rem 0;
		display: flex;
		flex-direction: column;
	}
	.skel-row {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.4rem 0.6rem;
		padding-left: calc(0.6rem + var(--depth, 0) * 1.4rem);
		margin: 1px 0.5rem;
	}
	.skel-toggle-empty {
		width: 0.75rem;
		height: 0.75rem;
		flex-shrink: 0;
	}

	/* Espelha .orgao-tree-footnote. */
	.skel-footnote {
		display: flex;
		align-items: center;
		padding: 0.625rem 1rem;
		border-top: 1px solid var(--ds-color-border-base);
		background: var(--ds-color-surface-muted);
	}
</style>
