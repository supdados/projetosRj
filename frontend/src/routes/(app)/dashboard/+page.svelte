<script lang="ts">
	/**
	 * Tela Dashboard (PILOTO). Consome `GET /api/dashboard` e renderiza
	 * contadores + projetos recentes. Acessivel: regiao com heading, estados de
	 * loading/erro anunciados via aria-live, foco gerenciado pelo fluxo natural.
	 */
	import { onMount } from 'svelte';
	import { base } from '$app/paths';
	import { goto } from '$app/navigation';
	import { fetchDashboard } from '$lib/api/dashboard';
	import { ApiClientError } from '$lib/api/client';
	import { auth } from '$lib/stores/auth';
	import { orgaoScopeQuery } from '$lib/stores/orgaoScope';
	import type { DashboardData } from '$lib/types/dashboard';
	import StatCard from '$lib/components/StatCard.svelte';
	import RecentProjectsPanel from '$lib/components/RecentProjectsPanel.svelte';
	import Card from '$lib/components/Card.svelte';
	import Button from '$lib/components/Button.svelte';
	import PageHeader from '$lib/components/PageHeader.svelte';
	import LoadErrorState from '$lib/components/LoadErrorState.svelte';
	import CriarProjetoModal from '$lib/components/CriarProjetoModal.svelte';
	import { fetchProjects, type CreateProjectResult } from '$lib/api/projects';
	import { flash } from '$lib/stores/flash';
	import type { ProjectsListOptions } from '$lib/types/projects';

	type LoadState = 'loading' | 'ready' | 'error';

	let loadState = $state<LoadState>('loading');
	let data = $state<DashboardData | null>(null);
	let errorMessage = $state<string>('');

	// Aborta a busca anterior quando o escopo muda durante um carregamento em
	// voo, evitando que uma resposta atrasada sobrescreva a mais recente.
	let inFlight: AbortController | null = null;

	async function load(): Promise<void> {
		inFlight?.abort();
		const controller = new AbortController();
		inFlight = controller;

		loadState = 'loading';
		errorMessage = '';
		try {
			// Propaga o escopo de orgao do topnav (`?orgao=<id>` | ''); o backend
			// sanitiza o filtro para o usuario corrente.
			const result = await fetchDashboard($orgaoScopeQuery, controller.signal);
			if (controller.signal.aborted) return;
			data = result;
			loadState = 'ready';
		} catch (err) {
			if (controller.signal.aborted) return;
			// 401 ja redirecionou; aqui tratamos os demais erros.
			if (err instanceof ApiClientError && err.code === 'unauthenticated') return;
			errorMessage =
				err instanceof Error ? err.message : 'Falha ao carregar o dashboard.';
			loadState = 'error';
		}
	}

	// Carrega no mount e RECARREGA sempre que o escopo de orgao mudar. Ler
	// `$orgaoScopeQuery` aqui registra a dependencia reativa do effect.
	$effect(() => {
		void $orgaoScopeQuery;
		void load();
	});

	// --- Apresentacao do hero (read-only) ---
	// Nome de boas-vindas: espelha {{ current_user_obj.name or username }} do
	// template Jinja (read-only do store de auth, sem alterar logica).
	const welcomeName = $derived(
		$auth.user?.name?.trim() || $auth.user?.username || ''
	);
	const isAdmin = $derived($auth.user?.is_admin ?? false);
	// Contexto sob o nome: "Administrador" ou siglas de orgao (read-only).
	const welcomeContext = $derived(
		isAdmin
			? 'Administrador'
			: ($auth.user?.orgaos ?? []).map((o) => o.sigla).join(' › ') ||
					'Sem órgão vinculado'
	);

	// Data "Hoje" formatada em pt-BR, identica ao script do index.html original
	// (Intl.DateTimeFormat com weekday/day/month/year, 1a letra maiuscula).
	// Puramente decorativa/informativa — nenhuma logica de dominio.
	function formatToday(now: Date): string {
		try {
			const raw = new Intl.DateTimeFormat('pt-BR', {
				weekday: 'long',
				day: '2-digit',
				month: 'long',
				year: 'numeric'
			}).format(now);
			return raw.charAt(0).toUpperCase() + raw.slice(1);
		} catch {
			const day = String(now.getDate()).padStart(2, '0');
			const month = String(now.getMonth() + 1).padStart(2, '0');
			return `${day}/${month}/${now.getFullYear()}`;
		}
	}
	let todayLabel = $state('--');
	onMount(() => {
		todayLabel = formatToday(new Date());
	});

	// "Novo Projeto" em 1 clique: abre o modal de criacao AQUI no Dashboard (sem
	// navegar para /projetos). As opcoes do formulario vivem no payload de
	// /api/projetos; buscamos sob demanda na primeira abertura e reaproveitamos.
	let createModalOpen = $state(false);
	let createOptions = $state<ProjectsListOptions | null>(null);
	let openingCreate = $state(false);

	async function openCreateModal(): Promise<void> {
		if (openingCreate) return;
		if (!createOptions) {
			openingCreate = true;
			try {
				const projectsData = await fetchProjects({});
				createOptions = projectsData.options;
			} catch (err) {
				flash.danger(
					err instanceof Error
						? err.message
						: 'Falha ao preparar o formulário de novo projeto.'
				);
				return;
			} finally {
				openingCreate = false;
			}
		}
		createModalOpen = true;
	}

	// Pos-criacao: mesmo fluxo da tela de projetos — fecha, avisa e vai ao projeto.
	function onProjectCreated(result: CreateProjectResult): void {
		createModalOpen = false;
		flash.success(result.message);
		const target = result.redirect_to.startsWith('/')
			? `${base}${result.redirect_to}`
			: result.redirect_to;
		void goto(target);
	}

	// --- Apresentacao do painel de tarefas (read-only) ---
	// Larguras dos segmentos da barra empilhada, em %, derivadas dos contadores
	// ja carregados (mesmo calculo do template Jinja: contagem/total * 100). E
	// formatacao visual da barra de progresso, nao logica de dominio.
	function pct(part: number, total: number): number {
		if (total <= 0) return 0;
		return Math.round((part / total) * 1000) / 10;
	}
	// Prioridades de tarefas em aberto (espelha `tasks-kpi-priority-row` do
	// original): cada linha vira link para /tarefas filtrado por prioridade.
	const taskPriorities = $derived.by(() => {
		const d = data;
		if (!d) return [] as { key: string; label: string; count: number; dot: string }[];
		return [
			{ key: 'urgente', label: 'Urgente', count: d.task_urgente_count, dot: 'bg-danger' },
			{ key: 'alta', label: 'Alta', count: d.task_alta_count, dot: 'bg-orange' },
			{ key: 'media', label: 'Média', count: d.task_media_count, dot: 'bg-primary-600' },
			{ key: 'baixa', label: 'Baixa', count: d.task_baixa_count, dot: 'bg-text-muted' }
		];
	});

	// Cor da pilula de prioridade na mini-lista de recentes (espelha
	// `tasks-kpi-recent-badge badge-*` do original; tons via tokens semanticos).
	const taskBadgeClass: Record<string, string> = {
		urgente: 'bg-surface-muted text-danger',
		alta: 'bg-surface-muted text-orange',
		media: 'bg-surface-muted text-primary-700',
		baixa: 'bg-surface-muted text-success'
	};

	// Status do indicador de cada tarefa recente -> classe de cor do ponto.
	const recentStatusDot: Record<string, string> = {
		finalizada: 'bar-finalizada',
		em_andamento: 'bar-em-andamento',
		para_validacao: 'bar-para-validacao',
		para_ajustes: 'bar-para-ajustes',
		nao_iniciada: 'bar-nao-iniciada'
	};

	const statusBar = $derived.by(() => {
		const d = data;
		if (!d) return [] as { key: string; filter: string; label: string; count: number; width: number; bar: string }[];
		const total = d.task_items_total;
		const finalizada = pct(d.task_items_finalizada, total);
		const andamento = pct(d.task_items_em_andamento, total);
		const validacao = pct(d.task_items_para_validacao, total);
		const ajustes = pct(d.task_items_para_ajustes, total);
		const naoIniciada =
			Math.round((100 - finalizada - andamento - validacao - ajustes) * 10) / 10;
		// `filter` usa o valor de status do backend (com underscore) consumido
		// por /tarefas; `key` (com hifen) e so a chave de iteracao/CSS.
		return [
			{ key: 'finalizada', filter: 'finalizada', label: 'Concluída', count: d.task_items_finalizada, width: finalizada, bar: 'bar-finalizada' },
			{ key: 'em-andamento', filter: 'em_andamento', label: 'Andamento', count: d.task_items_em_andamento, width: andamento, bar: 'bar-em-andamento' },
			{ key: 'para-validacao', filter: 'para_validacao', label: 'Validação', count: d.task_items_para_validacao, width: validacao, bar: 'bar-para-validacao' },
			{ key: 'para-ajustes', filter: 'para_ajustes', label: 'Ajustes', count: d.task_items_para_ajustes, width: ajustes, bar: 'bar-para-ajustes' },
			{ key: 'nao-iniciada', filter: 'nao_iniciada', label: 'N. iniciada', count: d.task_items_nao_iniciada, width: naoIniciada, bar: 'bar-nao-iniciada' }
		];
	});
</script>

<svelte:head>
	<title>Dashboard — ProjetosRJ</title>
</svelte:head>

<section aria-labelledby="dashboard-title" class="flex flex-col gap-4">
	<!-- Hero "Olá, <nome> / Administrador" + data + Novo Projeto -->
	<PageHeader subtitle={welcomeContext} labelId="dashboard-title">
		{#snippet titleContent()}
			<span class="mr-1 font-semibold text-text-secondary">Olá,</span>
			<span>{welcomeName}</span>
		{/snippet}
		{#snippet actions()}
			<div class="flex flex-col items-end gap-0.5 text-right">
				<span class="text-2xs font-bold uppercase tracking-caps text-text-muted">Hoje</span>
				<span class="text-md font-semibold text-primary-600">{todayLabel}</span>
			</div>
			<Button onclick={openCreateModal} disabled={openingCreate}>
				{#snippet icon()}
					<i class="fas fa-plus" aria-hidden="true"></i>
				{/snippet}
				Novo Projeto
			</Button>
		{/snippet}
	</PageHeader>

	{#if loadState === 'loading'}
		<p role="status" aria-live="polite" class="text-text-secondary">
			Carregando dados…
		</p>
	{:else if loadState === 'error'}
		<LoadErrorState message={errorMessage} onRetry={load} />
	{:else if data}
		<!-- KPI cards: ícone + cor + subtítulo, ordem fiel ao index.html -->
		<section aria-label="Indicadores de projetos">
			<div class="grid grid-cols-2 gap-3 lg:grid-cols-4">
				<StatCard
					label="Projetos"
					value={data.num_projects}
					tone="primary"
					subtitle="Todos os projetos cadastrados"
					href={`${base}/projetos`}
					linkLabel="Ver todos os projetos"
				>
					{#snippet icon()}
						<i class="fas fa-folder-open fa-lg" aria-hidden="true"></i>
					{/snippet}
				</StatCard>

				<StatCard
					label="Concluídos"
					value={data.count_finalizado}
					tone="success"
					subtitle="Projetos finalizados com sucesso"
					href={`${base}/projetos?status=Finalizado`}
					linkLabel="Ver projetos finalizados"
				>
					{#snippet icon()}
						<i class="fas fa-check-circle fa-lg" aria-hidden="true"></i>
					{/snippet}
				</StatCard>

				<StatCard
					label="Vigentes"
					value={data.count_vigente}
					tone="warning"
					subtitle="Projetos em andamento"
					href={`${base}/projetos?status=Vigente`}
					linkLabel="Ver projetos vigentes"
				>
					{#snippet icon()}
						<i class="fas fa-clock fa-lg" aria-hidden="true"></i>
					{/snippet}
				</StatCard>

				<StatCard
					label="Em Atraso"
					value={data.projetos_em_atraso}
					tone="danger"
					subtitle="Necessitam atenção imediata"
					href={`${base}/projetos?atraso=atrasado`}
					linkLabel="Ver projetos em atraso"
				>
					{#snippet icon()}
						<i class="fas fa-exclamation-triangle fa-lg" aria-hidden="true"></i>
					{/snippet}
				</StatCard>
			</div>
		</section>

		<!-- Layout 2 colunas: projetos recentes (esq) + tarefas (dir).
			 items-stretch (padrao do grid) faz as duas colunas terem a MESMA
			 altura; o painel de recentes rola internamente (scroll-lock) e o de
			 tarefas se alinha ao lado, como no index.html original. -->
		<div class="grid grid-cols-1 items-stretch gap-4 lg:grid-cols-3">
			<div class="lg:col-span-2">
				<RecentProjectsPanel projects={data.recent_projects} totalProjects={data.num_projects} />
			</div>

			<aside class="flex flex-col lg:col-span-1">
				<Card title="Tarefas" labelId="dashboard-tasks-title">
					{#snippet header()}
						<a
							href={`${base}/tarefas`}
							class="inline-flex items-center gap-1 text-xs font-semibold text-primary-600 no-underline transition-colors duration-fast hover:text-primary-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
						>
							Ver todas
							<i class="fas fa-arrow-right" aria-hidden="true"></i>
						</a>
					{/snippet}

					<div class="flex flex-col gap-5">
						<!-- Por prioridade: cada linha e um link para /tarefas filtrado
							 (espelha os `tasks-kpi-priority-row` clicaveis do original). -->
						<section class="flex flex-col gap-2" aria-label="Tarefas por prioridade">
							<div class="flex items-center justify-between">
								<span class="text-sm font-bold text-text-secondary">Por prioridade</span>
								<span class="text-xs font-semibold text-text-muted">{data.dashboard_open_tasks_count} abertas</span>
							</div>
							<div class="grid grid-cols-4 gap-1.5">
								{#each taskPriorities as prio (prio.key)}
									<a
										href={`${base}/tarefas?prioridade=${prio.key}`}
										class="flex min-h-[46px] flex-col items-start justify-center gap-1 rounded-md border border-border-subtle bg-surface-muted px-2 py-1.5 no-underline transition-colors duration-fast hover:border-primary-500 hover:bg-surface focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
									>
										<span class="flex items-center gap-1.5">
											<span class="h-2 w-2 shrink-0 rounded-full {prio.dot}" aria-hidden="true"></span>
											<span class="truncate text-xs font-semibold text-text-secondary">{prio.label}</span>
										</span>
										<span class="text-sm font-bold text-text-primary">{prio.count}</span>
									</a>
								{/each}
							</div>
						</section>

						<!-- Por status: barra empilhada de progresso + legenda. Segmentos
							 e itens de legenda sao links para /tarefas filtrado por status
							 (espelha os segmentos clicaveis + tooltips do original). -->
						<section class="flex flex-col gap-2" aria-label="Tarefas por status">
							<div class="flex items-center justify-between">
								<span class="text-sm font-bold text-text-secondary">Por status</span>
								<span class="text-xs font-semibold text-text-muted">{data.task_items_total} total</span>
							</div>
							<div
								class="flex h-4 overflow-hidden rounded-sm border border-border-subtle bg-surface-muted"
								role="group"
								aria-label="Distribuição de tarefas por status"
							>
								{#if data.task_items_total > 0}
									{#each statusBar as seg (seg.key)}
										<a
											href={`${base}/tarefas?status=${seg.filter}`}
											class="status-seg block h-full {seg.bar}"
											style="width: {seg.width}%"
											title="{seg.label}: {seg.count}"
											aria-label="Ver tarefas: {seg.label} ({seg.count})"
										></a>
									{/each}
								{/if}
							</div>
							<ul class="flex flex-wrap gap-x-3 gap-y-1" aria-label="Legenda por status">
								{#each statusBar as seg (seg.key)}
									<li>
										<a
											href={`${base}/tarefas?status=${seg.filter}`}
											class="inline-flex items-center gap-1 text-2xs font-medium text-text-secondary no-underline transition-colors duration-fast hover:text-primary-600 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
										>
											<span class="h-2 w-2 shrink-0 rounded-full {seg.bar}" aria-hidden="true"></span>
											{seg.label}
										</a>
									</li>
								{/each}
							</ul>
						</section>

						<!-- Recentes: mini-lista das ultimas tarefas (espelha
							 `tasks-kpi-recent-list` do original). Cada item leva a /tarefas
							 com a tarefa em foco; rola internamente se exceder a altura. -->
						{#if data.recent_tasks.length > 0}
							<section class="flex flex-col gap-2" aria-label="Tarefas recentes">
								<span class="text-sm font-bold text-text-secondary">Recentes</span>
								<div class="flex max-h-72 flex-col gap-1 overflow-y-auto">
									{#each data.recent_tasks as t (t.id)}
										<a
											href={`${base}/tarefas?focus_task=${t.id}`}
											title={t.descricao}
											class="flex items-center gap-2 rounded-md border border-transparent px-2 py-1.5 no-underline transition-colors duration-fast hover:border-border-subtle hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
										>
											<span
												class="h-2 w-2 shrink-0 rounded-full {recentStatusDot[t.status] ?? 'bg-text-muted'}"
												aria-hidden="true"
											></span>
											<span class="flex min-w-0 flex-1 flex-col">
												<span class="truncate text-xs font-medium text-text-primary">{t.descricao}</span>
												<span class="truncate text-2xs text-text-muted">
													{t.project_titulo ?? (t.project_id ? `Projeto #${t.project_id}` : 'Sem projeto vinculado')}
												</span>
											</span>
											{#if t.prioridade}
												<span
													class="shrink-0 rounded-sm px-1.5 py-0.5 text-2xs font-bold uppercase tracking-wide {taskBadgeClass[t.prioridade] ?? 'bg-surface-muted text-text-secondary'}"
												>
													{t.prioridade}
												</span>
											{/if}
										</a>
									{/each}
								</div>
							</section>
						{/if}
					</div>
				</Card>
			</aside>
		</div>

		<!-- Footer SETD -->
		<footer class="pt-2 text-center text-xs text-text-muted">
			SETD — Subsecretaria de Estado de Tecnologia Digital
		</footer>
	{/if}

	<!-- Modal de criação aberto no proprio Dashboard (sem navegar para /projetos). -->
	<CriarProjetoModal
		open={createModalOpen}
		options={createOptions}
		onClose={() => (createModalOpen = false)}
		onCreated={onProjectCreated}
	/>
</section>

<style>
	/* Cores dos segmentos da barra de status e dos pontos da legenda.
	   Valores 1:1 do index.css original (.bar-* / status dots); mapeados aos
	   tokens semanticos para trocarem sozinhos no dark mode. */
	:global(.bar-finalizada) {
		background-color: var(--ds-color-success-600);
	}
	:global(.bar-em-andamento) {
		background-color: var(--ds-color-primary-600);
	}
	:global(.bar-para-validacao) {
		background-color: var(--ds-color-warning-600);
	}
	:global(.bar-para-ajustes) {
		background-color: var(--ds-color-orange-600);
	}
	:global(.bar-nao-iniciada) {
		background-color: var(--color-text-muted);
	}

	/* Animacao da barra empilhada: transicao de largura 0.4s ease, igual ao
	   .tasks-kpi-bar-segment original. */
	.status-seg {
		min-width: 2px;
		transition: width 0.4s ease;
	}
</style>
