<script lang="ts">
	/**
	 * Busca global LIVE do topnav — porte 1:1 do widget v4.5
	 * (`static/js/app-shell/global-search.js` + as regras `.app-global-search*`
	 * de `static/css/legacy/00-foundation.css`).
	 *
	 * Reproduz as micro-interacoes do original:
	 *   - Campo com placeholder; foco com anel branco (focus-within).
	 *   - DEBOUNCE de 250ms (igual ao v4.5) apos a digitacao parar.
	 *   - AbortController: cancela a requisicao anterior (resultados em ordem).
	 *   - Termo < 2 chars => dropdown fechado (sem fetch).
	 *   - Dropdown com resultados AGRUPADOS por tipo (Projetos/Etapas/Tarefas/
	 *     Eventos), com contador por grupo, badge de match em comentarios e seta.
	 *   - Navegacao por TECLADO: ArrowUp/Down percorre, Enter abre o selecionado,
	 *     Escape fecha. Hover do mouse sincroniza o item ativo (mousemove).
	 *   - Rodape "Ver tudo" / "Ir para a pagina de busca" -> rota /busca da SPA.
	 *   - Fecha ao clicar fora.
	 *
	 * Escopo de orgao: anexa `?orgao=` (de `orgaoScope`) ao request e ao link de
	 * "ver tudo", exatamente como o legado anexava o hidden input do form.
	 *
	 * As `url` dos resultados sao caminhos ABSOLUTOS da app Flask (url_for em
	 * rotas Jinja) — href direto, sem prefixo `base` da SPA. A pagina /busca,
	 * essa sim, e da SPA (usa `base`).
	 */
	import { onDestroy } from 'svelte';
	import { base } from '$app/paths';
	import { goto } from '$app/navigation';
	import { get } from '$lib/api/client';
	import { orgaoScope } from '$lib/stores/orgaoScope';
	import AppIcon from '$lib/components/AppIcon.svelte';
	import { formatSearchCount } from '$lib/utils/searchCountLabel';
	import StateBanner from '$lib/components/StateBanner.svelte';
	import type { AppIconId } from '$lib/icons/appIcons';
	import type {
		GlobalSearchData,
		SearchMeta,
		SearchResultItem,
		SearchResultsByType
	} from '$lib/types/search';

	/** Termo minimo (mesma regra do backend: < 2 chars nao dispara). */
	const MIN_TERM_LENGTH = 2;
	/** Janela de debounce do campo (ms) — igual ao v4.5. */
	const DEBOUNCE_MS = 250;

	/** Grupos na ordem do v4.5, com rotulo, icone do redesign e classe de cor do titulo. */
	const GROUPS: ReadonlyArray<{
		key: keyof SearchResultsByType;
		label: string;
		icon: AppIconId;
		titleClass: 'type-project' | 'type-stage' | 'type-task' | 'type-event';
	}> = [
		{ key: 'projects', label: 'Projetos', icon: 'projetos', titleClass: 'type-project' },
		{ key: 'stages', label: 'Etapas', icon: 'etapa', titleClass: 'type-stage' },
		{ key: 'tasks', label: 'Tarefas', icon: 'tarefas', titleClass: 'type-task' },
		{ key: 'events', label: 'Eventos', icon: 'calendario', titleClass: 'type-event' }
	];

	let term = $state<string>('');
	/**
	 * "Engajado": o usuario focou/digitou no campo ao menos uma vez nesta sessao
	 * de interacao. Latcha em true no foco/digitacao e so volta a false quando o
	 * dropdown e DESCARTADO (clique-fora/Escape/selecao). NAO desliga no blur —
	 * isso evitaria a corrida blur-vs-clique que fechava o painel antes do clique
	 * num resultado registrar. A ABERTURA real e DERIVADA (engaged + termo valido
	 * + nao-descartado), entao o painel fica MONTADO continuamente e so o conteudo
	 * interno troca (Buscando... -> resultados), sem flicker.
	 */
	let engaged = $state<boolean>(false);
	/**
	 * Descarte explicito: so vira true por Escape, clique-fora ou selecao.
	 * Resetado quando o usuario volta a digitar/focar, para reabrir naturalmente.
	 */
	let dismissed = $state<boolean>(false);
	let stateMessage = $state<string>('Digite ao menos 2 caracteres.');
	/** Distingue falha de rede do texto neutro (vazio/carregando) — ganha role=alert. */
	let searchError = $state<boolean>(false);
	let data = $state<GlobalSearchData | null>(null);
	/** Indice do item selecionado por teclado/hover (-1 = nenhum). */
	let selectedIndex = $state<number>(-1);

	let inputEl = $state<HTMLInputElement | null>(null);
	let rootEl = $state<HTMLDivElement | null>(null);

	let debounceTimer: ReturnType<typeof setTimeout> | null = null;
	let inFlight: AbortController | null = null;

	const hasValidTerm = $derived(term.trim().length >= MIN_TERM_LENGTH);

	/**
	 * UNICA fonte de verdade da visibilidade do dropdown. Nunca abre para termos
	 * curtos (sem fetch, sem piscar) e PERMANECE aberto enquanto engajado + termo
	 * valido — fechando apenas por clique-fora/Escape/selecao (via `dismissed`).
	 */
	const open = $derived(engaged && hasValidTerm && !dismissed);

	/** Lista achatada de itens visiveis, na ordem dos grupos (para o teclado). */
	const flatItems = $derived.by<SearchResultItem[]>(() => {
		if (!data) return [];
		const out: SearchResultItem[] = [];
		for (const group of GROUPS) {
			const items = data.results[group.key];
			if (Array.isArray(items)) out.push(...items);
		}
		return out;
	});

	const hasAnyResult = $derived(flatItems.length > 0);
	const hasMore = $derived(Boolean(data?.meta?.has_more?.any));

	/**
	 * Teto dos contadores (routes/search.py: `meta.counts_capped_at`). O backend
	 * satura o COUNT no teto para nao varrer as tabelas a cada tecla; ausente =
	 * contagem exata. Campos ainda opcionais no contrato — extensao local do tipo.
	 */
	type CappedCountsMeta = {
		counts_capped_at?: number | null;
		counts_capped?: Partial<Record<keyof SearchResultsByType, boolean>>;
	};

	/** Rotulo do contador do grupo: exato, ou "99+" quando saturou no teto. */
	function groupCountLabel(key: keyof SearchResultsByType, fallback: number): string {
		const capMeta = data?.meta as (SearchMeta & CappedCountsMeta) | undefined;
		return formatSearchCount(data?.counts?.[key] ?? fallback, {
			capped: capMeta?.counts_capped?.[key],
			capAt: capMeta?.counts_capped_at
		});
	}

	/** Destino da pagina de busca (rota da SPA), preservando o escopo de orgao. */
	const searchPageHref = $derived.by(() => {
		const trimmed = term.trim();
		const params = new URLSearchParams();
		if ($orgaoScope.selectedId !== null) params.set('orgao', String($orgaoScope.selectedId));
		if (trimmed) params.set('q', trimmed);
		const qs = params.toString();
		return `${base}/busca${qs ? `?${qs}` : ''}`;
	});

	function clearDebounce(): void {
		if (debounceTimer) {
			clearTimeout(debounceTimer);
			debounceTimer = null;
		}
	}

	/** Fecha por intencao do usuario (Escape/clique-fora/selecao). */
	function closeDropdown(): void {
		dismissed = true;
		selectedIndex = -1;
	}

	async function runSearch(query: string): Promise<void> {
		if (inFlight) inFlight.abort();
		inFlight = new AbortController();
		const localController = inFlight;
		stateMessage = 'Buscando...';
		searchError = false;
		// NAO zera `data` aqui: manter os resultados anteriores visiveis enquanto
		// a nova requisicao corre evita o flash de "vazio" entre digitacoes.
		selectedIndex = -1;

		const params = new URLSearchParams({ q: query, limit: '5' });
		if ($orgaoScope.selectedId !== null) {
			params.set('orgao', String($orgaoScope.selectedId));
		}

		try {
			const result = await get<GlobalSearchData>(
				`/api/busca?${params.toString()}`,
				localController.signal
			);
			if (localController.signal.aborted) return;
			data = result;
			if (!hasAnyResult) stateMessage = 'Nenhuma referencia encontrada.';
			selectedIndex = -1;
		} catch (err) {
			if (localController.signal.aborted) return;
			if (err instanceof DOMException && err.name === 'AbortError') return;
			data = null;
			stateMessage = 'Nao foi possivel carregar os resultados.';
			searchError = true;
		} finally {
			if (inFlight === localController) inFlight = null;
		}
	}

	function handleInput(): void {
		const query = term.trim();
		clearDebounce();
		selectedIndex = -1;
		// Digitou de novo => engaja e limpa o descarte para o dropdown reabrir.
		engaged = true;
		dismissed = false;

		// Termo curto: aborta fetch pendente e zera resultados. O dropdown NAO
		// abre/pisca porque `open` e derivado (hasValidTerm == false aqui).
		if (query.length < MIN_TERM_LENGTH) {
			if (inFlight) inFlight.abort();
			data = null;
			stateMessage = 'Digite ao menos 2 caracteres.';
			searchError = false;
			return;
		}

		debounceTimer = setTimeout(() => {
			void runSearch(query);
		}, DEBOUNCE_MS);
	}

	function handleFocus(): void {
		engaged = true;
		dismissed = false;
		const query = term.trim();
		if (query.length < MIN_TERM_LENGTH) return;
		// Ao focar com termo valido sem resultados ainda carregados, busca.
		// (Se ja ha resultados, o dropdown reaparece sozinho via `open`.)
		if (!hasAnyResult && !inFlight) void runSearch(query);
	}

	function moveSelection(step: number): void {
		const total = flatItems.length;
		if (!total) return;
		if (selectedIndex === -1) {
			selectedIndex = step > 0 ? 0 : total - 1;
		} else {
			selectedIndex = (selectedIndex + step + total) % total;
		}
	}

	/** Navega para uma URL absoluta da app Flask (resultado) — recarrega o app. */
	function navigateToResult(url: string): void {
		closeDropdown();
		window.location.assign(url);
	}

	function handleKeydown(event: KeyboardEvent): void {
		if (event.key === 'ArrowDown') {
			event.preventDefault();
			if (open) moveSelection(1);
		} else if (event.key === 'ArrowUp') {
			event.preventDefault();
			if (open) moveSelection(-1);
		} else if (event.key === 'Escape') {
			if (open) {
				event.preventDefault();
				closeDropdown();
			}
		} else if (event.key === 'Enter') {
			event.preventDefault();
			const item = flatItems[selectedIndex];
			if (item) {
				navigateToResult(item.url);
			} else {
				void goto(searchPageHref);
				closeDropdown();
			}
		}
	}

	function handleSubmit(event: SubmitEvent): void {
		event.preventDefault();
		const item = flatItems[selectedIndex];
		if (item) {
			navigateToResult(item.url);
			return;
		}
		void goto(searchPageHref);
		closeDropdown();
	}

	/** Fecha ao clicar fora do widget. */
	function handleWindowPointer(event: MouseEvent): void {
		if (!open) return;
		if (rootEl && !rootEl.contains(event.target as Node)) closeDropdown();
	}

	onDestroy(() => {
		clearDebounce();
		if (inFlight) inFlight.abort();
	});
</script>

<svelte:window onclick={handleWindowPointer} />

<div class="app-global-search" bind:this={rootEl} data-global-search>
	<form
		class="app-global-search-form"
		role="search"
		autocomplete="off"
		onsubmit={handleSubmit}
	>
		<i class="fas fa-search app-global-search-icon" aria-hidden="true"></i>
		<input
			bind:this={inputEl}
			bind:value={term}
			oninput={handleInput}
			onfocus={handleFocus}
			onkeydown={handleKeydown}
			type="search"
			class="app-global-search-input"
			name="q"
			placeholder="Buscar projetos, etapas, tarefas e eventos..."
			autocomplete="off"
			aria-label="Busca global"
			aria-expanded={open}
			aria-controls="appGlobalSearchDropdown"
			role="combobox"
		/>
	</form>

	{#if open}
		<div class="app-global-search-dropdown" id="appGlobalSearchDropdown" role="listbox">
			{#if !data || !hasAnyResult}
				{#if searchError}
					<StateBanner tone="danger" title={stateMessage} />
				{:else}
					<div class="app-global-search-state">{stateMessage}</div>
				{/if}
			{/if}

			{#if data && hasAnyResult}
				<div class="app-global-search-results">
					{#each GROUPS as group (group.key)}
						{@const items = data.results[group.key]}
						{#if items && items.length}
							<div class="app-global-search-group">
								<div class="app-global-search-group-title {group.titleClass}">
									<AppIcon id={group.icon} size={14} />
									<span>{group.label}</span>
									<!-- Total encontrado (pode ser maior que a fatia exibida). -->
									<span class="app-global-search-group-count">
										{groupCountLabel(group.key, items.length)}
									</span>
								</div>
								{#each items as item (item.url)}
									{@const flatIndex = flatItems.indexOf(item)}
									{@const active = flatIndex === selectedIndex}
									<a
										href={item.url}
										class="app-global-search-item"
										class:active
										role="option"
										aria-selected={active}
										onmousemove={() => (selectedIndex = flatIndex)}
										onmousedown={(e) => {
											e.preventDefault();
											navigateToResult(item.url);
										}}
									>
										<div class="app-global-search-item-main">
											<div class="app-global-search-item-head">
												<span class="app-global-search-item-title"
													>{item.display_title || item.title}</span
												>
											</div>
											{#if item.subtitle}
												<div class="app-global-search-item-subtitle">{item.subtitle}</div>
											{/if}
											{#if item.meta}
												<div class="app-global-search-item-meta">{item.meta}</div>
											{/if}
											{#if item.match_field === 'comentarios' && (item.match_label || item.match_excerpt)}
												<div class="app-global-search-item-match">
													{#if item.match_label}
														<span class="app-global-search-match-badge"
															>Encontrado em: {item.match_label}</span
														>
													{/if}
													{#if item.match_excerpt}
														<div class="app-global-search-match-text">{item.match_excerpt}</div>
													{/if}
												</div>
											{/if}
										</div>
										<i class="fas fa-chevron-right app-global-search-item-arrow" aria-hidden="true"
										></i>
									</a>
								{/each}
							</div>
						{/if}
					{/each}
				</div>

				<div class="app-global-search-footer">
					<a
						href={searchPageHref}
						class="app-global-search-footer-link"
						onmousedown={(e) => {
							e.preventDefault();
							void goto(searchPageHref);
							closeDropdown();
						}}
					>
						<span>{hasMore ? 'Ver tudo' : 'Ir para a pagina de busca'}</span>
						<i class="fas fa-arrow-right" aria-hidden="true"></i>
					</a>
				</div>
			{/if}
		</div>
	{/if}
</div>

<style>
	/* O CAMPO mantem cores claras fixas (vive na barra azul do topnav, contraste
	   deliberado); o DROPDOWN usa os tokens semanticos (adapta ao dark). */
	.app-global-search {
		position: relative;
		width: clamp(220px, 24vw, 340px);
		min-width: 210px;
		z-index: 1080;
	}

	.app-global-search-form {
		width: 100%;
		display: flex;
		align-items: center;
		gap: 0.4rem;
		border: 1px solid rgba(255, 255, 255, 0.65);
		border-radius: 8px;
		padding: 0.32rem 0.6rem;
		background: rgba(255, 255, 255, 0.92);
		box-shadow: none;
		transition:
			border-color 0.18s ease,
			background 0.18s ease;
	}

	.app-global-search-form:hover {
		background: #ffffff;
		border-color: #ffffff;
	}

	.app-global-search-form:focus-within {
		border-color: #ffffff;
		background: #ffffff;
		box-shadow: 0 0 0 3px rgba(255, 255, 255, 0.25);
	}

	.app-global-search-icon {
		color: var(--ds-color-text-brand);
		font-size: 0.8125rem;
	}

	.app-global-search-input {
		width: 100%;
		min-width: 0;
		border: none;
		outline: none;
		background: transparent;
		color: #14304d;
		font-size: 0.875rem;
		line-height: 1.25;
	}

	.app-global-search-input::placeholder {
		color: rgba(23, 105, 168, 0.65);
	}

	/* No dark o topnav é carvão: a busca vira inset translúcido em vez de pill branco. */
	:global([data-theme='dark']) .app-global-search-form {
		border-color: var(--ds-color-border-base);
		background: rgba(255, 255, 255, 0.08);
	}
	:global([data-theme='dark']) .app-global-search-form:hover {
		background: rgba(255, 255, 255, 0.12);
		border-color: var(--ds-color-border-strong);
	}
	:global([data-theme='dark']) .app-global-search-form:focus-within {
		background: rgba(255, 255, 255, 0.12);
		border-color: var(--ds-color-border-strong);
		box-shadow: 0 0 0 3px rgba(255, 255, 255, 0.08);
	}
	:global([data-theme='dark']) .app-global-search-icon {
		color: var(--ds-color-text-muted);
	}
	:global([data-theme='dark']) .app-global-search-input {
		color: var(--ds-color-text-primary);
	}
	:global([data-theme='dark']) .app-global-search-input::placeholder {
		color: var(--ds-color-text-muted);
	}

	/* Remove o "x" nativo do type=search para manter o visual do v4.5. */
	.app-global-search-input::-webkit-search-cancel-button {
		-webkit-appearance: none;
		appearance: none;
	}

	.app-global-search-dropdown {
		position: absolute;
		top: calc(100% + 0.48rem);
		right: 0;
		width: min(530px, 76vw);
		min-width: 360px;
		max-height: min(70vh, 560px);
		overflow-y: auto;
		border: 1px solid var(--ds-color-border-base);
		border-radius: 12px;
		background: var(--ds-color-surface-base);
		box-shadow: var(--ds-shadow-lg);
		padding: 0.4rem;
	}

	.app-global-search-state {
		padding: 0.62rem 0.72rem;
		color: var(--ds-color-text-muted);
		font-size: 0.875rem;
	}

	.app-global-search-results {
		display: flex;
		flex-direction: column;
		gap: 0.32rem;
	}

	.app-global-search-group {
		border: 1px solid var(--ds-color-border-base);
		border-radius: 10px;
		overflow: hidden;
		background: var(--ds-color-surface-muted);
	}

	.app-global-search-group-title {
		display: flex;
		align-items: center;
		gap: 0.42rem;
		padding: 0.42rem 0.6rem;
		border-bottom: 1px solid var(--ds-color-border-base);
		font-size: 0.6875rem;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		font-weight: 700;
		color: var(--ds-color-text-muted);
	}

	.app-global-search-group-title.type-project {
		color: var(--ds-color-text-brand);
	}

	.app-global-search-group-title.type-stage {
		color: var(--ds-color-text-warning);
	}

	.app-global-search-group-title.type-task {
		color: var(--ds-color-text-success);
	}

	.app-global-search-group-title.type-event {
		color: var(--ds-color-text-secondary);
	}

	.app-global-search-group-count {
		margin-left: auto;
		border-radius: 999px;
		padding: 0.1rem 0.46rem;
		background: var(--ds-color-wash-neutral);
		color: var(--ds-color-text-brand);
		font-size: 0.6875rem;
	}

	.app-global-search-item {
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		gap: 0.65rem;
		text-decoration: none;
		color: var(--ds-color-text-primary);
		padding: 0.56rem 0.66rem;
		border-top: 1px solid var(--ds-color-border-base);
		transition:
			background 0.16s ease,
			border-color 0.16s ease;
	}

	.app-global-search-item:first-of-type {
		border-top: none;
	}

	.app-global-search-item:hover,
	.app-global-search-item.active {
		background: var(--ds-color-wash-brand);
		border-color: var(--ds-color-border-base);
	}

	.app-global-search-item-main {
		min-width: 0;
		flex: 1;
	}

	.app-global-search-item-head {
		display: flex;
		align-items: center;
		gap: 0.42rem;
		min-width: 0;
	}

	.app-global-search-item-title {
		font-size: 0.8125rem;
		font-weight: 600;
		color: var(--ds-color-text-primary);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.app-global-search-item-subtitle,
	.app-global-search-item-meta {
		font-size: 0.6875rem;
		color: var(--ds-color-text-muted);
		line-height: 1.25;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.app-global-search-item-match {
		margin-top: 0.25rem;
		display: flex;
		flex-direction: column;
		gap: 0.14rem;
		min-width: 0;
	}

	.app-global-search-match-badge {
		display: inline-flex;
		align-items: center;
		width: fit-content;
		border-radius: 999px;
		padding: 0.08rem 0.42rem;
		font-size: 0.6875rem;
		font-weight: 700;
		background: var(--ds-color-surface-muted);
		color: var(--ds-color-text-secondary);
	}

	.app-global-search-match-text {
		font-size: 0.6875rem;
		color: var(--ds-color-text-muted);
		line-height: 1.25;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.app-global-search-item-arrow {
		color: var(--ds-color-text-muted);
		font-size: 0.6875rem;
		margin-top: 0.16rem;
	}

	.app-global-search-footer {
		margin-top: 0.24rem;
		padding-top: 0.2rem;
		border-top: 1px solid var(--ds-color-border-base);
	}

	.app-global-search-footer-link {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.45rem;
		text-decoration: none;
		border: 1px solid var(--ds-color-border-base);
		border-radius: 9px;
		background: var(--ds-color-surface-muted);
		color: var(--ds-color-text-brand);
		font-size: 0.8125rem;
		font-weight: 600;
		line-height: 1.25;
		padding: 0.48rem 0.62rem;
		transition:
			background 0.16s ease,
			border-color 0.16s ease,
			color 0.16s ease;
	}

	.app-global-search-footer-link:hover,
	.app-global-search-footer-link:focus {
		background: var(--ds-color-wash-neutral);
		border-color: var(--ds-color-border-strong);
		color: var(--ds-color-text-brand);
	}

	@media (max-width: 767px) {
		.app-global-search {
			display: none;
		}
	}
</style>
