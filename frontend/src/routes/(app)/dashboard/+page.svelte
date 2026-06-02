<script lang="ts">
	/**
	 * Tela Dashboard (PILOTO). Consome `GET /api/dashboard` e renderiza
	 * contadores + projetos recentes. Acessivel: regiao com heading, estados de
	 * loading/erro anunciados via aria-live, foco gerenciado pelo fluxo natural.
	 */
	import { onMount } from 'svelte';
	import { base } from '$app/paths';
	import { fetchDashboard } from '$lib/api/dashboard';
	import { ApiClientError } from '$lib/api/client';
	import { auth } from '$lib/stores/auth';
	import type { DashboardData } from '$lib/types/dashboard';
	import StatCard from '$lib/components/StatCard.svelte';
	import RecentProjectsPanel from '$lib/components/RecentProjectsPanel.svelte';
	import Card from '$lib/components/Card.svelte';
	import Button from '$lib/components/Button.svelte';
	import LoadErrorState from '$lib/components/LoadErrorState.svelte';

	type LoadState = 'loading' | 'ready' | 'error';

	let loadState = $state<LoadState>('loading');
	let data = $state<DashboardData | null>(null);
	let errorMessage = $state<string>('');

	async function load(): Promise<void> {
		loadState = 'loading';
		errorMessage = '';
		try {
			data = await fetchDashboard();
			loadState = 'ready';
		} catch (err) {
			// 401 ja redirecionou; aqui tratamos os demais erros.
			if (err instanceof ApiClientError && err.code === 'unauthenticated') return;
			errorMessage =
				err instanceof Error ? err.message : 'Falha ao carregar o dashboard.';
			loadState = 'error';
		}
	}

	onMount(() => {
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

	// --- Apresentacao do painel de tarefas (read-only) ---
	// Larguras dos segmentos da barra empilhada, em %, derivadas dos contadores
	// ja carregados (mesmo calculo do template Jinja: contagem/total * 100). E
	// formatacao visual da barra de progresso, nao logica de dominio.
	function pct(part: number, total: number): number {
		if (total <= 0) return 0;
		return Math.round((part / total) * 1000) / 10;
	}
	const statusBar = $derived.by(() => {
		const d = data;
		if (!d) return [] as { key: string; label: string; count: number; width: number; bar: string }[];
		const total = d.task_items_total;
		const finalizada = pct(d.task_items_finalizada, total);
		const andamento = pct(d.task_items_em_andamento, total);
		const validacao = pct(d.task_items_para_validacao, total);
		const ajustes = pct(d.task_items_para_ajustes, total);
		const naoIniciada =
			Math.round((100 - finalizada - andamento - validacao - ajustes) * 10) / 10;
		return [
			{ key: 'finalizada', label: 'Concluída', count: d.task_items_finalizada, width: finalizada, bar: 'bar-finalizada' },
			{ key: 'em-andamento', label: 'Andamento', count: d.task_items_em_andamento, width: andamento, bar: 'bar-em-andamento' },
			{ key: 'para-validacao', label: 'Validação', count: d.task_items_para_validacao, width: validacao, bar: 'bar-para-validacao' },
			{ key: 'para-ajustes', label: 'Ajustes', count: d.task_items_para_ajustes, width: ajustes, bar: 'bar-para-ajustes' },
			{ key: 'nao-iniciada', label: 'N. iniciada', count: d.task_items_nao_iniciada, width: naoIniciada, bar: 'bar-nao-iniciada' }
		];
	});
</script>

<svelte:head>
	<title>Dashboard — ProjetosRJ</title>
</svelte:head>

<section aria-labelledby="dashboard-title" class="flex flex-col gap-4">
	<!-- Hero "Olá, <nome> / Administrador" + data + Novo Projeto -->
	<header
		class="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-border-subtle bg-surface px-4 py-3 shadow-sm"
	>
		<div class="min-w-0 flex-1">
			<h1
				id="dashboard-title"
				class="truncate font-heading text-3xl font-bold leading-tight text-primary-700"
			>
				<span class="mr-1 font-semibold text-text-secondary">Olá,</span>
				<span>{welcomeName}</span>
			</h1>
			<p class="mt-1 truncate text-sm font-medium {isAdmin ? 'text-primary-600' : 'text-text-muted'}">
				{welcomeContext}
			</p>
		</div>

		<div class="flex shrink-0 items-center gap-4">
			<div class="flex flex-col items-end gap-0.5 text-right">
				<span class="text-2xs font-bold uppercase tracking-caps text-text-muted">Hoje</span>
				<span class="text-md font-semibold text-primary-600">{todayLabel}</span>
			</div>
			<Button href={`${base}/projetos`}>
				{#snippet icon()}
					<svg
						aria-hidden="true"
						class="h-4 w-4"
						viewBox="0 0 20 20"
						fill="none"
						stroke="currentColor"
						stroke-width="2"
						stroke-linecap="round"
						stroke-linejoin="round"
					>
						<line x1="10" y1="4" x2="10" y2="16" />
						<line x1="4" y1="10" x2="16" y2="10" />
					</svg>
				{/snippet}
				Novo Projeto
			</Button>
		</div>
	</header>

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
				>
					{#snippet icon()}
						<svg aria-hidden="true" class="h-5 w-5" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
							<path d="M2 5.5A1.5 1.5 0 0 1 3.5 4h3.4a1.5 1.5 0 0 1 1.06.44l.94.94A1.5 1.5 0 0 0 11 5.8h5.5A1.5 1.5 0 0 1 18 7.3v1.2" />
							<path d="M2.4 9h15.2a1 1 0 0 1 .98 1.2l-1.1 5A1.5 1.5 0 0 1 16 16.5H4a1.5 1.5 0 0 1-1.48-1.3l-1.1-5.0A1 1 0 0 1 2.4 9Z" />
						</svg>
					{/snippet}
				</StatCard>

				<StatCard
					label="Concluídos"
					value={data.count_finalizado}
					tone="success"
					subtitle="Projetos finalizados com sucesso"
				>
					{#snippet icon()}
						<svg aria-hidden="true" class="h-5 w-5" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
							<circle cx="10" cy="10" r="7.5" />
							<path d="m6.5 10 2.2 2.2L13.5 7.5" />
						</svg>
					{/snippet}
				</StatCard>

				<StatCard
					label="Vigentes"
					value={data.count_vigente}
					tone="warning"
					subtitle="Projetos em andamento"
				>
					{#snippet icon()}
						<svg aria-hidden="true" class="h-5 w-5" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
							<circle cx="10" cy="10" r="7.5" />
							<path d="M10 5.5V10l3 1.8" />
						</svg>
					{/snippet}
				</StatCard>

				<StatCard
					label="Em Atraso"
					value={data.projetos_em_atraso}
					tone="danger"
					subtitle="Necessitam atenção imediata"
				>
					{#snippet icon()}
						<svg aria-hidden="true" class="h-5 w-5" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
							<path d="M10 2.5 18.5 17h-17L10 2.5Z" />
							<line x1="10" y1="8" x2="10" y2="12" />
							<line x1="10" y1="14.5" x2="10" y2="14.6" />
						</svg>
					{/snippet}
				</StatCard>
			</div>
		</section>

		<!-- Layout 2 colunas: projetos recentes (esq) + tarefas (dir) -->
		<div class="grid grid-cols-1 gap-4 lg:grid-cols-3">
			<div class="lg:col-span-2">
				<RecentProjectsPanel projects={data.recent_projects} />
			</div>

			<aside class="lg:col-span-1">
				<Card title="Tarefas" labelId="dashboard-tasks-title">
					{#snippet header()}
						<a
							href={`${base}/tarefas`}
							class="inline-flex items-center gap-1 text-xs font-semibold text-primary-600 no-underline transition-colors duration-fast hover:text-primary-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
						>
							Ver todas
							<svg aria-hidden="true" class="h-3.5 w-3.5" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
								<line x1="4" y1="10" x2="15" y2="10" />
								<path d="m11 6 4 4-4 4" />
							</svg>
						</a>
					{/snippet}

					<div class="flex flex-col gap-5">
						<!-- Por prioridade -->
						<section class="flex flex-col gap-2" aria-label="Tarefas por prioridade">
							<div class="flex items-center justify-between">
								<span class="text-sm font-bold text-text-secondary">Por prioridade</span>
								<span class="text-xs font-semibold text-text-muted">{data.dashboard_open_tasks_count} abertas</span>
							</div>
							<div class="grid grid-cols-4 gap-1.5">
								<div class="flex min-h-[46px] flex-col items-start justify-center gap-1 rounded-md border border-border-subtle bg-surface-muted px-2 py-1.5">
									<span class="flex items-center gap-1.5">
										<span class="h-2 w-2 shrink-0 rounded-full bg-danger" aria-hidden="true"></span>
										<span class="truncate text-xs font-semibold text-text-secondary">Urgente</span>
									</span>
									<span class="text-sm font-bold text-text-primary">{data.task_urgente_count}</span>
								</div>
								<div class="flex min-h-[46px] flex-col items-start justify-center gap-1 rounded-md border border-border-subtle bg-surface-muted px-2 py-1.5">
									<span class="flex items-center gap-1.5">
										<span class="h-2 w-2 shrink-0 rounded-full bg-orange" aria-hidden="true"></span>
										<span class="truncate text-xs font-semibold text-text-secondary">Alta</span>
									</span>
									<span class="text-sm font-bold text-text-primary">{data.task_alta_count}</span>
								</div>
								<div class="flex min-h-[46px] flex-col items-start justify-center gap-1 rounded-md border border-border-subtle bg-surface-muted px-2 py-1.5">
									<span class="flex items-center gap-1.5">
										<span class="h-2 w-2 shrink-0 rounded-full bg-primary-600" aria-hidden="true"></span>
										<span class="truncate text-xs font-semibold text-text-secondary">Média</span>
									</span>
									<span class="text-sm font-bold text-text-primary">{data.task_media_count}</span>
								</div>
								<div class="flex min-h-[46px] flex-col items-start justify-center gap-1 rounded-md border border-border-subtle bg-surface-muted px-2 py-1.5">
									<span class="flex items-center gap-1.5">
										<span class="h-2 w-2 shrink-0 rounded-full bg-text-muted" aria-hidden="true"></span>
										<span class="truncate text-xs font-semibold text-text-secondary">Baixa</span>
									</span>
									<span class="text-sm font-bold text-text-primary">{data.task_baixa_count}</span>
								</div>
							</div>
						</section>

						<!-- Por status: barra empilhada de progresso + legenda -->
						<section class="flex flex-col gap-2" aria-label="Tarefas por status">
							<div class="flex items-center justify-between">
								<span class="text-sm font-bold text-text-secondary">Por status</span>
								<span class="text-xs font-semibold text-text-muted">{data.task_items_total} total</span>
							</div>
							<div
								class="flex h-4 overflow-hidden rounded-sm border border-border-subtle bg-surface-muted"
								role="img"
								aria-label="Distribuição de tarefas por status"
							>
								{#if data.task_items_total > 0}
									{#each statusBar as seg (seg.key)}
										<span
											class="status-seg block h-full {seg.bar}"
											style="width: {seg.width}%"
											title="{seg.label}: {seg.count}"
											aria-hidden="true"
										></span>
									{/each}
								{/if}
							</div>
							<ul class="flex flex-wrap gap-x-3 gap-y-1" aria-label="Legenda por status">
								{#each statusBar as seg (seg.key)}
									<li class="inline-flex items-center gap-1 text-2xs font-medium text-text-secondary">
										<span class="h-2 w-2 shrink-0 rounded-full {seg.bar}" aria-hidden="true"></span>
										{seg.label}
									</li>
								{/each}
							</ul>
						</section>
					</div>
				</Card>
			</aside>
		</div>

		<!-- Footer SETD -->
		<footer class="pt-2 text-center text-xs text-text-muted">
			SETD — Subsecretaria de Estado de Tecnologia Digital
		</footer>
	{/if}
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
