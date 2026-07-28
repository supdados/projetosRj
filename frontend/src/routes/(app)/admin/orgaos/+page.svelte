<script lang="ts">
	/**
	 * Tela "Admin > Órgãos" (árvore READ-ONLY). URL `/spa/admin/orgaos`.
	 *
	 * A estrutura organizacional é espelho do SIORG-RJ: nada se cria/edita/move
	 * aqui. A tela renderiza a hierarquia (`GET /api/admin/orgaos`) com o
	 * componente recursivo `OrgaoTreeNode`, mostra a última sincronização
	 * (`GET /api/admin/siorg/status`) e oferece o botão "Atualizar estrutura"
	 * (`POST /api/admin/siorg/sync`; 409 = sync em andamento, 502 = SIORG fora, 503 = não configurado).
	 *
	 * Só admins acessam: o backend devolve 403 (`forbidden`) para não-admin e
	 * 401 já redireciona para `/login`. Estados loading/erro/vazio anunciados
	 * via aria-live/role=alert.
	 */
	import { onMount } from 'svelte';
	import {
		fetchOrgaoTree,
		peekOrgaoTree,
		siorgStatus,
		siorgSync,
		SiorgApiError
	} from '$lib/api/adminOrgaos';
	import { ApiClientError } from '$lib/api/client';
	import { flash } from '$lib/stores/flash';
	import type {
		OrgaoNode,
		OrgaoTreeData,
		SiorgStatusData,
		SiorgSyncResult
	} from '$lib/types/adminOrgaos';
	import OrgaoTreeNode from '$lib/components/OrgaoTreeNode.svelte';
	import AdminOrgaosSkeleton from '$lib/components/skeletons/AdminOrgaosSkeleton.svelte';
	import PageHeader from '$lib/components/PageHeader.svelte';
	import Button from '$lib/components/Button.svelte';
	import CountBadge from '$lib/components/CountBadge.svelte';

	type LoadState = 'loading' | 'ready' | 'error';

	// SWR: reabre com a ultima arvore boa (cache de modulo em $lib/api/adminOrgaos)
	// e revalida em silencio — sem flash de loading nas revisitas.
	const initialData = peekOrgaoTree();
	let loadState = $state<LoadState>(initialData ? 'ready' : 'loading');
	let data = $state<OrgaoTreeData | null>(initialData);
	let errorMessage = $state<string>('');
	/** Distingue 403 (sem permissão) do erro genérico para a UI. */
	let errorKind = $state<'forbidden' | 'generic'>('generic');

	let siorg = $state<SiorgStatusData | null>(null);
	let syncing = $state(false);
	let syncResult = $state<SiorgSyncResult | null>(null);
	/** Mensagem de erro do sync (409/502/rede). */
	let syncError = $state<string>('');

	/** Ids de nós expandidos; abre níveis 0 e 1 ao carregar. */
	let expandedIds = $state<Set<number>>(
		initialData ? collectInitialExpanded(initialData.arvore) : new Set()
	);
	/** Termo de busca por sigla/nome (debounced). */
	let searchQuery = $state<string>('');
	/** Termo efetivamente aplicado ao filtro (após debounce de 120ms). */
	let filterQuery = $state<string>('');
	/** Id do nó selecionado (clique na linha → realce). */
	let selectedId = $state<number | null>(null);

	let searchTimer: ReturnType<typeof setTimeout> | null = null;
	let inFlight: AbortController | null = null;

	async function load(): Promise<void> {
		inFlight?.abort();
		const controller = new AbortController();
		inFlight = controller;

		// SWR: com cache mostra a arvore antiga ja (sem skeleton) e a revalidacao
		// abaixo troca em silencio; sem cache, skeleton.
		const cached = peekOrgaoTree();
		if (cached) {
			data = cached;
			loadState = 'ready';
		} else {
			data = null;
			loadState = 'loading';
		}
		errorMessage = '';
		errorKind = 'generic';
		try {
			const next = await fetchOrgaoTree(controller.signal);
			if (controller.signal.aborted) return;
			data = next;
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
				errorMessage = 'Você não tem permissão para visualizar órgãos.';
				loadState = 'error';
				return;
			}
			const message =
				err instanceof Error ? err.message : 'Falha ao carregar a árvore de órgãos.';
			// Revalidacao falhou com dado stale na tela: mantem a arvore e avisa via
			// flash, em vez de trocar a tela inteira pelo painel de erro.
			if (data) {
				flash.danger(message);
				return;
			}
			errorMessage = message;
			loadState = 'error';
		}
	}

	async function loadSiorgStatus(): Promise<void> {
		try {
			siorg = await siorgStatus();
		} catch (err) {
			// Status indisponível não bloqueia a árvore nem o botão; o POST de sync resolve.
			console.warn('Falha ao consultar status do SIORG', err);
			siorg = null;
		}
	}

	async function handleSync(): Promise<void> {
		if (syncDisabled) return;
		syncing = true;
		syncError = '';
		syncResult = null;
		try {
			syncResult = await siorgSync();
			await Promise.all([load(), loadSiorgStatus()]);
		} catch (err) {
			syncError = syncErrorMessage(err);
			await loadSiorgStatus();
		} finally {
			syncing = false;
		}
	}

	function syncErrorMessage(err: unknown): string {
		if (err instanceof SiorgApiError && err.status === 409) {
			return `Já existe uma sincronização em andamento: ${err.message}`;
		}
		if (err instanceof SiorgApiError && err.status === 502) {
			return `SIORG indisponível no momento: ${err.message}`;
		}
		if (err instanceof SiorgApiError && err.status === 503) {
			return `Integração SIORG não configurada: ${err.message}`;
		}
		if (err instanceof Error) return err.message;
		return 'Não foi possível sincronizar com o SIORG.';
	}

	/** Formata ISO em data/hora pt-BR curta; null vira em-dash. */
	function formatDateTime(iso: string | null): string {
		if (!iso) return '—';
		const parsed = new Date(iso);
		if (Number.isNaN(parsed.getTime())) return iso;
		return parsed.toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' });
	}

	// === Expand / collapse ===

	/** Ids dos nós nos níveis 0 e 1 (estado inicial de expansão). */
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
		expandedIds = new Set(data.arvore.map((n) => n.id));
	}

	// === Busca (debounce 120ms) ===
	function onSearchInput(event: Event): void {
		const value = (event.currentTarget as HTMLInputElement).value;
		searchQuery = value;
		if (searchTimer) clearTimeout(searchTimer);
		searchTimer = setTimeout(() => {
			filterQuery = value.trim().toLowerCase();
			if (filterQuery) expandAll();
		}, 120);
	}

	function selectNode(orgaoId: number): void {
		selectedId = orgaoId;
	}

	onMount(() => {
		void load();
		void loadSiorgStatus();
		return () => {
			inFlight?.abort();
			if (searchTimer) clearTimeout(searchTimer);
		};
	});

	const total = $derived(data?.total ?? 0);
	const ultimaSync = $derived(siorg?.ultima_sincronizacao ?? null);
	// Status indisponível (siorg === null) mantém o botão habilitado: o POST reporta o erro real.
	const syncDisabled = $derived(syncing || siorg?.configurado === false);
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
			<Button size="sm" onclick={handleSync} disabled={syncDisabled} aria-busy={syncing}>
				{#snippet icon()}
					<i class="fas {syncing ? 'fa-circle-notch fa-spin' : 'fa-sync-alt'}" aria-hidden="true"
					></i>
				{/snippet}
				{syncing ? 'Sincronizando…' : 'Atualizar estrutura'}
			</Button>
		{/snippet}
	</PageHeader>

	<div class="siorg-card" aria-live="polite">
		<div class="siorg-card-main">
			<span class="siorg-card-icon" aria-hidden="true">
				<i class="fas fa-satellite-dish"></i>
			</span>
			<div class="siorg-card-body">
				<span class="siorg-card-title">Última sincronização com o SIORG</span>
				{#if siorg && !siorg.configurado}
					<span class="siorg-warn">
						<i class="fas fa-exclamation-triangle" aria-hidden="true"></i>
						Integração SIORG não configurada
					</span>
				{:else if ultimaSync}
					<span class="siorg-card-line">
						<span class="siorg-status" data-status={ultimaSync.status}>{ultimaSync.status}</span>
						em {formatDateTime(ultimaSync.finalizado_em ?? ultimaSync.iniciado_em)}
						{#if ultimaSync.disparado_por_nome}
							por {ultimaSync.disparado_por_nome}
						{/if}
						— {ultimaSync.criadas} criada{ultimaSync.criadas === 1 ? '' : 's'},
						{ultimaSync.atualizadas} atualizada{ultimaSync.atualizadas === 1 ? '' : 's'},
						{ultimaSync.desativadas} desativada{ultimaSync.desativadas === 1 ? '' : 's'}
					</span>
					{#if ultimaSync.erro}
						<span class="siorg-warn">
							<i class="fas fa-exclamation-triangle" aria-hidden="true"></i>
							{ultimaSync.erro}
						</span>
					{/if}
				{:else if siorg}
					<span class="siorg-card-line">Nenhuma sincronização registrada ainda.</span>
				{:else}
					<span class="siorg-card-line">Status da integração indisponível.</span>
				{/if}
			</div>
		</div>
	</div>

	{#if syncResult}
		<div role="status" class="siorg-feedback is-success">
			<i class="fas fa-check-circle" aria-hidden="true"></i>
			Estrutura atualizada: {syncResult.criadas} criada{syncResult.criadas === 1 ? '' : 's'},
			{syncResult.atualizadas} atualizada{syncResult.atualizadas === 1 ? '' : 's'},
			{syncResult.desativadas} desativada{syncResult.desativadas === 1 ? '' : 's'}.
		</div>
	{/if}
	{#if syncError}
		<div role="alert" class="siorg-feedback is-error">
			<i class="fas fa-exclamation-circle" aria-hidden="true"></i>
			{syncError}
		</div>
	{/if}

	{#if loadState === 'loading'}
		<p role="status" class="sr-only">Carregando árvore de órgãos…</p>
		<AdminOrgaosSkeleton />
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
					class="rounded-md border border-border-subtle bg-surface px-4 py-2 text-sm font-medium text-text-primary transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
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
					A estrutura organizacional vem do SIORG. Use "Atualizar estrutura" para importar as
					unidades.
				</p>
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

				<ul class="orgao-tree" role="tree" aria-label="Hierarquia de órgãos" aria-busy={syncing}>
					{#each data.arvore as raiz (raiz.id)}
						<OrgaoTreeNode
							node={raiz}
							depth={0}
							{expandedIds}
							{selectedId}
							{filterQuery}
							onToggle={toggleExpanded}
							onSelect={selectNode}
						/>
					{/each}
				</ul>

				<div class="orgao-tree-footnote">
					<i class="fas fa-lock" aria-hidden="true"></i>
					Estrutura gerenciada pelo SIORG-RJ — somente leitura.
				</div>
			</div>
		{/if}
	{/if}
</section>

<style>
	/* Tokens semânticos p/ dark. */
	.orgao-tree-card {
		background: var(--ds-color-surface-base);
		border: 1px solid var(--ds-color-border-base);
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
		border-bottom: 1px solid var(--ds-color-border-base);
		background: var(--ds-color-surface-muted);
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
		color: var(--ds-color-text-muted);
		font-size: 0.8125rem;
		pointer-events: none;
	}

	.orgao-search-input {
		width: 100%;
		height: 2.25rem;
		padding: 0 0.75rem 0 2.25rem;
		border: 1px solid var(--ds-color-border-base);
		border-radius: 12px;
		background: var(--ds-color-surface-base);
		font-size: 0.8125rem;
		color: var(--ds-color-text-primary);
		transition: border-color 120ms ease;
	}
	.orgao-search-input:focus {
		outline: none;
		border-color: var(--ds-color-border-brand);
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
		color: var(--ds-color-text-secondary);
		cursor: pointer;
		border-radius: 6px;
		transition:
			color 120ms ease,
			background 120ms ease;
	}
	.orgao-toolbar-link:hover {
		color: var(--ds-color-text-brand);
		background: var(--ds-color-wash-neutral);
	}
	.orgao-toolbar-link:focus-visible {
		outline: none;
		box-shadow: 0 0 0 2px var(--ds-color-focus-ring);
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
		border-top: 1px solid var(--ds-color-border-base);
		background: var(--ds-color-surface-muted);
		font-size: 0.75rem;
		color: var(--ds-color-text-muted);
	}

	/* Card "última sincronização" (dados do SiorgSyncLog). */
	.siorg-card {
		background: var(--ds-color-surface-base);
		border: 1px solid var(--ds-color-border-base);
		border-radius: 12px;
		box-shadow: var(--ds-shadow-sm);
		padding: 0.75rem 1rem;
	}

	.siorg-card-main {
		display: flex;
		align-items: flex-start;
		gap: 0.75rem;
	}

	.siorg-card-icon {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 2.25rem;
		height: 2.25rem;
		border-radius: 10px;
		background: var(--ds-color-surface-muted);
		color: var(--ds-color-text-muted);
		flex-shrink: 0;
	}

	.siorg-card-body {
		display: flex;
		flex-direction: column;
		gap: 0.15rem;
		min-width: 0;
	}

	.siorg-card-title {
		font-size: 0.75rem;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		font-weight: 600;
		color: var(--ds-color-text-muted);
	}

	.siorg-card-line {
		font-size: 0.8125rem;
		color: var(--ds-color-text-secondary);
	}

	.siorg-status {
		font-weight: 700;
		text-transform: capitalize;
		color: var(--ds-color-text-primary);
	}
	.siorg-status[data-status='sucesso'] {
		color: var(--ds-color-text-success, #15803d);
	}
	.siorg-status[data-status='erro'] {
		color: var(--ds-color-text-danger, #b91c1c);
	}

	.siorg-warn {
		display: inline-flex;
		align-items: center;
		gap: 0.4rem;
		font-size: 0.8125rem;
		font-weight: 600;
		color: var(--ds-color-text-warning, #b45309);
	}

	.siorg-feedback {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		border-radius: 10px;
		padding: 0.625rem 1rem;
		font-size: 0.875rem;
		border: 1px solid transparent;
		background: var(--ds-color-surface-base);
	}
	.siorg-feedback.is-success {
		border-color: var(--ds-color-border-success, #15803d);
		color: var(--ds-color-text-success, #15803d);
		background: var(--ds-color-wash-success, rgba(21, 128, 61, 0.08));
	}
	.siorg-feedback.is-error {
		border-color: var(--ds-color-border-danger, #b91c1c);
		color: var(--ds-color-text-danger, #b91c1c);
		background: var(--ds-color-wash-danger, rgba(185, 28, 28, 0.08));
	}
</style>
