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
		icon: 'folder' | 'list-check' | 'clipboard' | 'calendar';
	}> = [
		{ key: 'projects', label: 'Projetos', tone: 'primary', icon: 'folder' },
		{ key: 'stages', label: 'Etapas', tone: 'warning', icon: 'list-check' },
		{ key: 'tasks', label: 'Tarefas', tone: 'success', icon: 'clipboard' },
		{ key: 'events', label: 'Eventos', tone: 'info', icon: 'calendar' }
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

<section aria-labelledby="busca-title" class="flex flex-col gap-4">
	<!-- Cabecalho "raised": card com titulo, subtitulo e form (search-results-header). -->
	<header
		class="rounded-lg border border-border-subtle bg-surface px-5 py-5 shadow-md"
	>
		<h1
			id="busca-title"
			class="m-0 flex items-center gap-2 font-heading text-xl font-bold text-text-primary"
		>
			<svg
				aria-hidden="true"
				class="h-5 w-5 text-primary-600"
				viewBox="0 0 512 512"
				fill="currentColor"
			>
				<path
					d="M416 208c0 45.9-14.9 88.3-40 122.7L502.6 457.4c12.5 12.5 12.5 32.8 0 45.3s-32.8 12.5-45.3 0L330.7 376c-34.4 25.2-76.8 40-122.7 40C93.1 416 0 322.9 0 208S93.1 0 208 0S416 93.1 416 208zM208 352a144 144 0 1 0 0-288 144 144 0 1 0 0 288z"
				/>
			</svg>
			Busca Global
		</h1>

		<!-- aria-live com a contagem; substitui o subtitulo estatico do original. -->
		<div role="status" aria-live="polite" class="min-h-[1.25rem]">
			{#if searchState === 'ready' && data && data.counts.total > 0}
				<p class="mt-2 mb-0 text-md text-text-secondary">
					{data.counts.total} referência{data.counts.total === 1 ? '' : 's'} para
					"<strong class="text-text-primary">{shownTerm}</strong>".
				</p>
			{:else if searchState === 'loading'}
				<p class="mt-2 mb-0 text-md text-text-secondary">Buscando…</p>
			{:else}
				<p class="mt-2 mb-0 text-md text-text-secondary">
					Busque por projetos, etapas, tarefas e eventos.
				</p>
			{/if}
		</div>

		<form
			role="search"
			class="mt-4 flex flex-wrap gap-3"
			onsubmit={onSubmit}
		>
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
				class="min-w-0 flex-[1_1_360px] rounded-lg border border-border-subtle bg-surface-muted px-4 py-2 text-base text-text-primary placeholder:text-text-muted transition-shadow duration-fast focus:border-primary-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/30"
			/>
			<button
				type="submit"
				class="rounded-lg border-none bg-primary-600 px-4 py-2 text-base font-semibold text-white transition-colors duration-fast hover:bg-primary-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
			>
				Buscar
			</button>
		</form>
		<p id="busca-hint" class="sr-only">Digite ao menos dois caracteres para iniciar a busca.</p>
	</header>

	{#if searchState === 'idle'}
		<div
			class="rounded-lg border border-dashed border-border-subtle bg-surface-muted px-5 py-4 text-text-secondary"
		>
			Digite um termo para iniciar a busca.
		</div>
	{:else if searchState === 'loading'}
		<div
			class="rounded-lg border border-dashed border-border-subtle bg-surface-muted px-5 py-4 text-text-secondary"
		>
			Buscando…
		</div>
	{:else if searchState === 'error'}
		<LoadErrorState message={errorMessage} onRetry={retry} />
	{:else if data}
		{#if data.counts.total === 0}
			<div
				class="rounded-lg border border-dashed border-border-subtle bg-surface-muted px-5 py-4 text-text-secondary"
			>
				Nenhuma referência encontrada para "<strong class="text-text-primary">{shownTerm}</strong>".
			</div>
		{:else}
			<!-- Grade de secoes (search-results-grid): coluna unica, gap 0.85rem. -->
			<div class="grid grid-cols-1 gap-3">
				{#each SECTIONS as section (section.key)}
					{@const items = sectionItems(section.key)}
					{#if items.length > 0}
						<section
							aria-labelledby={`busca-sec-${section.key}`}
							class="overflow-hidden rounded-lg border border-border-subtle bg-surface"
						>
							<!-- Cabecalho da secao: icone + titulo a esquerda, pilula de contagem a direita. -->
							<div
								class="flex items-center justify-between gap-3 border-b border-border-subtle bg-surface-muted px-4 py-3"
							>
								<h2
									id={`busca-sec-${section.key}`}
									class="m-0 flex items-center gap-2 text-base font-bold text-text-primary"
								>
									<svg
										aria-hidden="true"
										class="h-4 w-4 text-text-muted"
										viewBox="0 0 512 512"
										fill="currentColor"
									>
										{#if section.icon === 'folder'}
											<path
												d="M88.7 223.8L0 375.8V96C0 60.7 28.7 32 64 32H181.5c17 0 33.3 6.7 45.3 18.7l26.5 26.5c12 12 28.3 18.7 45.3 18.7H416c35.3 0 64 28.7 64 64v32H144c-22.8 0-43.8 12.1-55.3 31.8zm27.6 16.1C122.1 230 132.6 224 144 224H544c11.5 0 22 6.1 27.7 16.1s5.7 22.2-.1 32.1l-112 192C453.9 474 443.4 480 432 480H32c-11.5 0-22-6.1-27.7-16.1s-5.7-22.2 .1-32.1l112-192z"
											/>
										{:else if section.icon === 'list-check'}
											<path
												d="M152.1 38.2c9.9 8.9 10.7 24 1.8 33.9l-72 80c-4.4 4.9-10.6 7.8-17.2 7.9s-12.9-2.4-17.6-7L7 113C-2.3 103.6-2.3 88.4 7 79s24.6-9.4 33.9 0l22.1 22.1 55.1-61.2c8.9-9.9 24-10.7 33.9-1.8zm0 160c9.9 8.9 10.7 24 1.8 33.9l-72 80c-4.4 4.9-10.6 7.8-17.2 7.9s-12.9-2.4-17.6-7L7 273c-9.4-9.4-9.4-24.6 0-33.9s24.6-9.4 33.9 0l22.1 22.1 55.1-61.2c8.9-9.9 24-10.7 33.9-1.8zM224 96c0-17.7 14.3-32 32-32H480c17.7 0 32 14.3 32 32s-14.3 32-32 32H256c-17.7 0-32-14.3-32-32zm0 160c0-17.7 14.3-32 32-32H480c17.7 0 32 14.3 32 32s-14.3 32-32 32H256c-17.7 0-32-14.3-32-32zM160 416c0-17.7 14.3-32 32-32H480c17.7 0 32 14.3 32 32s-14.3 32-32 32H192c-17.7 0-32-14.3-32-32zM48 368a48 48 0 1 1 0 96 48 48 0 1 1 0-96z"
											/>
										{:else if section.icon === 'clipboard'}
											<path
												d="M280 64h40c35.3 0 64 28.7 64 64V448c0 35.3-28.7 64-64 64H64c-35.3 0-64-28.7-64-64V128C0 92.7 28.7 64 64 64h40 9.6C121 27.5 153.3 0 192 0s71 27.5 78.4 64H280zM64 112c-8.8 0-16 7.2-16 16V448c0 8.8 7.2 16 16 16H320c8.8 0 16-7.2 16-16V128c0-8.8-7.2-16-16-16H304v24c0 13.3-10.7 24-24 24H192 104c-13.3 0-24-10.7-24-24V112H64zm128-8a24 24 0 1 0 0-48 24 24 0 1 0 0 48z"
											/>
										{:else if section.icon === 'calendar'}
											<path
												d="M128 0c17.7 0 32 14.3 32 32V64H288V32c0-17.7 14.3-32 32-32s32 14.3 32 32V64h48c26.5 0 48 21.5 48 48v48H0V112C0 85.5 21.5 64 48 64H96V32c0-17.7 14.3-32 32-32zM0 192H448V464c0 26.5-21.5 48-48 48H48c-26.5 0-48-21.5-48-48V192z"
											/>
										{/if}
									</svg>
									{section.label}
								</h2>
								<span
									class="rounded-full bg-primary-100 px-2 py-0.5 text-2xs font-bold text-primary-700"
								>
									{items.length}
								</span>
							</div>

							<ul class="flex flex-col" aria-labelledby={`busca-sec-${section.key}`}>
								{#each items as item (`${item.type}-${item.url}`)}
									<li>
										<a
											href={item.url}
											class="group mx-1.5 my-1 flex items-start justify-between gap-3 rounded-md border border-border-subtle px-3 py-3 text-text-primary no-underline transition-[background-color,border-color] duration-fast hover:border-border-strong hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
										>
											<span class="flex min-w-0 flex-1 flex-col gap-1">
												<span class="flex items-center gap-1.5">
													<Badge tone={section.tone}>{item.type_label}</Badge>
													<span class="truncate font-semibold text-text-primary">
														{item.title}
													</span>
												</span>
												{#if item.subtitle}
													<span class="truncate text-sm text-text-secondary">
														{item.subtitle}
													</span>
												{/if}
												{#if item.meta}
													<span class="truncate text-sm text-text-secondary">{item.meta}</span>
												{/if}
												{#if item.match_field === 'comentarios' && (item.match_label || item.match_excerpt)}
													<span class="mt-1 flex min-w-0 flex-col gap-0.5">
														{#if item.match_label}
															<span
																class="inline-flex w-fit items-center rounded-full bg-surface-muted px-2 py-0.5 text-2xs font-bold text-text-secondary"
															>
																Encontrado em: {item.match_label}
															</span>
														{/if}
														{#if item.match_excerpt}
															<span class="truncate text-sm text-text-secondary">{item.match_excerpt}</span>
														{/if}
													</span>
												{/if}
											</span>
											<svg
												aria-hidden="true"
												class="mt-0.5 h-3.5 w-3.5 shrink-0 text-text-muted"
												viewBox="0 0 320 512"
												fill="currentColor"
											>
												<path
													d="M310.6 233.4c12.5 12.5 12.5 32.8 0 45.3l-192 192c-12.5 12.5-32.8 12.5-45.3 0s-12.5-32.8 0-45.3L242.7 256 73.4 86.6c-12.5-12.5-12.5-32.8 0-45.3s32.8-12.5 45.3 0l192 192z"
												/>
											</svg>
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
