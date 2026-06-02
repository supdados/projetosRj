<script lang="ts">
	/**
	 * Tela "Lista de Projetos" (FASE 3). Consome `GET /api/projetos` via
	 * `$lib/api/projects` e renderiza a tabela com os componentes
	 * compartilhados Card/Badge (reusados, não editados). Os filtros
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
	import Card from '$lib/components/Card.svelte';
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

<section aria-labelledby="projetos-title" class="flex flex-col gap-6">
	<header class="flex flex-col gap-2">
		<div class="flex flex-wrap items-center gap-3">
			<h1 id="projetos-title" class="font-heading text-2xl font-bold text-text-primary">
				Todos os Projetos
			</h1>
			{#if data}
				<span
					class="inline-flex items-center gap-1 rounded-sm border border-primary-500 bg-primary-100 px-2 py-1 text-xs font-medium text-primary-700"
				>
					{totalProjects} projeto{totalProjects === 1 ? '' : 's'}
				</span>
			{/if}
			<div class="ml-auto flex items-center gap-2">
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
						class="inline-flex items-center gap-2 rounded-md border border-border-subtle bg-surface px-4 py-2 text-sm font-medium text-text-primary transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
					>
						<i class="fas fa-download" aria-hidden="true"></i>
						Exportar CSV
					</a>
				{/if}
				<button
					type="button"
					onclick={() => (createModalOpen = true)}
					class="inline-flex items-center gap-2 rounded-md border border-primary-500 bg-primary-100 px-4 py-2 text-sm font-medium text-primary-700 transition-colors duration-fast hover:bg-primary-500 hover:text-white focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
				>
					<i class="fas fa-plus-circle" aria-hidden="true"></i>
					Novo projeto
				</button>
			</div>
		</div>
		<p class="text-sm text-text-secondary">Visualize, filtre e acompanhe seus projetos.</p>
	</header>

	<!-- Filtros (re-buscam server-side) -->
	<form
		class="flex flex-wrap items-end gap-4 rounded-lg border border-border-subtle bg-surface px-5 py-4 shadow-sm"
		role="search"
		aria-label="Filtros de projetos"
		onsubmit={onSubmit}
	>
		<div class="flex min-w-[14rem] flex-1 flex-col gap-1">
			<label
				for="projetosSearch"
				class="text-xs font-semibold uppercase tracking-wide text-text-muted"
			>
				Busca livre
			</label>
			<input
				id="projetosSearch"
				name="q"
				type="search"
				autocomplete="off"
				bind:value={search}
				oninput={onSearchInput}
				placeholder="Título, órgão ou indicador…"
				class="rounded-md border border-border-subtle bg-surface px-3 py-2 text-sm text-text-primary placeholder:text-text-muted transition-colors duration-fast focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
			/>
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
				class="rounded-md border border-border-subtle bg-surface px-3 py-2 text-sm text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
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
				class="rounded-md border border-border-subtle bg-surface px-3 py-2 text-sm text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
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
				class="rounded-md border border-border-subtle bg-surface px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
			/>
			{#if abepOpen}
				<ul
					id="projetosAbepListbox"
					role="listbox"
					aria-label="Indicadores ABEP"
					class="absolute left-0 right-0 top-full z-10 mt-1 max-h-64 overflow-auto rounded-md border border-border-subtle bg-surface py-1 shadow-md"
				>
					{#if abepVisible.length === 0}
						<li class="px-3 py-2 text-sm text-text-muted">Nenhum indicador encontrado</li>
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
									class="block w-full cursor-pointer px-3 py-2 text-left text-sm text-text-primary hover:bg-surface-muted {index ===
									abepActiveIndex
										? 'bg-surface-muted'
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

		<div class="flex items-end gap-2">
			<button
				type="submit"
				class="rounded-md border border-primary-500 bg-primary-100 px-4 py-2 text-sm font-medium text-primary-700 transition-colors duration-fast hover:bg-primary-100/80 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
			>
				Filtrar
			</button>
			{#if hasActiveFilters}
				<button
					type="button"
					onclick={clearFilters}
					class="rounded-md border border-border-subtle bg-surface px-4 py-2 text-sm font-medium text-text-primary transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
				>
					Limpar filtros
				</button>
			{/if}
		</div>
	</form>

	{#if loadState === 'loading'}
		<p role="status" aria-live="polite" class="text-text-secondary">Carregando projetos…</p>
	{:else if loadState === 'error'}
		<LoadErrorState message={errorMessage} onRetry={() => load()} />
	{:else if data}
		<div role="status" aria-live="polite" class="sr-only">
			{totalProjects} projeto{totalProjects === 1 ? '' : 's'} encontrado{totalProjects === 1
				? ''
				: 's'}.
		</div>

		{#if data.projetos.length === 0}
			<div
				class="rounded-lg border border-border-subtle bg-surface px-5 py-12 text-center"
			>
				<h2 class="font-heading text-lg font-semibold text-text-primary">
					Nenhum projeto encontrado
				</h2>
				<p class="mt-2 text-sm text-text-muted">
					Os filtros aplicados não retornaram resultados. Ajuste os filtros e tente
					novamente.
				</p>
			</div>
		{:else}
			<Card>
				<div class="overflow-x-auto" aria-busy={loadState !== 'ready'}>
					<table class="w-full border-collapse text-sm">
						<caption class="sr-only">Lista de projetos filtrados</caption>
						<thead>
							<tr class="border-b border-border-subtle text-left text-text-muted">
								<th scope="col" class="px-3 py-2 font-semibold">ID</th>
								<th scope="col" class="px-3 py-2 font-semibold">Título</th>
								<th scope="col" class="px-3 py-2 font-semibold">Órgão</th>
								<th scope="col" class="px-3 py-2 font-semibold">Prioridade</th>
								<th scope="col" class="px-3 py-2 font-semibold">Status</th>
								<th scope="col" class="px-3 py-2 font-semibold">Data Início</th>
								<th scope="col" class="px-3 py-2 font-semibold">Data Fim</th>
							</tr>
						</thead>
						<tbody>
							{#each data.projetos as project (project.id)}
								<tr class="border-b border-border-subtle last:border-0">
									<td class="px-3 py-2 text-text-muted">{project.id}</td>
									<td class="px-3 py-2">
										<a
											href={projectDetailHref(project)}
											class="font-medium text-primary-700 no-underline hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
										>
											{project.titulo}
										</a>
									</td>
									<td class="px-3 py-2 text-text-secondary">
										{project.orgao_sigla ?? project.orgao ?? '—'}
									</td>
									<td class="px-3 py-2">
										{#if project.prioridade}
											<Badge tone={priorityTone(project.prioridade)}>
												{capitalize(project.prioridade)}
											</Badge>
										{:else}
											<span class="text-text-muted">—</span>
										{/if}
									</td>
									<td class="px-3 py-2">
										<Badge tone={project.status === 'Vigente' ? 'success' : 'neutral'}>
											{project.status}
										</Badge>
									</td>
									<td class="px-3 py-2 text-text-secondary">
										{#if project.data_inicio_projeto}
											<time datetime={project.data_inicio_projeto}>
												{formatDateBr(project.data_inicio_projeto)}
											</time>
										{:else}
											<span class="text-text-muted">—</span>
										{/if}
									</td>
									<td class="px-3 py-2 text-text-secondary">
										{#if project.data_fim_projeto}
											<time datetime={project.data_fim_projeto}>
												{formatDateBr(project.data_fim_projeto)}
											</time>
										{:else}
											<span class="text-text-muted">—</span>
										{/if}
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			</Card>

			{#if pagination && pagination.total_pages > 1}
				<nav class="flex items-center justify-center gap-3" aria-label="Paginação de projetos">
					<button
						type="button"
						onclick={() => goToPage(pagination.page - 1)}
						disabled={pagination.page <= 1}
						class="rounded-md border border-border-subtle bg-surface px-4 py-2 text-sm font-medium text-text-primary transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-50"
					>
						Anterior
					</button>
					<span class="text-sm text-text-secondary" aria-live="polite">
						Página {pagination.page} de {pagination.total_pages}
					</span>
					<button
						type="button"
						onclick={() => goToPage(pagination.page + 1)}
						disabled={pagination.page >= pagination.total_pages}
						class="rounded-md border border-border-subtle bg-surface px-4 py-2 text-sm font-medium text-text-primary transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-50"
					>
						Próxima
					</button>
				</nav>
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
