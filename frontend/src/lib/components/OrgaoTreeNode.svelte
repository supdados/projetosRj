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
	<div
		class="flex items-center gap-2 rounded-md px-2 py-1.5 transition-colors duration-fast hover:bg-surface-muted"
		class:ring-2={dragOver}
		class:ring-primary-500={dragOver}
		style={`padding-left:calc(0.5rem + ${depth} * 1.25rem)`}
	>
		{#if canDrag}
			<span
				class="flex h-6 w-4 shrink-0 cursor-grab items-center justify-center text-text-muted"
				title="Arraste para reordenar"
				aria-hidden="true"
			>
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
				class="flex h-6 w-6 shrink-0 items-center justify-center rounded-sm text-text-muted transition-transform duration-fast hover:text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
			>
				<svg
					viewBox="0 0 20 20"
					fill="currentColor"
					class="h-3.5 w-3.5 transition-transform duration-fast"
					style={expanded ? 'transform:rotate(90deg)' : ''}
					aria-hidden="true"
				>
					<path d="M7 5l6 5-6 5V5z" />
				</svg>
			</button>
		{:else}
			<span class="h-6 w-6 shrink-0" aria-hidden="true"></span>
		{/if}

		<span class="flex min-w-0 flex-1 items-center gap-2">
			<span class="truncate text-sm font-semibold text-text-primary">{node.sigla}</span>
			<span class="truncate text-sm text-text-secondary">{node.nome}</span>
			{#if node.tipo}
				<Badge tone="info">{node.tipo}</Badge>
			{/if}
			{#if !node.ativo}
				<Badge tone="neutral">Inativo</Badge>
			{/if}
		</span>

		<div class="flex shrink-0 items-center gap-1">
			<a
				href={`${base}/admin/orgaos/novo?pai_id=${node.id}`}
				title="Adicionar subunidade"
				aria-label={`Adicionar subunidade em ${node.sigla}`}
				class="flex h-7 w-7 items-center justify-center rounded-sm text-text-muted hover:bg-primary-100 hover:text-primary-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
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
				class="flex h-7 w-7 items-center justify-center rounded-sm text-text-muted hover:bg-surface-muted hover:text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:cursor-not-allowed disabled:opacity-40"
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
				class="flex h-7 w-7 items-center justify-center rounded-sm text-text-muted hover:bg-surface-muted hover:text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:cursor-not-allowed disabled:opacity-40"
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
					class="flex h-7 w-7 items-center justify-center rounded-sm text-text-muted hover:bg-surface-muted hover:text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:cursor-not-allowed disabled:opacity-40"
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
				class="flex h-7 w-7 items-center justify-center rounded-sm text-text-muted hover:bg-surface-muted hover:text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
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
				class="flex h-7 w-7 items-center justify-center rounded-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:cursor-not-allowed disabled:opacity-40 {node.ativo
					? 'text-warning hover:bg-surface-muted'
					: 'text-success hover:bg-surface-muted'}"
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
					class="flex h-7 w-7 items-center justify-center rounded-sm text-danger hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:cursor-not-allowed disabled:opacity-40"
				>
					<svg viewBox="0 0 20 20" fill="currentColor" class="h-4 w-4" aria-hidden="true">
						<path d="M7 2a1 1 0 00-1 1v1H3v2h14V4h-3V3a1 1 0 00-1-1H7zM5 7v9a2 2 0 002 2h6a2 2 0 002-2V7H5z" />
					</svg>
				</button>
			{:else if !isRoot}
				<span
					title="Mova as subunidades antes de excluir"
					aria-label="Exclusão indisponível: mova as subunidades antes"
					class="flex h-7 w-7 cursor-not-allowed items-center justify-center rounded-sm text-text-muted opacity-40"
				>
					<svg viewBox="0 0 20 20" fill="currentColor" class="h-4 w-4" aria-hidden="true">
						<path d="M7 2a1 1 0 00-1 1v1H3v2h14V4h-3V3a1 1 0 00-1-1H7zM5 7v9a2 2 0 002 2h6a2 2 0 002-2V7H5z" />
					</svg>
				</span>
			{/if}
		</div>
	</div>

	{#if moveOpen && !isRoot}
		<div
			class="mt-1 flex items-center gap-2"
			style={`padding-left:calc(2.5rem + ${depth} * 1.25rem)`}
		>
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
		<ul class="flex flex-col">
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
