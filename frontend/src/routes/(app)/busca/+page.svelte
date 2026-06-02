<script lang="ts">
	/**
	 * Tela de Busca Global (FASE 2). Consome `GET /api/busca` via
	 * `$lib/api/search` e renderiza resultados agrupados por tipo
	 * (projeto/etapa/tarefa/evento).
	 *
	 * Padrao espelhado do piloto (dashboard/+page.svelte): estados
	 * loading/erro/vazio, erros 401 ja redirecionados por `client.ts`.
	 *
	 * Especifico da busca:
	 *   - Campo de busca com DEBOUNCE (300ms): so dispara apos a digitacao parar.
	 *   - Cancela a requisicao anterior (AbortController) para evitar respostas
	 *     fora de ordem.
	 *   - Termo < 2 chars => estado "digite para buscar" (sem fetch; o servidor
	 *     tambem devolveria payload vazio).
	 *   - Acessibilidade: input rotulado, contagem anunciada via aria-live,
	 *     resultados em listas com headings por secao, foco visivel em cada link.
	 *
	 * Os `url` dos resultados sao caminhos ABSOLUTOS da app Flask (url_for em
	 * rotas Jinja) — href direto, sem prefixo `base` da SPA.
	 */
	import { onDestroy } from 'svelte';
	import { fetchGlobalSearch } from '$lib/api/search';
	import { ApiClientError } from '$lib/api/client';
	import type {
		GlobalSearchData,
		SearchResultItem,
		SearchResultsByType
	} from '$lib/types/search';
	import Badge from '$lib/components/Badge.svelte';
	import LoadErrorState from '$lib/components/LoadErrorState.svelte';

	/** Estados da busca: ocioso (termo curto), buscando, pronto ou erro. */
	type SearchState = 'idle' | 'loading' | 'ready' | 'error';

	/** Termo minimo (mesma regra do backend: < 2 chars nao dispara busca). */
	const MIN_TERM_LENGTH = 2;
	/** Janela de debounce do campo de busca (ms). */
	const DEBOUNCE_MS = 300;

	/** Secoes na ordem de exibicao, com rotulo e chave em `results`. */
	const SECTIONS: ReadonlyArray<{
		key: keyof SearchResultsByType;
		label: string;
		tone: 'primary' | 'info' | 'warning' | 'success';
	}> = [
		{ key: 'projects', label: 'Projetos', tone: 'primary' },
		{ key: 'stages', label: 'Etapas', tone: 'info' },
		{ key: 'tasks', label: 'Tarefas', tone: 'warning' },
		{ key: 'events', label: 'Eventos', tone: 'success' }
	];

	let term = $state<string>('');
	let searchState = $state<SearchState>('idle');
	let data = $state<GlobalSearchData | null>(null);
	let errorMessage = $state<string>('');

	let debounceTimer: ReturnType<typeof setTimeout> | null = null;
	let inFlight: AbortController | null = null;

	/** Texto exibido para o termo atual (o do payload, ja normalizado). */
	const shownTerm = $derived(data?.query ?? term.trim());

	function cancelInFlight(): void {
		if (inFlight) {
			inFlight.abort();
			inFlight = null;
		}
	}

	async function runSearch(rawTerm: string): Promise<void> {
		const trimmed = rawTerm.trim();
		if (trimmed.length < MIN_TERM_LENGTH) {
			cancelInFlight();
			searchState = 'idle';
			data = null;
			errorMessage = '';
			return;
		}

		cancelInFlight();
		const controller = new AbortController();
		inFlight = controller;
		searchState = 'loading';
		errorMessage = '';

		try {
			const result = await fetchGlobalSearch(trimmed, controller.signal);
			// Ignora respostas de buscas ja superadas por uma mais recente.
			if (controller.signal.aborted) return;
			data = result;
			searchState = 'ready';
		} catch (err) {
			if (controller.signal.aborted) return;
			// 401 ja redirecionou em client.ts; demais erros viram alerta.
			if (err instanceof ApiClientError && err.code === 'unauthenticated') return;
			errorMessage =
				err instanceof Error ? err.message : 'Falha ao realizar a busca.';
			searchState = 'error';
		} finally {
			if (inFlight === controller) inFlight = null;
		}
	}

	/** Agenda a busca com debounce ao digitar. */
	function onInput(): void {
		if (debounceTimer) clearTimeout(debounceTimer);
		const current = term;
		// Resposta imediata ao limpar/encurtar: sai do estado de resultados.
		if (current.trim().length < MIN_TERM_LENGTH) {
			cancelInFlight();
			searchState = 'idle';
			data = null;
			errorMessage = '';
			return;
		}
		debounceTimer = setTimeout(() => void runSearch(current), DEBOUNCE_MS);
	}

	/** Submit do form: dispara a busca imediatamente (sem esperar o debounce). */
	function onSubmit(event: SubmitEvent): void {
		event.preventDefault();
		if (debounceTimer) clearTimeout(debounceTimer);
		void runSearch(term);
	}

	function retry(): void {
		void runSearch(term);
	}

	function sectionItems(key: keyof SearchResultsByType): SearchResultItem[] {
		return data?.results[key] ?? [];
	}

	onDestroy(() => {
		if (debounceTimer) clearTimeout(debounceTimer);
		cancelInFlight();
	});
</script>

<svelte:head>
	<title>Busca Global — ProjetosRJ</title>
</svelte:head>

<section aria-labelledby="busca-title" class="flex flex-col gap-6">
	<h1 id="busca-title" class="font-heading text-2xl font-bold text-text-primary">
		Busca Global
	</h1>

	<form role="search" class="flex flex-col gap-2 sm:flex-row sm:items-center" onsubmit={onSubmit}>
		<label for="busca-input" class="sr-only">Buscar projetos, etapas, tarefas e eventos</label>
		<input
			id="busca-input"
			name="q"
			type="search"
			autocomplete="off"
			bind:value={term}
			oninput={onInput}
			placeholder="Buscar projetos, etapas, tarefas e eventos…"
			aria-describedby="busca-hint"
			class="w-full flex-1 rounded-md border border-border-subtle bg-surface px-4 py-2 text-text-primary placeholder:text-text-muted transition-colors duration-fast focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
		/>
		<button
			type="submit"
			class="rounded-md border border-border-subtle bg-surface px-4 py-2 text-sm font-medium text-text-primary transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
		>
			Buscar
		</button>
	</form>
	<p id="busca-hint" class="sr-only">Digite ao menos dois caracteres para iniciar a busca.</p>

	<!-- Regiao de status: anuncia contagem e estados para leitores de tela. -->
	<div role="status" aria-live="polite" class="sr-only">
		{#if searchState === 'loading'}
			Buscando…
		{:else if searchState === 'ready' && data}
			{data.counts.total} resultado{data.counts.total === 1 ? '' : 's'} para {shownTerm}.
		{/if}
	</div>

	{#if searchState === 'idle'}
		<p class="text-text-secondary">Digite ao menos dois caracteres para iniciar a busca.</p>
	{:else if searchState === 'loading'}
		<p class="text-text-secondary">Buscando…</p>
	{:else if searchState === 'error'}
		<LoadErrorState message={errorMessage} onRetry={retry} />
	{:else if data}
		{#if data.counts.total === 0}
			<p class="text-text-secondary">
				Nenhuma referência encontrada para <strong class="text-text-primary">{shownTerm}</strong>.
			</p>
		{:else}
			<p class="text-sm text-text-muted">
				{data.counts.total} referência{data.counts.total === 1 ? '' : 's'} para
				<strong class="text-text-primary">{shownTerm}</strong>.
			</p>

			<div class="flex flex-col gap-6">
				{#each SECTIONS as section (section.key)}
					{@const items = sectionItems(section.key)}
					{#if items.length > 0}
						<section aria-labelledby={`busca-sec-${section.key}`} class="flex flex-col gap-3">
							<div class="flex items-center gap-2">
								<h2
									id={`busca-sec-${section.key}`}
									class="text-sm font-semibold uppercase tracking-wide text-text-muted"
								>
									{section.label}
								</h2>
								<Badge tone={section.tone}>{items.length}</Badge>
							</div>

							<ul class="flex flex-col gap-2" aria-labelledby={`busca-sec-${section.key}`}>
								{#each items as item (`${item.type}-${item.url}`)}
									<li>
										<a
											href={item.url}
											class="flex items-start gap-3 rounded-md border border-border-subtle bg-surface px-4 py-3 no-underline transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
										>
											<span class="flex min-w-0 flex-1 flex-col gap-1">
												<span class="flex items-center gap-2">
													<Badge tone={section.tone}>{item.type_label}</Badge>
													<span class="truncate font-medium text-text-primary">
														{item.title}
													</span>
												</span>
												{#if item.subtitle}
													<span class="truncate text-sm text-text-secondary">
														{item.subtitle}
													</span>
												{/if}
												{#if item.meta}
													<span class="truncate text-xs text-text-muted">{item.meta}</span>
												{/if}
												{#if item.match_field === 'comentarios' && (item.match_label || item.match_excerpt)}
													<span class="flex flex-col gap-1 rounded-sm bg-surface-muted px-2 py-1">
														{#if item.match_label}
															<span class="text-xs font-medium text-text-secondary">
																Encontrado em: {item.match_label}
															</span>
														{/if}
														{#if item.match_excerpt}
															<span class="text-xs text-text-muted">{item.match_excerpt}</span>
														{/if}
													</span>
												{/if}
											</span>
											<span aria-hidden="true" class="mt-0.5 shrink-0 text-text-muted">›</span>
										</a>
									</li>
								{/each}
							</ul>
						</section>
					{/if}
				{/each}
			</div>
		{/if}
	{/if}
</section>
