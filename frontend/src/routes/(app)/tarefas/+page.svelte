<script lang="ts">
	/**
	 * Tela "Hub de Tarefas" em MODO LISTA (sem Kanban). Consome
	 * `GET /api/tarefas` via `$lib/api/tasks` e renderiza as tarefas agrupadas
	 * por projeto, reusando os componentes compartilhados Card/Badge (apenas
	 * lidos/reusados, nunca editados). Dentro de cada grupo as tarefas são
	 * sub-agrupadas por etapa a partir de `etapa_titulo`/`is_first_of_stage`,
	 * já calculados no backend.
	 *
	 * Os filtros de projeto e órgão re-buscam server-side (o `orgao_scope` é
	 * aplicado no backend); a alternância de status (ativas/arquivadas/
	 * finalizadas) traduz para o `?modo=` do endpoint. Estados de loading/erro/
	 * vazio são anunciados via aria-live.
	 *
	 * Referência visual: templates/tasks/hub.html.
	 */
	import { onMount } from 'svelte';
	import { fetchTarefas } from '$lib/api/tasks';
	import { ApiClientError } from '$lib/api/client';
	import type { TaskCard, TaskHubData, TaskHubModo, TaskHubQuery } from '$lib/types/tasks';
	import Card from '$lib/components/Card.svelte';
	import Badge from '$lib/components/Badge.svelte';

	type LoadState = 'loading' | 'ready' | 'error';
	type BadgeTone = 'neutral' | 'primary' | 'success' | 'warning' | 'danger' | 'info';

	/** Modos da topnav (espelham `?modo=` do endpoint). */
	const MODO_OPTIONS: { value: TaskHubModo; label: string }[] = [
		{ value: 'ativas', label: 'Ativas' },
		{ value: 'finalizadas', label: 'Finalizadas' },
		{ value: 'arquivadas', label: 'Arquivadas' }
	];

	/** Rótulos PT dos status (espelham `status_labels` do hub Jinja). */
	const STATUS_LABEL: Record<string, string> = {
		nao_iniciada: 'Não iniciada',
		em_andamento: 'Em andamento',
		para_validacao: 'Para validação',
		para_ajustes: 'Para ajustes',
		finalizada: 'Finalizada'
	};

	/** Tom semântico do Badge por status. */
	const STATUS_TONE: Record<string, BadgeTone> = {
		nao_iniciada: 'neutral',
		em_andamento: 'info',
		para_validacao: 'primary',
		para_ajustes: 'warning',
		finalizada: 'success'
	};

	/** Rótulos PT das prioridades (espelham `prioridade_labels` do hub Jinja). */
	const PRIORIDADE_LABEL: Record<string, string> = {
		baixa: 'Baixa',
		media: 'Média',
		alta: 'Alta',
		urgente: 'Urgente'
	};

	/** Tom semântico do Badge por prioridade. */
	const PRIORIDADE_TONE: Record<string, BadgeTone> = {
		baixa: 'neutral',
		media: 'info',
		alta: 'warning',
		urgente: 'danger'
	};

	/** Rótulos PT dos tipos de pedido (espelham `tipo_labels` do hub Jinja). */
	const TIPO_LABEL: Record<string, string> = {
		bug: 'Bug',
		melhoria: 'Melhoria',
		duvida: 'Dúvida',
		outros: 'Outros',
		implementacao: 'Implementação'
	};

	function statusLabel(value: string): string {
		return STATUS_LABEL[value] ?? value;
	}
	function statusTone(value: string): BadgeTone {
		return STATUS_TONE[value] ?? 'neutral';
	}
	function prioridadeLabel(value: string | null): string | null {
		if (!value) return null;
		return PRIORIDADE_LABEL[value] ?? value;
	}
	function prioridadeTone(value: string | null): BadgeTone {
		if (!value) return 'neutral';
		return PRIORIDADE_TONE[value] ?? 'neutral';
	}
	function tipoLabel(value: string | null): string | null {
		if (!value) return null;
		return TIPO_LABEL[value] ?? value;
	}

	let loadState = $state<LoadState>('loading');
	let data = $state<TaskHubData | null>(null);
	let errorMessage = $state<string>('');

	// Filtros controlados pela UI; a busca acontece server-side.
	let modo = $state<TaskHubModo>('ativas');
	let project = $state<string>('');
	let orgao = $state<string>('');

	let inFlight: AbortController | null = null;

	async function load(): Promise<void> {
		loadState = data ? loadState : 'loading';
		errorMessage = '';
		inFlight?.abort();
		const controller = new AbortController();
		inFlight = controller;

		const query: TaskHubQuery = { modo, project, orgao };
		try {
			const next = await fetchTarefas(query, controller.signal);
			if (controller.signal.aborted) return;
			data = next;
			// Reconcilia os filtros com o que o backend efetivamente aplicou.
			project = next.filters.project ?? '';
			orgao =
				next.filters.selected_orgao === null || next.filters.selected_orgao === undefined
					? ''
					: String(next.filters.selected_orgao);
			loadState = 'ready';
		} catch (err) {
			if (controller.signal.aborted) return;
			// 401 já redirecionou; aqui tratamos os demais erros.
			if (err instanceof ApiClientError && err.code === 'unauthenticated') return;
			errorMessage =
				err instanceof Error ? err.message : 'Falha ao carregar as tarefas.';
			loadState = 'error';
		}
	}

	function selectModo(next: TaskHubModo): void {
		if (modo === next) return;
		modo = next;
		void load();
	}

	function onProjectChange(event: Event): void {
		project = (event.currentTarget as HTMLSelectElement).value;
		void load();
	}

	function onOrgaoChange(event: Event): void {
		orgao = (event.currentTarget as HTMLSelectElement).value;
		void load();
	}

	function clearFilters(): void {
		project = '';
		orgao = '';
		void load();
	}

	onMount(() => {
		void load();
		return () => inFlight?.abort();
	});

	/**
	 * Opções de órgão para o filtro local: siglas distintas presentes nas
	 * opções de projeto devolvidas pelo backend (que já respeitam o escopo).
	 */
	const orgaoOptions = $derived.by(() => {
		if (!data) return [] as string[];
		const seen = new Set<string>();
		for (const option of data.project_options) {
			const sigla = option.orgao_sigla?.trim();
			if (sigla) seen.add(sigla);
		}
		return Array.from(seen).sort((a, b) => a.localeCompare(b, 'pt-BR'));
	});

	const hasActiveFilters = $derived(project !== '' || orgao !== '');
	const totalItems = $derived(data?.total_items ?? 0);

	/**
	 * Divide as tarefas de um grupo em subgrupos por etapa, respeitando o
	 * `is_first_of_stage` calculado no backend (cada `true` abre um bloco).
	 */
	function stagesOf(tasks: TaskCard[]): { titulo: string | null; tasks: TaskCard[] }[] {
		const blocks: { titulo: string | null; tasks: TaskCard[] }[] = [];
		for (const task of tasks) {
			if (task.is_first_of_stage || blocks.length === 0) {
				blocks.push({ titulo: task.etapa_titulo, tasks: [task] });
			} else {
				blocks[blocks.length - 1].tasks.push(task);
			}
		}
		return blocks;
	}
</script>

<svelte:head>
	<title>Tarefas — ProjetosRJ</title>
</svelte:head>

<section aria-labelledby="tarefas-title" class="flex flex-col gap-6">
	<header class="flex flex-col gap-2">
		<div class="flex flex-wrap items-center gap-3">
			<h1 id="tarefas-title" class="font-heading text-2xl font-bold text-text-primary">
				Tarefas
			</h1>
			<span
				class="inline-flex items-center gap-1 rounded-sm border border-primary-500 bg-primary-100 px-2 py-1 text-xs font-medium text-primary-700"
			>
				{totalItems} tarefa{totalItems === 1 ? '' : 's'}
			</span>
		</div>
		<p class="text-sm text-text-secondary">Tarefas agrupadas por projeto.</p>
	</header>

	<!-- Alternância de status (ativas/finalizadas/arquivadas) -->
	<div
		role="group"
		aria-label="Visão das tarefas"
		class="inline-flex w-fit rounded-md border border-border-subtle bg-surface p-1"
	>
		{#each MODO_OPTIONS as option (option.value)}
			<button
				type="button"
				aria-pressed={modo === option.value}
				onclick={() => selectModo(option.value)}
				class="rounded-sm px-4 py-1.5 text-sm font-medium transition-colors duration-fast focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 {modo ===
				option.value
					? 'bg-primary-100 text-primary-700'
					: 'text-text-secondary hover:bg-surface-muted'}"
			>
				{option.label}
			</button>
		{/each}
	</div>

	<!-- Filtros (re-buscam server-side) -->
	<form
		class="flex flex-wrap items-end gap-4 rounded-lg border border-border-subtle bg-surface px-5 py-4 shadow-sm"
		aria-label="Filtros de tarefas"
		onsubmit={(e) => e.preventDefault()}
	>
		<div class="flex min-w-[14rem] flex-col gap-1">
			<label for="projectFilter" class="text-xs font-semibold uppercase tracking-wide text-text-muted">
				Projeto
			</label>
			<select
				id="projectFilter"
				value={project}
				onchange={onProjectChange}
				disabled={!data || data.project_options.length === 0}
				class="rounded-md border border-border-subtle bg-surface px-3 py-2 text-sm text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-60"
			>
				<option value="">Todos os projetos</option>
				{#if data}
					{#each data.project_options as option (option.value)}
						<option value={option.value}>{option.label}</option>
					{/each}
				{/if}
			</select>
		</div>

		<div class="flex min-w-[12rem] flex-col gap-1">
			<label for="orgaoFilter" class="text-xs font-semibold uppercase tracking-wide text-text-muted">
				Órgão
			</label>
			<select
				id="orgaoFilter"
				value={orgao}
				onchange={onOrgaoChange}
				disabled={orgaoOptions.length === 0}
				class="rounded-md border border-border-subtle bg-surface px-3 py-2 text-sm text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-60"
			>
				<option value="">Todos os órgãos</option>
				{#each orgaoOptions as sigla (sigla)}
					<option value={sigla}>{sigla}</option>
				{/each}
			</select>
		</div>

		{#if hasActiveFilters}
			<button
				type="button"
				onclick={clearFilters}
				class="rounded-md border border-border-subtle bg-surface px-4 py-2 text-sm font-medium text-text-primary transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
			>
				Limpar filtros
			</button>
		{/if}
	</form>

	{#if loadState === 'loading'}
		<p role="status" aria-live="polite" class="text-text-secondary">Carregando tarefas…</p>
	{:else if loadState === 'error'}
		<div
			role="alert"
			class="flex flex-col items-start gap-3 rounded-lg border border-danger bg-surface px-5 py-4"
		>
			<p class="text-text-primary">{errorMessage}</p>
			<button
				type="button"
				onclick={() => load()}
				class="rounded-md border border-border-subtle bg-surface px-4 py-2 text-sm font-medium text-text-primary transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
			>
				Tentar novamente
			</button>
		</div>
	{:else if data}
		{#if data.groups.length === 0}
			<div
				role="status"
				aria-live="polite"
				class="rounded-lg border border-border-subtle bg-surface px-5 py-8 text-center text-text-muted"
			>
				Nenhuma tarefa para os filtros selecionados.
			</div>
		{:else}
			<div class="flex flex-col gap-5" aria-busy={loadState !== 'ready'}>
				{#each data.groups as group (group.key)}
					{@const labelId = `group-${group.key}`}
					<Card {labelId}>
						{#snippet header()}
							<div class="flex flex-wrap items-baseline gap-2">
								<h2 id={labelId} class="font-heading text-lg font-semibold text-text-primary">
									{group.project_titulo}
								</h2>
								<span class="text-xs font-medium text-text-secondary">
									{group.project_orgao_sigla || 'Não informado'}
								</span>
								<span class="text-xs text-text-muted">
									· {group.tasks.length} tarefa{group.tasks.length === 1 ? '' : 's'}
								</span>
							</div>
						{/snippet}

						<div class="flex flex-col gap-5">
							{#each stagesOf(group.tasks) as stage (stage.titulo ?? '__sem_etapa__')}
								<div class="flex flex-col gap-2">
									<h3 class="text-xs font-semibold uppercase tracking-wide text-text-muted">
										{stage.titulo ?? 'Sem etapa'}
									</h3>
									<ul class="flex flex-col gap-2">
										{#each stage.tasks as task (task.id)}
											<li class="flex flex-col gap-2 rounded-md border border-border-subtle bg-surface px-4 py-3">
												<p class="text-sm text-text-primary">{task.descricao}</p>
												<div class="flex flex-wrap items-center gap-2">
													<Badge tone={statusTone(task.status)}>
														{statusLabel(task.status)}
													</Badge>
													{#if prioridadeLabel(task.prioridade)}
														<Badge tone={prioridadeTone(task.prioridade)}>
															{prioridadeLabel(task.prioridade)}
														</Badge>
													{/if}
													{#if tipoLabel(task.tipo_pedido)}
														<span class="text-xs text-text-secondary">
															{tipoLabel(task.tipo_pedido)}
														</span>
													{/if}
													{#if task.responsavel}
														<span class="text-xs text-text-muted">
															· {task.responsavel}
														</span>
													{/if}
												</div>
											</li>
										{/each}
									</ul>
								</div>
							{/each}
						</div>
					</Card>
				{/each}
			</div>
		{/if}
	{/if}
</section>
