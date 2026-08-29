<script lang="ts">
	/**
	 * DRAWER de Projetos Relacionados — vínculo simétrico entre projetos, aberto
	 * pelo botão no section-divider de "Detalhes do Projeto" (mesmo molde do
	 * ProjectHistoryDrawer: overlay, largura, animação, focus trap, Esc/backdrop).
	 *
	 * A lista chega pronta do detalhe (`relacionados`); vincular/desvincular
	 * acontecem AQUI (a página só repassa props + callback de refresh). Para
	 * `canEdit`, busca debounced no header com resultados num POPOVER combobox
	 * ancorado no input (transiente — flutua sobre o corpo, não desloca a lista
	 * de vinculados). Candidatos limitados a 10 pelo backend; a busca sobrevive
	 * ao vínculo (o recém-vinculado some via `linkedIds`, permitindo vincular
	 * vários em sequência). Esc em 2 estágios: com busca ativa limpa a busca,
	 * sem busca fecha o drawer. Remoção sem confirmação: religar custa 2
	 * cliques, nada é destruído. Dívida: a máquina de busca duplica
	 * ColecaoProjectPicker (extração exige tocar Coleções).
	 */
	import { fly, fade, slide } from 'svelte/transition';
	import { cubicOut } from 'svelte/easing';
	import { prefersReducedMotion } from 'svelte/motion';
	import { base } from '$app/paths';
	import {
		linkRelatedProject,
		unlinkRelatedProject,
		searchRelatedCandidates
	} from '$lib/api/projectDetail';
	import { ApiClientError } from '$lib/api/client';
	import { focusTrap } from '$lib/actions/focusTrap';
	import { flash } from '$lib/stores/flash';
	import { projectStatusIconId, projectStatusToneTextClass } from '$lib/utils/projectLabels';
	import AppIcon from '$lib/components/AppIcon.svelte';
	import ProjectIcon from '$lib/components/ProjectIcon.svelte';
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
	const MAX_CANDIDATOS = 10;

	let searchTerm = $state('');
	let candidates = $state<ProjetoRelacionadoCandidato[]>([]);
	let searchState = $state<'idle' | 'searching' | 'ready' | 'error'>('idle');
	let linkInFlightId = $state<number | null>(null);
	let unlinkInFlightId = $state<number | null>(null);
	let searchInput = $state<HTMLInputElement | null>(null);

	let searchWrap = $state<HTMLDivElement | null>(null);
	let debounceTimer: ReturnType<typeof setTimeout> | null = null;
	let abortController: AbortController | null = null;
	// Token de geração: resposta atrasada de um termo anterior não pode vencer.
	let gen = 0;

	const linkedIds = $derived(new Set(relacionados.map((rel) => rel.id)));
	// Reforço client-side; o backend já exclui o próprio projeto e os vinculados.
	const visibleCandidates = $derived(
		candidates.filter((c) => c.id !== projectId && !linkedIds.has(c.id))
	);

	const slideParams = $derived({
		duration: prefersReducedMotion.current ? 0 : 180,
		easing: cubicOut
	});

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

	// Fecha o popover preservando o termo digitado (clique-fora, como um
	// autocomplete nativo); `limparBusca` zera tudo (Esc estágio 1).
	function fecharPopover(): void {
		gen++;
		abortController?.abort();
		if (debounceTimer) {
			clearTimeout(debounceTimer);
			debounceTimer = null;
		}
		candidates = [];
		searchState = 'idle';
	}

	function limparBusca(): void {
		fecharPopover();
		searchTerm = '';
		searchInput?.focus();
	}

	function onPanelPointerDown(event: PointerEvent): void {
		if (searchState === 'idle') return;
		if (searchWrap && event.target instanceof Node && !searchWrap.contains(event.target)) {
			fecharPopover();
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

	// `onChanged` (refresh da página) trata os próprios erros — fica fora do
	// try para uma falha de refetch não virar toast de mutação fracassada.
	async function vincular(candidateId: number): Promise<void> {
		if (linkInFlightId !== null) return;
		linkInFlightId = candidateId;
		try {
			await linkRelatedProject(projectId, candidateId);
		} catch (err) {
			if (!isUnauthenticated(err)) {
				flash.danger(messageOf(err, 'Não foi possível vincular o projeto.'));
			}
			return;
		} finally {
			linkInFlightId = null;
		}
		flash.success('Projeto vinculado.');
		await onChanged();
		// A linha clicada some da lista (linkedIds) e levaria o foco junto.
		searchInput?.focus();
	}

	async function desvincular(relatedId: number): Promise<void> {
		if (unlinkInFlightId !== null) return;
		unlinkInFlightId = relatedId;
		try {
			await unlinkRelatedProject(projectId, relatedId);
		} catch (err) {
			if (!isUnauthenticated(err)) {
				flash.danger(messageOf(err, 'Não foi possível desvincular o projeto.'));
			}
			return;
		} finally {
			unlinkInFlightId = null;
		}
		flash.success('Vínculo removido.');
		await onChanged();
		searchInput?.focus();
	}

	// Esc em 2 estágios: busca ativa → limpa a busca; senão → fecha o drawer.
	// preventDefault evita colidir com o clear nativo do type="search".
	function onKeydown(event: KeyboardEvent): void {
		if (event.key !== 'Escape') return;
		event.stopPropagation();
		if (searchState !== 'idle' || searchTerm !== '') {
			event.preventDefault();
			limparBusca();
			return;
		}
		onClose();
	}

	// O focusTrap foca o botão Fechar; a ação primária do editor é digitar.
	$effect(() => {
		if (canEdit && searchInput) searchInput.focus();
	});

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
	onpointerdown={onPanelPointerDown}
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
				<span
					class="inline-flex items-center rounded-md border border-border-subtle bg-surface px-2 py-0.5 text-xs font-semibold text-text-secondary"
					aria-live="polite"
				>
					{relacionados.length}
					{relacionados.length === 1 ? 'vínculo' : 'vínculos'}
				</span>
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

		{#if canEdit}
			<div class="relative" bind:this={searchWrap}>
				<i
					class="fas fa-search pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-sm text-text-muted"
					aria-hidden="true"
				></i>
				<input
					type="search"
					bind:this={searchInput}
					bind:value={searchTerm}
					oninput={onSearchInput}
					placeholder="Buscar projeto pelo nome…"
					aria-label="Buscar projeto para vincular pelo nome"
					autocomplete="off"
					class="h-9 w-full rounded-lg border border-border-subtle bg-surface pl-8 pr-2.5 text-md text-text-primary placeholder:text-text-muted transition-colors duration-fast focus:border-brand focus:outline-none"
				/>

				<!-- Popover de candidatos: transiente, flutua sobre o corpo. -->
				{#if searchState !== 'idle'}
					<div
						class="absolute left-0 right-0 top-full z-20 mt-1 flex flex-col overflow-hidden rounded-lg border border-border-subtle bg-surface-elevated shadow-lg"
					>
						{#if searchState === 'searching'}
							<p class="m-0 px-3 py-4 text-center text-sm text-text-muted" aria-live="polite">
								Buscando projetos…
							</p>
						{:else if searchState === 'error'}
							<div class="flex flex-col items-center gap-2 px-3 py-4 text-center">
								<p class="m-0 text-sm text-danger">Não foi possível buscar projetos.</p>
								<button
									type="button"
									onclick={() => void buscarCandidatos(searchTerm.trim())}
									class="text-sm font-semibold text-brand hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
								>
									Tentar novamente
								</button>
							</div>
						{:else if visibleCandidates.length === 0}
							<p class="m-0 px-3 py-4 text-center text-sm text-text-muted" aria-live="polite">
								{candidates.length > 0
									? 'Todos os projetos encontrados já estão vinculados.'
									: `Nenhum projeto encontrado para "${searchTerm.trim()}".`}
							</p>
						{:else}
							<ul
								aria-label="Projetos disponíveis para vincular"
								class="thin-scroll m-0 max-h-[min(21rem,60vh)] list-none overflow-y-auto p-0"
							>
								{#each visibleCandidates as candidate (candidate.id)}
									{@const candidateIcon = projectStatusIconId(candidate.status)}
									<li class="border-b border-border-subtle last:border-b-0" transition:slide={slideParams}>
										<button
											type="button"
											onclick={() => void vincular(candidate.id)}
											disabled={linkInFlightId !== null && linkInFlightId !== candidate.id}
											aria-busy={linkInFlightId === candidate.id}
											class="group flex w-full items-center gap-2.5 px-3 py-2.5 text-left transition-colors duration-fast hover:bg-surface-muted disabled:cursor-not-allowed disabled:opacity-60 focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand"
										>
											<span class="shrink-0 font-mono text-xs font-bold text-text-muted">{candidate.id}</span>
											<span class="shrink-0 text-text-muted" aria-hidden="true">–</span>
											<span class="min-w-0 flex-1 truncate text-sm text-text-primary" title={candidate.titulo}>
												{candidate.titulo}
											</span>
											<span
												class="inline-flex shrink-0 items-center gap-1 text-xs font-semibold uppercase tracking-wide {projectStatusToneTextClass(candidate.status)}"
											>
												{#if candidateIcon}
													<ProjectIcon id={candidateIcon} size={14} />
												{/if}
												{candidate.status}
											</span>
											<span class="w-20 shrink-0 truncate text-right text-xs text-text-muted">
												{candidate.orgao_sigla ?? ''}
											</span>
											<span
												class="pointer-events-none inline-flex shrink-0 items-center gap-1 rounded-md border border-border-subtle bg-surface px-2 py-1 text-xs font-semibold text-brand transition-colors duration-fast group-hover:border-brand group-hover:bg-wash-brand"
											>
												{#if linkInFlightId === candidate.id}
													<span
														class="h-3 w-3 animate-spin rounded-full border-2 border-border-subtle border-t-primary-600"
														aria-hidden="true"
													></span>
												{:else}
													<i class="fas fa-plus text-2xs" aria-hidden="true"></i> Vincular
												{/if}
											</span>
										</button>
									</li>
								{/each}
							</ul>
							{#if candidates.length === MAX_CANDIDATOS}
								<p
									class="m-0 shrink-0 border-t border-border-subtle bg-surface-muted px-3 py-1.5 text-center text-2xs text-text-muted"
								>
									Mostrando os {MAX_CANDIDATOS} primeiros — refine a busca
								</p>
							{/if}
						{/if}
					</div>
				{/if}
			</div>
		{/if}
	</header>

	<div class="thin-scroll flex flex-1 flex-col gap-4 overflow-y-auto px-5 py-4">
		{#if relacionados.length === 0}
			<div
				class="flex flex-col items-center gap-2 rounded-lg border border-dashed border-border-subtle px-4 py-8 text-center"
			>
				<p class="m-0 text-sm font-medium text-text-secondary">Nenhum projeto vinculado.</p>
				{#if canEdit}
					<p class="m-0 text-xs text-text-muted">
						Use a busca acima para vincular o primeiro projeto.
					</p>
				{:else}
					<p class="m-0 text-xs text-text-muted">
						Quando este projeto tiver projetos relacionados, eles aparecerão aqui.
					</p>
				{/if}
			</div>
		{:else}
			<section aria-label="Projetos vinculados" class="flex flex-col gap-2">
				<h3 class="m-0 text-xs font-bold uppercase tracking-caps text-text-muted">
					Vinculados ({relacionados.length})
				</h3>
				<ul
					class="m-0 flex list-none flex-col overflow-hidden rounded-lg border border-border-subtle p-0"
					aria-label="Projetos relacionados"
				>
					{#each relacionados as rel (rel.id)}
						{@const relIcon = projectStatusIconId(rel.status)}
						<li
							class="flex items-center gap-2.5 border-b border-border-subtle px-3 py-2.5 last:border-b-0"
							transition:slide={slideParams}
						>
							<span class="shrink-0 font-mono text-xs font-bold text-text-muted">{rel.id}</span>
							<span class="shrink-0 text-text-muted" aria-hidden="true">–</span>
							<a
								href={`${base}/projetos/${rel.id}`}
								title={rel.titulo}
								class="min-w-0 flex-1 truncate rounded-sm text-sm font-medium text-text-primary transition-colors duration-fast hover:text-brand hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
							>
								{rel.titulo}
							</a>
							<span
								class="inline-flex shrink-0 items-center gap-1 text-xs font-semibold uppercase tracking-wide {projectStatusToneTextClass(rel.status)}"
							>
								{#if relIcon}
									<ProjectIcon id={relIcon} size={14} />
								{/if}
								{rel.status}
							</span>
							<span class="w-20 shrink-0 truncate text-right text-xs text-text-muted">{rel.orgao_sigla ?? ''}</span>
							{#if canEdit}
								<button
									type="button"
									onclick={() => void desvincular(rel.id)}
									disabled={unlinkInFlightId !== null && unlinkInFlightId !== rel.id}
									aria-busy={unlinkInFlightId === rel.id}
									aria-label="Desvincular {rel.titulo}"
									title="Desvincular"
									class="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-text-muted transition-colors duration-fast hover:bg-surface-muted hover:text-danger disabled:cursor-not-allowed disabled:opacity-60 focus:outline-none focus-visible:ring-2 focus-visible:ring-danger"
								>
									{#if unlinkInFlightId === rel.id}
										<span
											class="h-3 w-3 animate-spin rounded-full border-2 border-border-subtle border-t-primary-600"
											aria-hidden="true"
										></span>
									{:else}
										<AppIcon id="exclusao" size={16} />
									{/if}
								</button>
							{/if}
						</li>
					{/each}
				</ul>
			</section>
		{/if}
	</div>
</div>

<style>
	:global([data-theme='dark']) .related-drawer-panel {
		box-shadow: -18px 0 44px rgba(0, 0, 0, 0.55);
	}
</style>
