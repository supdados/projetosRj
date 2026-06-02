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
	import Card from '$lib/components/Card.svelte';
	import OrgaoTreeNode from '$lib/components/OrgaoTreeNode.svelte';

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

	/** Lista de irmãos (mesmo nível) que contém `orgaoId`, ou `null`. */
	function findSiblings(nodes: OrgaoNode[], orgaoId: number): OrgaoNode[] | null {
		if (nodes.some((n) => n.id === orgaoId)) return nodes;
		for (const n of nodes) {
			const hit = findSiblings(n.filhos, orgaoId);
			if (hit) return hit;
		}
		return null;
	}

	/**
	 * Reordena por drag-and-drop: solta `draggedId` na posição de `targetId`.
	 * Só reordena entre irmãos (mesmo pai); o endpoint `/reorder` é single-step,
	 * então emitimos N chamadas `up`/`down` sequenciais e recarregamos uma vez.
	 */
	function handleReorderTo(draggedId: number, targetId: number): void {
		if (!data || draggedId === targetId) return;
		const siblings = findSiblings(data.arvore, draggedId);
		if (!siblings) return;
		const from = siblings.findIndex((n) => n.id === draggedId);
		const to = siblings.findIndex((n) => n.id === targetId);
		// Alvo em outro pai: não reordenamos (use "mover para outro pai").
		if (from === -1 || to === -1 || from === to) return;
		const direction: ReorderDirection = to > from ? 'down' : 'up';
		const steps = Math.abs(to - from);
		void runMutation(async () => {
			for (let i = 0; i < steps; i++) {
				await reorderOrgao(draggedId, direction);
			}
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

	onMount(() => {
		void load();
		return () => inFlight?.abort();
	});

	const total = $derived(data?.total ?? 0);
	const candidatosPai = $derived(data?.candidatos_pai ?? []);
</script>

<svelte:head>
	<title>Órgãos — ProjetosRJ</title>
</svelte:head>

<section aria-labelledby="orgaos-title" class="flex flex-col gap-6">
	<header class="flex flex-wrap items-center justify-between gap-3">
		<div class="flex flex-col gap-2">
			<div class="flex flex-wrap items-center gap-3">
				<h1 id="orgaos-title" class="font-heading text-2xl font-bold text-text-primary">
					Órgãos
				</h1>
				<span
					class="inline-flex items-center gap-1 rounded-sm border border-primary-500 bg-primary-100 px-2 py-1 text-xs font-medium text-primary-700"
				>
					{total} órgão{total === 1 ? '' : 's'}
				</span>
			</div>
			<p class="text-sm text-text-secondary">
				Hierarquia de órgãos e unidades. Use as ações de cada nó para reordenar, mover,
				ativar/desativar ou excluir.
			</p>
		</div>
		<div class="flex items-center gap-2">
			<a
				href={`${base}/admin/orgaos/tipos`}
				class="rounded-md border border-border-subtle bg-surface px-4 py-2 text-sm font-medium text-text-primary transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
			>
				Tipos de órgão
			</a>
			<a
				href={`${base}/admin/orgaos/novo`}
				class="rounded-md border border-primary-500 bg-primary-100 px-4 py-2 text-sm font-medium text-primary-700 transition-colors duration-fast hover:bg-primary-100/70 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
			>
				Novo órgão
			</a>
		</div>
	</header>

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
				class="flex flex-col items-start gap-3 rounded-lg border border-border-subtle bg-surface px-5 py-8 text-text-muted"
			>
				<p>Nenhum órgão cadastrado ainda.</p>
				<a
					href={`${base}/admin/orgaos/novo`}
					class="rounded-md border border-primary-500 bg-primary-100 px-4 py-2 text-sm font-medium text-primary-700 hover:bg-primary-100/70 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
				>
					Criar órgão raiz
				</a>
			</div>
		{:else}
			<Card>
				<ul class="flex flex-col" aria-busy={mutating}>
					{#each data.arvore as raiz, i (raiz.id)}
						<OrgaoTreeNode
							node={raiz}
							depth={0}
							index={i}
							siblingCount={data.arvore.length}
							paiOptions={candidatosPai}
							busy={mutating}
							onReorder={handleReorder}
							onReorderTo={handleReorderTo}
							onToggleAtivo={handleToggleAtivo}
							onMove={handleMove}
							onDelete={handleDelete}
						/>
					{/each}
				</ul>
			</Card>
		{/if}
	{/if}
</section>
