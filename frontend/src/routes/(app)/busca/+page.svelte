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
	 *   - Modo PAGINADO (`?page=`): 40 itens/pagina sobre a lista plana
	 *     projetos -> etapas -> tarefas -> eventos, com filtros de tipo
	 *     combinaveis (`?types=`) e URL sync (q+types+page) via replaceState.
	 *   - Acessibilidade: input rotulado, contagem anunciada via aria-live,
	 *     resultados em listas com headings por secao, foco visivel em cada link.
	 *
	 * Os `url` dos resultados sao caminhos ABSOLUTOS da app Flask (url_for em
	 * rotas Jinja) — href direto, sem prefixo `base` da SPA.
	 */
	import { onDestroy } from 'svelte';
	import { page as pageState } from '$app/state';
	import { base } from '$app/paths';
	import { replaceState } from '$app/navigation';
	import { ApiClientError } from '$lib/api/client';
	import { fetchGlobalSearch, peekGlobalSearch, type GlobalSearchParams } from '$lib/api/search';
	import { orgaoScopeQuery } from '$lib/stores/orgaoScope';
	import { flash } from '$lib/stores/flash';
	import type {
		GlobalSearchData,
		SearchResultItem,
		SearchResultsByType,
		SearchTypeKey
	} from '$lib/types/search';
	import LoadErrorState from '$lib/components/LoadErrorState.svelte';
	import AppIcon from '$lib/components/AppIcon.svelte';
	import type { AppIconId } from '$lib/icons/appIcons';
	import PageHeader from '$lib/components/PageHeader.svelte';
	import CountBadge from '$lib/components/CountBadge.svelte';
	import PaginationBar from '$lib/components/PaginationBar.svelte';
	import BuscaSkeleton from '$lib/components/skeletons/BuscaSkeleton.svelte';

	/** Estados da busca: ocioso (termo curto), buscando, pronto ou erro. */
	type SearchState = 'idle' | 'loading' | 'ready' | 'error';

	/** Termo minimo (mesma regra do backend: < 2 chars nao dispara busca). */
	const MIN_TERM_LENGTH = 2;
	const DEBOUNCE_MS = 300;
	/** Itens por pagina do modo paginado (contrato do backend). */
	const PER_PAGE = 40;
	/** Ordem canonica dos tipos (espelha SEARCH_TYPE_KEYS do backend). */
	const ALL_TYPES: readonly SearchTypeKey[] = ['projects', 'stages', 'tasks', 'events'];

	/** Secoes na ordem de exibicao: rotulo, chave em `results` e AppIcon do tipo. */
	const SECTIONS: ReadonlyArray<{
		key: keyof SearchResultsByType;
		label: string;
		icon: AppIconId;
	}> = [
		{ key: 'projects', label: 'Projetos', icon: 'projetos' },
		{ key: 'stages', label: 'Etapas', icon: 'etapa' },
		{ key: 'tasks', label: 'Tarefas', icon: 'tarefas' },
		{ key: 'events', label: 'Eventos', icon: 'calendario' }
	];

	// SWR: hidrata o estado inicial a partir da URL (deep-link) + peek do cache
	// de modulo (mesma chave que fetchGlobalSearch grava) — evita o flash de
	// "Digite um termo"/skeleton quando a revisita ja tem dado bom.
	const initialTerm = (pageState.url.searchParams.get('q') ?? '').trim();
	const initialTypes = parseTypesParam(pageState.url.searchParams.get('types'));
	const initialPage = parsePageParam(pageState.url.searchParams.get('page'));
	const initialData =
		initialTerm.length >= MIN_TERM_LENGTH
			? peekGlobalSearch({
					q: initialTerm,
					page: initialPage,
					perPage: PER_PAGE,
					types: initialTypes.length < ALL_TYPES.length ? initialTypes : undefined,
					orgaoQuery: $orgaoScopeQuery
				})
			: null;

	let term = $state<string>(initialTerm);
	let searchState = $state<SearchState>(
		initialTerm.length < MIN_TERM_LENGTH ? 'idle' : initialData ? 'ready' : 'loading'
	);
	let data = $state<GlobalSearchData | null>(initialData);
	let errorMessage = $state<string>('');
	let selectedTypes = $state<SearchTypeKey[]>(initialTypes);
	let page = $state(initialPage);

	let debounceTimer: ReturnType<typeof setTimeout> | null = null;
	let inFlight: AbortController | null = null;

	let typeMenuOpen = $state(false);
	let typeMenuEl = $state<HTMLDivElement | null>(null);
	let typeTriggerEl = $state<HTMLButtonElement | null>(null);

	const typeTriggerLabel = $derived.by<string>(() => {
		if (selectedTypes.length === ALL_TYPES.length) return 'Todos os tipos';
		if (selectedTypes.length === 1) {
			return SECTIONS.find((s) => s.key === selectedTypes[0])?.label ?? 'Tipos';
		}
		return `${selectedTypes.length} tipos`;
	});

	function closeTypeMenu(): void {
		if (!typeMenuOpen) return;
		typeMenuOpen = false;
		typeTriggerEl?.focus({ preventScroll: true });
	}

	// Fecha o menu de tipos ao clicar fora ou com Esc (captura, como no SelectMenu).
	$effect(() => {
		if (!typeMenuOpen) return;
		const onPointerDown = (event: PointerEvent): void => {
			if (typeMenuEl && !typeMenuEl.contains(event.target as Node)) typeMenuOpen = false;
		};
		const onKeydown = (event: KeyboardEvent): void => {
			if (event.key !== 'Escape') return;
			event.preventDefault();
			event.stopPropagation();
			closeTypeMenu();
		};
		window.addEventListener('pointerdown', onPointerDown, true);
		window.addEventListener('keydown', onKeydown, true);
		return () => {
			window.removeEventListener('pointerdown', onPointerDown, true);
			window.removeEventListener('keydown', onKeydown, true);
		};
	});

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
		errorMessage = '';

		// Propaga o escopo de orgao do topnav (`?orgao=<id>` | ''); o backend
		// sanitiza o filtro para o usuario corrente. `page` presente = modo
		// paginado (40/pagina; o dropdown do topo segue com limit=5).
		const params: GlobalSearchParams = {
			q: trimmed,
			page,
			perPage: PER_PAGE,
			types: selectedTypes.length < ALL_TYPES.length ? selectedTypes : undefined,
			orgaoQuery: $orgaoScopeQuery
		};

		// SWR: com cache da mesma chave mostra o dado antigo ja (sem skeleton) e
		// revalida em silencio abaixo; sem cache, skeleton.
		const cached = peekGlobalSearch(params);
		if (cached) {
			data = cached;
			searchState = 'ready';
		} else {
			searchState = 'loading';
		}

		try {
			const result = await fetchGlobalSearch(params, controller.signal);
			// Ignora respostas de buscas ja superadas por uma mais recente.
			if (controller.signal.aborted) return;
			data = result;
			// Reconcilia o clamp do servidor (page > total_pages).
			page = result.meta.pagination?.page ?? 1;
			searchState = 'ready';
			syncUrlFromSearch();
		} catch (err) {
			if (controller.signal.aborted) return;
			// 401 ja redirecionou em client.ts; demais erros viram alerta.
			if (err instanceof ApiClientError && err.code === 'unauthenticated') return;
			const message = err instanceof Error ? err.message : 'Falha ao realizar a busca.';
			// Revalidacao falhou com dado stale na tela: mantem o dado e avisa via
			// flash, em vez de trocar a lista inteira pelo painel de erro.
			if (data) {
				flash.danger(message);
				return;
			}
			errorMessage = message;
			searchState = 'error';
		} finally {
			if (inFlight === controller) inFlight = null;
		}
	}

	/** Agenda a busca com debounce ao digitar (termo novo => volta a pagina 1). */
	function onInput(): void {
		if (debounceTimer) clearTimeout(debounceTimer);
		page = 1;
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
		page = 1;
		void runSearch(term);
	}

	function retry(): void {
		void runSearch(term);
	}

	/** Liga/desliga um tipo; nunca permite zerar a selecao (ultimo chip e no-op). */
	function toggleType(key: SearchTypeKey): void {
		const active = selectedTypes.includes(key);
		if (active && selectedTypes.length === 1) return;
		selectedTypes = active
			? selectedTypes.filter((t) => t !== key)
			: ALL_TYPES.filter((t) => t === key || selectedTypes.includes(t));
		page = 1;
		if (term.trim().length >= MIN_TERM_LENGTH) void runSearch(term);
	}

	function goToPage(target: number): void {
		const tp = data?.meta.pagination?.total_pages ?? 1;
		if (target < 1 || target > tp || target === page) return;
		page = target;
		void runSearch(term);
	}

	/** csv -> tipos validos em ordem canonica; ausente/vazio/invalido => todos. */
	function parseTypesParam(raw: string | null): SearchTypeKey[] {
		if (!raw) return [...ALL_TYPES];
		const tokens = raw.split(',').map((token) => token.trim());
		const valid = ALL_TYPES.filter((key) => tokens.includes(key));
		return valid.length > 0 ? valid : [...ALL_TYPES];
	}

	function parsePageParam(raw: string | null): number {
		const parsed = Number.parseInt(raw ?? '', 10);
		return Number.isFinite(parsed) && parsed > 0 ? parsed : 1;
	}

	function urlStateKey(query: string, types: readonly SearchTypeKey[], pageNum: number): string {
		return `${query}|${types.join(',')}|${pageNum}`;
	}

	/** Reflete q+types+page na URL (replaceState) para reload/voltar/deep-link. */
	function syncUrlFromSearch(): void {
		const trimmed = term.trim();
		const params = new URLSearchParams();
		if (trimmed.length >= MIN_TERM_LENGTH) params.set('q', trimmed);
		if (selectedTypes.length < ALL_TYPES.length) params.set('types', selectedTypes.join(','));
		if (page > 1) params.set('page', String(page));
		// Atualiza a chave de dedupe ANTES do replaceState para o $effect de
		// hidratacao nao re-disparar o fetch.
		syncedUrlQuery = urlStateKey(trimmed, selectedTypes, page);
		const qs = params.toString();
		const target = `${base}/busca${qs ? `?${qs}` : ''}`;
		try {
			replaceState(target, {});
		} catch {
			// replaceState exige contexto de roteamento; ignora fora dele (SSR/teste).
		}
	}

	// Hidrata termo/tipos/pagina a partir da URL e dispara a busca: é assim que
	// o "Ver tudo" do GlobalSearchBox chega aqui (deep-link). A chave de dedupe
	// composta (q|types|page) evita re-fetch quando o proprio syncUrlFromSearch
	// reescreve a URL; digitar não mexe na URL, então não sobrescreve o input.
	let syncedUrlQuery: string | null = null;
	$effect(() => {
		const urlQuery = (pageState.url.searchParams.get('q') ?? '').trim();
		const urlTypes = parseTypesParam(pageState.url.searchParams.get('types'));
		const urlPage = parsePageParam(pageState.url.searchParams.get('page'));
		const key = urlStateKey(urlQuery, urlTypes, urlPage);
		if (key === syncedUrlQuery) return;
		syncedUrlQuery = key;
		term = urlQuery;
		selectedTypes = urlTypes;
		page = urlPage;
		if (debounceTimer) clearTimeout(debounceTimer);
		if (urlQuery.length >= MIN_TERM_LENGTH) void runSearch(urlQuery);
	});

	// Reexecuta a busca (imediatamente, sem debounce, voltando a pagina 1)
	// quando o escopo de orgao do topnav MUDA de fato — o guard com o valor
	// anterior evita que a primeira execucao (montagem) clobbe o `page` vindo
	// de deep-link e que mudancas de `term` re-disparem este efeito.
	let lastOrgaoScope: string | null = null;
	$effect(() => {
		const scope = $orgaoScopeQuery;
		if (lastOrgaoScope === scope) return;
		const isFirstRun = lastOrgaoScope === null;
		lastOrgaoScope = scope;
		if (isFirstRun) return;
		if (term.trim().length < MIN_TERM_LENGTH) return;
		if (debounceTimer) clearTimeout(debounceTimer);
		page = 1;
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
	<title>ProjetosRJ — Busca Global</title>
</svelte:head>

<!-- Meta no padrao "Rotulo: valor" da referencia (PendingProjectCard.svelte:430). -->
{#snippet metaLine(raw: string)}
	<span class="truncate text-xs text-text-muted">
		{#each toMetaSegments(raw) as segment, i (i)}{i > 0 ? ' · ' : ''}{#if segment.label !== null}{segment.label}:
			<strong class="font-medium text-text-secondary">{segment.value}</strong
			>{:else}{segment.value}{/if}{/each}
	</span>
{/snippet}

<!-- Quadro de vazio padrão (Projetos/Pendentes/Coleções): tracejado + ícone emoldurado. -->
{#snippet emptyPanel(titulo: string, texto: string)}
	<div
		role="status"
		aria-live="polite"
		class="rounded-lg border border-dashed border-border-strong bg-surface-muted px-4 py-8 text-center"
	>
		<div
			class="mx-auto mb-3 inline-flex h-14 w-14 items-center justify-center rounded-xl border border-brand-soft bg-wash-neutral text-brand"
		>
			<AppIcon id="busca" size={28} />
		</div>
		<h2 class="m-0 font-heading text-xl font-bold text-text-primary">{titulo}</h2>
		<p class="mb-0 mt-1.5 text-sm text-text-muted">{texto}</p>
	</div>
{/snippet}

<section aria-labelledby="busca-title" class="flex flex-col gap-4">
	<!-- Card único (padrão das telas com filtro): header compacto + linha de busca
		 embutida abaixo de um divisor fino. -->
	<div class="rounded-xl border border-border-subtle bg-surface shadow-sm">
		<PageHeader compact embedded class="min-h-[3.5rem]" labelId="busca-title">
			{#snippet titleContent()}
				<span class="align-middle">Busca Global</span>
				{#if data && data.counts.total > 0}
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
					class="h-9 w-full rounded-lg border border-border-subtle bg-surface pl-8 pr-2.5 text-md text-text-primary placeholder:text-text-muted transition-colors duration-fast focus:border-brand focus:outline-none"
				/>
			</div>
			<div bind:this={typeMenuEl} class="relative">
				<button
					bind:this={typeTriggerEl}
					type="button"
					aria-haspopup="true"
					aria-expanded={typeMenuOpen}
					aria-controls="busca-types-menu"
					onclick={() => (typeMenuOpen = !typeMenuOpen)}
					class="flex h-[var(--control-h-md)] min-w-[11rem] items-center justify-between gap-2 rounded-lg border border-border-subtle bg-surface px-3 text-left text-md transition-colors duration-fast hover:border-brand focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
				>
					<span class="truncate text-text-primary">{typeTriggerLabel}</span>
					<svg
						width="10"
						height="6"
						viewBox="0 0 10 6"
						class="shrink-0 text-text-muted transition-transform duration-fast"
						style:transform={typeMenuOpen ? 'rotate(180deg)' : 'none'}
						aria-hidden="true"
					>
						<path
							d="M1 1 L5 5 L9 1"
							fill="none"
							stroke="currentColor"
							stroke-width="1.6"
							stroke-linecap="round"
							stroke-linejoin="round"
						/>
					</svg>
				</button>
				{#if typeMenuOpen}
					<!-- Linhas no padrão do seletor de indicadores (EeggInlineEditor). -->
					<div
						id="busca-types-menu"
						role="group"
						aria-label="Filtrar por tipo de resultado"
						class="absolute left-0 top-[calc(100%+6px)] z-dropdown flex w-60 flex-col gap-1.5 rounded-xl border border-border-subtle bg-surface p-2 shadow-lg"
					>
						{#each SECTIONS as section (section.key)}
							{@const active = selectedTypes.includes(section.key)}
							{@const typeCount = data?.meta.type_counts?.[section.key]}
							{@const locked = active && selectedTypes.length === 1}
							<button
								type="button"
								role="checkbox"
								aria-checked={active}
								disabled={locked}
								onclick={() => toggleType(section.key)}
								class="flex items-center gap-2.5 rounded-sm border px-2.5 py-2 text-left text-md transition-colors duration-fast focus:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed {active
									? 'border-border-strong bg-wash-neutral text-text-primary'
									: 'border-border-subtle text-text-muted hover:bg-surface-muted hover:text-text-primary'}"
							>
								<span
									aria-hidden="true"
									class="inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-sm border transition-colors duration-fast {active
										? 'border-brand bg-brand'
										: 'border-border-strong bg-surface'}"
								>
									{#if active}
										<svg
											viewBox="0 0 24 24"
											class="h-3 w-3 text-on-brand"
											fill="none"
											stroke="currentColor"
											stroke-width="3.5"
											stroke-linecap="round"
											stroke-linejoin="round"
										>
											<path d="M5 13l4 4L19 7" />
										</svg>
									{/if}
								</span>
								<span class="min-w-0 flex-1 truncate">{section.label}</span>
								{#if typeCount !== undefined}
									<span class="tabular-nums text-sm text-text-muted">{typeCount}</span>
								{/if}
							</button>
						{/each}
					</div>
				{/if}
			</div>
		</form>
		<p id="busca-hint" class="sr-only">Digite ao menos dois caracteres para iniciar a busca.</p>
	</div>

	{#if searchState === 'idle'}
		{@render emptyPanel(
			'Digite um termo para buscar',
			'Pesquise por projetos, etapas, tarefas e eventos — ao menos dois caracteres.'
		)}
	{:else if searchState === 'loading' && !data}
		<p role="status" aria-live="polite" class="sr-only">Buscando…</p>
		<BuscaSkeleton />
	{:else if searchState === 'error'}
		<LoadErrorState message={errorMessage} onRetry={retry} />
	{:else if data}
		{#if data.counts.total === 0}
			{@render emptyPanel(
				'Nenhuma referência encontrada',
				`Nada corresponde a “${shownTerm}”. Ajuste o termo e tente novamente.`
			)}
		{:else}
			<!-- Seções de resultados no padrão de cards das outras telas (gap 16px). -->
			<div class="flex flex-col gap-4" aria-busy={searchState === 'loading'}>
				{#each SECTIONS as section (section.key)}
					{@const items = sectionItems(section.key)}
					{#if items.length > 0}
						<section
							aria-labelledby={`busca-sec-${section.key}`}
							class="overflow-hidden rounded-lg border border-border-subtle bg-surface shadow-sm"
						>
							<div class="border-b border-border-subtle px-5 py-4">
								<h2
									id={`busca-sec-${section.key}`}
									class="m-0 flex items-center gap-2 font-heading text-lg font-semibold text-text-primary"
								>
									<AppIcon id={section.icon} size={18} class="text-text-muted" />
									{section.label}
								</h2>
							</div>

							<ul class="m-0 flex list-none flex-col p-0">
								{#each items as item, i (`${item.type}-${item.url}-${i}`)}
									{@const metaRaw = [item.subtitle, item.meta].filter(Boolean).join(' | ')}
									<li class="border-b border-border-subtle last:border-b-0">
										<a
											href={item.url}
											class="flex min-w-0 flex-col gap-1 px-5 py-3 no-underline transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand"
										>
											<span class="truncate text-base font-medium text-brand"
												>{item.display_title || item.title}</span
											>
											{#if metaRaw}
												{@render metaLine(metaRaw)}
											{/if}
											{#if item.match_field === 'comentarios' && item.match_excerpt}
												<span class="flex min-w-0 items-center gap-1.5 text-xs text-text-muted">
													<AppIcon id="comentario" size={12} />
													<span class="truncate">{item.match_excerpt}</span>
												</span>
											{/if}
										</a>
									</li>
								{/each}
							</ul>
						</section>
					{/if}
				{/each}
			</div>
			{#if data.meta.pagination}
				<PaginationBar
					page={data.meta.pagination.page}
					totalPages={data.meta.pagination.total_pages}
					total={data.meta.pagination.total}
					perPage={data.meta.pagination.per_page}
					itemLabel="referências"
					label="Paginação da busca"
					disabled={searchState === 'loading'}
					onChange={goToPage}
				/>
			{/if}
		{/if}
	{/if}
</section>
