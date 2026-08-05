<script lang="ts">
	/**
	 * DRAWER de Histórico do projeto — substitui a página
	 * `/projetos/<id>/historico` (que agora só redireciona para cá), padronizando
	 * a UX com os demais drawers (TaskDrawer, tarefas da etapa).
	 *
	 * Consome `GET /api/projetos/<id>/historico` e renderiza uma TIMELINE
	 * agrupada por dia (Hoje/Ontem/data), deliberadamente sóbria: nada de
	 * badges multicoloridos nem caixas verde/vermelho — o evento é um ponto
	 * sobre a linha do tempo (cor semântica SÓ para criação/conclusão e
	 * exclusões; o resto é neutro), rótulo discreto em caixa alta e o
	 * antes/depois em pares neutros sobre `surface-muted`.
	 *
	 * Mantém os filtros client-side da tela original (busca livre, tipo de
	 * evento, período) sobre as entradas já carregadas, com contagem ao vivo
	 * na pílula do header. Acessível: role=dialog, focus trap, Esc fecha,
	 * estados loading/erro/vazio anunciados via aria-live/role=alert.
	 */
	import { onMount } from 'svelte';
	import { fly, fade } from 'svelte/transition';
	import { cubicOut } from 'svelte/easing';
	import { fetchProjectHistory } from '$lib/api/history';
	import { ApiClientError } from '$lib/api/client';
	import {
		MSG_PROJETO_INACESSIVEL,
		accessErrorKind,
		accessErrorMessage,
		type AccessErrorKind
	} from '$lib/utils/accessErrorMessages';
	import { focusTrap } from '$lib/actions/focusTrap';
	import SelectMenu from '$lib/components/SelectMenu.svelte';
	import type { SelectMenuOption } from '$lib/types/selectMenu';
	import type { HistoryEntry } from '$lib/types/history';

	interface Props {
		projectId: number;
		projectTitulo: string;
		onClose: () => void;
	}

	let { projectId, projectTitulo, onClose }: Props = $props();

	type LoadState = 'loading' | 'ready' | 'error';

	let loadState = $state<LoadState>('loading');
	let history = $state<HistoryEntry[]>([]);
	let errorMessage = $state<string>('');
	let errorKind = $state<AccessErrorKind>('generic');

	// ── Apresentação dos tipos de evento ────────────────────────────────────
	// Rótulos espelham a tela original; o "tom" foi reduzido a 3 estados para
	// o ponto da timeline: positivo (criar/concluir), destrutivo (excluir) e
	// neutro (todo o resto).
	type DotTone = 'positive' | 'destructive' | 'neutral';

	interface ActionPresentation {
		category: 'project' | 'stage' | 'system';
		label: string;
		tone: DotTone;
	}

	const PROJECT_ACTIONS: Record<string, { label: string; tone: DotTone }> = {
		create: { label: 'Criação de projeto', tone: 'positive' },
		edit: { label: 'Edição de projeto', tone: 'neutral' },
		delete: { label: 'Exclusão de projeto', tone: 'destructive' },
		finalize: { label: 'Conclusão de projeto', tone: 'positive' },
		reactivate: { label: 'Reativação de projeto', tone: 'neutral' }
	};

	const STAGE_ACTIONS: Record<string, { label: string; tone: DotTone }> = {
		add_etapa: { label: 'Nova etapa', tone: 'neutral' },
		add_google_meeting: { label: 'Nova reunião Google', tone: 'neutral' },
		edit_google_meeting: { label: 'Edição de reunião Google', tone: 'neutral' },
		edit_etapa: { label: 'Edição de etapa', tone: 'neutral' },
		edit_etapa_inline: { label: 'Edição rápida de etapa', tone: 'neutral' },
		reschedule_google_meeting: { label: 'Reagendamento de reunião', tone: 'neutral' },
		delete_etapa: { label: 'Exclusão de etapa', tone: 'destructive' },
		delete_google_meeting: { label: 'Exclusão de reunião', tone: 'destructive' },
		toggle_iniciada: { label: 'Mudança de início da etapa', tone: 'neutral' },
		toggle_done: { label: 'Mudança de conclusão da etapa', tone: 'positive' },
		import_model: { label: 'Importação de modelo', tone: 'neutral' },
		edit_etapa_comentario: { label: 'Comentário de etapa', tone: 'neutral' },
		reorder_etapas: { label: 'Reordenação de etapas', tone: 'neutral' },
		cascade_update: { label: 'Cascata de datas', tone: 'neutral' }
	};

	function presentAction(actionType: string): ActionPresentation {
		const project = PROJECT_ACTIONS[actionType];
		if (project) return { category: 'project', ...project };
		const stage = STAGE_ACTIONS[actionType];
		if (stage) return { category: 'stage', ...stage };
		return { category: 'system', label: 'Evento de sistema', tone: 'neutral' };
	}

	const DOT_CLASS: Record<DotTone, string> = {
		positive: 'bg-success',
		destructive: 'bg-danger',
		neutral: 'bg-text-muted'
	};

	function actorName(entry: HistoryEntry): string {
		return entry.user ? entry.user.name : 'Sistema';
	}

	// ── Filtros client-side (paridade com a tela original) ──────────────────
	let searchTerm = $state<string>('');
	let typeFilter = $state<'all' | 'project' | 'stage' | 'system'>('all');
	let periodFilter = $state<'all' | '7d' | '30d' | '90d'>('all');

	const TYPE_FILTER_LABELS: Record<'project' | 'stage' | 'system', string> = {
		project: 'Projeto',
		stage: 'Etapas',
		system: 'Sistema'
	};
	const typeFilterOptions = $derived<SelectMenuOption[]>(
		(Object.keys(TYPE_FILTER_LABELS) as Array<keyof typeof TYPE_FILTER_LABELS>).map((value) => ({
			value,
			label: TYPE_FILTER_LABELS[value]
		}))
	);

	const PERIOD_FILTER_LABELS: Record<'7d' | '30d' | '90d', string> = {
		'7d': '7 dias',
		'30d': '30 dias',
		'90d': '90 dias'
	};
	const periodFilterOptions = $derived<SelectMenuOption[]>(
		(Object.keys(PERIOD_FILTER_LABELS) as Array<keyof typeof PERIOD_FILTER_LABELS>).map(
			(value) => ({ value, label: PERIOD_FILTER_LABELS[value] })
		)
	);

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

	function inPeriod(iso: string | null): boolean {
		if (periodFilter === 'all') return true;
		if (!iso) return true;
		const parsed = new Date(iso);
		if (Number.isNaN(parsed.getTime())) return true;
		const days = periodFilter === '7d' ? 7 : periodFilter === '30d' ? 30 : 90;
		const threshold = new Date(Date.now() - days * 24 * 60 * 60 * 1000);
		return parsed >= threshold;
	}

	const filteredHistory = $derived.by<HistoryEntry[]>(() => {
		const term = searchTerm.trim().toLowerCase();
		return history.filter((entry) => {
			const category = presentAction(entry.action_type).category;
			const typeOk = typeFilter === 'all' || category === typeFilter;
			const searchOk = !term || entryTextBlob(entry).includes(term);
			const periodOk = inPeriod(entry.timestamp);
			return typeOk && searchOk && periodOk;
		});
	});

	const hasActiveFilters = $derived(
		searchTerm.trim() !== '' || typeFilter !== 'all' || periodFilter !== 'all'
	);

	// ── Agrupamento por dia (Hoje/Ontem/dd/mm/aaaa) ─────────────────────────
	interface DayGroup {
		label: string;
		entries: HistoryEntry[];
	}

	function dayLabel(iso: string | null): string {
		if (!iso) return 'Sem data';
		const parsed = new Date(iso);
		if (Number.isNaN(parsed.getTime())) return 'Sem data';
		const today = new Date();
		const yesterday = new Date(today);
		yesterday.setDate(today.getDate() - 1);
		const sameDay = (a: Date, b: Date) =>
			a.getFullYear() === b.getFullYear() &&
			a.getMonth() === b.getMonth() &&
			a.getDate() === b.getDate();
		if (sameDay(parsed, today)) return 'Hoje';
		if (sameDay(parsed, yesterday)) return 'Ontem';
		return parsed.toLocaleDateString('pt-BR');
	}

	const dayGroups = $derived.by<DayGroup[]>(() => {
		const groups: DayGroup[] = [];
		for (const entry of filteredHistory) {
			const label = dayLabel(entry.timestamp);
			const last = groups[groups.length - 1];
			if (last && last.label === label) last.entries.push(entry);
			else groups.push({ label, entries: [entry] });
		}
		return groups;
	});

	function formatTime(iso: string | null): string {
		if (!iso) return '';
		const parsed = new Date(iso);
		if (Number.isNaN(parsed.getTime())) return '';
		return parsed.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
	}

	async function load(): Promise<void> {
		loadState = 'loading';
		errorMessage = '';
		errorKind = 'generic';
		try {
			const data = await fetchProjectHistory(projectId);
			history = data.history;
			loadState = 'ready';
		} catch (err) {
			if (err instanceof ApiClientError && err.code === 'unauthenticated') return;
			errorKind = accessErrorKind(err);
			errorMessage = accessErrorMessage(
				err,
				MSG_PROJETO_INACESSIVEL,
				'Falha ao carregar o histórico do projeto.'
			);
			loadState = 'error';
		}
	}

	onMount(() => {
		void load();
	});

	function onKeydown(event: KeyboardEvent): void {
		if (event.key === 'Escape') {
			event.stopPropagation();
			onClose();
		}
	}
</script>

<!-- Backdrop: mesma tinta/blur dos demais drawers, fade 200ms. -->
<div
	class="fixed inset-0 z-modal bg-overlay backdrop-blur-[1.2px]"
	role="presentation"
	transition:fade={{ duration: 200 }}
	onclick={onClose}
></div>

<!-- Painel lateral: 620px (timeline + pares antes/depois). -->
<div
	role="dialog"
	aria-modal="true"
	aria-labelledby="project-history-title"
	tabindex="-1"
	use:focusTrap
	onkeydown={onKeydown}
	transition:fly={{ x: 620, duration: 240, easing: cubicOut, opacity: 1 }}
	class="history-drawer-panel fixed right-0 top-0 z-modal flex h-full w-[min(620px,100vw)] flex-col border-l border-border-subtle bg-surface shadow-[-18px_0_44px_rgba(12,44,74,0.18)]"
>
	<header
		class="flex shrink-0 flex-col gap-3 border-b border-border-subtle bg-surface-elevated px-5 pb-3.5 pt-4"
	>
		<div class="flex items-start justify-between gap-3">
			<div class="flex min-w-0 flex-1 flex-col gap-1">
				<p class="m-0 text-xs font-bold uppercase tracking-caps text-text-muted">
					Histórico do projeto
				</p>
				<h2
					id="project-history-title"
					class="m-0 line-clamp-2 break-words font-heading text-lg font-bold leading-snug text-text-primary"
				>
					{projectTitulo}
				</h2>
			</div>
			<div class="flex shrink-0 items-center gap-2">
				{#if loadState === 'ready'}
					<span
						class="inline-flex items-center rounded-md border border-border-subtle bg-surface px-2 py-0.5 text-xs font-semibold text-text-secondary"
						aria-live="polite"
					>
						{filteredHistory.length}
						{filteredHistory.length === 1 ? 'evento' : 'eventos'}
					</span>
				{/if}
				<button
					type="button"
					onclick={onClose}
					aria-label="Fechar"
					class="inline-flex h-8 w-8 items-center justify-center rounded-md text-text-secondary transition-colors duration-fast hover:bg-surface-muted hover:text-brand focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
				>
					<svg viewBox="0 0 24 24" class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
						<path d="M18 6 6 18M6 6l12 12" />
					</svg>
				</button>
			</div>
		</div>

		<!-- Filtros compactos numa linha só (busca + tipo + período). -->
		{#if loadState === 'ready' && history.length > 0}
			<div class="flex items-center gap-2" aria-label="Filtros do histórico">
				<input
					type="search"
					autocomplete="off"
					bind:value={searchTerm}
					placeholder="Buscar no histórico…"
					aria-label="Buscar no histórico"
					class="h-8 min-w-0 flex-1 rounded-md border border-border-subtle bg-surface px-2.5 text-sm text-text-primary placeholder:text-text-muted transition-colors duration-fast focus:border-brand focus:outline-none"
				/>
				<div class="w-36 shrink-0">
					<SelectMenu
						options={typeFilterOptions}
						value={typeFilter === 'all' ? null : typeFilter}
						onSelect={(v) => (typeFilter = (v as typeof typeFilter) ?? 'all')}
						allowAll
						ariaLabel="Tipo de evento"
					/>
				</div>
				<div class="w-36 shrink-0">
					<SelectMenu
						options={periodFilterOptions}
						value={periodFilter === 'all' ? null : periodFilter}
						onSelect={(v) => (periodFilter = (v as typeof periodFilter) ?? 'all')}
						allowAll
						allLabel="Todo período"
						ariaLabel="Período"
					/>
				</div>
			</div>
		{/if}
	</header>

	<!-- Corpo rolável: timeline agrupada por dia. -->
	<div class="thin-scroll flex-1 overflow-y-auto px-5 py-4">
		{#if loadState === 'loading'}
			<div role="status" aria-live="polite" class="flex items-center gap-2 py-2 text-sm text-text-secondary">
				<span
					class="h-4 w-4 animate-spin rounded-full border-2 border-border-subtle border-t-primary-600"
					aria-hidden="true"
				></span>
				Carregando histórico…
			</div>
		{:else if loadState === 'error'}
			<div role="alert" class="flex flex-col items-start gap-2 rounded-lg border border-danger bg-surface px-4 py-3 text-sm text-text-primary">
				<p class="m-0">{errorMessage}</p>
				<!-- 404/403 nao se resolvem repetindo a requisicao (S5, §6.3). -->
				{#if errorKind === 'generic'}
					<button
						type="button"
						onclick={() => void load()}
						class="rounded-md border border-border-subtle bg-surface px-3 py-1.5 text-sm font-medium text-text-primary transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
					>
						Tentar novamente
					</button>
				{/if}
			</div>
		{:else if history.length === 0}
			<div
				class="flex flex-col items-center gap-1 rounded-lg border border-dashed border-border-subtle px-4 py-8 text-center"
			>
				<p class="m-0 text-sm font-medium text-text-secondary">Nenhuma ação registrada ainda.</p>
				<p class="m-0 text-xs text-text-muted">
					O histórico será exibido aqui à medida que o projeto for atualizado.
				</p>
			</div>
		{:else if filteredHistory.length === 0}
			<p role="status" aria-live="polite" class="m-0 py-6 text-center text-sm text-text-muted">
				Nenhum evento encontrado para os filtros selecionados.
				{#if hasActiveFilters}
					<button
						type="button"
						onclick={() => {
							searchTerm = '';
							typeFilter = 'all';
							periodFilter = 'all';
						}}
						class="ml-1 rounded-sm font-semibold text-brand hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
					>
						Limpar filtros
					</button>
				{/if}
			</p>
		{:else}
			<div class="flex flex-col gap-5">
				{#each dayGroups as group (group.label)}
					<section aria-label={group.label} class="flex flex-col gap-2">
						<h3 class="m-0 text-xs font-bold uppercase tracking-caps text-text-muted">
							{group.label}
						</h3>
						<ol class="m-0 flex list-none flex-col border-l border-border-subtle p-0">
							{#each group.entries as entry (entry.id)}
								{@const present = presentAction(entry.action_type)}
								<li class="relative flex flex-col gap-1 pb-4 pl-5 last:pb-1">
									<!-- Ponto da timeline (cor semântica só p/ criar/concluir e excluir). -->
									<span
										aria-hidden="true"
										class="absolute -left-[5px] top-1 h-2.5 w-2.5 rounded-full border-2 border-surface {DOT_CLASS[present.tone]}"
									></span>

									<div class="flex items-baseline justify-between gap-2">
										<span class="text-xs font-semibold uppercase tracking-wide text-text-muted">
											{present.label}
										</span>
										<time
											class="shrink-0 whitespace-nowrap text-xs tabular-nums text-text-muted"
											datetime={entry.timestamp ?? undefined}
										>
											{formatTime(entry.timestamp)}
										</time>
									</div>

									{#if entry.action_description}
										<p class="m-0 text-sm leading-snug text-text-primary">
											{entry.action_description}
										</p>
									{/if}

									<p class="m-0 text-xs text-text-muted">por {actorName(entry)}</p>

									{#if entry.old_value || entry.new_value}
										<div class="mt-1 grid gap-2 sm:grid-cols-2">
											{#if entry.old_value}
												<div class="flex flex-col gap-1 rounded-md border border-border-subtle bg-surface-muted px-2.5 py-2">
													<h4 class="m-0 text-xs font-bold uppercase tracking-wide text-text-muted">
														Antes
													</h4>
													<pre class="m-0 whitespace-pre-wrap break-words font-sans text-xs leading-normal text-text-secondary">{entry.old_value}</pre>
												</div>
											{/if}
											{#if entry.new_value}
												<div class="flex flex-col gap-1 rounded-md border border-border-subtle bg-surface-muted px-2.5 py-2">
													<h4 class="m-0 text-xs font-bold uppercase tracking-wide text-text-muted">
														Depois
													</h4>
													<pre class="m-0 whitespace-pre-wrap break-words font-sans text-xs leading-normal text-text-secondary">{entry.new_value}</pre>
												</div>
											{/if}
										</div>
									{/if}
								</li>
							{/each}
						</ol>
					</section>
				{/each}
			</div>
		{/if}
	</div>
</div>

<style>
	:global([data-theme='dark']) .history-drawer-panel {
		box-shadow: -18px 0 44px rgba(0, 0, 0, 0.55);
	}
</style>
