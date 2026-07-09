<script lang="ts">
	/**
	 * Tela "Admin > Órgãos" (árvore). URL `/spa/admin/orgaos`. Consome
	 * `GET /api/admin/orgaos` via `$lib/api/adminOrgaos` e renderiza a hierarquia
	 * com o componente recursivo `OrgaoTreeNode`. As operações (reordenar, mover,
	 * ativar/desativar, excluir) chamam os endpoints `/api/admin/orgaos/*` e
	 * recarregam a árvore; criar/editar navegam para os forms
	 * (`/admin/orgaos/novo`, `/admin/orgaos/[id]`).
	 *
	 * Só admins acessam: o backend devolve 403 (`forbidden`) para não-admin e 401
	 * já redireciona para `/login` em `client.ts`. Estados loading/erro/vazio são
	 * anunciados via aria-live/role=alert; o delete exige confirmação. Links
	 * internos são base-aware (`$app/paths`).
	 *
	 * Referência visual: templates/admin/orgao_tree.html e _orgao_node.html.
	 */
	import { onMount } from 'svelte';
	import { base } from '$app/paths';
	import {
		fetchOrgaoTree,
		reorderOrgao,
		toggleOrgaoAtivo,
		moveOrgao,
		deleteOrgao
	} from '$lib/api/adminOrgaos';
	import { ApiClientError } from '$lib/api/client';
	import type { OrgaoNode, OrgaoTreeData, ReorderDirection } from '$lib/types/adminOrgaos';
	import OrgaoTreeNode from '$lib/components/OrgaoTreeNode.svelte';
	import PageHeader from '$lib/components/PageHeader.svelte';
	import Button from '$lib/components/Button.svelte';
	import CountBadge from '$lib/components/CountBadge.svelte';

	type LoadState = 'loading' | 'ready' | 'error';

	let loadState = $state<LoadState>('loading');
	let data = $state<OrgaoTreeData | null>(null);
	let errorMessage = $state<string>('');
	/** Distingue 403 (sem permissão) do erro genérico para a UI. */
	let errorKind = $state<'forbidden' | 'generic'>('generic');

	/** True enquanto uma mutação está em voo (desabilita ações da árvore). */
	let mutating = $state(false);
	/** Mensagem de erro de uma mutação (ex.: 409 ao mover/excluir). */
	let actionError = $state<string>('');

	/**
	 * Conjunto de ids de nós expandidos. Espelha o v4.5 (orgao_tree.js): a árvore
	 * abre os níveis 0 e 1 ao carregar; "expandir/recolher tudo" e a busca
	 * manipulam este set. Mantê-lo na página (e não em cada nó) preserva o estado
	 * de expand/collapse entre recargas após uma mutação.
	 */
	let expandedIds = $state<Set<number>>(new Set());
	/** Termo de busca por sigla/nome (debounced, espelha #orgaoTreeSearch do v4.5). */
	let searchQuery = $state<string>('');
	/** Termo efetivamente aplicado ao filtro (após debounce de 120ms). */
	let filterQuery = $state<string>('');
	/** Id do nó selecionado (clique na linha → realce, espelha is-selected do v4.5). */
	let selectedId = $state<number | null>(null);

	let searchTimer: ReturnType<typeof setTimeout> | null = null;

	let inFlight: AbortController | null = null;

	async function load(): Promise<void> {
		loadState = data ? loadState : 'loading';
		errorMessage = '';
		errorKind = 'generic';
		inFlight?.abort();
		const controller = new AbortController();
		inFlight = controller;
		try {
			const next = await fetchOrgaoTree(controller.signal);
			if (controller.signal.aborted) return;
			data = next;
			// Espelha orgao_tree.js: ao montar, abre níveis 0 e 1; nas recargas
			// pós-mutação, preserva o que o usuário já tinha expandido e garante
			// que os ancestrais de qualquer nó recém-criado fiquem visíveis.
			if (expandedIds.size === 0) {
				expandedIds = collectInitialExpanded(next.arvore);
			} else {
				expandedIds = pruneExpanded(next.arvore, expandedIds);
			}
			loadState = 'ready';
		} catch (err) {
			if (controller.signal.aborted) return;
			if (err instanceof ApiClientError && err.code === 'unauthenticated') return;
			if (err instanceof ApiClientError && err.code === 'forbidden') {
				errorKind = 'forbidden';
				errorMessage = 'Você não tem permissão para gerenciar órgãos.';
			} else {
				errorMessage =
					err instanceof Error ? err.message : 'Falha ao carregar a árvore de órgãos.';
			}
			loadState = 'error';
		}
	}

	/**
	 * Executa uma mutação e recarrega a árvore. Concentra o tratamento de erro
	 * (409/422/404) para todas as ações dos nós, evitando duplicação.
	 */
	async function runMutation(action: () => Promise<unknown>): Promise<void> {
		if (mutating) return;
		mutating = true;
		actionError = '';
		try {
			await action();
			await load();
		} catch (err) {
			if (err instanceof ApiClientError && err.code === 'unauthenticated') return;
			actionError =
				err instanceof Error ? err.message : 'Não foi possível concluir a operação.';
		} finally {
			mutating = false;
		}
	}

	function handleReorder(orgaoId: number, direction: ReorderDirection): void {
		void runMutation(() => reorderOrgao(orgaoId, direction));
	}

	/** Localiza um nó por id em qualquer profundidade da árvore. */
	function findNode(nodes: OrgaoNode[], orgaoId: number): OrgaoNode | null {
		for (const n of nodes) {
			if (n.id === orgaoId) return n;
			const hit = findNode(n.filhos, orgaoId);
			if (hit) return hit;
		}
		return null;
	}

	/** Conjunto de ids do nó + todos os seus descendentes. */
	function collectDescendantIds(node: OrgaoNode): Set<number> {
		const ids = new Set<number>([node.id]);
		for (const child of node.filhos) {
			for (const id of collectDescendantIds(child)) ids.add(id);
		}
		return ids;
	}

	/**
	 * Validação de pai por tipo, espelhando `isValidParentTipo` do orgao_tree.js:
	 * o pai precisa ter rank (nível) ESTRITAMENTE menor que o do filho. Sem rank
	 * conhecido, permite (o backend faz a validação final).
	 */
	function isValidParentTipo(parentTipo: string | null, childTipo: string | null): boolean {
		const ranks = data?.tipo_rank ?? {};
		const pr = parentTipo != null ? ranks[parentTipo] : undefined;
		const cr = childTipo != null ? ranks[childTipo] : undefined;
		if (pr === undefined || cr === undefined) return true;
		return pr < cr;
	}

	/**
	 * Decide se um nó pode receber outro como filho via drag-and-drop. Espelha as
	 * guardas de `dragover`/`drop` do v4.5: não pode soltar sobre si mesmo nem
	 * sobre um descendente (criaria ciclo), e o tipo do alvo precisa poder ser
	 * pai do tipo arrastado.
	 */
	function canDropOn(draggedId: number, targetId: number): boolean {
		if (!data || draggedId === targetId) return false;
		const dragged = findNode(data.arvore, draggedId);
		const target = findNode(data.arvore, targetId);
		if (!dragged || !target) return false;
		if (collectDescendantIds(dragged).has(targetId)) return false;
		// Já é o pai atual: nada a fazer.
		if (dragged.pai_id === targetId) return false;
		return isValidParentTipo(target.tipo, dragged.tipo);
	}

	/**
	 * Drag-and-drop = REPARENTING (igual ao v4.5): soltar `draggedId` sobre
	 * `targetId` torna o alvo o novo pai, via POST `/move`. Após mover, garante
	 * que o novo pai fique expandido e seleciona o nó movido (espelha
	 * `reparentNode`/`is-selected`).
	 */
	function handleReparent(draggedId: number, targetId: number): void {
		if (!canDropOn(draggedId, targetId)) {
			const dragged = data ? findNode(data.arvore, draggedId) : null;
			const target = data ? findNode(data.arvore, targetId) : null;
			if (dragged && target && !isValidParentTipo(target.tipo, dragged.tipo)) {
				actionError = `Um órgão do tipo "${target.tipo}" não pode ser pai de "${dragged.tipo}".`;
			}
			return;
		}
		void runMutation(async () => {
			await moveOrgao(draggedId, targetId);
			expandedIds = new Set([...expandedIds, targetId]);
			selectedId = draggedId;
		});
	}

	function handleToggleAtivo(orgaoId: number): void {
		void runMutation(() => toggleOrgaoAtivo(orgaoId));
	}

	function handleMove(orgaoId: number, paiId: number | null): void {
		void runMutation(() => moveOrgao(orgaoId, paiId));
	}

	function handleDelete(node: OrgaoNode): void {
		const confirmed = confirm(`Excluir o órgão ${node.sigla}? Esta ação não pode ser desfeita.`);
		if (!confirmed) return;
		void runMutation(() => deleteOrgao(node.id));
	}

	// === Expand / collapse (espelha orgao_tree.js) ===

	/** Ids dos nós nos níveis 0 e 1 (estado inicial de expansão do v4.5). */
	function collectInitialExpanded(nodes: OrgaoNode[], depth = 0): Set<number> {
		const ids = new Set<number>();
		for (const n of nodes) {
			if (depth <= 1) ids.add(n.id);
			for (const id of collectInitialExpanded(n.filhos, depth + 1)) ids.add(id);
		}
		return ids;
	}

	/** Remove do set ids que não existem mais (pós-recarga). */
	function pruneExpanded(nodes: OrgaoNode[], current: Set<number>): Set<number> {
		const alive = new Set<number>();
		const walk = (list: OrgaoNode[]): void => {
			for (const n of list) {
				if (current.has(n.id)) alive.add(n.id);
				walk(n.filhos);
			}
		};
		walk(nodes);
		return alive;
	}

	/** Todos os ids da árvore (para "expandir tudo"). */
	function collectAllIds(nodes: OrgaoNode[]): Set<number> {
		const ids = new Set<number>();
		const walk = (list: OrgaoNode[]): void => {
			for (const n of list) {
				ids.add(n.id);
				walk(n.filhos);
			}
		};
		walk(nodes);
		return ids;
	}

	function toggleExpanded(orgaoId: number): void {
		const next = new Set(expandedIds);
		if (next.has(orgaoId)) next.delete(orgaoId);
		else next.add(orgaoId);
		expandedIds = next;
	}

	function expandAll(): void {
		if (!data) return;
		expandedIds = collectAllIds(data.arvore);
	}

	function collapseAll(): void {
		if (!data) return;
		// v4.5 mantém apenas a raiz (depth 0) aberta ao recolher tudo.
		expandedIds = new Set(data.arvore.map((n) => n.id));
	}

	// === Busca (debounce 120ms, espelha applyFilter do orgao_tree.js) ===
	function onSearchInput(event: Event): void {
		const value = (event.currentTarget as HTMLInputElement).value;
		searchQuery = value;
		if (searchTimer) clearTimeout(searchTimer);
		searchTimer = setTimeout(() => {
			filterQuery = value.trim().toLowerCase();
			if (filterQuery) {
				// Ao buscar, abre tudo para revelar os matches (como expandToRoot).
				expandAll();
			}
		}, 120);
	}

	/** Marca um nó como selecionado ao clicar na linha (não nas ações/chevron). */
	function selectNode(orgaoId: number): void {
		selectedId = orgaoId;
	}

	onMount(() => {
		void load();
		return () => {
			inFlight?.abort();
			if (searchTimer) clearTimeout(searchTimer);
		};
	});

	const total = $derived(data?.total ?? 0);
	const candidatosPai = $derived(data?.candidatos_pai ?? []);
	const maxDepth = $derived(data?.max_depth ?? 0);
</script>

<svelte:head>
	<title>Órgãos — ProjetosRJ</title>
</svelte:head>

<section aria-labelledby="orgaos-title" class="flex flex-col gap-4">
	<PageHeader compact class="min-h-[3.5rem]" labelId="orgaos-title">
		{#snippet titleContent()}
			<span class="align-middle">Hierarquia de Órgãos</span>
			{#if data}
				<CountBadge class="ml-2">{total} unidade{total === 1 ? '' : 's'}</CountBadge>
			{/if}
		{/snippet}
		{#snippet actions()}
			<a
				href={`${base}/admin/orgaos/tipos`}
				class="inline-flex h-8 items-center gap-1.5 rounded-md border border-border-subtle bg-surface px-3 text-sm font-medium text-text-primary no-underline transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
			>
				<i class="fas fa-layer-group" aria-hidden="true"></i>Tipos
			</a>
			<Button size="sm" href={`${base}/admin/orgaos/novo`}>
				{#snippet icon()}<i class="fas fa-plus" aria-hidden="true"></i>{/snippet}
				{total === 0 ? 'Criar Órgão Raiz' : 'Nova Unidade'}
			</Button>
		{/snippet}
	</PageHeader>

	<div class="flex flex-wrap items-center gap-2">
		<span
			class="inline-flex items-center gap-1.5 rounded-full bg-surface-muted px-3 py-1 text-xs font-medium text-text-secondary"
		>
			<i class="fas fa-layer-group" aria-hidden="true"></i>Profundidade máxima: {maxDepth}
		</span>
	</div>

	{#if actionError}
		<div role="alert" class="rounded-md border border-danger bg-surface px-4 py-3 text-sm text-text-primary">
			{actionError}
		</div>
	{/if}

	{#if loadState === 'loading'}
		<p role="status" aria-live="polite" class="text-text-secondary">Carregando árvore de órgãos…</p>
	{:else if loadState === 'error'}
		<div
			role="alert"
			class="flex flex-col items-start gap-3 rounded-lg border border-danger bg-surface px-5 py-4"
		>
			<p class="text-text-primary">{errorMessage}</p>
			{#if errorKind !== 'forbidden'}
				<button
					type="button"
					onclick={() => load()}
					class="rounded-md border border-border-subtle bg-surface px-4 py-2 text-sm font-medium text-text-primary transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
				>
					Tentar novamente
				</button>
			{/if}
		</div>
	{:else if data}
		{#if data.arvore.length === 0}
			<div
				role="status"
				aria-live="polite"
				class="flex flex-col items-center gap-3 rounded-xl border border-border-subtle bg-surface px-5 py-12 text-center shadow-sm"
			>
				<span
					class="flex h-14 w-14 items-center justify-center rounded-full bg-surface-muted text-text-muted"
					aria-hidden="true"
				>
					<i class="fas fa-sitemap text-2xl"></i>
				</span>
				<h2 class="font-heading text-lg font-semibold text-text-primary">
					Nenhum órgão cadastrado
				</h2>
				<p class="max-w-md text-sm text-text-secondary">
					Comece criando o órgão raiz "Estado do Rio de Janeiro" para depois adicionar secretarias
					e suas áreas.
				</p>
				<a
					href={`${base}/admin/orgaos/novo`}
					class="mt-2 inline-flex h-9 items-center gap-2 rounded-md bg-primary-600 px-3.5 text-sm font-semibold text-white no-underline shadow-sm transition-all duration-fast hover:bg-primary-700 hover:shadow-md focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2"
				>
					<i class="fas fa-plus" aria-hidden="true"></i>Criar Órgão Raiz
				</a>
			</div>
		{:else}
			<div class="orgao-tree-card">
				<div class="orgao-tree-toolbar">
					<div class="orgao-search">
						<i class="fas fa-search orgao-search-icon" aria-hidden="true"></i>
						<input
							type="search"
							class="orgao-search-input"
							placeholder="Buscar por sigla ou nome…"
							autocomplete="off"
							aria-label="Buscar órgãos por sigla ou nome"
							value={searchQuery}
							oninput={onSearchInput}
						/>
					</div>
					<div class="orgao-tree-toolbar-actions">
						<button type="button" class="orgao-toolbar-link" onclick={expandAll}>
							<i class="fas fa-angle-double-down" aria-hidden="true"></i>Expandir tudo
						</button>
						<button type="button" class="orgao-toolbar-link" onclick={collapseAll}>
							<i class="fas fa-angle-double-up" aria-hidden="true"></i>Recolher tudo
						</button>
					</div>
				</div>

				<ul class="orgao-tree" role="tree" aria-label="Hierarquia de órgãos" aria-busy={mutating}>
					{#each data.arvore as raiz, i (raiz.id)}
						<OrgaoTreeNode
							node={raiz}
							depth={0}
							index={i}
							siblingCount={data.arvore.length}
							paiOptions={candidatosPai}
							busy={mutating}
							{expandedIds}
							{selectedId}
							{filterQuery}
							{canDropOn}
							onToggle={toggleExpanded}
							onSelect={selectNode}
							onReorder={handleReorder}
							onReparent={handleReparent}
							onToggleAtivo={handleToggleAtivo}
							onMove={handleMove}
							onDelete={handleDelete}
						/>
					{/each}
				</ul>

				<div class="orgao-tree-footnote">
					<i class="fas fa-arrows-alt" aria-hidden="true"></i>
					Arraste uma unidade sobre outra para mudar o pai.
				</div>
			</div>
		{/if}
	{/if}
</section>

<style>
	/* Espelha static/css/admin/orgao_tree.css (v4.5). Tokens semânticos p/ dark. */
	.orgao-tree-card {
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: 16px;
		box-shadow: var(--ds-shadow-sm);
		overflow: hidden;
	}

	.orgao-tree-toolbar {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 1rem;
		padding: 0.875rem 1rem;
		border-bottom: 1px solid var(--color-border);
		background: var(--color-surface-muted);
		flex-wrap: wrap;
	}

	.orgao-search {
		position: relative;
		flex: 1 1 280px;
		min-width: 200px;
		max-width: 460px;
	}

	.orgao-search-icon {
		position: absolute;
		left: 0.75rem;
		top: 50%;
		transform: translateY(-50%);
		color: var(--color-text-muted);
		font-size: 0.8125rem;
		pointer-events: none;
	}

	.orgao-search-input {
		width: 100%;
		height: 2.25rem;
		padding: 0 0.75rem 0 2.25rem;
		border: 1px solid var(--color-border);
		border-radius: 12px;
		background: var(--color-surface);
		font-size: 0.8125rem;
		color: var(--color-text-primary);
		transition: border-color 120ms ease;
	}
	.orgao-search-input:focus {
		outline: none;
		border-color: var(--ds-color-primary-500);
	}

	.orgao-tree-toolbar-actions {
		display: flex;
		gap: 0.75rem;
		align-items: center;
	}

	.orgao-toolbar-link {
		display: inline-flex;
		align-items: center;
		gap: 0.3rem;
		background: transparent;
		border: 0;
		padding: 0.25rem 0.5rem;
		font-size: 0.8125rem;
		color: var(--color-text-secondary);
		cursor: pointer;
		border-radius: 6px;
		transition:
			color 120ms ease,
			background 120ms ease;
	}
	.orgao-toolbar-link:hover {
		color: var(--ds-color-primary-700);
		background: var(--ds-color-primary-light-bg);
	}
	.orgao-toolbar-link:focus-visible {
		outline: none;
		box-shadow: 0 0 0 2px var(--ds-color-primary-500);
	}

	/* Lista rolável até 70vh (espelha .orgao-tree do v4.5). */
	.orgao-tree {
		list-style: none;
		margin: 0;
		padding: 0.5rem 0.25rem 0.5rem 0;
		display: flex;
		flex-direction: column;
		max-height: 70vh;
		overflow: auto;
	}

	.orgao-tree-footnote {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.625rem 1rem;
		border-top: 1px solid var(--color-border);
		background: var(--color-surface-muted);
		font-size: 0.75rem;
		color: var(--color-text-muted);
	}
</style>
