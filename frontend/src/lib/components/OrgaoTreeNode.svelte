<script lang="ts">
	/**
	 * Nó RECURSIVO da árvore de órgãos (Admin > Órgãos). Espelha o macro Jinja
	 * `render_orgao_node` de `templates/admin/_orgao_node.html`: linha com chevron
	 * de expandir/recolher, dot + badge de tipo, sigla/nome e barra de ações
	 * (adicionar subunidade, mover ↑/↓, mover de pai, editar, ativar/desativar,
	 * excluir). Os filhos são renderizados por auto-referência ao próprio nome do
	 * componente (`<OrgaoTreeNode>`) — idiom Svelte 5 que substitui `svelte:self`.
	 *
	 * O componente é CONTROLADO: não muta o estado nem chama a API diretamente —
	 * apenas emite callbacks (`onReorder`/`onReorderTo`/`onToggleAtivo`/`onMove`/
	 * `onDelete`) para a página, que orquestra as chamadas a
	 * `$lib/api/adminOrgaos` e o recarregamento da árvore. Links de criar/editar
	 * são base-aware (`$app/paths`). Acessível: chevron com `aria-expanded`,
	 * ações com `title`/`aria-label`, indentação por nível via `--orgao-depth`.
	 *
	 * Reordenação por DRAG-AND-DROP (débito #8): cada nó é `draggable` e pode ser
	 * solto sobre um irmão do MESMO pai (a árvore reordena só entre irmãos; mudar
	 * de pai continua via "mover para outro pai"). Ao soltar, emite
	 * `onReorderTo(orgaoId, fromIndex, toIndex)`; a página traduz o salto em
	 * chamadas single-step ao endpoint POST `/reorder` existente. As setas ↑/↓
	 * permanecem como alternativa acessível por teclado (mesmo callback `onReorder`).
	 * DnD nativo HTML5 (sem dependências), espelhando StageList.svelte.
	 */
	import { base } from '$app/paths';
	import Badge from '$lib/components/Badge.svelte';
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
		onReorder: (orgaoId: number, direction: ReorderDirection) => void;
		/**
		 * Reordena por drag-and-drop: solta o nó `draggedId` sobre `targetId`. A
		 * página localiza ambos na árvore, valida que são irmãos (mesmo pai) e
		 * converte o salto em chamadas single-step ao endpoint `/reorder`.
		 */
		onReorderTo: (draggedId: number, targetId: number) => void;
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
		onReorder,
		onReorderTo,
		onToggleAtivo,
		onMove,
		onDelete
	}: Props = $props();

	let expanded = $state(true);
	/** Abre o seletor inline de "mover para outro pai". */
	let moveOpen = $state(false);
	/** Índice do irmão sobre o qual se arrasta (para realce de alvo de drop). */
	let dragOver = $state(false);

	const canDrag = $derived(!busy && siblingCount > 1);

	function handleDragStart(event: DragEvent): void {
		// O nó arrastado é o alvo mais interno; impede que ancestrais sobrescrevam
		// o payload (ou cancelem o arraste) ao receberem o evento por bubbling.
		event.stopPropagation();
		if (!canDrag || !event.dataTransfer) {
			event.preventDefault();
			return;
		}
		event.dataTransfer.effectAllowed = 'move';
		// Origem identificada por id do órgão; a página valida o mesmo pai.
		event.dataTransfer.setData('application/x-orgao-id', String(node.id));
		// Firefox exige um payload text/plain para iniciar o arraste.
		event.dataTransfer.setData('text/plain', node.sigla ?? String(node.id));
	}

	function handleDragOver(event: DragEvent): void {
		if (!canDrag || !event.dataTransfer) return;
		const types = event.dataTransfer.types;
		if (!types.includes('application/x-orgao-id')) return;
		event.preventDefault();
		// Evita que o nó-pai também realce/receba o drop ao passar sobre um filho.
		event.stopPropagation();
		event.dataTransfer.dropEffect = 'move';
		dragOver = true;
	}

	function handleDragLeave(): void {
		dragOver = false;
	}

	function handleDrop(event: DragEvent): void {
		dragOver = false;
		if (!canDrag || !event.dataTransfer) return;
		const draggedId = Number(event.dataTransfer.getData('application/x-orgao-id'));
		if (!Number.isFinite(draggedId) || draggedId === node.id) return;
		event.preventDefault();
		event.stopPropagation();
		// A página valida que origem e destino são irmãos antes de reordenar.
		onReorderTo(draggedId, node.id);
	}

	const hasChildren = $derived(node.filhos.length > 0);
	const isRoot = $derived(node.pai_id === null);
	const isFirst = $derived(index === 0);
	const isLast = $derived(index === siblingCount - 1);
	/** Raiz não pode ser excluída; órgão com filhos também não (backend 409). */
	const canDelete = $derived(!isRoot && !hasChildren);

	/**
	 * Slug do tipo para a cor do dot (espelha `_orgao_node.html`:
	 * `tipo_nome|lower|replace(...)`). Apresentação apenas — as cores por tipo
	 * vivem no bloco style com escopo, reproduzindo `orgao_tree.css`.
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

	function toggleExpanded(): void {
		expanded = !expanded;
	}

	function confirmDelete(): void {
		onDelete(node);
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
	style={`--orgao-depth:${depth}`}
	data-id={node.id}
	draggable={canDrag}
	ondragstart={handleDragStart}
	ondragover={handleDragOver}
	ondragleave={handleDragLeave}
	ondrop={handleDrop}
	ondragend={handleDragLeave}
>
	<div class="orgao-row" class:is-drop-target={dragOver}>
		{#if canDrag}
			<span class="orgao-grip" title="Arraste para reordenar" aria-hidden="true">
				<svg viewBox="0 0 20 20" fill="currentColor" class="h-4 w-4">
					<path d="M7 4a1 1 0 11-2 0 1 1 0 012 0zm0 6a1 1 0 11-2 0 1 1 0 012 0zm-1 7a1 1 0 100-2 1 1 0 000 2zm9-13a1 1 0 11-2 0 1 1 0 012 0zm-1 7a1 1 0 100-2 1 1 0 000 2zm1 5a1 1 0 11-2 0 1 1 0 012 0z" />
				</svg>
			</span>
		{/if}
		{#if hasChildren}
			<button
				type="button"
				onclick={toggleExpanded}
				aria-expanded={expanded}
				aria-label={expanded ? 'Recolher subunidades' : 'Expandir subunidades'}
				class="orgao-toggle"
				class:is-open={expanded}
			>
				<svg viewBox="0 0 20 20" fill="currentColor" class="h-3 w-3" aria-hidden="true">
					<path d="M7 5l6 5-6 5V5z" />
				</svg>
			</button>
		{:else}
			<span class="orgao-toggle is-empty" aria-hidden="true"></span>
		{/if}

		<span
			class="orgao-tipo-dot"
			data-tipo={tipoSlug}
			title={node.tipo ?? ''}
			aria-hidden="true"
		></span>

		<span class="orgao-sigla">{node.sigla}</span>
		<span class="orgao-nome">{node.nome}</span>
		{#if node.tipo}
			<span class="orgao-tipo-badge">{node.tipo}</span>
		{/if}
		{#if !node.ativo}
			<Badge tone="neutral">Inativo</Badge>
		{/if}

		<div class="orgao-actions">
			<a
				href={`${base}/admin/orgaos/novo?pai_id=${node.id}`}
				title="Adicionar subunidade"
				aria-label={`Adicionar subunidade em ${node.sigla}`}
				class="orgao-action-btn is-add"
			>
				<svg viewBox="0 0 20 20" fill="currentColor" class="h-4 w-4" aria-hidden="true">
					<path d="M11 3a1 1 0 10-2 0v6H3a1 1 0 100 2h6v6a1 1 0 102 0v-6h6a1 1 0 100-2h-6V3z" />
				</svg>
			</a>

			<button
				type="button"
				onclick={() => onReorder(node.id, 'up')}
				disabled={busy || isFirst}
				title="Mover para cima"
				aria-label={`Mover ${node.sigla} para cima`}
				class="orgao-action-btn"
			>
				<svg viewBox="0 0 20 20" fill="currentColor" class="h-4 w-4" aria-hidden="true">
					<path d="M10 5l5 6H5l5-6z" />
				</svg>
			</button>
			<button
				type="button"
				onclick={() => onReorder(node.id, 'down')}
				disabled={busy || isLast}
				title="Mover para baixo"
				aria-label={`Mover ${node.sigla} para baixo`}
				class="orgao-action-btn"
			>
				<svg viewBox="0 0 20 20" fill="currentColor" class="h-4 w-4" aria-hidden="true">
					<path d="M10 15l-5-6h10l-5 6z" />
				</svg>
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
					<svg viewBox="0 0 20 20" fill="currentColor" class="h-4 w-4" aria-hidden="true">
						<path
							d="M10 2a1 1 0 01.7.3l3 3a1 1 0 01-1.4 1.4L11 5.4V10a1 1 0 01-1 1H5.4l1.3 1.3a1 1 0 11-1.4 1.4l-3-3a1 1 0 010-1.4l3-3a1 1 0 111.4 1.4L5.4 9H9V5.4L7.7 6.7a1 1 0 11-1.4-1.4l3-3A1 1 0 0110 2z"
						/>
					</svg>
				</button>
			{/if}

			<a
				href={`${base}/admin/orgaos/${node.id}`}
				title="Editar"
				aria-label={`Editar ${node.sigla}`}
				class="orgao-action-btn is-edit"
			>
				<svg viewBox="0 0 20 20" fill="currentColor" class="h-4 w-4" aria-hidden="true">
					<path d="M13.5 3.5l3 3L7 16H4v-3l9.5-9.5z" />
				</svg>
			</a>

			<button
				type="button"
				onclick={() => onToggleAtivo(node.id)}
				disabled={busy}
				title={node.ativo ? 'Desativar' : 'Ativar'}
				aria-label={`${node.ativo ? 'Desativar' : 'Ativar'} ${node.sigla}`}
				class="orgao-action-btn {node.ativo ? 'is-warning' : 'is-success'}"
			>
				{#if node.ativo}
					<svg viewBox="0 0 20 20" fill="currentColor" class="h-4 w-4" aria-hidden="true">
						<path d="M10 4C5 4 1.7 8 1 10c.7 2 4 6 9 6s8.3-4 9-6c-.7-2-4-6-9-6zm0 9a3 3 0 110-6 3 3 0 010 6z" />
					</svg>
				{:else}
					<svg viewBox="0 0 20 20" fill="currentColor" class="h-4 w-4" aria-hidden="true">
						<path d="M3 3l14 14-1.4 1.4-2.3-2.3A9.6 9.6 0 0110 16c-5 0-8.3-4-9-6a12 12 0 013.3-4.1L1.6 4.4 3 3zm7 3a4 4 0 014 4c0 .5-.1 1-.3 1.4l1.5 1.5C16.6 11.8 17.6 10.7 18 10c-.7-2-4-6-9-6-.5 0-1 0-1.5.1L9 5.6c.3-.1.7-.1 1-.1z" />
					</svg>
				{/if}
			</button>

			{#if canDelete}
				<button
					type="button"
					onclick={confirmDelete}
					disabled={busy}
					title="Excluir"
					aria-label={`Excluir ${node.sigla}`}
					class="orgao-action-btn is-delete"
				>
					<svg viewBox="0 0 20 20" fill="currentColor" class="h-4 w-4" aria-hidden="true">
						<path d="M7 2a1 1 0 00-1 1v1H3v2h14V4h-3V3a1 1 0 00-1-1H7zM5 7v9a2 2 0 002 2h6a2 2 0 002-2V7H5z" />
					</svg>
				</button>
			{:else if !isRoot}
				<span
					title="Mova as subunidades antes de excluir"
					aria-label="Exclusão indisponível: mova as subunidades antes"
					class="orgao-action-btn is-disabled"
				>
					<svg viewBox="0 0 20 20" fill="currentColor" class="h-4 w-4" aria-hidden="true">
						<path d="M7 2a1 1 0 00-1 1v1H3v2h14V4h-3V3a1 1 0 00-1-1H7zM5 7v9a2 2 0 002 2h6a2 2 0 002-2V7H5z" />
					</svg>
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
		<ul class="orgao-children">
			{#each node.filhos as filho, i (filho.id)}
				<OrgaoTreeNode
					node={filho}
					depth={depth + 1}
					index={i}
					siblingCount={node.filhos.length}
					{paiOptions}
					{busy}
					{onReorder}
					{onReorderTo}
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

	.orgao-row.is-drop-target {
		background: var(--ds-color-success-light-bg);
		border-color: var(--ds-color-success-600);
		border-style: dashed;
	}

	.orgao-node.is-inactive > .orgao-row .orgao-sigla {
		text-decoration: line-through;
		color: var(--color-text-muted);
	}

	.orgao-grip {
		width: 1rem;
		height: 1.5rem;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		color: var(--color-text-muted);
		cursor: grab;
		flex-shrink: 0;
	}
	.orgao-grip:active {
		cursor: grabbing;
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
	.orgao-row:hover .orgao-actions {
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
	.orgao-action-btn.is-add:hover {
		color: var(--ds-color-primary-700);
		background: var(--ds-color-info-light-bg);
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
