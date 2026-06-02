<script lang="ts">
	/**
	 * Tela "Lista de Projetos" (FASE 3). Consome `GET /api/projetos` via
	 * `$lib/api/projects` e renderiza a tabela com os componentes
	 * compartilhado Badge (reusado, não editado). Os filtros
	 * (busca textual com debounce, status, indicador ABEP como combobox,
	 * especial) re-buscam server-side — o `orgao_scope` é aplicado no
	 * backend. Estados loading/erro/vazio anunciados via aria-live.
	 *
	 * Padrão espelhado das telas de leitura (FASE 2):
	 *   - busca/pendentes/+page.svelte (debounce + AbortController, filtros
	 *     server-side, reconciliação dos filtros com o payload).
	 *   - Links base-aware via `$app/paths` (links internos da SPA). O link
	 *     de detalhe do projeto aponta para a rota SPA `${base}/projetos/<id>`
	 *     (Detalhe migrado na Fase 5a).
	 *
	 * Referência visual: templates/projects/list.html.
	 */
	import { onMount, onDestroy } from 'svelte';
	import { base } from '$app/paths';
	import { goto } from '$app/navigation';
	import { fetchProjects, type CreateProjectResult } from '$lib/api/projects';
	import { ApiClientError } from '$lib/api/client';
	import { auth } from '$lib/stores/auth';
	import type { ProjectsListData, ProjectsListQuery } from '$lib/types/projects';
	import type { Project } from '$lib/types/entities';
	import Badge from '$lib/components/Badge.svelte';
	import CriarProjetoModal from '$lib/components/CriarProjetoModal.svelte';
	import LoadErrorState from '$lib/components/LoadErrorState.svelte';
	import { flash } from '$lib/stores/flash';

	type LoadState = 'loading' | 'ready' | 'error';

	/** Janela de debounce da busca textual (ms). */
	const DEBOUNCE_MS = 300;

	/** Status default aplicado pelo backend quando ?status= é omitido. */
	const DEFAULT_STATUS = 'Vigente';

	let loadState = $state<LoadState>('loading');
	let data = $state<ProjectsListData | null>(null);
	let errorMessage = $state<string>('');

	// Filtros controlados pela UI; a busca acontece server-side.
	let search = $state<string>('');
	let status = $state<string>(DEFAULT_STATUS);
	let specialProject = $state<string>('');
	let abepIndicator = $state<string>(''); // value canônico (hidden)
	let abepLabel = $state<string>(''); // texto exibido no combobox
	let page = $state<number>(1);

	// Combobox ABEP: estado de abertura e item destacado por teclado.
	let abepOpen = $state<boolean>(false);
	let abepActiveIndex = $state<number>(-1);

	// Modal de criação de projeto (Quick Create).
	let createModalOpen = $state<boolean>(false);

	/** Gate do botão de exportar CSV: visível somente para admin (paridade Jinja). */
	const isAdmin = $derived($auth.user?.is_admin ?? false);

	/** Opções do GET /api/projetos repassadas ao modal (órgãos/ABEP/etc.). */
	const createOptions = $derived(data?.options ?? null);

	/**
	 * Sucesso da criação: replica o flash success + redirect do Jinja.
	 * Mostra o toast verde (window.showFlash) e navega client-side para o
	 * detalhe do projeto criado. Converte o `redirect_to` do backend
	 * ('/projetos/<id>') em rota SPA base-aware.
	 */
	function onProjectCreated(result: CreateProjectResult): void {
		createModalOpen = false;
		flash.success(result.message);
		const target = result.redirect_to.startsWith('/')
			? `${base}${result.redirect_to}`
			: result.redirect_to;
		void goto(target);
	}
	// Guarda o rótulo do item selecionado para não filtrar a lista logo após
	// escolher uma opção (o input passa a exibir o rótulo completo).
	let lastSelectedAbepLabel = $state<string>('');

	let debounceTimer: ReturnType<typeof setTimeout> | null = null;
	let inFlight: AbortController | null = null;

	/** Opções de status disponíveis (do payload; com fallback canônico). */
	const statusOptions = $derived(data?.options.statuses ?? ['Vigente', 'Finalizado']);
	const specialOptions = $derived(data?.options.special_projects_options ?? []);
	const abepOptions = $derived(data?.options.abep_indicadores_options ?? []);
	const pagination = $derived(data?.pagination ?? null);
	const totalProjects = $derived(data?.pagination.total ?? 0);
	const hasActiveFilters = $derived(
		search.trim() !== '' ||
			status !== DEFAULT_STATUS ||
			specialProject !== '' ||
			abepIndicator !== ''
	);

	/** Subconjunto de indicadores ABEP que casa com o texto digitado. */
	const abepVisible = $derived.by(() => {
		const term = abepLabel.trim().toLowerCase();
		if (!term || term === lastSelectedAbepLabel.toLowerCase()) return abepOptions;
		return abepOptions.filter(
			(o) =>
				o.label.toLowerCase().includes(term) || o.value.toLowerCase().includes(term)
		);
	});

	async function load(): Promise<void> {
		loadState = data ? loadState : 'loading';
		errorMessage = '';
		inFlight?.abort();
		const controller = new AbortController();
		inFlight = controller;

		const query: ProjectsListQuery = {
			status,
			special_project: specialProject || undefined,
			abep_indicator: abepIndicator || undefined,
			q: search.trim() || undefined,
			page
		};
		try {
			const next = await fetchProjects(query, controller.signal);
			if (controller.signal.aborted) return;
			data = next;
			// Reconcilia os filtros com o que o backend efetivamente aplicou.
			status = next.filters.status ?? DEFAULT_STATUS;
			specialProject = next.filters.special_project ?? '';
			abepIndicator = next.filters.abep_indicator ?? '';
			page = next.pagination.page;
			syncAbepLabelFromValue();
			loadState = 'ready';
		} catch (err) {
			if (controller.signal.aborted) return;
			// 401 já redirecionou em client.ts; aqui tratamos os demais erros.
			if (err instanceof ApiClientError && err.code === 'unauthenticated') return;
			errorMessage =
				err instanceof Error ? err.message : 'Falha ao carregar os projetos.';
			loadState = 'error';
		}
	}

	/** Casa o `abep_indicator` (value) com o rótulo exibido no combobox. */
	function syncAbepLabelFromValue(): void {
		if (!abepIndicator) {
			abepLabel = '';
			lastSelectedAbepLabel = '';
			return;
		}
		const match = (data?.options.abep_indicadores_options ?? []).find(
			(o) => o.value === abepIndicator
		);
		abepLabel = match?.label ?? abepLabel;
		lastSelectedAbepLabel = abepLabel;
	}

	/** Busca textual com debounce: agenda o reload ao parar de digitar. */
	function onSearchInput(): void {
		if (debounceTimer) clearTimeout(debounceTimer);
		debounceTimer = setTimeout(() => {
			page = 1;
			void load();
		}, DEBOUNCE_MS);
	}

	/** Submit do form: dispara a busca imediatamente (sem esperar o debounce). */
	function onSubmit(event: SubmitEvent): void {
		event.preventDefault();
		if (debounceTimer) clearTimeout(debounceTimer);
		page = 1;
		void load();
	}

	function onStatusChange(event: Event): void {
		status = (event.currentTarget as HTMLSelectElement).value;
		page = 1;
		void load();
	}

	function onSpecialChange(event: Event): void {
		specialProject = (event.currentTarget as HTMLSelectElement).value;
		page = 1;
		void load();
	}

	function clearFilters(): void {
		if (debounceTimer) clearTimeout(debounceTimer);
		search = '';
		status = DEFAULT_STATUS;
		specialProject = '';
		abepIndicator = '';
		abepLabel = '';
		lastSelectedAbepLabel = '';
		abepOpen = false;
		page = 1;
		void load();
	}

	function goToPage(target: number): void {
		page = target;
		void load();
	}

	// --- Combobox ABEP (acessível: role=combobox + listbox) ---------------

	function openAbep(): void {
		abepOpen = true;
		abepActiveIndex = -1;
	}

	function closeAbep(): void {
		abepOpen = false;
		abepActiveIndex = -1;
	}

	function onAbepInput(): void {
		// Digitar invalida a seleção atual até escolher uma opção.
		abepIndicator = '';
		lastSelectedAbepLabel = '';
		openAbep();
	}

	function selectAbep(value: string, label: string): void {
		abepIndicator = value;
		abepLabel = label;
		lastSelectedAbepLabel = label;
		closeAbep();
		page = 1;
		void load();
	}

	function onAbepKeydown(event: KeyboardEvent): void {
		const list = abepVisible;
		if (event.key === 'Escape') {
			closeAbep();
			return;
		}
		if (event.key === 'ArrowDown') {
			event.preventDefault();
			if (!abepOpen) openAbep();
			if (list.length === 0) return;
			abepActiveIndex = Math.min(abepActiveIndex + 1, list.length - 1);
			return;
		}
		if (event.key === 'ArrowUp') {
			event.preventDefault();
			if (list.length === 0) return;
			abepActiveIndex = Math.max(abepActiveIndex - 1, 0);
			return;
		}
		if (event.key === 'Enter') {
			if (abepOpen && abepActiveIndex >= 0 && abepActiveIndex < list.length) {
				event.preventDefault();
				const chosen = list[abepActiveIndex];
				selectAbep(chosen.value, chosen.label);
			}
		}
	}

	onMount(() => {
		void load();
		return () => inFlight?.abort();
	});

	onDestroy(() => {
		if (debounceTimer) clearTimeout(debounceTimer);
		inFlight?.abort();
	});

	/** Detalhe do projeto: rota SPA base-aware (Fase 5a migrada). */
	function projectDetailHref(project: Project): string {
		return `${base}/projetos/${project.id}`;
	}

	/** Formata uma data ISO em pt-BR; vazio vira travessão. */
	function formatDateBr(iso: string | null): string {
		if (!iso) return '—';
		const parsed = new Date(iso);
		if (Number.isNaN(parsed.getTime())) return '—';
		return parsed.toLocaleDateString('pt-BR', {
			day: '2-digit',
			month: '2-digit',
			year: 'numeric',
			timeZone: 'UTC'
		});
	}

	/** Tom do badge de prioridade conforme a severidade. */
	function priorityTone(
		prioridade: string | null
	): 'neutral' | 'info' | 'warning' | 'danger' {
		switch ((prioridade ?? '').toLowerCase()) {
			case 'urgente':
				return 'danger';
			case 'alta':
				return 'warning';
			case 'media':
				return 'info';
			default:
				return 'neutral';
		}
	}

	function capitalize(value: string | null): string {
		if (!value) return '—';
		return value.charAt(0).toUpperCase() + value.slice(1);
	}
</script>

<svelte:head>
	<title>Todos os Projetos — ProjetosRJ</title>
</svelte:head>

<section aria-labelledby="projetos-title" class="flex flex-col gap-4">
	<!--
		Cabeçalho-card (projects-v4-header): superfície elevada com borda + sombra,
		título + meta-pill à esquerda, ações à direita. Empilha no mobile (<992px).
	-->
	<header
		class="flex flex-col items-stretch justify-between gap-3 rounded-lg border border-border-subtle bg-surface p-5 shadow-sm md:flex-row md:items-start"
	>
		<div class="min-w-0">
			<h1
				id="projetos-title"
				class="m-0 inline-flex flex-wrap items-center gap-2 font-heading text-2xl font-bold text-text-primary"
			>
				<span>Todos os Projetos</span>
				{#if data}
					<!-- projects-v4-meta-pill: pílula suave com a contagem. -->
					<span
						class="inline-flex items-center whitespace-nowrap rounded-md border border-primary-500/40 bg-primary-100 px-2.5 py-1 text-xs font-semibold text-primary-700"
					>
						{totalProjects} projeto{totalProjects === 1 ? '' : 's'}
					</span>
				{/if}
			</h1>
			<p class="mt-1.5 text-base text-text-muted">Visualize, filtre e acompanhe seus projetos.</p>
		</div>

		<div class="flex flex-wrap items-center justify-end gap-2">
			{#if isAdmin}
				<!--
					Exportar CSV: link direto para a rota Flask nativa /projects/download
					(download de attachment, FORA do envelope JSON). Visível só p/ admin,
					replicando o {% if is_admin_user %} do Jinja. Sem toast/som/loading —
					o browser baixa 'projetosDDMMYYYYHHMM.csv'. NÃO base-aware: é rota
					nativa do Flask, não da SPA.
				-->
				<a
					href="/projects/download"
					download
					title="Exportar projetos (CSV)"
					class="inline-flex h-9 items-center justify-center gap-1.5 rounded-md border border-border-subtle bg-surface px-3 text-sm font-semibold text-text-primary transition-all duration-fast ease-out hover:border-border-strong hover:bg-surface-muted hover:text-primary-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
				>
					<i class="fas fa-download" aria-hidden="true"></i>
					Exportar CSV
				</a>
			{/if}
			<!--
				Botão primário (btn-projects-v4-primary): gradiente da marca + sombra
				elevada. Reproduzido com o token primary e leve elevação no hover.
			-->
			<button
				type="button"
				onclick={() => (createModalOpen = true)}
				class="inline-flex h-9 items-center justify-center gap-1.5 rounded-md border border-primary-700/25 bg-gradient-to-br from-primary-600 to-primary-700 px-3 text-sm font-semibold text-white shadow-md transition-all duration-fast ease-out hover:from-primary-500 hover:to-primary-600 hover:shadow-lg focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
			>
				<i class="fas fa-plus" aria-hidden="true"></i>
				Novo projeto
			</button>
		</div>
	</header>

	<!--
		Filtros (projects-v4-filters): card de superfície com borda + sombra. Os
		campos re-buscam server-side. Linha de campos com a busca crescendo (flex-1)
		e as ações empurradas para a direita (ml-auto). Quebra no mobile.
	-->
	<form
		class="flex flex-wrap items-end gap-3 rounded-lg border border-border-subtle bg-surface px-4 py-3.5 shadow-sm"
		role="search"
		aria-label="Filtros de projetos"
		onsubmit={onSubmit}
	>
		<div class="flex min-w-[15rem] flex-1 flex-col gap-1">
			<label
				for="projetosSearch"
				class="text-xs font-semibold uppercase tracking-wide text-text-muted"
			>
				Busca livre
			</label>
			<!-- projects-v4-search-wrap: ícone de lupa à esquerda, padding interno. -->
			<div class="relative">
				<i
					class="fas fa-search pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-sm text-text-muted"
					aria-hidden="true"
				></i>
				<input
					id="projetosSearch"
					name="q"
					type="search"
					autocomplete="off"
					bind:value={search}
					oninput={onSearchInput}
					placeholder="Digite título, órgão ou indicador…"
					class="h-9 w-full rounded-md border border-border-subtle bg-surface pl-8 pr-2.5 text-md text-text-primary placeholder:text-text-muted transition-colors duration-fast focus:border-primary-500 focus:outline-none focus:ring-[3px] focus:ring-primary-500/15"
				/>
			</div>
		</div>

		<div class="flex min-w-[10rem] flex-col gap-1">
			<label
				for="projetosStatus"
				class="text-xs font-semibold uppercase tracking-wide text-text-muted"
			>
				Status
			</label>
			<select
				id="projetosStatus"
				value={status}
				onchange={onStatusChange}
				class="h-9 cursor-pointer rounded-md border border-border-subtle bg-surface px-2.5 text-md text-text-primary transition-colors duration-fast focus:border-primary-500 focus:outline-none focus:ring-[3px] focus:ring-primary-500/15"
			>
				{#each statusOptions as option (option)}
					<option value={option}>{option}</option>
				{/each}
			</select>
		</div>

		<div class="flex min-w-[10rem] flex-col gap-1">
			<label
				for="projetosSpecial"
				class="text-xs font-semibold uppercase tracking-wide text-text-muted"
			>
				Especial
			</label>
			<select
				id="projetosSpecial"
				value={specialProject}
				onchange={onSpecialChange}
				class="h-9 cursor-pointer rounded-md border border-border-subtle bg-surface px-2.5 text-md text-text-primary transition-colors duration-fast focus:border-primary-500 focus:outline-none focus:ring-[3px] focus:ring-primary-500/15"
			>
				<option value="">Todos os especiais</option>
				{#each specialOptions as option (option)}
					<option value={option}>{option}</option>
				{/each}
			</select>
		</div>

		<!-- Indicador ABEP: combobox filtrável e navegável por teclado. -->
		<div class="relative flex min-w-[16rem] flex-col gap-1">
			<label
				for="projetosAbep"
				class="text-xs font-semibold uppercase tracking-wide text-text-muted"
			>
				Indicador ABEP
			</label>
			<input
				id="projetosAbep"
				type="text"
				autocomplete="off"
				role="combobox"
				aria-expanded={abepOpen}
				aria-controls="projetosAbepListbox"
				aria-autocomplete="list"
				aria-activedescendant={abepActiveIndex >= 0
					? `abep-option-${abepActiveIndex}`
					: undefined}
				bind:value={abepLabel}
				oninput={onAbepInput}
				onfocus={openAbep}
				onkeydown={onAbepKeydown}
				onblur={() => setTimeout(closeAbep, 120)}
				placeholder="Busque por número ou título…"
				class="h-9 cursor-text rounded-md border border-border-subtle bg-surface px-2.5 text-md text-text-primary placeholder:text-text-muted transition-colors duration-fast focus:border-primary-500 focus:outline-none focus:ring-[3px] focus:ring-primary-500/15"
			/>
			{#if abepOpen}
				<!--
					projects-v4-abep-dropdown: painel flutuante com entrada suave
					(animate-dropdown-in, 0.16s ease-out — keyframes do kit Fase 1).
				-->
				<ul
					id="projetosAbepListbox"
					role="listbox"
					aria-label="Indicadores ABEP"
					class="absolute left-0 right-0 top-full z-dropdown mt-1 max-h-[220px] origin-top animate-dropdown-in overflow-y-auto rounded-md border border-border-subtle bg-surface py-1 shadow-lg"
				>
					{#if abepVisible.length === 0}
						<li class="px-2.5 py-2 text-sm italic text-text-muted">Nenhum indicador encontrado</li>
					{:else}
						{#each abepVisible as option, index (option.value)}
							<li class="contents">
								<!--
									role="option" num <button> mantém o item acessível: a navegação por
									teclado segue via aria-activedescendant + onkeydown no input (foco
									permanece no combobox), e o <button> elimina o warning a11y de
									click sem keydown. onmousedown previne o blur antes do onclick.
								-->
								<button
									type="button"
									id={`abep-option-${index}`}
									role="option"
									aria-selected={option.value === abepIndicator}
									class="block w-full cursor-pointer px-2.5 py-2 text-left text-sm text-text-primary transition-colors duration-fast hover:bg-primary-100 hover:text-primary-700 {index ===
									abepActiveIndex
										? 'bg-primary-100 text-primary-700'
										: ''}"
									onmousedown={(e) => e.preventDefault()}
									onclick={() => selectAbep(option.value, option.label)}
								>
									{option.label}
								</button>
							</li>
						{/each}
					{/if}
				</ul>
			{/if}
		</div>

		<div class="ml-auto flex items-end gap-2">
			<!-- Botão primário "Filtrar" com gradiente da marca, igual ao header. -->
			<button
				type="submit"
				title="Filtrar"
				class="inline-flex h-9 items-center justify-center gap-1.5 rounded-md border border-primary-700/25 bg-gradient-to-br from-primary-600 to-primary-700 px-3 text-sm font-semibold text-white shadow-md transition-all duration-fast ease-out hover:from-primary-500 hover:to-primary-600 hover:shadow-lg focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
			>
				<i class="fas fa-filter" aria-hidden="true"></i>
				Filtrar
			</button>
			{#if hasActiveFilters}
				<button
					type="button"
					onclick={clearFilters}
					title="Limpar filtros"
					class="inline-flex h-9 items-center justify-center gap-1.5 rounded-md border border-border-subtle bg-surface px-3 text-sm font-semibold text-text-secondary transition-all duration-fast ease-out hover:border-border-strong hover:bg-surface-muted hover:text-primary-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
				>
					<i class="fas fa-rotate-left" aria-hidden="true"></i>
					Limpar
				</button>
			{/if}
		</div>
	</form>

	{#if loadState === 'loading'}
		<p
			role="status"
			aria-live="polite"
			class="rounded-lg border border-border-subtle bg-surface px-4 py-8 text-center text-sm text-text-muted shadow-sm"
		>
			Carregando projetos…
		</p>
	{:else if loadState === 'error'}
		<LoadErrorState message={errorMessage} onRetry={() => load()} />
	{:else if data}
		<div role="status" aria-live="polite" class="sr-only">
			{totalProjects} projeto{totalProjects === 1 ? '' : 's'} encontrado{totalProjects === 1
				? ''
				: 's'}.
		</div>

		{#if data.projetos.length === 0}
			<!--
				Estado vazio (projects-v4-empty-state): borda tracejada, ícone em
				quadro suave, título e texto centralizados.
			-->
			<div
				class="rounded-lg border border-dashed border-border-strong bg-surface-muted/40 px-4 py-8 text-center"
			>
				<div
					class="mx-auto mb-3 inline-flex h-14 w-14 items-center justify-center rounded-xl border border-primary-500/25 bg-primary-100 text-xl text-primary-700"
				>
					<i class="fas fa-folder-open" aria-hidden="true"></i>
				</div>
				<h2 class="m-0 font-heading text-xl font-bold text-text-primary">
					Nenhum projeto encontrado
				</h2>
				<p class="mb-3.5 mt-1.5 text-md text-text-muted">
					Os filtros aplicados não retornaram resultados. Ajuste os filtros e tente
					novamente.
				</p>
			</div>
		{:else}
			<!--
				Tabela-card (projects-v4-table-card): superfície com borda + sombra e
				overflow-hidden para os cantos arredondarem a tabela. Sem padding
				interno — a tabela encosta nas bordas, igual ao original.
			-->
			<div
				class="overflow-hidden rounded-lg border border-border-subtle bg-surface shadow-sm"
			>
				<div class="overflow-x-auto" aria-busy={loadState !== 'ready'}>
					<table class="m-0 w-full min-w-[980px] border-separate border-spacing-0 text-sm">
						<caption class="sr-only">Lista de projetos filtrados</caption>
						<thead>
							<!-- Cabeçalho: fundo suave, MAIÚSCULAS com letter-spacing caps. -->
							<tr class="text-left text-text-muted">
								<th
									scope="col"
									class="w-16 border-b border-border-subtle bg-surface-muted px-2.5 py-2 text-center text-xs font-bold uppercase tracking-caps whitespace-nowrap"
								>
									ID
								</th>
								<th
									scope="col"
									class="min-w-[260px] border-b border-border-subtle bg-surface-muted px-2.5 py-2 text-xs font-bold uppercase tracking-caps whitespace-nowrap"
								>
									Título
								</th>
								<th
									scope="col"
									class="border-b border-border-subtle bg-surface-muted px-2.5 py-2 text-xs font-bold uppercase tracking-caps whitespace-nowrap"
								>
									Órgão
								</th>
								<th
									scope="col"
									class="border-b border-border-subtle bg-surface-muted px-2.5 py-2 text-center text-xs font-bold uppercase tracking-caps whitespace-nowrap"
								>
									Prioridade
								</th>
								<th
									scope="col"
									class="border-b border-border-subtle bg-surface-muted px-2.5 py-2 text-center text-xs font-bold uppercase tracking-caps whitespace-nowrap"
								>
									Status
								</th>
								<th
									scope="col"
									class="border-b border-border-subtle bg-surface-muted px-2.5 py-2 text-xs font-bold uppercase tracking-caps whitespace-nowrap"
								>
									Data Início
								</th>
								<th
									scope="col"
									class="border-b border-border-subtle bg-surface-muted px-2.5 py-2 text-xs font-bold uppercase tracking-caps whitespace-nowrap"
								>
									Data Fim
								</th>
							</tr>
						</thead>
						<tbody>
							{#each data.projetos as project (project.id)}
								<!-- Linha com hover suave (transição de fundo). -->
								<tr class="group transition-colors duration-fast hover:bg-surface-muted/60">
									<td
										class="border-t border-border-subtle px-2.5 py-2.5 text-center align-middle"
									>
										<!-- projects-v4-id-chip: chip arredondado com o ID. -->
										<span
											class="inline-flex items-center rounded-sm border border-border-subtle bg-surface-muted px-2 py-0.5 text-xs font-bold text-text-muted"
										>
											{project.id}
										</span>
									</td>
									<td class="border-t border-border-subtle px-2.5 py-2.5 align-middle">
										<a
											href={projectDetailHref(project)}
											class="font-semibold text-primary-700 no-underline transition-colors duration-fast hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
										>
											{project.titulo}
										</a>
									</td>
									<td
										class="border-t border-border-subtle px-2.5 py-2.5 align-middle text-text-secondary"
									>
										{project.orgao_sigla ?? project.orgao ?? '—'}
									</td>
									<td
										class="border-t border-border-subtle px-2.5 py-2.5 text-center align-middle"
									>
										{#if project.prioridade}
											<Badge tone={priorityTone(project.prioridade)}>
												{capitalize(project.prioridade)}
											</Badge>
										{:else}
											<span class="italic text-text-muted">—</span>
										{/if}
									</td>
									<td
										class="border-t border-border-subtle px-2.5 py-2.5 text-center align-middle"
									>
										<Badge tone={project.status === 'Vigente' ? 'success' : 'neutral'}>
											{project.status}
										</Badge>
									</td>
									<td
										class="border-t border-border-subtle px-2.5 py-2.5 align-middle font-mono font-medium whitespace-nowrap text-text-secondary"
									>
										{#if project.data_inicio_projeto}
											<time datetime={project.data_inicio_projeto}>
												{formatDateBr(project.data_inicio_projeto)}
											</time>
										{:else}
											<span class="italic text-text-muted">—</span>
										{/if}
									</td>
									<td
										class="border-t border-border-subtle px-2.5 py-2.5 align-middle font-mono font-medium whitespace-nowrap text-text-secondary"
									>
										{#if project.data_fim_projeto}
											<time datetime={project.data_fim_projeto}>
												{formatDateBr(project.data_fim_projeto)}
											</time>
										{:else}
											<span class="italic text-text-muted">—</span>
										{/if}
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			</div>

			{#if pagination && pagination.total_pages > 1}
				<!--
					Paginação (projects-v4-pagination-wrap): card com a info "Mostrando…"
					à esquerda e a navegação (chips) à direita. Empilha no mobile.
				-->
				<section
					class="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border-subtle bg-surface px-4 py-3 shadow-sm"
				>
					<div class="text-sm font-medium text-text-secondary">
						Mostrando {(pagination.page - 1) * pagination.per_page + 1} - {Math.min(
							pagination.page * pagination.per_page,
							totalProjects
						)} de {totalProjects} projetos
					</div>
					<nav class="flex items-center gap-2" aria-label="Paginação de projetos">
						<button
							type="button"
							onclick={() => goToPage(pagination.page - 1)}
							disabled={pagination.page <= 1}
							class="inline-flex h-9 min-w-9 items-center justify-center rounded-md border border-border-subtle bg-surface px-3 text-sm font-semibold text-text-secondary transition-all duration-fast ease-out hover:border-border-strong hover:bg-surface-muted hover:text-primary-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:bg-surface disabled:hover:text-text-secondary"
						>
							Anterior
						</button>
						<span
							class="inline-flex h-9 items-center rounded-md border border-primary-700 bg-gradient-to-b from-primary-500 to-primary-700 px-3 text-sm font-semibold text-white"
							aria-live="polite"
						>
							Página {pagination.page} de {pagination.total_pages}
						</span>
						<button
							type="button"
							onclick={() => goToPage(pagination.page + 1)}
							disabled={pagination.page >= pagination.total_pages}
							class="inline-flex h-9 min-w-9 items-center justify-center rounded-md border border-border-subtle bg-surface px-3 text-sm font-semibold text-text-secondary transition-all duration-fast ease-out hover:border-border-strong hover:bg-surface-muted hover:text-primary-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:bg-surface disabled:hover:text-text-secondary"
						>
							Próxima
						</button>
					</nav>
				</section>
			{/if}
		{/if}
	{/if}
</section>

<!-- Modal de criação (Quick Create) com a mesma UX do add_form Jinja. -->
<CriarProjetoModal
	open={createModalOpen}
	options={createOptions}
	onClose={() => (createModalOpen = false)}
	onCreated={onProjectCreated}
/>
