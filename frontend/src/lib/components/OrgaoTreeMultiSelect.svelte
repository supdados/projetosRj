<script lang="ts">
	/**
	 * Multi-select de órgãos em ÁRVORE com HERANÇA descendente, embutido inline
	 * no formulário (não é popover). Selecionar um nó cobre toda a subárvore:
	 * descendentes aparecem marcados como "via X" — espelho visual de
	 * `get_user_orgao_subtree_ids` do backend.
	 *
	 * Um descendente coberto CONTINUA selecionável (S2): é assim que se dá um
	 * papel diferente dentro da subárvore. Por isso não há mais minimização da
	 * seleção — cada vínculo tem o seu papel no repeater que envolve este campo.
	 * Mesma linguagem visual do OrgaoTreeSelect (indentação, chevrons, busca).
	 */
	import type { AdminOrgaoOption } from '$lib/types/adminUsers';
	import {
		buildOrgaoTree,
		computeDefaultExpanded,
		buildOrgaoTreeRows,
		computeCoveringAncestors,
		type OrgaoTreeNode
	} from '$lib/utils/orgaoTree';

	interface Props {
		options: AdminOrgaoOption[];
		value: number[];
		onChange: (next: number[]) => void;
		disabled?: boolean;
		id?: string;
		ariaLabel?: string;
	}

	let { options, value, onChange, disabled = false, id, ariaLabel }: Props = $props();

	interface TreeOption {
		value: number;
		pai_id: number | null;
		sigla: string;
		nome: string;
	}

	let term = $state('');
	// Override manual de expansão por nó — prevalece sobre o default da spec.
	let overrides = $state<Map<number, boolean>>(new Map());

	const treeOptions = $derived<TreeOption[]>(
		options.map((o) => ({ value: o.id, pai_id: o.pai_id, sigla: o.sigla, nome: o.nome }))
	);
	const tree = $derived.by<OrgaoTreeNode<TreeOption>[]>(() => buildOrgaoTree(treeOptions));
	const defaultExpanded = $derived.by<Set<number>>(() => computeDefaultExpanded(tree));
	const isExpanded = (v: number): boolean =>
		overrides.has(v) ? overrides.get(v)! : defaultExpanded.has(v);

	function toggleExpand(v: number): void {
		const next = new Map(overrides);
		next.set(v, !isExpanded(v));
		overrides = next;
	}

	const rows = $derived.by(() => buildOrgaoTreeRows(tree, isExpanded, term));

	const selectedSet = $derived(new Set(value));
	const coveringById = $derived.by(() => computeCoveringAncestors(tree, selectedSet));
	const siglaById = $derived(new Map(options.map((o) => [o.id, o.sigla])));

	/** Unidades efetivamente acessíveis (selecionadas + herdadas). */
	const coveredTotal = $derived(
		[...coveringById.entries()].filter(([id, by]) => by != null || selectedSet.has(id)).length
	);

	function toggleNode(v: number): void {
		if (disabled) return;
		const next = selectedSet.has(v) ? value.filter((idSel) => idSel !== v) : [...value, v];
		onChange(next);
	}
</script>

<div class="overflow-hidden rounded-lg border border-border-subtle">
	<!-- Busca -->
	<div class="relative border-b border-border-subtle bg-surface-muted">
		<i
			class="fas fa-search pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-sm text-text-muted"
			aria-hidden="true"
		></i>
		<input
			{id}
			type="search"
			bind:value={term}
			{disabled}
			placeholder="Buscar órgão por sigla ou nome…"
			aria-label="Buscar órgão por sigla ou nome"
			autocomplete="off"
			class="h-10 w-full border-none bg-transparent pl-9 pr-3 text-sm text-text-primary placeholder:text-text-muted focus:outline-none"
		/>
	</div>

	<!-- Árvore -->
	<ul
		role="tree"
		aria-multiselectable="true"
		aria-label={ariaLabel ?? 'Órgãos responsáveis'}
		class="thin-scroll max-h-80 overflow-y-auto p-1.5"
	>
		{#if rows.length === 0}
			<li class="px-3 py-4 text-center text-sm text-text-muted">
				Nenhum órgão encontrado{term.trim() ? ` para "${term.trim()}"` : ''}.
			</li>
		{:else}
			{#each rows as row (row.value)}
				{@const coveredBy = coveringById.get(row.value) ?? null}
				{@const isSelected = selectedSet.has(row.value)}
				{@const isCovered = coveredBy != null && !isSelected}
				<li
					role="treeitem"
					aria-selected={isSelected}
					aria-checked={isSelected || isCovered}
					aria-disabled={disabled || undefined}
					aria-expanded={row.hasChildren ? row.expanded : undefined}
					tabindex="-1"
					onclick={() => toggleNode(row.value)}
					onkeydown={(e) => {
						if (e.key === 'Enter' || e.key === ' ') {
							e.preventDefault();
							toggleNode(row.value);
						}
					}}
					title={isCovered && coveredBy != null
						? `Incluído por herança de ${siglaById.get(coveredBy) ?? ''} — selecione para dar um papel próprio`
						: row.option.nome}
					class="flex min-h-[30px] cursor-pointer items-center rounded-md pr-2 transition-colors duration-fast hover:bg-surface-muted {isCovered
						? 'opacity-70'
						: ''} {isSelected ? 'bg-wash-brand' : ''}"
				>
					{#if !row.isSearch}
						<div class="shrink-0" style:width="{row.depth * 14}px"></div>
					{/if}
					<div class="flex h-[22px] w-[22px] shrink-0 items-center justify-center">
						{#if row.hasChildren && !row.isSearch}
							<button
								type="button"
								tabindex="-1"
								aria-label={row.expanded ? 'Recolher' : 'Expandir'}
								onclick={(e) => {
									e.stopPropagation();
									toggleExpand(row.value);
								}}
								class="flex h-[22px] w-[22px] items-center justify-center rounded text-text-muted transition-colors duration-fast hover:bg-border-subtle"
							>
								<svg
									width="10"
									height="10"
									viewBox="0 0 10 10"
									class="transition-transform duration-fast"
									style:transform={row.expanded ? 'rotate(90deg)' : 'none'}
									aria-hidden="true"
								>
									<path
										d="M3 1.5 L7 5 L3 8.5"
										fill="none"
										stroke="currentColor"
										stroke-width="1.6"
										stroke-linecap="round"
										stroke-linejoin="round"
									/>
								</svg>
							</button>
						{:else}
							<span class="h-[5px] w-[5px] rounded-full bg-brand" aria-hidden="true"></span>
						{/if}
					</div>
					<!-- Checkbox visual: marcado (direto), marcado-herdado (cinza) ou vazio. -->
					<span
						class="mr-2 flex h-4 w-4 shrink-0 items-center justify-center rounded border {isSelected
							? 'border-brand bg-brand text-on-brand'
							: isCovered
								? 'border-border-strong bg-surface-muted text-text-muted'
								: 'border-border-strong bg-surface'}"
						aria-hidden="true"
					>
						{#if isSelected || isCovered}
							<svg width="10" height="10" viewBox="0 0 12 12">
								<path
									d="M2 6.5 L4.8 9.2 L10 3"
									fill="none"
									stroke="currentColor"
									stroke-width="2"
									stroke-linecap="round"
									stroke-linejoin="round"
								/>
							</svg>
						{/if}
					</span>
					<span class="min-w-0 flex-1 truncate">
						{#if row.path}<span class="text-xs text-text-muted">{row.path} › </span
							>{/if}<span
							class="text-sm font-medium {isCovered
								? 'text-text-muted'
								: 'text-text-primary'}">{row.option.sigla}</span
						>{#if row.option.nome && row.option.nome !== row.option.sigla}
							<span class="text-xs {isCovered ? 'text-text-muted' : 'text-text-secondary'}">
								— {row.option.nome}</span
							>{/if}
					</span>
					{#if coveredBy != null}
						<span
							class="ml-2 shrink-0 rounded bg-surface-muted px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-text-muted"
						>
							via {siglaById.get(coveredBy) ?? ''}
						</span>
					{/if}
				</li>
			{/each}
		{/if}
	</ul>
</div>

<span class="sr-only" aria-live="polite">
	{value.length} selecionados, cobrindo {coveredTotal} unidades
</span>
