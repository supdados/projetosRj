<script lang="ts">
	/**
	 * Tela Dashboard (PILOTO). Consome `GET /api/dashboard` e renderiza
	 * contadores + projetos recentes. Acessivel: regiao com heading, estados de
	 * loading/erro anunciados via aria-live, foco gerenciado pelo fluxo natural.
	 */
	import { onMount } from 'svelte';
	import { base } from '$app/paths';
	import { goto } from '$app/navigation';
	import { fetchDashboard, peekDashboard } from '$lib/api/dashboard';
	import { ApiClientError } from '$lib/api/client';
	import { auth } from '$lib/stores/auth';
	import { orgaoScopeQuery } from '$lib/stores/orgaoScope';
	import type { DashboardData } from '$lib/types/dashboard';
	import StatCard from '$lib/components/StatCard.svelte';
	import AppIcon from '$lib/components/AppIcon.svelte';
	import TaskTipoIcon from '$lib/components/TaskTipoIcon.svelte';
	import FolderReveal from '$lib/components/micro/FolderReveal.svelte';
	import ClipboardStamp from '$lib/components/micro/ClipboardStamp.svelte';
	import FolderPeek from '$lib/components/micro/FolderPeek.svelte';
	import AlertHourglass from '$lib/components/micro/AlertHourglass.svelte';
	import RecentProjectsPanel from '$lib/components/RecentProjectsPanel.svelte';
	import AssigneeAvatar from '$lib/components/AssigneeAvatar.svelte';
	import { statusLabel } from '$lib/utils/taskLabels';
	import Card from '$lib/components/Card.svelte';
	import Button from '$lib/components/Button.svelte';
	import PageHeader from '$lib/components/PageHeader.svelte';
	import LoadErrorState from '$lib/components/LoadErrorState.svelte';
	import DashboardSkeleton from '$lib/components/DashboardSkeleton.svelte';
	import CriarProjetoModal from '$lib/components/CriarProjetoModal.svelte';
	import { fetchProjects, type CreateProjectResult } from '$lib/api/projects';
	import { flash } from '$lib/stores/flash';
	import type { ProjectsListOptions } from '$lib/types/projects';

	type LoadState = 'loading' | 'ready' | 'error';

	// SWR: reabre com o ultimo dado bom do escopo corrente (cache de modulo em
	// $lib/api/dashboard) e revalida em background — sem flash de loading ao
	// voltar para a rota. O skeleton so aparece quando NAO ha cache (1a visita
	// ou escopo de orgao nunca carregado).
	const initialData = peekDashboard($orgaoScopeQuery);
	let data = $state<DashboardData | null>(initialData);
	let loadState = $state<LoadState>(initialData ? 'ready' : 'loading');
	let errorMessage = $state<string>('');

	// Aborta a busca anterior quando o escopo muda durante um carregamento em
	// voo, evitando que uma resposta atrasada sobrescreva a mais recente.
	let inFlight: AbortController | null = null;

	async function load(): Promise<void> {
		inFlight?.abort();
		const controller = new AbortController();
		inFlight = controller;

		// SWR: com cache do escopo mostra o dado antigo ja (sem skeleton) e a
		// revalidacao abaixo troca em silencio; sem cache, skeleton.
		const cached = peekDashboard($orgaoScopeQuery);
		if (cached) {
			data = cached;
			loadState = 'ready';
		} else {
			loadState = 'loading';
		}
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
			const message =
				err instanceof Error ? err.message : 'Falha ao carregar o dashboard.';
			// Revalidacao falhou com dado stale na tela: mantem o dado e avisa via
			// flash, em vez de trocar o dashboard inteiro pelo painel de erro.
			if (data) {
				flash.danger(message);
				return;
			}
			errorMessage = message;
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
	const welcomeName = $derived(
		$auth.user?.name?.trim() || $auth.user?.username || ''
	);
	const isAdmin = $derived($auth.user?.is_admin ?? false);
	// Contexto sob o nome: "Administrador" ou siglas de orgao (read-only).
	const welcomeContext = $derived(
		isAdmin
			? 'Administrador'
			: ($auth.user?.orgaos ?? []).map((o) => o.sigla).join(' › ') ||
					'Sem área vinculada'
	);

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

	/** Sucesso dispensado sem "Ver o projeto": flash + contadores atualizados. */
	function onProjectCreatedDismissed(result: CreateProjectResult): void {
		flash.success(result.message);
		void load();
	}

	// --- Apresentacao do painel de tarefas (read-only) ---
	// Transposicao do mock "concept4": anel de % concluido + legenda por status,
	// chips "Por tipo" e mini-lista de recentes (tipo/comentarios/anexos/avatar).
	// Tudo derivado dos contadores ja carregados — sem logica de dominio nova.

	// Anel de progresso (donut) RESPONSIVO: o SVG usa um viewBox em unidades fixas
	// (`RING_VIEW`) e escala via CSS (largura em clamp + container queries para a
	// fonte interna). Rotacionado -90deg para o 1o segmento comecar no topo.
	const RING_VIEW = 100;
	const RING_STROKE = 11;

	// Ordem + cores dos 5 status. Cada fatia usa o token de PAPEL da sua categoria
	// (--ds-color-slice-*), calibrado para leitura lado a lado no donut. Os rotulos
	// vem de `statusLabel` (mesma fonte do drop de selecao em tarefas).
	const STATUS_ORDER = [
		{ key: 'finalizada', color: 'var(--ds-color-slice-finalizada)' },
		{ key: 'em_andamento', color: 'var(--ds-color-slice-andamento)' },
		{ key: 'para_validacao', color: 'var(--ds-color-slice-validacao)' },
		{ key: 'para_ajustes', color: 'var(--ds-color-slice-ajustes)' },
		{ key: 'nao_iniciada', color: 'var(--ds-color-slice-nao-iniciada)' }
	] as const;

	const statusCounts = $derived.by(() => ({
		finalizada: data?.task_items_finalizada ?? 0,
		em_andamento: data?.task_items_em_andamento ?? 0,
		para_validacao: data?.task_items_para_validacao ?? 0,
		para_ajustes: data?.task_items_para_ajustes ?? 0,
		nao_iniciada: data?.task_items_nao_iniciada ?? 0
	}));

	const statusLegend = $derived(
		STATUS_ORDER.map((s) => ({ ...s, label: statusLabel(s.key), count: statusCounts[s.key] }))
	);

	// % concluido (finalizada / total). 0 quando nao ha tarefas.
	const donutPct = $derived.by(() => {
		const total = data?.task_items_total ?? 0;
		return total > 0 ? Math.round((statusCounts.finalizada / total) * 100) : 0;
	});

	// Segmentos do anel: comprimento/offset proporcionais a cada status (com um
	// pequeno gap entre arcos). Segmentos vazios sao omitidos.
	const ring = $derived.by(() => {
		const total = data?.task_items_total ?? 0;
		const r = (RING_VIEW - RING_STROKE) / 2;
		const C = 2 * Math.PI * r;
		const gap = 2;
		const segs: { color: string; dash: string; offset: number }[] = [];
		if (total > 0) {
			let acc = 0;
			for (const s of STATUS_ORDER) {
				const n = statusCounts[s.key];
				if (n > 0) {
					const len = Math.max(0, (n / total) * C - gap);
					segs.push({ color: s.color, dash: `${len} ${C}`, offset: -((acc / total) * C) });
				}
				acc += n;
			}
		}
		return { r, C, segs };
	});

	// Icone/cor de tipo de pedido moram em TaskTipoIcon (bloco T-A do design).
	const TYPE_LABEL: Record<string, string> = {
		bug: 'Bug',
		melhoria: 'Melhoria',
		duvida: 'Dúvida'
	};
	// "outros" NAO vira chip em "Por tipo" — fica de fora da ordem de propósito.
	// "implementacao" foi descontinuado como opção (só existe em tarefas legadas).
	const TYPE_ORDER = ['bug', 'melhoria', 'duvida'] as const;

	// Chips "Por tipo": so os tipos com tarefas em aberto (count > 0).
	const taskTypes = $derived.by(() => {
		const d = data;
		if (!d) return [] as { key: string; label: string; count: number }[];
		const counts: Record<string, number> = {
			bug: d.task_tipo_bug_count,
			melhoria: d.task_tipo_melhoria_count,
			duvida: d.task_tipo_duvida_count
		};
		return TYPE_ORDER.filter((k) => counts[k] > 0).map((k) => ({
			key: k,
			label: TYPE_LABEL[k],
			count: counts[k]
		}));
	});


	// "Tarefas recentes" SEM scroll: a lista preenche a altura disponivel e
	// mostra apenas os itens que cabem INTEIROS — telas maiores exibem mais,
	// menores exibem menos. Inspirado no `applyRecentTaskFit` do index.html (v4.5):
	// 1) mede com os itens empacotados no topo (`flex-start`) e oculta
	//    (`tk-fit-hidden`) o primeiro que ultrapassa o rodape e todos os seguintes;
	// 2) distribui a folga restante COMO espacamento entre os itens visiveis
	//    (`space-between`), para que o ultimo encoste no fim e nao sobre branco.
	let recentListEl = $state<HTMLDivElement | null>(null);

	function applyRecentFit(): void {
		const list = recentListEl;
		if (!list) return;
		const items = Array.from(list.children) as HTMLElement[];
		// Empacota no topo para a medicao refletir a altura real dos itens.
		list.style.justifyContent = 'flex-start';
		for (const item of items) item.classList.remove('tk-fit-hidden');
		const listBottom = list.getBoundingClientRect().bottom;
		if (list.clientHeight <= 0) return;
		let hideRest = false;
		const visible: HTMLElement[] = [];
		for (const item of items) {
			if (hideRest) {
				item.classList.add('tk-fit-hidden');
				continue;
			}
			if (item.getBoundingClientRect().bottom > listBottom + 2) {
				item.classList.add('tk-fit-hidden');
				hideRest = true;
			} else {
				visible.push(item);
			}
		}
		if (visible.length <= 1) {
			list.style.justifyContent = 'flex-start';
			return;
		}
		// Distribui a folga entre os itens (`space-between`) APENAS enquanto o vão
		// resultante fica discreto (<= MAX_GAP_PX). Se a folga for grande — um item
		// quase coube, ou a tela é bem mais alta que a lista — empacota no topo
		// (`flex-start`) com o gap natural e a sobra vai para o RODAPÉ, em vez de
		// abrir buracos enormes entre os cards.
		const used = visible.reduce((sum, el) => sum + el.offsetHeight, 0);
		const gapPerItem = (list.clientHeight - used) / (visible.length - 1);
		const MAX_GAP_PX = 14;
		list.style.justifyContent = gapPerItem <= MAX_GAP_PX ? 'space-between' : 'flex-start';
	}

	// Recalcula no mount, quando a lista de tarefas muda e a cada redimensionamento
	// (ResizeObserver na propria lista + resize da janela). `requestAnimationFrame`
	// garante medicao apos o paint do layout flex.
	$effect(() => {
		void data?.recent_tasks;
		const list = recentListEl;
		if (!list) return;
		let frame = requestAnimationFrame(applyRecentFit);
		const ro = new ResizeObserver(() => {
			cancelAnimationFrame(frame);
			frame = requestAnimationFrame(applyRecentFit);
		});
		ro.observe(list);
		return () => {
			cancelAnimationFrame(frame);
			ro.disconnect();
		};
	});
</script>

<svelte:head>
	<title>ProjetosRJ — Início</title>
</svelte:head>

<!-- lg:h-full + min-h-0 ancoram o layout viewport-fit adaptativo da v4.5: a
	 secao preenche a altura do <main> e distribui o espaco restante para a linha
	 dos paineis (que rolam internamente). No mobile fica em fluxo normal. -->
<section
	aria-labelledby="dashboard-title"
	class="dashboard-viewport-lock flex flex-col gap-4 lg:h-full lg:min-h-0"
>
	<!-- Hero "Olá, <nome> / Administrador" + data + Novo Projeto -->
	<PageHeader compact class="min-h-[3.5rem]" subtitle={welcomeContext} labelId="dashboard-title">
		{#snippet titleContent()}
			<span class="mr-1 font-semibold text-text-secondary">Olá,</span>
			<span>{welcomeName}</span>
		{/snippet}
		{#snippet actions()}
			<div class="flex flex-col items-end gap-0.5 text-right">
				<span class="text-2xs font-bold uppercase tracking-caps text-text-muted">Hoje</span>
				<span class="text-sm font-semibold text-brand">{todayLabel}</span>
			</div>
			<Button size="sm" onclick={openCreateModal} disabled={openingCreate}>
				{#snippet icon()}
					<i class="fas fa-plus" aria-hidden="true"></i>
				{/snippet}
				Novo Projeto
			</Button>
		{/snippet}
	</PageHeader>

	{#if loadState === 'loading' && !data}
		<p role="status" aria-live="polite" class="sr-only">Carregando dados…</p>
		<DashboardSkeleton />
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
						<!-- Micro-interacao: a pasta abre no hover do cartao revelando 3 prints
							 do app (servidos pelo Flask em /static/img/, fora do bundle da SPA). -->
						<FolderReveal
							size={46}
							images={[
								'/static/img/dashboard/folder/1.webp',
								'/static/img/dashboard/folder/2.webp',
								'/static/img/dashboard/folder/3.webp'
							]}
						/>
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
						<!-- Micro-interacao: carimbo desce e sela o termo com lacre de cera "OK". -->
						<ClipboardStamp size={52} />
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
						<!-- Micro-interacao: capa da pasta abre em 3D e duas folhas sobem em leque
							 no hover (mesmos prints do card "Projetos", servidos pelo Flask). -->
						<FolderPeek
							size={52}
							images={[
								'/static/img/dashboard/folder/3.webp',
								'/static/img/dashboard/folder/1.webp'
							]}
						/>
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
						<!-- Micro-interacao: ampulheta racha e a areia despeja para fora no hover. -->
						<AlertHourglass size={34} />
					{/snippet}
				</StatCard>
			</div>
		</section>

		<!-- Layout 2 colunas: projetos recentes (esq) + tarefas (dir).
			 items-stretch (padrao do grid) faz as duas colunas terem a MESMA
			 altura; o painel de recentes rola internamente (scroll-lock) e o de
			 tarefas se alinha ao lado, como no index.html original. -->
		<div class="grid grid-cols-1 items-stretch gap-4 lg:min-h-0 lg:flex-1 lg:grid-cols-3">
			<div class="lg:col-span-2 lg:min-h-0">
				<RecentProjectsPanel projects={data.recent_projects} totalProjects={data.num_projects} />
			</div>

			<aside class="flex flex-col lg:col-span-1 lg:min-h-0">
				<Card title="Tarefas" labelId="dashboard-tasks-title" fill>
					{#snippet header()}
						<a
							href={`${base}/tarefas`}
							class="inline-flex items-center gap-1 text-xs font-semibold text-brand no-underline transition-colors duration-fast hover:text-brand focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
						>
							Ver todas
							<i class="fas fa-arrow-right" aria-hidden="true"></i>
						</a>
					{/snippet}

					<div class="flex flex-col gap-4 lg:min-h-0 lg:flex-1">
						<!-- Hero: anel de % concluido + total em aberto + legenda por status. -->
						<section
							class="dashboard-tasks-hero relative flex shrink-0 items-center gap-4 rounded-xl border border-border-subtle px-4 py-3 transition-colors duration-fast focus-within:border-brand hover:border-brand"
							aria-label="Resumo de tarefas por status"
						>
							<!-- Link sobreposto: clicar em qualquer ponto do resumo leva a
								 /tarefas, sem envolver o conteudo num <a> (o resumo tem lista e
								 numeros, nao rotulo de link). -->
							<a
								href={`${base}/tarefas`}
								aria-label="Ver todas as tarefas"
								class="absolute inset-0 z-10 rounded-xl focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
							></a>
							<div class="dashboard-tasks-ring relative shrink-0">
								<svg
									viewBox="0 0 {RING_VIEW} {RING_VIEW}"
									class="block h-full w-full -rotate-90"
									aria-hidden="true"
								>
									<circle
										cx={RING_VIEW / 2}
										cy={RING_VIEW / 2}
										r={ring.r}
										fill="none"
										stroke="var(--ds-color-border-base)"
										stroke-width={RING_STROKE - 2}
									/>
									{#each ring.segs as seg, i (i)}
										<circle
											cx={RING_VIEW / 2}
											cy={RING_VIEW / 2}
											r={ring.r}
											fill="none"
											stroke={seg.color}
											stroke-width={RING_STROKE}
											stroke-dasharray={seg.dash}
											stroke-dashoffset={seg.offset}
											stroke-linecap="butt"
										/>
									{/each}
								</svg>
								<div class="pointer-events-none absolute inset-0 flex flex-col items-center justify-center tabular-nums">
									<div class="ring-pct font-heading font-bold leading-none text-text-primary">
										{donutPct}<span class="ring-pct-sign font-semibold text-text-muted">%</span>
									</div>
									<div class="ring-label font-semibold uppercase tracking-caps text-text-muted">
										Concluído
									</div>
								</div>
							</div>
							<div class="min-w-0 flex-1">
								<div class="mb-1 flex items-baseline gap-1.5">
									<span class="text-xl font-bold tabular-nums text-text-primary">{data.dashboard_open_tasks_count}</span>
									<span class="text-xs text-text-muted">tarefas abertas</span>
								</div>
								<ul class="flex flex-col gap-1.5" aria-label="Legenda por status">
									{#each statusLegend as s (s.key)}
										<li class="flex items-center gap-2 leading-none">
											<span class="h-2 w-2 shrink-0 rounded-full" style="background: {s.color};" aria-hidden="true"></span>
											<span class="min-w-0 flex-1 truncate text-2xs text-text-secondary">{s.label}</span>
											<span class="shrink-0 text-2xs font-semibold tabular-nums text-text-primary">{s.count}</span>
										</li>
									{/each}
								</ul>
							</div>
						</section>

						<!-- Por tipo: chips (so tipos com tarefas em aberto). Link p/ /tarefas. -->
						{#if taskTypes.length > 0}
							<section class="flex shrink-0 flex-col gap-2" aria-label="Tarefas por tipo">
								<span class="text-2xs font-semibold uppercase tracking-caps text-text-muted">Por tipo</span>
								<div class="flex flex-wrap gap-1.5">
									{#each taskTypes as ty (ty.key)}
										<a
											href={`${base}/tarefas?tipo=${ty.key}`}
											class="inline-flex items-center gap-1.5 rounded-lg border border-border-subtle bg-surface px-2.5 py-1.5 text-xs font-semibold text-text-secondary no-underline transition-colors duration-fast hover:border-brand hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
										>
											<TaskTipoIcon tipo={ty.key} size={16} />
											{ty.label}
											<span class="text-2xs font-semibold tabular-nums text-text-muted">{ty.count}</span>
										</a>
									{/each}
								</div>
							</section>
						{/if}

						<!-- Recentes: mini-lista (tipo + titulo + projeto + comentarios/anexos +
							 avatar do responsavel). SEM scroll: `applyRecentFit` esconde os itens
							 que nao cabem inteiros — telas maiores mostram mais, menores menos. -->
						{#if data.recent_tasks.length > 0}
							<section class="flex flex-col gap-2 lg:min-h-0 lg:flex-1" aria-label="Tarefas recentes">
								<span class="shrink-0 text-2xs font-semibold uppercase tracking-caps text-text-muted">Recentes</span>
								<div
									bind:this={recentListEl}
									class="flex flex-col gap-1.5 overflow-hidden lg:min-h-0 lg:flex-1"
								>
									{#each data.recent_tasks as t (t.id)}
										<a
											href={`${base}/tarefas?focus_task=${t.id}`}
											title={t.descricao}
											class="recent-task-item flex items-center gap-2.5 rounded-md border border-border-faint px-3 py-1 no-underline transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
										>
											<span class="flex h-5 w-5 shrink-0 items-center justify-center" aria-hidden="true">
												<TaskTipoIcon tipo={t.tipo_pedido} size={16} />
											</span>
											<span class="flex min-w-0 flex-1 flex-col">
												<span class="truncate text-sm font-semibold text-text-primary">{t.descricao}</span>
												<span class="flex items-center gap-1.5 truncate text-2xs text-text-muted">
													<span class="truncate">{t.project_titulo ?? (t.project_id ? `Projeto #${t.project_id}` : 'Sem projeto vinculado')}</span>
													{#if t.comments_count > 0 || t.anexos_count > 0}
														<span class="opacity-40">·</span>
														{#if t.comments_count > 0}
															<span class="inline-flex shrink-0 items-center gap-0.5"><AppIcon id="comentario" size={12} />{t.comments_count}</span>
														{/if}
														{#if t.anexos_count > 0}
															<span class="inline-flex shrink-0 items-center gap-0.5"><AppIcon id="anexo" size={12} />{t.anexos_count}</span>
														{/if}
													{/if}
												</span>
											</span>
											{#if t.assignees.length > 0}
												<span class="flex shrink-0 items-center -space-x-1.5">
													{#each t.assignees.slice(0, 3) as a (a.id)}
														<AssigneeAvatar name={a.name} initials={a.initials} size="sm" />
													{/each}
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
	{/if}

	<!-- Modal de criação aberto no proprio Dashboard (sem navegar para /projetos). -->
	<CriarProjetoModal
		open={createModalOpen}
		options={createOptions}
		onClose={() => (createModalOpen = false)}
		onCreated={onProjectCreated}
		onCreatedDismissed={onProjectCreatedDismissed}
	/>
</section>

<style>
	/* Caixa "hero" do painel de tarefas (anel + legenda): gradiente sutil de
	   surface-muted -> surface, como no mock concept4. Tokens => dark mode ok. */
	.dashboard-tasks-hero {
		background: linear-gradient(
			180deg,
			var(--ds-color-surface-muted),
			var(--ds-color-surface-base)
		);
	}

	/* Anel responsivo: largura acompanha a coluna (clamp), sempre quadrado. O
	   `container-type` habilita unidades `cqw` para a fonte interna escalar junto
	   com o anel — em vez de tamanhos fixos. */
	.dashboard-tasks-ring {
		width: clamp(80px, 30%, 128px);
		aspect-ratio: 1 / 1;
		container-type: inline-size;
	}
	.ring-pct {
		font-size: 19cqw;
	}
	.ring-pct-sign {
		font-size: 0.55em;
	}
	.ring-label {
		margin-top: 3cqw;
		font-size: 8cqw;
		letter-spacing: 0.06em;
	}

	/* Itens de tarefas recentes que nao cabem inteiros na altura da lista sao
	   ocultados por `applyRecentFit` (sem scroll) — mesma estrategia do
	   `is-fit-hidden` da v4.5. Global porque a classe e aplicada via JS. */
	:global(.tk-fit-hidden) {
		display: none !important;
	}
</style>
