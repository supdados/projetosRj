<script module lang="ts">
	/**
	 * Estado de arraste COMPARTILHADO entre todas as instâncias recursivas do nó.
	 * Espelha as variáveis de módulo `dragId`/`dragTipo` do orgao_tree.js (v4.5):
	 * o `dragstart` registra quem está sendo arrastado para que o `dragover` de
	 * QUALQUER nó-alvo possa decidir se é um destino de drop válido (o payload do
	 * DataTransfer não é legível durante o dragover, por segurança do browser).
	 */
	let draggedId: number | null = null;

	export function setDraggedOrgaoId(id: number | null): void {
		draggedId = id;
	}
	export function getDraggedOrgaoId(): number | null {
		return draggedId;
	}
</script>

<script lang="ts">
	/**
	 * Nó RECURSIVO da árvore de órgãos (Admin > Órgãos). Espelha o macro Jinja
	 * `render_orgao_node` de `templates/admin/_orgao_node.html` e o comportamento
	 * de `static/js/admin/orgao_tree.js` (v4.5): linha com chevron de
	 * expandir/recolher, dot + sigla/nome + badge de tipo e barra de ações
	 * (adicionar subunidade, mover ↑/↓, mover de pai, editar, ativar/desativar,
	 * excluir). Os filhos são renderizados por auto-referência (`<OrgaoTreeNode>`).
	 *
	 * Componente CONTROLADO: não muta estado nem chama a API. O estado de
	 * expand/collapse, seleção e busca vive na página (`expandedIds`,
	 * `selectedId`, `filterQuery`) e as mutações são emitidas via callbacks
	 * (`onToggle`/`onSelect`/`onReorder`/`onReparent`/`onToggleAtivo`/`onMove`/
	 * `onDelete`).
	 *
	 * DRAG-AND-DROP = REPARENTING (igual ao v4.5): a linha é `draggable` quando o
	 * nó não é raiz (`pai_id !== null`). Soltar o nó arrastado SOBRE outro nó
	 * torna o alvo o novo pai (POST `/move`). O realce de alvo (`is-drop-target`)
	 * só aparece em destinos válidos: a função `canDropOn(draggedId, targetId)`
	 * (na página) recusa o próprio nó, descendentes e tipos incompatíveis
	 * (espelha `isValidParentTipo`/guarda de descendentes do orgao_tree.js). As
	 * setas ↑/↓ continuam reordenando entre irmãos como alternativa por teclado.
	 * DnD nativo HTML5, sem dependências.
	 */
	import { base } from '$app/paths';
	import OrgaoTreeNode from './OrgaoTreeNode.svelte';
	import type { CandidatoPai, OrgaoNode, ReorderDirection } from '$lib/types/adminOrgaos';

	interface Props {
		node: OrgaoNode;
		depth?: number;
		/** Posição do nó entre os irmãos (para desabilitar ↑/↓ nos extremos). */
		index: number;
		/** Total de irmãos no mesmo nível. */
		siblingCount: number;
		/** Candidatos a pai válidos para "mover" (excluem o nó e descendentes). */
		paiOptions: CandidatoPai[];
		/** True enquanto uma mutação está em voo (desabilita ações). */
		busy: boolean;
		/** Ids de nós expandidos (controlado pela página). */
		expandedIds: Set<number>;
		/** Id do nó selecionado (realce, espelha is-selected do v4.5). */
		selectedId: number | null;
		/** Termo de busca normalizado (lowercase, sem espaços nas bordas). */
		filterQuery: string;
		/** Valida se `draggedId` pode ser solto sobre `targetId` (reparent). */
		canDropOn: (draggedId: number, targetId: number) => boolean;
		onToggle: (orgaoId: number) => void;
		onSelect: (orgaoId: number) => void;
		onReorder: (orgaoId: number, direction: ReorderDirection) => void;
		/** Reparenting por DnD: torna `targetId` o novo pai de `draggedId`. */
		onReparent: (draggedId: number, targetId: number) => void;
		onToggleAtivo: (orgaoId: number) => void;
		onMove: (orgaoId: number, paiId: number | null) => void;
		onDelete: (node: OrgaoNode) => void;
	}

	let {
		node,
		depth = 0,
		index,
		siblingCount,
		paiOptions,
		busy,
		expandedIds,
		selectedId,
		filterQuery,
		canDropOn,
		onToggle,
		onSelect,
		onReorder,
		onReparent,
		onToggleAtivo,
		onMove,
		onDelete
	}: Props = $props();

	/** Abre o seletor inline de "mover para outro pai". */
	let moveOpen = $state(false);
	/** True quando o nó arrastado está sobre esta linha e o drop é válido. */
	let dropTarget = $state(false);

	const hasChildren = $derived(node.filhos.length > 0);
	const isRoot = $derived(node.pai_id === null);
	const isFirst = $derived(index === 0);
	const isLast = $derived(index === siblingCount - 1);
	const expanded = $derived(expandedIds.has(node.id));
	const isSelected = $derived(selectedId === node.id);
	/** Raiz não é arrastável (espelha draggable="false" do v4.5). */
	const canDrag = $derived(!busy && !isRoot);
	/** Raiz não pode ser excluída; órgão com filhos também não (backend 409). */
	const canDelete = $derived(!isRoot && !hasChildren);

	// === Busca: espelha applyFilter do orgao_tree.js ===
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

	/**
	 * Slug do tipo para a cor do dot (espelha `_orgao_node.html`:
	 * `tipo_nome|lower|replace(...)`). As cores por tipo vivem no bloco style.
	 */
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

	function handleDragStart(event: DragEvent): void {
		// O nó arrastado é o alvo mais interno; impede que ancestrais sobrescrevam
		// o payload ao receberem o evento por bubbling.
		event.stopPropagation();
		if (!canDrag || !event.dataTransfer) {
			event.preventDefault();
			return;
		}
		event.dataTransfer.effectAllowed = 'move';
		event.dataTransfer.setData('application/x-orgao-id', String(node.id));
		// Firefox exige um payload text/plain para iniciar o arraste.
		event.dataTransfer.setData('text/plain', node.sigla ?? String(node.id));
		// Registra no estado compartilhado para a validação durante o dragover.
		setDraggedOrgaoId(node.id);
	}

	function handleDragOver(event: DragEvent): void {
		if (!event.dataTransfer) return;
		if (!event.dataTransfer.types.includes('application/x-orgao-id')) return;
		const draggedId = getDraggedOrgaoId();
		// Só realça destinos válidos (espelha a guarda do dragover do v4.5):
		// não o próprio/descendente, e tipo do alvo pode ser pai do arrastado.
		if (draggedId === null || !canDropOn(draggedId, node.id)) return;
		event.preventDefault();
		// Impede que o nó-pai também receba o drop ao passar sobre um filho.
		event.stopPropagation();
		event.dataTransfer.dropEffect = 'move';
		dropTarget = true;
	}

	function handleDragLeave(): void {
		dropTarget = false;
	}

	function handleDrop(event: DragEvent): void {
		dropTarget = false;
		const draggedId = getDraggedOrgaoId();
		if (draggedId === null) return;
		event.preventDefault();
		event.stopPropagation();
		// A página valida tipo/descendência/pai-atual antes de mover.
		onReparent(draggedId, node.id);
	}

	function handleDragEnd(): void {
		dropTarget = false;
		setDraggedOrgaoId(null);
	}

	function handleRowClick(event: MouseEvent): void {
		// Cliques em ações/chevron não selecionam (espelha guarda do orgao_tree.js).
		const target = event.target as HTMLElement;
		if (target.closest('.orgao-actions') || target.closest('.orgao-toggle')) return;
		onSelect(node.id);
	}

	function handleRowKeydown(event: KeyboardEvent): void {
		// Seleção por teclado quando o foco está na própria linha (não nos botões).
		if (event.target !== event.currentTarget) return;
		if (event.key === 'Enter' || event.key === ' ') {
			event.preventDefault();
			onSelect(node.id);
		}
	}

	function onMoveSelect(event: Event): void {
		const raw = (event.currentTarget as HTMLSelectElement).value;
		moveOpen = false;
		if (raw === '') return;
		const paiId = raw === '__root__' ? null : Number(raw);
		if (paiId === node.pai_id) return;
		onMove(node.id, paiId);
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
		class:is-drop-target={dropTarget}
		class:is-selected={isSelected}
		class:is-match={selfMatches}
		draggable={canDrag}
		role="treeitem"
		aria-selected={isSelected}
		aria-expanded={hasChildren ? expanded : undefined}
		tabindex="-1"
		ondragstart={handleDragStart}
		ondragover={handleDragOver}
		ondragleave={handleDragLeave}
		ondrop={handleDrop}
		ondragend={handleDragEnd}
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

		<div class="orgao-actions">
			<a
				href={`${base}/admin/orgaos/novo?pai_id=${node.id}`}
				title="Adicionar subunidade"
				aria-label={`Adicionar subunidade em ${node.sigla}`}
				class="orgao-action-btn"
			>
				<i class="fas fa-plus" aria-hidden="true"></i>
			</a>

			<button
				type="button"
				onclick={() => onReorder(node.id, 'up')}
				disabled={busy || isFirst}
				title="Mover para cima"
				aria-label={`Mover ${node.sigla} para cima`}
				class="orgao-action-btn"
			>
				<i class="fas fa-arrow-up" aria-hidden="true"></i>
			</button>
			<button
				type="button"
				onclick={() => onReorder(node.id, 'down')}
				disabled={busy || isLast}
				title="Mover para baixo"
				aria-label={`Mover ${node.sigla} para baixo`}
				class="orgao-action-btn"
			>
				<i class="fas fa-arrow-down" aria-hidden="true"></i>
			</button>

			{#if !isRoot}
				<button
					type="button"
					onclick={() => (moveOpen = !moveOpen)}
					disabled={busy}
					aria-expanded={moveOpen}
					title="Mover para outro pai"
					aria-label={`Mover ${node.sigla} para outro pai`}
					class="orgao-action-btn"
				>
					<i class="fas fa-arrows-alt" aria-hidden="true"></i>
				</button>
			{/if}

			<a
				href={`${base}/admin/orgaos/${node.id}`}
				title="Editar"
				aria-label={`Editar ${node.sigla}`}
				class="orgao-action-btn is-edit"
			>
				<i class="fas fa-pen" aria-hidden="true"></i>
			</a>

			<button
				type="button"
				onclick={() => onToggleAtivo(node.id)}
				disabled={busy}
				title={node.ativo ? 'Desativar' : 'Ativar'}
				aria-label={`${node.ativo ? 'Desativar' : 'Ativar'} ${node.sigla}`}
				class="orgao-action-btn {node.ativo ? 'is-warning' : 'is-success'}"
			>
				<i class="fas {node.ativo ? 'fa-eye' : 'fa-eye-slash'}" aria-hidden="true"></i>
			</button>

			{#if canDelete}
				<button
					type="button"
					onclick={() => onDelete(node)}
					disabled={busy}
					title="Excluir"
					aria-label={`Excluir ${node.sigla}`}
					class="orgao-action-btn is-delete"
				>
					<i class="fas fa-trash" aria-hidden="true"></i>
				</button>
			{:else if !isRoot}
				<span
					title="Mova as subunidades antes de excluir"
					aria-label="Exclusão indisponível: mova as subunidades antes"
					class="orgao-action-btn is-disabled"
				>
					<i class="fas fa-trash" aria-hidden="true"></i>
				</span>
			{/if}
		</div>
	</div>

	{#if moveOpen && !isRoot}
		<div class="orgao-move-row" style={`--orgao-depth:${depth}`}>
			<label class="text-xs text-text-muted" for={`move-${node.id}`}>Mover para:</label>
			<select
				id={`move-${node.id}`}
				onchange={onMoveSelect}
				disabled={busy}
				class="rounded-md border border-border-subtle bg-surface px-2 py-1 text-sm text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
			>
				<option value="">Selecione…</option>
				{#each paiOptions as pai (pai.id)}
					{#if pai.id !== node.pai_id}
						<option value={pai.id}>{pai.sigla} — {pai.nome}</option>
					{/if}
				{/each}
			</select>
		</div>
	{/if}

	{#if hasChildren && expanded}
		<ul class="orgao-children" role="group">
			{#each node.filhos as filho, i (filho.id)}
				<OrgaoTreeNode
					node={filho}
					depth={depth + 1}
					index={i}
					siblingCount={node.filhos.length}
					{paiOptions}
					{busy}
					{expandedIds}
					{selectedId}
					{filterQuery}
					{canDropOn}
					{onToggle}
					{onSelect}
					{onReorder}
					{onReparent}
					{onToggleAtivo}
					{onMove}
					{onDelete}
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
		background: var(--color-surface-muted);
	}

	.orgao-row.is-selected {
		background: var(--ds-color-primary-light-bg, rgba(0, 90, 146, 0.08));
		border-color: var(--ds-color-primary-600);
	}

	/* Realce de busca (espelha .orgao-node.is-match do v4.5). */
	.orgao-row.is-match {
		background: var(--ds-color-warning-light-bg, rgba(254, 240, 138, 0.45));
	}

	.orgao-row.is-drop-target {
		background: var(--ds-color-success-light-bg);
		border-color: var(--ds-color-success-600);
		border-style: dashed;
	}

	.orgao-node.is-inactive > .orgao-row .orgao-sigla {
		text-decoration: line-through;
		color: var(--color-text-muted);
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
		color: var(--color-text-muted);
		font-size: 0.75rem;
		transition: transform 150ms ease;
		flex-shrink: 0;
		border-radius: 6px;
	}
	.orgao-toggle:hover {
		color: var(--color-text-primary);
	}
	.orgao-toggle:focus-visible {
		outline: none;
		box-shadow: 0 0 0 2px var(--ds-color-primary-600);
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
		background: var(--color-text-muted);
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

	.orgao-sigla {
		font-family: 'JetBrains Mono', 'SFMono-Regular', ui-monospace, monospace;
		font-weight: 700;
		font-size: 0.8125rem;
		color: var(--color-text-primary);
		letter-spacing: 0.02em;
		flex-shrink: 0;
		min-width: 0;
	}

	.orgao-nome {
		font-size: 0.8125rem;
		color: var(--color-text-secondary);
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
		color: var(--color-text-muted);
		background: var(--color-surface-muted);
		padding: 0.15rem 0.5rem;
		border-radius: 999px;
		flex-shrink: 0;
	}

	.orgao-actions {
		display: flex;
		align-items: center;
		gap: 0.2rem;
		margin-left: auto;
		opacity: 0.55;
		transition: opacity 120ms ease;
		flex-shrink: 0;
	}
	.orgao-row:hover .orgao-actions,
	.orgao-row.is-selected .orgao-actions {
		opacity: 1;
	}

	.orgao-action-btn {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 1.75rem;
		height: 1.75rem;
		border-radius: 6px;
		border: 1px solid transparent;
		background: transparent;
		color: var(--color-text-muted);
		font-size: 0.75rem;
		cursor: pointer;
		text-decoration: none;
		transition:
			background 120ms ease,
			color 120ms ease,
			border-color 120ms ease;
	}
	.orgao-action-btn:hover {
		background: var(--color-surface-muted);
		color: var(--color-text-primary);
	}
	.orgao-action-btn:focus-visible {
		outline: none;
		box-shadow: 0 0 0 2px var(--ds-color-primary-600);
	}
	.orgao-action-btn:disabled {
		cursor: not-allowed;
		opacity: 0.4;
	}
	.orgao-action-btn.is-edit:hover {
		color: var(--ds-color-info-600);
		background: var(--ds-color-info-light-bg);
	}
	.orgao-action-btn.is-delete:hover {
		color: var(--ds-color-danger-600);
		background: var(--ds-color-danger-light-bg);
	}
	.orgao-action-btn.is-warning:hover {
		color: var(--ds-color-warning-600);
		background: var(--ds-color-info-light-bg);
	}
	.orgao-action-btn.is-success:hover {
		color: var(--ds-color-success-600);
		background: var(--ds-color-success-light-bg);
	}
	.orgao-action-btn.is-disabled {
		opacity: 0.35;
		cursor: not-allowed;
	}

	.orgao-move-row {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		margin-top: 0.25rem;
		padding-left: calc(2.5rem + var(--orgao-depth, 0) * 1.4rem);
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
		.orgao-actions {
			gap: 0;
		}
	}
</style>
