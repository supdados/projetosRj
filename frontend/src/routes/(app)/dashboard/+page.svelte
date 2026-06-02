<script lang="ts">
	/**
	 * Tela Dashboard (PILOTO). Consome `GET /api/dashboard` e renderiza
	 * contadores + projetos recentes. Acessivel: regiao com heading, estados de
	 * loading/erro anunciados via aria-live, foco gerenciado pelo fluxo natural.
	 */
	import { onMount } from 'svelte';
	import { fetchDashboard } from '$lib/api/dashboard';
	import { ApiClientError } from '$lib/api/client';
	import type { DashboardData } from '$lib/types/dashboard';
	import StatCard from '$lib/components/StatCard.svelte';
	import RecentProjectsPanel from '$lib/components/RecentProjectsPanel.svelte';
	import Card from '$lib/components/Card.svelte';
	import Badge from '$lib/components/Badge.svelte';

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
</script>

<svelte:head>
	<title>Dashboard — ProjetosRJ</title>
</svelte:head>

<section aria-labelledby="dashboard-title" class="flex flex-col gap-6">
	<h1 id="dashboard-title" class="font-heading text-2xl font-bold text-text-primary">
		Dashboard
	</h1>

	{#if loadState === 'loading'}
		<p role="status" aria-live="polite" class="text-text-secondary">
			Carregando dados…
		</p>
	{:else if loadState === 'error'}
		<div
			role="alert"
			class="flex flex-col items-start gap-3 rounded-lg border border-danger bg-surface px-5 py-4"
		>
			<p class="text-text-primary">{errorMessage}</p>
			<button
				type="button"
				onclick={load}
				class="rounded-md border border-border-subtle bg-surface px-4 py-2 text-sm font-medium text-text-primary transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
			>
				Tentar novamente
			</button>
		</div>
	{:else if data}
		<!-- Contadores de projetos -->
		<section aria-labelledby="proj-stats-title" class="flex flex-col gap-3">
			<h2 id="proj-stats-title" class="text-sm font-semibold uppercase tracking-wide text-text-muted">
				Projetos
			</h2>
			<div class="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
				<StatCard label="Total" value={data.num_projects} tone="primary" />
				<StatCard label="Vigentes" value={data.count_vigente} tone="success" />
				<StatCard label="Finalizados" value={data.count_finalizado} />
				<StatCard label="Em atraso" value={data.projetos_em_atraso} tone="danger" />
			</div>
		</section>

		<!-- Contadores de tarefas -->
		<section aria-labelledby="task-stats-title" class="flex flex-col gap-3">
			<h2 id="task-stats-title" class="text-sm font-semibold uppercase tracking-wide text-text-muted">
				Tarefas em aberto
			</h2>
			<div class="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
				<StatCard label="Abertas" value={data.dashboard_open_tasks_count} tone="primary" />
				<StatCard label="Urgentes" value={data.task_urgente_count} tone="danger" />
				<StatCard label="Alta prioridade" value={data.task_alta_count} tone="warning" />
				<StatCard label="Atenção" value={data.task_atencao_count} tone="warning" />
			</div>
		</section>

		<!-- Distribuicao por status (tarefas) -->
		<Card title="Tarefas por status" labelId="task-status-title">
			<ul class="flex flex-wrap gap-2" aria-labelledby="task-status-title">
				<li><Badge tone="neutral">Não iniciadas: {data.task_items_nao_iniciada}</Badge></li>
				<li><Badge tone="info">Em andamento: {data.task_items_em_andamento}</Badge></li>
				<li><Badge tone="warning">Para validação: {data.task_items_para_validacao}</Badge></li>
				<li><Badge tone="warning">Para ajustes: {data.task_items_para_ajustes}</Badge></li>
				<li><Badge tone="success">Finalizadas: {data.task_items_finalizada}</Badge></li>
			</ul>
		</Card>

		<RecentProjectsPanel projects={data.recent_projects} />
	{/if}
</section>
