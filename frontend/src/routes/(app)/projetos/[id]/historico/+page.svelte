<script lang="ts">
	/**
	 * Tela Historico de projeto. Consome `GET /api/projetos/<id>/historico`
	 * (modulo `$lib/api/history`) e renderiza o cabecalho do projeto + a linha do
	 * tempo de eventos. O `id` vem do parametro de rota (`[id]`).
	 *
	 * Acessivel: regiao com heading, estados loading/erro/vazio anunciados via
	 * aria-live/role=alert, retry focavel. Erros tratados explicitamente:
	 *   - 404 `not_found` (projeto inexistente);
	 *   - 403 `forbidden` (fora do escopo do usuario);
	 *   - 401 ja redireciona para /login em `client.ts`.
	 *
	 * Espelha o mapeamento de categoria/label/tom de
	 * templates/projects/_history_content.html (sem recalcular derivados de
	 * dominio). Links internos sao base-aware (`$app/paths`).
	 */
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import { base } from '$app/paths';
	import { fetchProjectHistory } from '$lib/api/history';
	import { ApiClientError } from '$lib/api/client';
	import type { ProjectHistoryData, HistoryEntry } from '$lib/types/history';
	import Card from '$lib/components/Card.svelte';
	import Badge from '$lib/components/Badge.svelte';

	type LoadState = 'loading' | 'ready' | 'error';
	type Tone = 'neutral' | 'primary' | 'success' | 'warning' | 'danger' | 'info';

	const projectId = $derived(Number($page.params.id));

	let loadState = $state<LoadState>('loading');
	let data = $state<ProjectHistoryData | null>(null);
	let errorMessage = $state<string>('');
	/** Distingue erros de acesso/inexistencia do generico para a UI. */
	let errorKind = $state<'forbidden' | 'not_found' | 'generic'>('generic');

	/** Apresentacao (categoria/label/tom) de um tipo de acao — espelha o Jinja. */
	interface ActionPresentation {
		category: 'project' | 'stage' | 'system';
		label: string;
		tone: Tone;
	}

	const PROJECT_ACTIONS: Record<string, { label: string; tone: Tone }> = {
		create: { label: 'Criação de projeto', tone: 'success' },
		edit: { label: 'Edição de projeto', tone: 'primary' },
		delete: { label: 'Exclusão de projeto', tone: 'danger' },
		finalize: { label: 'Conclusão de projeto', tone: 'success' },
		reactivate: { label: 'Reativação de projeto', tone: 'primary' }
	};

	const STAGE_ACTIONS: Record<string, { label: string; tone: Tone }> = {
		add_etapa: { label: 'Nova etapa', tone: 'info' },
		add_google_meeting: { label: 'Nova reunião Google', tone: 'info' },
		edit_google_meeting: { label: 'Edição de reunião Google', tone: 'info' },
		edit_etapa: { label: 'Edição de etapa', tone: 'info' },
		edit_etapa_inline: { label: 'Edição rápida de etapa', tone: 'info' },
		reschedule_google_meeting: { label: 'Reagendamento de reunião', tone: 'info' },
		delete_etapa: { label: 'Exclusão de etapa', tone: 'danger' },
		delete_google_meeting: { label: 'Exclusão de reunião', tone: 'danger' },
		toggle_iniciada: { label: 'Mudança de início da etapa', tone: 'info' },
		toggle_done: { label: 'Mudança de conclusão da etapa', tone: 'success' },
		import_model: { label: 'Importação de modelo', tone: 'info' },
		edit_etapa_comentario: { label: 'Comentário de etapa', tone: 'info' },
		reorder_etapas: { label: 'Reordenação de etapas', tone: 'info' },
		cascade_update: { label: 'Cascata de datas', tone: 'info' }
	};

	/** Mapeia `action_type` para categoria/label/tom (fallback "Evento"/sistema). */
	function presentAction(actionType: string): ActionPresentation {
		const project = PROJECT_ACTIONS[actionType];
		if (project) return { category: 'project', ...project };
		const stage = STAGE_ACTIONS[actionType];
		if (stage) return { category: 'stage', ...stage };
		return { category: 'system', label: 'Evento de sistema', tone: 'neutral' };
	}

	/** Nome do autor (fallback para id ou "Sistema"), espelhando o Jinja. */
	function actorName(entry: HistoryEntry): string {
		if (entry.user) return entry.user.name;
		return 'Sistema';
	}

	// ── Filtros client-side (espelha static/js/pages/projects/history.js) ──
	// O original filtra entradas JA carregadas (sem ir ao backend): busca livre
	// por descricao/usuario/antes/depois, tipo de evento e periodo relativo.
	let searchTerm = $state<string>('');
	let typeFilter = $state<'all' | 'project' | 'stage' | 'system'>('all');
	let periodFilter = $state<'all' | '7d' | '30d' | '90d'>('all');

	/** Blob de texto pesquisavel de uma entrada (descricao+usuario+antes+depois). */
	function entryTextBlob(entry: HistoryEntry): string {
		return [
			entry.action_description ?? '',
			actorName(entry),
			entry.old_value ?? '',
			entry.new_value ?? ''
		]
			.join(' ')
			.toLowerCase();
	}

	/** Verifica se a entrada cai dentro do periodo relativo selecionado. */
	function inPeriod(iso: string | null): boolean {
		if (periodFilter === 'all') return true;
		if (!iso) return true;
		const parsed = new Date(iso);
		if (Number.isNaN(parsed.getTime())) return true;
		const days = periodFilter === '7d' ? 7 : periodFilter === '30d' ? 30 : 90;
		const threshold = new Date(Date.now() - days * 24 * 60 * 60 * 1000);
		return parsed >= threshold;
	}

	/** Lista de entradas que passam por todos os filtros ativos. */
	const filteredHistory = $derived.by<HistoryEntry[]>(() => {
		if (!data) return [];
		const term = searchTerm.trim().toLowerCase();
		return data.history.filter((entry) => {
			const category = presentAction(entry.action_type).category;
			const typeOk = typeFilter === 'all' || category === typeFilter;
			const searchOk = !term || entryTextBlob(entry).includes(term);
			const periodOk = inPeriod(entry.timestamp);
			return typeOk && searchOk && periodOk;
		});
	});

	/** Contadores ao vivo por categoria sobre as entradas visiveis. */
	const counters = $derived.by(() => {
		let project = 0;
		let stage = 0;
		let system = 0;
		for (const entry of filteredHistory) {
			const category = presentAction(entry.action_type).category;
			if (category === 'project') project += 1;
			else if (category === 'stage') stage += 1;
			else system += 1;
		}
		return { total: filteredHistory.length, project, stage, system };
	});

	/** Formata o timestamp ISO em data/hora local pt-BR (dd/mm/aaaa às HH:MM). */
	function formatTimestamp(iso: string | null): string {
		if (!iso) return '';
		const parsed = new Date(iso);
		if (Number.isNaN(parsed.getTime())) return '';
		const dia = parsed.toLocaleDateString('pt-BR');
		const hora = parsed.toLocaleTimeString('pt-BR', {
			hour: '2-digit',
			minute: '2-digit'
		});
		return `${dia} às ${hora}`;
	}

	async function load(): Promise<void> {
		loadState = 'loading';
		errorMessage = '';
		errorKind = 'generic';
		try {
			data = await fetchProjectHistory(projectId);
			loadState = 'ready';
		} catch (err) {
			// 401 ja redirecionou em client.ts; aqui tratamos os demais erros.
			if (err instanceof ApiClientError) {
				if (err.code === 'unauthenticated') return;
				if (err.code === 'not_found') errorKind = 'not_found';
				else if (err.code === 'forbidden') errorKind = 'forbidden';
			}
			errorMessage =
				err instanceof ApiClientError
					? err.message
					: err instanceof Error
						? err.message
						: 'Falha ao carregar o histórico do projeto.';
			loadState = 'error';
		}
	}

	onMount(() => {
		void load();
	});
</script>

<svelte:head>
	<title>Histórico do projeto — ProjetosRJ</title>
</svelte:head>

<section aria-labelledby="history-title" class="flex flex-col gap-6">
	<header class="flex flex-col gap-2">
		<h1 id="history-title" class="font-heading text-2xl font-bold text-text-primary">
			Histórico do projeto
		</h1>
		{#if loadState === 'ready' && data}
			<p class="text-text-secondary">{data.project.titulo}</p>
			<a
				href={`${base}/projetos/${data.project.id}`}
				class="inline-flex w-fit items-center whitespace-nowrap rounded-md border border-border-subtle bg-surface px-3 py-1.5 text-sm font-semibold text-text-primary no-underline transition-colors duration-fast hover:bg-surface-muted hover:border-border-strong focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
			>
				Voltar ao projeto
			</a>
		{/if}
	</header>

	{#if loadState === 'loading'}
		<p role="status" aria-live="polite" class="text-text-secondary">
			Carregando histórico…
		</p>
	{:else if loadState === 'error'}
		<div
			role="alert"
			class="flex flex-col items-start gap-3 rounded-lg border border-danger bg-surface px-5 py-4"
		>
			{#if errorKind === 'not_found'}
				<p class="text-text-primary">Projeto não encontrado.</p>
				<a
					href={`${base}/dashboard`}
					class="rounded-md border border-border-subtle bg-surface px-4 py-2 text-sm font-medium text-text-primary no-underline transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
				>
					Voltar ao dashboard
				</a>
			{:else if errorKind === 'forbidden'}
				<p class="text-text-primary">
					Você não tem permissão para visualizar este projeto.
				</p>
				<a
					href={`${base}/dashboard`}
					class="rounded-md border border-border-subtle bg-surface px-4 py-2 text-sm font-medium text-text-primary no-underline transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
				>
					Voltar ao dashboard
				</a>
			{:else}
				<p class="text-text-primary">{errorMessage}</p>
				<button
					type="button"
					onclick={load}
					class="rounded-md border border-border-subtle bg-surface px-4 py-2 text-sm font-medium text-text-primary transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
				>
					Tentar novamente
				</button>
			{/if}
		</div>
	{:else if data}
		{#if data.history.length === 0}
			<Card>
				<div class="flex flex-col gap-1 px-1 py-8 text-center">
					<p class="font-semibold text-text-primary">Nenhuma ação registrada ainda</p>
					<p class="text-md text-text-secondary">
						O histórico será exibido aqui à medida que o projeto for atualizado.
					</p>
				</div>
			</Card>
		{:else}
			<!--
				Barra de ferramentas (.history-tools do original): busca livre + tipo
				de evento + periodo, e contadores ao vivo. Tudo client-side sobre as
				entradas ja carregadas — espelha static/js/pages/projects/history.js.
			-->
			<section
				class="flex flex-col gap-3 rounded-lg border border-border-subtle bg-surface px-4 py-3.5 shadow-sm"
				aria-label="Filtros do histórico"
			>
				<div class="grid gap-3 md:grid-cols-[minmax(260px,1fr)_minmax(170px,220px)_minmax(170px,220px)]">
					<div class="flex flex-col gap-1">
						<label
							for="historySearch"
							class="text-xs font-bold uppercase tracking-wide text-text-muted"
						>
							Buscar no histórico
						</label>
						<input
							id="historySearch"
							type="search"
							autocomplete="off"
							bind:value={searchTerm}
							placeholder="Descrição, usuário, antes/depois"
							class="h-9 w-full rounded-md border border-border-subtle bg-surface px-2.5 text-md text-text-primary placeholder:text-text-muted transition-colors duration-fast focus:border-primary-500 focus:outline-none focus:ring-[3px] focus:ring-primary-500/15"
						/>
					</div>

					<div class="flex flex-col gap-1">
						<label
							for="historyTypeFilter"
							class="text-xs font-bold uppercase tracking-wide text-text-muted"
						>
							Tipo de evento
						</label>
						<select
							id="historyTypeFilter"
							bind:value={typeFilter}
							class="h-9 cursor-pointer rounded-md border border-border-subtle bg-surface px-2.5 text-md text-text-primary transition-colors duration-fast focus:border-primary-500 focus:outline-none focus:ring-[3px] focus:ring-primary-500/15"
						>
							<option value="all">Todos</option>
							<option value="project">Projeto</option>
							<option value="stage">Etapas</option>
							<option value="system">Sistema</option>
						</select>
					</div>

					<div class="flex flex-col gap-1">
						<label
							for="historyPeriodFilter"
							class="text-xs font-bold uppercase tracking-wide text-text-muted"
						>
							Período
						</label>
						<select
							id="historyPeriodFilter"
							bind:value={periodFilter}
							class="h-9 cursor-pointer rounded-md border border-border-subtle bg-surface px-2.5 text-md text-text-primary transition-colors duration-fast focus:border-primary-500 focus:outline-none focus:ring-[3px] focus:ring-primary-500/15"
						>
							<option value="all">Todo período</option>
							<option value="7d">Últimos 7 dias</option>
							<option value="30d">Últimos 30 dias</option>
							<option value="90d">Últimos 90 dias</option>
						</select>
					</div>
				</div>

				<!--
					Contadores ao vivo (.history-counters): pilulas que refletem a
					contagem por categoria das entradas que passam pelos filtros.
				-->
				<div class="flex flex-wrap gap-1.5" aria-live="polite">
					<span
						class="rounded-full border border-border-subtle bg-surface-muted px-2.5 py-1 text-xs font-semibold text-text-secondary"
					>
						<strong class="mr-1 text-text-primary">{counters.total}</strong>eventos
					</span>
					<span
						class="rounded-full border border-border-subtle bg-surface-muted px-2.5 py-1 text-xs font-semibold text-text-secondary"
					>
						<strong class="mr-1 text-text-primary">{counters.project}</strong>projeto
					</span>
					<span
						class="rounded-full border border-border-subtle bg-surface-muted px-2.5 py-1 text-xs font-semibold text-text-secondary"
					>
						<strong class="mr-1 text-text-primary">{counters.stage}</strong>etapas
					</span>
					<span
						class="rounded-full border border-border-subtle bg-surface-muted px-2.5 py-1 text-xs font-semibold text-text-secondary"
					>
						<strong class="mr-1 text-text-primary">{counters.system}</strong>sistema
					</span>
				</div>
			</section>

			<!--
				Card do kit (overflow-hidden via rounded-lg + border) reproduz o
				.history-list-card original: cabecalho-subtitulo discreto + lista de
				entradas separadas por divisorias (sem padding lateral no corpo da
				lista para que as bordas das linhas atinjam as laterais do card).
			-->
			<section
				class="overflow-hidden rounded-lg border border-border-subtle bg-surface shadow-sm"
				aria-labelledby="history-list-title"
			>
				<div
					id="history-list-title"
					class="border-b border-border-subtle px-4 py-3 text-sm font-semibold text-text-secondary"
				>
					Registro consolidado de ações no projeto.
				</div>

				{#if filteredHistory.length === 0}
					<p
						role="status"
						aria-live="polite"
						class="px-4 py-[1.1rem] text-center text-md text-text-secondary"
					>
						Nenhum evento encontrado para os filtros selecionados.
					</p>
				{:else}
					<ol class="flex flex-col">
						{#each filteredHistory as entry (entry.id)}
							{@const present = presentAction(entry.action_type)}
							<li
								class="flex flex-col gap-1.5 border-b border-border-subtle px-4 py-3.5 transition-colors duration-fast last:border-b-0 hover:bg-surface-muted"
							>
								<div class="flex items-start justify-between gap-2">
									<Badge tone={present.tone}>{present.label}</Badge>
									<time
										class="whitespace-nowrap text-xs text-text-muted"
										datetime={entry.timestamp ?? undefined}
									>
										{formatTimestamp(entry.timestamp)}
									</time>
								</div>

								{#if entry.action_description}
									<h3 class="font-heading text-base font-semibold leading-normal text-text-primary">
										{entry.action_description}
									</h3>
								{/if}

								<p class="text-sm text-text-secondary">
									Responsável: {actorName(entry)}
								</p>

								{#if entry.old_value || entry.new_value}
									<div class="mt-1 grid gap-2 sm:grid-cols-2">
										{#if entry.old_value}
											<div class="flex flex-col gap-1 rounded-md border border-danger/40 bg-danger/5 px-2.5 py-2">
												<h4 class="text-xs font-bold uppercase tracking-wide text-text-muted">
													Antes
												</h4>
												<pre class="m-0 whitespace-pre-wrap break-words font-sans text-sm leading-normal text-text-secondary">{entry.old_value}</pre>
											</div>
										{/if}
										{#if entry.new_value}
											<div class="flex flex-col gap-1 rounded-md border border-success/40 bg-success/5 px-2.5 py-2">
												<h4 class="text-xs font-bold uppercase tracking-wide text-text-muted">
													Depois
												</h4>
												<pre class="m-0 whitespace-pre-wrap break-words font-sans text-sm leading-normal text-text-secondary">{entry.new_value}</pre>
											</div>
										{/if}
									</div>
								{/if}
							</li>
						{/each}
					</ol>
				{/if}
			</section>
		{/if}
	{/if}
</section>
