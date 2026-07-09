<script lang="ts">
	/**
	 * Tela de Busca Global (FASE 2). Consome `GET /api/busca` (client tipado de
	 * `$lib/api/client`) e renderiza resultados agrupados por tipo
	 * (projeto/etapa/tarefa/evento). Propaga o escopo de orgao do topnav
	 * (`?orgao=<id>`, via `orgaoScopeQuery`) para respeitar o filtro escolhido.
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
	import { page } from '$app/state';
	import { get, ApiClientError } from '$lib/api/client';
	import { orgaoScopeQuery } from '$lib/stores/orgaoScope';
	import type {
		GlobalSearchData,
		SearchResultItem,
		SearchResultsByType
	} from '$lib/types/search';
	import LoadErrorState from '$lib/components/LoadErrorState.svelte';
	import PageHeader from '$lib/components/PageHeader.svelte';
	import CountBadge from '$lib/components/CountBadge.svelte';

	/** Estados da busca: ocioso (termo curto), buscando, pronto ou erro. */
	type SearchState = 'idle' | 'loading' | 'ready' | 'error';

	/** Termo minimo (mesma regra do backend: < 2 chars nao dispara busca). */
	const MIN_TERM_LENGTH = 2;
	/** Janela de debounce do campo de busca (ms). */
	const DEBOUNCE_MS = 300;

	/**
	 * Secoes na ordem de exibicao, com rotulo, chave em `results`, icone Font
	 * Awesome (`fas fa-*`, 1:1 com o template v4.5) e classes de cor da pilula de
	 * tipo — os mesmos tons do Badge compartilhado (Badge.svelte): primary usa
	 * `bg-primary-100`, demais tons `bg-surface-muted` + texto colorido
	 * (dark-safe via tokens).
	 */
	const SECTIONS: ReadonlyArray<{
		key: keyof SearchResultsByType;
		label: string;
		icon: string;
		badgeClass: string;
	}> = [
		{
			key: 'projects',
			label: 'Projetos',
			icon: 'fa-folder-open',
			badgeClass: 'bg-primary-100 text-primary-700'
		},
		{
			key: 'stages',
			label: 'Etapas',
			icon: 'fa-list-check',
			badgeClass: 'bg-surface-muted text-warning'
		},
		{
			key: 'tasks',
			label: 'Tarefas',
			icon: 'fa-clipboard-list',
			badgeClass: 'bg-surface-muted text-success'
		},
		{
			key: 'events',
			label: 'Eventos',
			icon: 'fa-calendar-alt',
			badgeClass: 'bg-surface-muted text-info'
		}
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
			// Propaga o escopo de orgao do topnav (`?orgao=<id>` | ''); o backend
			// sanitiza o filtro para o usuario corrente. Espelha o `?orgao=` que o
			// v4.5 propagava em todas as telas (routes/search.py).
			const params = new URLSearchParams({ q: trimmed });
			const scope = $orgaoScopeQuery;
			const path = scope ? `/api/busca?${params}&${scope}` : `/api/busca?${params}`;
			const result = await get<GlobalSearchData>(path, controller.signal);
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

	// Hidrata o termo a partir do `?q=` da URL e dispara a busca: é assim que o
	// "Ver tudo" do GlobalSearchBox chega aqui (deep-link). Reage a novas
	// navegações para /busca?q=... (mesma rota, sem remontar); digitar não mexe
	// na URL, então não sobrescreve o que o usuário escreve.
	let syncedUrlQuery: string | null = null;
	$effect(() => {
		const urlQuery = (page.url.searchParams.get('q') ?? '').trim();
		if (urlQuery === syncedUrlQuery) return;
		syncedUrlQuery = urlQuery;
		term = urlQuery;
		if (debounceTimer) clearTimeout(debounceTimer);
		if (urlQuery.length >= MIN_TERM_LENGTH) void runSearch(urlQuery);
	});

	// Reexecuta a busca (imediatamente, sem debounce) quando o escopo de orgao
	// do topnav muda, para que os resultados respeitem o novo filtro. Ler
	// `$orgaoScopeQuery` registra a dependencia reativa; so refaz a busca se ja
	// houver um termo valido em tela (>= MIN_TERM_LENGTH).
	$effect(() => {
		void $orgaoScopeQuery;
		if (term.trim().length < MIN_TERM_LENGTH) return;
		if (debounceTimer) clearTimeout(debounceTimer);
		void runSearch(term);
	});

	function sectionItems(key: keyof SearchResultsByType): SearchResultItem[] {
		return data?.results[key] ?? [];
	}

	/** Segmento de meta: par "Rotulo: valor" ou texto simples (label null). */
	type MetaSegment = { label: string | null; value: string };

	/**
	 * Quebra subtitle/meta do backend ("Status: X | Responsavel: Y") em pares
	 * "Rotulo: valor" para renderizar no padrao de meta da referencia
	 * (PendingProjectCard: rotulo muted + valor em strong text-secondary, "·").
	 */
	function toMetaSegments(raw: string): MetaSegment[] {
		return raw
			.split(' | ')
			.map((part) => part.trim())
			.filter((part) => part.length > 0)
			.map((part) => {
				const sep = part.indexOf(': ');
				if (sep <= 0) return { label: null, value: part };
				return { label: part.slice(0, sep), value: part.slice(sep + 2) };
			});
	}

	onDestroy(() => {
		if (debounceTimer) clearTimeout(debounceTimer);
		cancelInFlight();
	});
</script>

<svelte:head>
	<title>Busca Global — ProjetosRJ</title>
</svelte:head>

<!-- Meta no padrao "Rotulo: valor" da referencia (PendingProjectCard.svelte:430). -->
{#snippet metaLine(raw: string)}
	<span class="truncate text-xs text-text-muted">
		{#each toMetaSegments(raw) as segment, i (i)}{i > 0 ? ' · ' : ''}{#if segment.label !== null}{segment.label}:
			<strong class="font-medium text-text-secondary">{segment.value}</strong
			>{:else}{segment.value}{/if}{/each}
	</span>
{/snippet}

<section aria-labelledby="busca-title" class="flex flex-col gap-4">
	<!-- Card único (padrão das telas com filtro): header compacto + linha de busca
		 embutida abaixo de um divisor fino. -->
	<div class="rounded-xl border border-border-subtle bg-surface shadow-sm">
		<PageHeader compact embedded class="min-h-[3.5rem]" labelId="busca-title">
			{#snippet titleContent()}
				<span class="align-middle">Busca Global</span>
				{#if searchState === 'ready' && data && data.counts.total > 0}
					<CountBadge class="ml-2"
						>{data.counts.total} referência{data.counts.total === 1 ? '' : 's'}</CountBadge
					>
				{/if}
			{/snippet}
		</PageHeader>

		<!-- aria-live (sr-only): anuncia a contagem/estado da busca p/ leitores de tela. -->
		<div role="status" aria-live="polite" class="sr-only">
			{#if searchState === 'ready' && data && data.counts.total > 0}
				{data.counts.total} referência{data.counts.total === 1 ? '' : 's'} para "{shownTerm}".
			{:else if searchState === 'loading'}
				Buscando…
			{/if}
		</div>

		<form
			role="search"
			class="flex flex-wrap items-center gap-2 border-t border-border-subtle px-4 py-2.5"
			onsubmit={onSubmit}
		>
			<div class="relative w-full min-w-[14rem] max-w-[26rem]">
				<i
					class="fas fa-search pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-sm text-text-muted"
					aria-hidden="true"
				></i>
				<input
					id="busca-input"
					name="q"
					type="search"
					autocomplete="off"
					bind:value={term}
					oninput={onInput}
					aria-label="Buscar projetos, etapas, tarefas e eventos"
					aria-describedby="busca-hint"
					placeholder="Buscar projetos, etapas, tarefas e eventos…"
					class="h-9 w-full rounded-lg border border-border-subtle bg-surface pl-8 pr-2.5 text-sm text-text-primary placeholder:text-text-muted transition-colors duration-fast focus:border-primary-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
				/>
			</div>
		</form>
		<p id="busca-hint" class="sr-only">Digite ao menos dois caracteres para iniciar a busca.</p>
	</div>

	{#if searchState === 'idle'}
		<!-- Estado inicial no mesmo padrão do vazio das outras telas (Pendentes):
			 quadro suave com ícone emoldurado, título font-heading e texto muted. -->
		<div
			role="status"
			aria-live="polite"
			class="rounded-lg border border-dashed border-border-strong bg-surface-muted/40 px-4 py-8 text-center"
		>
			<div
				class="mx-auto mb-3 inline-flex h-14 w-14 items-center justify-center rounded-xl border border-primary-500/25 bg-primary-100 text-xl text-primary-700"
			>
				<i class="fas fa-magnifying-glass" aria-hidden="true"></i>
			</div>
			<h2 class="m-0 font-heading text-xl font-bold text-text-primary">
				Digite um termo para buscar
			</h2>
			<p class="mb-0 mt-1.5 text-sm text-text-muted">
				Pesquise por projetos, etapas, tarefas e eventos — ao menos dois caracteres.
			</p>
		</div>
	{:else if searchState === 'loading'}
		<p role="status" aria-live="polite" class="text-text-secondary">Buscando…</p>
	{:else if searchState === 'error'}
		<LoadErrorState message={errorMessage} onRetry={retry} />
	{:else if data}
		{#if data.counts.total === 0}
			<div
				role="status"
				aria-live="polite"
				class="rounded-lg border border-dashed border-border-strong bg-surface-muted/40 px-4 py-8 text-center"
			>
				<div
					class="mx-auto mb-3 inline-flex h-14 w-14 items-center justify-center rounded-xl border border-primary-500/25 bg-primary-100 text-xl text-primary-700"
				>
					<i class="fas fa-magnifying-glass" aria-hidden="true"></i>
				</div>
				<h2 class="m-0 font-heading text-xl font-bold text-text-primary">
					Nenhuma referência encontrada
				</h2>
				<p class="mb-0 mt-1.5 text-sm text-text-muted">
					Nada corresponde a “{shownTerm}”. Ajuste o termo e tente novamente.
				</p>
			</div>
		{:else}
			<!-- Seções de resultados no padrão de cards das outras telas (gap 16px). -->
			<div class="flex flex-col gap-4">
				{#each SECTIONS as section (section.key)}
					{@const items = sectionItems(section.key)}
					{#if items.length > 0}
						<section
							aria-labelledby={`busca-sec-${section.key}`}
							class="overflow-hidden rounded-xl border border-border-subtle bg-surface shadow-sm"
						>
							<!-- Cabecalho da secao no padrao do Card compartilhado. -->
							<div
								class="flex items-center justify-between gap-3 border-b border-border-subtle px-5 py-4"
							>
								<h2
									id={`busca-sec-${section.key}`}
									class="m-0 flex items-center gap-2 font-heading text-lg font-semibold text-text-primary"
								>
									<i class="fas {section.icon} text-sm text-text-muted" aria-hidden="true"></i>
									{section.label}
								</h2>
								<CountBadge>{items.length}</CountBadge>
							</div>

							<ul class="flex flex-col" aria-labelledby={`busca-sec-${section.key}`}>
								{#each items as item (`${item.type}-${item.url}`)}
									<li>
										<a
											href={item.url}
											class="group mx-1.5 my-1 flex items-start justify-between gap-3 rounded-md border border-border-subtle px-3 py-3 text-text-primary no-underline transition-[background-color,border-color] duration-fast hover:border-border-strong hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
										>
											<span class="flex min-w-0 flex-1 flex-col gap-1">
												<span class="flex min-w-0 items-center gap-1.5">
													<span
														class="inline-flex shrink-0 items-center gap-1 rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-wide {section.badgeClass}"
													>
														{item.type_label}
													</span>
													<span
														class="truncate text-base font-medium text-primary-700 group-hover:underline"
													>
														{item.title}
													</span>
												</span>
												{#if item.subtitle}
													{@render metaLine(item.subtitle)}
												{/if}
												{#if item.meta}
													{@render metaLine(item.meta)}
												{/if}
												{#if item.match_field === 'comentarios' && (item.match_label || item.match_excerpt)}
													<span class="mt-1 flex min-w-0 flex-col gap-0.5">
														{#if item.match_label}
															<span
																class="inline-flex w-fit items-center rounded-full bg-surface-muted px-3 py-1 text-xs font-semibold text-text-secondary"
															>
																Encontrado em: {item.match_label}
															</span>
														{/if}
														{#if item.match_excerpt}
															<span class="truncate text-xs text-text-muted">{item.match_excerpt}</span>
														{/if}
													</span>
												{/if}
											</span>
											<i
												class="fas fa-chevron-right mt-0.5 shrink-0 text-sm text-text-muted"
												aria-hidden="true"
											></i>
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
