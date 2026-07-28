<script lang="ts">
	/**
	 * Nó RECURSIVO da árvore de órgãos (Admin > Órgãos), agora READ-ONLY: a
	 * estrutura é espelho do SIORG-RJ e não se edita aqui. Linha com chevron de
	 * expandir/recolher, dot + sigla/nome + badge de tipo, badge "inativa" e
	 * chip "não oficial" quando `codigo_externo` é null (legado local, ex.:
	 * ECENTRAL). Filhos renderizados por auto-referência.
	 *
	 * Componente CONTROLADO: expand/collapse, seleção e busca vivem na página
	 * (`expandedIds`, `selectedId`, `filterQuery`); emite `onToggle`/`onSelect`.
	 */
	import OrgaoTreeNode from './OrgaoTreeNode.svelte';
	import type { OrgaoNode } from '$lib/types/adminOrgaos';

	interface Props {
		node: OrgaoNode;
		depth?: number;
		/** Ids de nós expandidos (controlado pela página). */
		expandedIds: Set<number>;
		/** Id do nó selecionado (realce da linha). */
		selectedId: number | null;
		/** Termo de busca normalizado (lowercase, sem espaços nas bordas). */
		filterQuery: string;
		onToggle: (orgaoId: number) => void;
		onSelect: (orgaoId: number) => void;
	}

	let { node, depth = 0, expandedIds, selectedId, filterQuery, onToggle, onSelect }: Props =
		$props();

	const hasChildren = $derived(node.filhos.length > 0);
	const expanded = $derived(expandedIds.has(node.id));
	const isSelected = $derived(selectedId === node.id);

	const selfMatches = $derived(matchesQuery(node));
	/** True se o nó ou algum descendente casa com a busca. */
	const subtreeMatches = $derived(filterQuery === '' || selfMatches || anyDescendantMatches(node));
	/** Esconde o nó quando há busca e nem ele nem o subtree casam. */
	const hidden = $derived(filterQuery !== '' && !subtreeMatches);

	function matchesQuery(n: OrgaoNode): boolean {
		if (filterQuery === '') return false;
		const sigla = (n.sigla ?? '').toLowerCase();
		const nome = (n.nome ?? '').toLowerCase();
		return sigla.includes(filterQuery) || nome.includes(filterQuery);
	}

	function anyDescendantMatches(n: OrgaoNode): boolean {
		for (const child of n.filhos) {
			if (matchesQuery(child) || anyDescendantMatches(child)) return true;
		}
		return false;
	}

	/** Slug do tipo para a cor do dot (cores no bloco style). */
	const tipoSlug = $derived(
		(node.tipo ?? '')
			.toLowerCase()
			.replace(/ç/g, 'c')
			.replace(/ã/g, 'a')
			.replace(/ú/g, 'u')
			.replace(/í/g, 'i')
			.replace(/é/g, 'e')
			.replace(/á/g, 'a')
			.replace(/ /g, '-')
	);

	function handleRowClick(event: MouseEvent): void {
		const target = event.target as HTMLElement;
		if (target.closest('.orgao-toggle')) return;
		onSelect(node.id);
	}

	function handleRowKeydown(event: KeyboardEvent): void {
		if (event.target !== event.currentTarget) return;
		if (event.key === 'Enter' || event.key === ' ') {
			event.preventDefault();
			onSelect(node.id);
		}
	}
</script>

<li
	class="orgao-node"
	class:is-inactive={!node.ativo}
	class:is-hidden={hidden}
	class:is-leaf={!hasChildren}
	style={`--orgao-depth:${depth}`}
	data-id={node.id}
	role="none"
>
	<div
		class="orgao-row"
		class:is-selected={isSelected}
		class:is-match={selfMatches}
		role="treeitem"
		aria-selected={isSelected}
		aria-expanded={hasChildren ? expanded : undefined}
		tabindex="-1"
		onclick={handleRowClick}
		onkeydown={handleRowKeydown}
	>
		{#if hasChildren}
			<button
				type="button"
				onclick={() => onToggle(node.id)}
				aria-expanded={expanded}
				aria-label={expanded ? 'Recolher subunidades' : 'Expandir subunidades'}
				class="orgao-toggle"
				class:is-open={expanded}
			>
				<i class="fas fa-chevron-right" aria-hidden="true"></i>
			</button>
		{:else}
			<span class="orgao-toggle is-empty" aria-hidden="true"></span>
		{/if}

		<span class="orgao-tipo-dot" data-tipo={tipoSlug} title={node.tipo ?? ''} aria-hidden="true"
		></span>

		<span class="orgao-sigla">{node.sigla}</span>
		<span class="orgao-nome">{node.nome}</span>
		{#if node.tipo}
			<span class="orgao-tipo-badge">{node.tipo}</span>
		{/if}
		{#if node.codigo_externo === null}
			<span class="orgao-chip-nao-oficial" title="Unidade sem código SIORG (legado local)">
				não oficial
			</span>
		{/if}
		{#if !node.ativo}
			<span class="orgao-badge-inativo">inativa</span>
		{/if}
	</div>

	{#if hasChildren && expanded}
		<ul class="orgao-children" role="group">
			{#each node.filhos as filho (filho.id)}
				<OrgaoTreeNode
					node={filho}
					depth={depth + 1}
					{expandedIds}
					{selectedId}
					{filterQuery}
					{onToggle}
					{onSelect}
				/>
			{/each}
		</ul>
	{/if}
</li>

<style>
	/* Espelha static/css/admin/orgao_tree.css (v4.5). Cores via vars semânticas
	   (dark-safe). Os dots por tipo mantêm os hex decorativos do original. */
	.orgao-node {
		list-style: none;
	}
	.orgao-node.is-hidden {
		display: none;
	}

	.orgao-children {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
	}

	.orgao-row {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.4rem 0.6rem;
		padding-left: calc(0.6rem + var(--orgao-depth, 0) * 1.4rem);
		border-radius: 8px;
		cursor: pointer;
		transition:
			background 100ms ease,
			box-shadow 120ms ease,
			border-color 120ms ease;
		border: 1px solid transparent;
		margin: 1px 0.5rem;
	}

	.orgao-row:hover {
		background: var(--ds-color-surface-muted);
	}

	.orgao-row.is-selected {
		background: var(--ds-color-wash-brand, rgba(0, 90, 146, 0.08));
		border-color: var(--ds-color-border-brand);
	}

	/* Realce de busca (espelha .orgao-node.is-match do v4.5). */
	.orgao-row.is-match {
		background: var(--ds-color-wash-warning, rgba(202, 138, 4, 0.1));
	}
	:global([data-theme='dark']) .orgao-row.is-match {
		background: rgba(216, 162, 77, 0.16);
	}

	.orgao-node.is-inactive > .orgao-row .orgao-sigla {
		text-decoration: line-through;
		color: var(--ds-color-text-muted);
	}

	.orgao-toggle {
		width: 1.25rem;
		height: 1.25rem;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		background: transparent;
		border: 0;
		cursor: pointer;
		color: var(--ds-color-text-muted);
		font-size: 0.75rem;
		transition: transform 150ms ease;
		flex-shrink: 0;
		border-radius: 6px;
	}
	.orgao-toggle:hover {
		color: var(--ds-color-text-primary);
	}
	.orgao-toggle:focus-visible {
		outline: none;
		box-shadow: 0 0 0 2px var(--ds-color-focus-ring);
	}
	.orgao-toggle.is-empty {
		cursor: default;
	}
	.orgao-toggle.is-open {
		transform: rotate(90deg);
	}

	.orgao-tipo-dot {
		width: 0.55rem;
		height: 0.55rem;
		border-radius: 50%;
		flex-shrink: 0;
		background: var(--ds-color-text-muted);
	}
	.orgao-tipo-dot[data-tipo='estado'] {
		background: #0b4d86;
	}
	.orgao-tipo-dot[data-tipo='secretaria'] {
		background: #1d4ed8;
	}
	.orgao-tipo-dot[data-tipo='subsecretaria'] {
		background: #0891b2;
	}
	.orgao-tipo-dot[data-tipo='autarquia'] {
		background: #7c3aed;
	}
	.orgao-tipo-dot[data-tipo='fundacao'] {
		background: #db2777;
	}
	.orgao-tipo-dot[data-tipo='empresa-publica'] {
		background: #be185d;
	}
	.orgao-tipo-dot[data-tipo='assessoria'] {
		background: #0d9488;
	}
	.orgao-tipo-dot[data-tipo='coordenacao'] {
		background: #b45309;
	}
	.orgao-tipo-dot[data-tipo='nucleo'] {
		background: #b45309;
	}
	.orgao-tipo-dot[data-tipo='departamento'] {
		background: #6b7280;
	}
	/* Taxonomia SIORG (ENTE/ORGAO/ENTIDADE/UA/UC). */
	.orgao-tipo-dot[data-tipo='ente'] {
		background: #0b4d86;
	}
	.orgao-tipo-dot[data-tipo='orgao'] {
		background: #1d4ed8;
	}
	.orgao-tipo-dot[data-tipo='entidade'] {
		background: #7c3aed;
	}
	.orgao-tipo-dot[data-tipo='ua'] {
		background: #0891b2;
	}
	.orgao-tipo-dot[data-tipo='uc'] {
		background: #b45309;
	}

	.orgao-sigla {
		font-family: 'JetBrains Mono', 'SFMono-Regular', ui-monospace, monospace;
		font-weight: 700;
		font-size: 0.8125rem;
		color: var(--ds-color-text-primary);
		letter-spacing: 0.02em;
		flex-shrink: 0;
		min-width: 0;
	}

	.orgao-nome {
		font-size: 0.8125rem;
		color: var(--ds-color-text-secondary);
		flex: 1 1 auto;
		min-width: 0;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.orgao-tipo-badge {
		font-size: 0.65rem;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		font-weight: 600;
		color: var(--ds-color-text-muted);
		background: var(--ds-color-surface-muted);
		padding: 0.15rem 0.5rem;
		border-radius: 999px;
		flex-shrink: 0;
	}

	.orgao-chip-nao-oficial {
		font-size: 0.65rem;
		font-weight: 600;
		letter-spacing: 0.04em;
		color: var(--ds-color-text-warning, #b45309);
		border: 1px dashed currentColor;
		background: transparent;
		padding: 0.1rem 0.45rem;
		border-radius: 999px;
		flex-shrink: 0;
		white-space: nowrap;
	}

	.orgao-badge-inativo {
		font-size: 0.65rem;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		font-weight: 600;
		color: var(--ds-color-text-danger, #b91c1c);
		background: var(--ds-color-wash-danger, rgba(185, 28, 28, 0.1));
		padding: 0.15rem 0.5rem;
		border-radius: 999px;
		flex-shrink: 0;
	}

	@media (max-width: 720px) {
		.orgao-row {
			gap: 0.35rem;
			padding-left: calc(0.4rem + var(--orgao-depth, 0) * 1rem);
		}
		.orgao-tipo-badge {
			display: none;
		}
		.orgao-nome {
			font-size: 0.75rem;
		}
	}

	:global([data-theme='dark']) .orgao-tipo-dot[data-tipo='estado'] {
		background: #a9bac9;
	}
	:global([data-theme='dark']) .orgao-tipo-dot[data-tipo='secretaria'] {
		background: #6ea8fe;
	}
	:global([data-theme='dark']) .orgao-tipo-dot[data-tipo='autarquia'] {
		/* paleta categórica de tipo de órgão — exceção declarada (plano-regua-de-cor §7.12) */
		background: #7c3aed;
	}
	:global([data-theme='dark']) .orgao-tipo-dot[data-tipo='fundacao'] {
		background: #f472b6;
	}
	:global([data-theme='dark']) .orgao-tipo-dot[data-tipo='empresa-publica'] {
		background: #f9a8d4;
	}
	:global([data-theme='dark']) .orgao-tipo-dot[data-tipo='coordenacao'],
	:global([data-theme='dark']) .orgao-tipo-dot[data-tipo='nucleo'] {
		background: #fbbf24;
	}
	:global([data-theme='dark']) .orgao-tipo-dot[data-tipo='departamento'] {
		background: #9ca3af;
	}
</style>
