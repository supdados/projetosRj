<script lang="ts">
	/**
	 * DRAWER de Projetos Relacionados — vínculo simétrico entre projetos, aberto
	 * pelo botão no section-divider de "Detalhes do Projeto" (mesmo molde do
	 * ProjectHistoryDrawer: overlay, largura, animação, focus trap, Esc/backdrop).
	 *
	 * A lista chega pronta do detalhe (`relacionados`); vincular/desvincular
	 * acontecem AQUI (a página só repassa props + callback de refresh). Para
	 * `canEdit`, busca debounced de candidatos no topo — sem modal separado.
	 * Remoção sem confirmação: religar custa 2 cliques, nada é destruído.
	 */
	import { fly, fade } from 'svelte/transition';
	import { cubicOut } from 'svelte/easing';
	import {
		linkRelatedProject,
		unlinkRelatedProject,
		searchRelatedCandidates
	} from '$lib/api/projectDetail';
	import { ApiClientError } from '$lib/api/client';
	import { focusTrap } from '$lib/actions/focusTrap';
	import { projectStatusChipTone } from '$lib/utils/projectLabels';
	import type {
		ProjetoRelacionado,
		ProjetoRelacionadoCandidato
	} from '$lib/types/projectDetail';

	interface Props {
		projectId: number;
		projectTitulo: string;
		relacionados: ProjetoRelacionado[];
		canEdit: boolean;
		/** Re-busca o detalhe na página após vincular/desvincular. */
		onChanged: () => Promise<void>;
		onClose: () => void;
	}

	let { projectId, projectTitulo, relacionados, canEdit, onChanged, onClose }: Props = $props();

	const DEBOUNCE_MS = 300;
	const MIN_QUERY_LEN = 2;

	let searchTerm = $state('');
	let candidates = $state<ProjetoRelacionadoCandidato[]>([]);
	let searchState = $state<'idle' | 'searching' | 'ready' | 'error'>('idle');
	let mutationError = $state('');
	let linkInFlightId = $state<number | null>(null);
	let unlinkInFlightId = $state<number | null>(null);
	let searchInput = $state<HTMLInputElement | null>(null);

	let debounceTimer: ReturnType<typeof setTimeout> | null = null;
	let abortController: AbortController | null = null;
	// Token de geração: resposta atrasada de um termo anterior não pode vencer.
	let gen = 0;

	const linkedIds = $derived(new Set(relacionados.map((rel) => rel.id)));
	// Reforço client-side; o backend já exclui o próprio projeto e os vinculados.
	const visibleCandidates = $derived(
		candidates.filter((c) => c.id !== projectId && !linkedIds.has(c.id))
	);

	function messageOf(err: unknown, fallback: string): string {
		return err instanceof ApiClientError && err.message ? err.message : fallback;
	}

	function isUnauthenticated(err: unknown): boolean {
		return err instanceof ApiClientError && err.code === 'unauthenticated';
	}

	async function buscarCandidatos(q: string): Promise<void> {
		const minhaGen = ++gen;
		abortController?.abort();
		abortController = new AbortController();
		searchState = 'searching';
		try {
			const data = await searchRelatedCandidates(projectId, q, abortController.signal);
			if (minhaGen !== gen) return;
			candidates = data;
			searchState = 'ready';
		} catch (err) {
			if (minhaGen !== gen) return;
			if (err instanceof DOMException && err.name === 'AbortError') return;
			if (isUnauthenticated(err)) return;
			searchState = 'error';
		}
	}

	function onSearchInput(): void {
		if (debounceTimer) clearTimeout(debounceTimer);
		const q = searchTerm.trim();
		if (q.length < MIN_QUERY_LEN) {
			gen++;
			abortController?.abort();
			candidates = [];
			searchState = 'idle';
			return;
		}
		debounceTimer = setTimeout(() => {
			debounceTimer = null;
			void buscarCandidatos(q);
		}, DEBOUNCE_MS);
	}

	async function vincular(candidateId: number): Promise<void> {
		mutationError = '';
		linkInFlightId = candidateId;
		try {
			await linkRelatedProject(projectId, candidateId);
			searchTerm = '';
			candidates = [];
			searchState = 'idle';
			await onChanged();
		} catch (err) {
			if (isUnauthenticated(err)) return;
			mutationError = messageOf(err, 'Não foi possível vincular o projeto.');
		} finally {
			linkInFlightId = null;
		}
	}

	async function desvincular(relatedId: number): Promise<void> {
		mutationError = '';
		unlinkInFlightId = relatedId;
		try {
			await unlinkRelatedProject(projectId, relatedId);
			await onChanged();
		} catch (err) {
			if (isUnauthenticated(err)) return;
			mutationError = messageOf(err, 'Não foi possível desvincular o projeto.');
		} finally {
			unlinkInFlightId = null;
		}
	}

	function onKeydown(event: KeyboardEvent): void {
		if (event.key === 'Escape') {
			event.stopPropagation();
			onClose();
		}
	}

	$effect(() => () => {
		if (debounceTimer) clearTimeout(debounceTimer);
		abortController?.abort();
	});
</script>

<!-- Backdrop: mesma tinta/blur dos demais drawers, fade 200ms. -->
<div
	class="fixed inset-0 z-modal bg-overlay backdrop-blur-[1.2px]"
	role="presentation"
	transition:fade={{ duration: 200 }}
	onclick={onClose}
></div>

<!-- Painel lateral: mesma largura do drawer de histórico. -->
<div
	role="dialog"
	aria-modal="true"
	aria-labelledby="projetos-relacionados-title"
	tabindex="-1"
	use:focusTrap
	onkeydown={onKeydown}
	transition:fly={{ x: 620, duration: 240, easing: cubicOut, opacity: 1 }}
	class="related-drawer-panel fixed right-0 top-0 z-modal flex h-full w-[min(620px,100vw)] flex-col border-l border-border-subtle bg-surface shadow-[-18px_0_44px_rgba(12,44,74,0.18)]"
>
	<header
		class="flex shrink-0 flex-col gap-3 border-b border-border-subtle bg-surface-elevated px-5 pb-3.5 pt-4"
	>
		<div class="flex items-start justify-between gap-3">
			<div class="flex min-w-0 flex-1 flex-col gap-1">
				<p class="m-0 text-xs font-bold uppercase tracking-caps text-text-muted">
					Projetos relacionados
				</p>
				<h2
					id="projetos-relacionados-title"
					class="m-0 line-clamp-2 break-words font-heading text-lg font-bold leading-snug text-text-primary"
				>
					{projectTitulo}
				</h2>
			</div>
			<div class="flex shrink-0 items-center gap-2">
				{#if relacionados.length > 0}
					<span
						class="inline-flex items-center rounded-md border border-border-subtle bg-surface px-2 py-0.5 text-xs font-semibold text-text-secondary"
						aria-live="polite"
					>
						{relacionados.length}
						{relacionados.length === 1 ? 'vínculo' : 'vínculos'}
					</span>
				{/if}
				<button
					type="button"
					onclick={onClose}
					aria-label="Fechar"
					class="inline-flex h-8 w-8 items-center justify-center rounded-md text-text-secondary transition-colors duration-fast hover:bg-surface-muted hover:text-brand focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
				>
					<svg viewBox="0 0 24 24" class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
						<path d="M18 6 6 18M6 6l12 12" />
					</svg>
				</button>
			</div>
		</div>
	</header>

	<div class="thin-scroll flex flex-1 flex-col gap-4 overflow-y-auto px-5 py-4">
		{#if mutationError}
			<div role="alert" class="rounded-lg border border-danger bg-surface px-4 py-3 text-sm text-text-primary">
				{mutationError}
			</div>
		{/if}

		{#if canEdit}
			<div class="flex flex-col gap-2">
				<div class="relative">
					<i
						class="fas fa-search pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-sm text-text-muted"
						aria-hidden="true"
					></i>
					<input
						type="search"
						bind:this={searchInput}
						bind:value={searchTerm}
						oninput={onSearchInput}
						placeholder="Buscar projeto para vincular…"
						aria-label="Buscar projeto para vincular"
						autocomplete="off"
						class="h-[var(--control-h-md)] w-full rounded-control border border-border-strong bg-surface pl-9 pr-3 text-md text-text-primary placeholder:text-text-faint transition-colors duration-fast focus:border-brand focus:outline-none"
					/>
				</div>

				{#if searchState === 'searching'}
					<p class="m-0 px-1 text-sm text-text-muted" aria-live="polite">Buscando projetos…</p>
				{:else if searchState === 'error'}
					<div class="flex items-center gap-2 px-1">
						<p class="m-0 text-sm text-danger">Não foi possível buscar projetos.</p>
						<button
							type="button"
							onclick={() => void buscarCandidatos(searchTerm.trim())}
							class="text-sm font-semibold text-brand hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
						>
							Tentar novamente
						</button>
					</div>
				{:else if searchState === 'ready' && visibleCandidates.length === 0}
					<p class="m-0 px-1 text-sm text-text-muted" aria-live="polite">
						Nenhum projeto encontrado para "{searchTerm.trim()}".
					</p>
				{:else if searchState === 'ready'}
					<ul
						class="thin-scroll m-0 max-h-60 list-none overflow-y-auto overflow-x-hidden rounded-control border border-border-subtle p-0"
						aria-label="Projetos disponíveis para vincular"
					>
						{#each visibleCandidates as candidate (candidate.id)}
							<li class="border-b border-border-hairline last:border-b-0">
								<button
									type="button"
									onclick={() => void vincular(candidate.id)}
									disabled={linkInFlightId !== null}
									class="flex w-full items-center gap-2.5 px-3 py-2.5 text-left transition-colors duration-fast hover:bg-surface-muted disabled:cursor-not-allowed disabled:opacity-60 focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand"
								>
									<span class="min-w-0 flex-1 truncate text-sm text-text-primary">
										{candidate.titulo}
									</span>
									<span class="chip chip--{projectStatusChipTone(candidate.status)} pointer-events-none shrink-0">
										{candidate.status}
									</span>
									{#if candidate.orgao_sigla}
										<span class="shrink-0 text-2xs text-text-muted">{candidate.orgao_sigla}</span>
									{/if}
								</button>
							</li>
						{/each}
					</ul>
				{/if}
			</div>
		{/if}

		{#if relacionados.length === 0}
			<div
				class="flex flex-col items-center gap-2 rounded-lg border border-dashed border-border-subtle px-4 py-8 text-center"
			>
				<p class="m-0 text-sm font-medium text-text-secondary">Nenhum projeto vinculado.</p>
				{#if canEdit}
					<button
						type="button"
						onclick={() => searchInput?.focus()}
						class="rounded-md border border-border-subtle bg-surface px-3 py-1.5 text-sm font-medium text-text-primary transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
					>
						Vincular projeto
					</button>
				{:else}
					<p class="m-0 text-xs text-text-muted">
						Vínculos criados pelos editores do projeto aparecerão aqui.
					</p>
				{/if}
			</div>
		{:else}
			<ul
				class="m-0 flex list-none flex-col rounded-lg border border-border-subtle p-0"
				aria-label="Projetos relacionados"
			>
				{#each relacionados as rel (rel.id)}
					<li class="flex items-center gap-3 border-b border-border-hairline px-3 py-2.5 last:border-b-0">
						<div class="flex min-w-0 flex-1 flex-col gap-1">
							<a
								href="/projetos/{rel.id}"
								class="truncate rounded-sm text-sm font-medium text-text-primary transition-colors duration-fast hover:text-brand hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
							>
								{rel.titulo}
							</a>
							<div class="flex items-center gap-2">
								<span class="chip chip--{projectStatusChipTone(rel.status)} pointer-events-none">{rel.status}</span>
								{#if rel.orgao_sigla}
									<span class="text-2xs text-text-muted">{rel.orgao_sigla}</span>
								{/if}
							</div>
						</div>
						{#if canEdit}
							<button
								type="button"
								onclick={() => void desvincular(rel.id)}
								disabled={unlinkInFlightId === rel.id}
								aria-label="Desvincular {rel.titulo}"
								title="Desvincular"
								class="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-text-muted transition-colors duration-fast hover:bg-surface-muted hover:text-danger disabled:cursor-not-allowed disabled:opacity-60 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
							>
								{#if unlinkInFlightId === rel.id}
									<i class="fas fa-spinner fa-spin text-xs" aria-hidden="true"></i>
								{:else}
									<svg viewBox="0 0 24 24" class="h-3.5 w-3.5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
										<path d="M18 6 6 18M6 6l12 12" />
									</svg>
								{/if}
							</button>
						{/if}
					</li>
				{/each}
			</ul>
		{/if}
	</div>
</div>

<style>
	:global([data-theme='dark']) .related-drawer-panel {
		box-shadow: -18px 0 44px rgba(0, 0, 0, 0.55);
	}
</style>
