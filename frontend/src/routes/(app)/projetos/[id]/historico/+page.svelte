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
				class="inline-flex w-fit items-center rounded-md border border-border-subtle bg-surface px-4 py-2 text-sm font-medium text-text-primary no-underline transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
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
		<Card labelId="history-list-title">
			{#snippet header()}
				<h2 id="history-list-title" class="font-heading text-lg font-semibold text-text-primary">
					Registro consolidado de ações no projeto
				</h2>
			{/snippet}

			{#if data.history.length === 0}
				<div class="flex flex-col gap-1 py-4 text-center">
					<p class="font-medium text-text-primary">Nenhuma ação registrada ainda</p>
					<p class="text-sm text-text-muted">
						O histórico será exibido aqui à medida que o projeto for atualizado.
					</p>
				</div>
			{:else}
				<ol class="flex flex-col gap-4" aria-labelledby="history-list-title">
					{#each data.history as entry (entry.id)}
						{@const present = presentAction(entry.action_type)}
						<li
							class="flex flex-col gap-2 rounded-md border border-border-subtle bg-surface px-4 py-3"
						>
							<div class="flex flex-wrap items-center justify-between gap-2">
								<Badge tone={present.tone}>{present.label}</Badge>
								<time
									class="text-xs text-text-muted"
									datetime={entry.timestamp ?? undefined}
								>
									{formatTimestamp(entry.timestamp)}
								</time>
							</div>

							{#if entry.action_description}
								<h3 class="font-heading text-base font-semibold text-text-primary">
									{entry.action_description}
								</h3>
							{/if}

							<p class="text-sm text-text-secondary">
								Responsável: {actorName(entry)}
							</p>

							{#if entry.old_value || entry.new_value}
								<div class="grid gap-3 sm:grid-cols-2">
									{#if entry.old_value}
										<div class="flex flex-col gap-1 rounded-md border border-border-subtle bg-surface-muted px-3 py-2">
											<h4 class="text-xs font-semibold uppercase tracking-wide text-text-muted">
												Antes
											</h4>
											<pre class="whitespace-pre-wrap break-words font-mono text-sm text-text-primary">{entry.old_value}</pre>
										</div>
									{/if}
									{#if entry.new_value}
										<div class="flex flex-col gap-1 rounded-md border border-border-subtle bg-surface-muted px-3 py-2">
											<h4 class="text-xs font-semibold uppercase tracking-wide text-text-muted">
												Depois
											</h4>
											<pre class="whitespace-pre-wrap break-words font-mono text-sm text-text-primary">{entry.new_value}</pre>
										</div>
									{/if}
								</div>
							{/if}
						</li>
					{/each}
				</ol>
			{/if}
		</Card>
	{/if}
</section>
