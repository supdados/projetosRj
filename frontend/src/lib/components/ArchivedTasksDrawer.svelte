<script lang="ts">
	/**
	 * DRAWER de tarefas ARQUIVADAS. Substitui o antigo filtro `?modo=arquivadas`
	 * da lista (que trocava a tela inteira de forma pouco perceptível) por um
	 * painel lateral dedicado: lista agrupada por projeto, busca própria,
	 * paginação padrão (PaginationBar) e ação "Desarquivar" por linha.
	 *
	 * Anatomia portada do TaskDrawer (backdrop + painel direito com fly,
	 * focusTrap, Esc fecha, header fixo e corpo rolável). Clicar na descrição
	 * delega a `onOpenTask` — o pai FECHA este drawer antes de abrir o
	 * TaskDrawer (nunca empilha drawers).
	 */
	import { fade, fly } from 'svelte/transition';
	import { cubicOut } from 'svelte/easing';
	import { base } from '$app/paths';
	import { focusTrap } from '$lib/actions/focusTrap';
	import { fetchTarefas } from '$lib/api/tasks';
	import { desarquivarTask } from '$lib/api/taskDrawer';
	import { ApiClientError } from '$lib/api/client';
	import { flash } from '$lib/stores/flash';
	import type { TaskCard, TaskHubData } from '$lib/types/tasks';
	import PaginationBar from './PaginationBar.svelte';
	import CountBadge from './CountBadge.svelte';
	import OrgaoTreeSelect from './OrgaoTreeSelect.svelte';
	import type { OrgaoSelectOption } from '$lib/types/orgaoTreeSelect';

	interface Props {
		open: boolean;
		onClose: () => void;
		/** Abre o TaskDrawer da tarefa (o pai fecha este drawer antes). */
		onOpenTask: (taskId: number) => void;
		/** Notifica o pai após desarquivar (re-busca lista/board ativos). */
		onUnarchived: () => void;
	}

	let { open, onClose, onOpenTask, onUnarchived }: Props = $props();

	type LoadState = 'loading' | 'ready' | 'error';

	let data = $state<TaskHubData | null>(null);
	let loadState = $state<LoadState>('loading');
	let errorMessage = $state<string>('');
	let page = $state<number>(1);
	let search = $state<string>('');
	let orgao = $state<string>('');
	let unarchivingId = $state<number | null>(null);

	let inFlight: AbortController | null = null;

	const SEARCH_DEBOUNCE_MS = 350;
	let searchDebounce: ReturnType<typeof setTimeout> | null = null;
	function onSearchInput(): void {
		if (searchDebounce) clearTimeout(searchDebounce);
		searchDebounce = setTimeout(() => {
			page = 1;
			void load();
		}, SEARCH_DEBOUNCE_MS);
	}

	async function load(): Promise<void> {
		inFlight?.abort();
		const controller = new AbortController();
		inFlight = controller;
		loadState = 'loading';
		errorMessage = '';
		try {
			const next = await fetchTarefas(
				{ modo: 'arquivadas', search: search.trim() || undefined, orgao: orgao || undefined, page },
				controller.signal
			);
			if (controller.signal.aborted) return;
			data = next;
			page = next.pagination.page;
			loadState = 'ready';
		} catch (err) {
			if (controller.signal.aborted) return;
			if (err instanceof ApiClientError && err.code === 'unauthenticated') return;
			errorMessage =
				err instanceof Error ? err.message : 'Falha ao carregar as tarefas arquivadas.';
			loadState = 'error';
		}
	}

	// Abriu: recomeça do zero (busca limpa, página 1). Fechou: aborta o fetch.
	let wasOpen = false;
	$effect(() => {
		if (open && !wasOpen) {
			search = '';
			orgao = '';
			page = 1;
			data = null;
			void load();
		}
		if (!open && wasOpen) {
			if (searchDebounce) clearTimeout(searchDebounce);
			inFlight?.abort();
			unarchivingId = null;
		}
		wasOpen = open;
	});

	async function unarchive(task: TaskCard): Promise<void> {
		unarchivingId = task.id;
		try {
			await desarquivarTask(task.id);
			flash.success('Tarefa desarquivada.');
			onUnarchived();
			void load();
		} catch (err) {
			flash.danger(
				err instanceof ApiClientError ? err.message : 'Não foi possível desarquivar a tarefa.'
			);
		} finally {
			unarchivingId = null;
		}
	}

	function goToPage(target: number): void {
		const tp = data?.pagination.total_pages ?? 1;
		if (target < 1 || target > tp || target === page) return;
		page = target;
		void load();
	}

	function onKeydown(event: KeyboardEvent): void {
		if (event.key === 'Escape') {
			event.stopPropagation();
			onClose();
		}
	}

	const DATE_FMT = new Intl.DateTimeFormat('pt-BR', {
		day: '2-digit',
		month: '2-digit',
		year: 'numeric'
	});

	function archivedAtLabel(task: TaskCard): string | null {
		if (!task.archived_at) return null;
		const parsed = new Date(task.archived_at);
		return Number.isNaN(parsed.getTime()) ? null : DATE_FMT.format(parsed);
	}

	function selectOrgao(next: number | null): void {
		orgao = next === null ? '' : String(next);
		page = 1;
		void load();
	}

	// Mesma conversão da tela de tarefas: `serialize_orgao_option` manda
	// value/pai_id como string; o OrgaoTreeSelect monta a árvore com number.
	const orgaoTreeOptions = $derived<OrgaoSelectOption[]>(
		(data?.orgaos_options ?? []).map((o) => ({
			value: Number(o.value),
			label: o.label,
			sigla: o.sigla,
			nome: o.nome,
			pai_id: o.pai_id === null ? null : Number(o.pai_id),
			is_inactive: o.is_inactive
		}))
	);

	const groups = $derived(data?.groups ?? []);
	const totalItems = $derived(data?.total_items ?? 0);
	const isEmpty = $derived(
		loadState === 'ready' && groups.every((g) => g.tasks.length === 0)
	);
</script>

{#if open}
	<div
		class="fixed inset-0 z-modal bg-overlay"
		role="presentation"
		onclick={onClose}
		transition:fade={{ duration: 200 }}
	></div>

	<div
		role="dialog"
		aria-modal="true"
		aria-labelledby="archived-drawer-title"
		tabindex="-1"
		class="fixed right-0 top-0 z-modal flex h-full w-[min(560px,100vw)] flex-col border-l border-border-subtle bg-surface shadow-lg"
		onkeydown={onKeydown}
		use:focusTrap
		transition:fly={{ x: 560, duration: 240, easing: cubicOut, opacity: 1 }}
	>
		<header
			class="flex shrink-0 flex-col gap-3 border-b border-border-subtle bg-surface-elevated px-5 pb-3.5 pt-4"
		>
			<div class="flex items-start justify-between gap-3">
				<div class="flex min-w-0 flex-col gap-1">
					<p class="m-0 text-2xs font-bold uppercase tracking-caps text-text-muted">
						Histórico
					</p>
					<h2
						id="archived-drawer-title"
						class="m-0 font-heading text-lg font-bold leading-snug text-text-primary"
					>
						Tarefas arquivadas
						{#if loadState === 'ready'}
							<CountBadge class="ml-1.5 align-middle">
								{totalItems} tarefa{totalItems === 1 ? '' : 's'}
							</CountBadge>
						{/if}
					</h2>
				</div>
				<button
					type="button"
					onclick={onClose}
					aria-label="Fechar"
					class="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-text-secondary transition-colors duration-fast hover:bg-surface-muted hover:text-brand focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
				>
					<svg viewBox="0 0 24 24" class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
						<path d="M18 6 6 18M6 6l12 12" />
					</svg>
				</button>
			</div>

			<div class="flex items-center gap-2">
				<div class="relative min-w-0 flex-1">
					<i
						class="fas fa-search pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-sm text-text-muted"
						aria-hidden="true"
					></i>
					<input
						id="archivedSearch"
						name="search"
						type="search"
						autocomplete="off"
						bind:value={search}
						oninput={onSearchInput}
						aria-label="Buscar nas tarefas arquivadas"
						placeholder="Digite tarefa ou projeto…"
						class="h-9 w-full rounded-lg border border-border-subtle bg-surface pl-8 pr-2.5 text-sm text-text-primary placeholder:text-text-muted transition-colors duration-fast focus:border-brand focus:outline-none"
					/>
				</div>
				<div class="archived-orgao-select w-44 shrink-0">
					<OrgaoTreeSelect
						id="archived_filter_orgao"
						options={orgaoTreeOptions}
						value={orgao === '' ? null : Number(orgao)}
						onSelect={selectOrgao}
						allowTodos={true}
						ariaLabel="Filtrar arquivadas por órgão"
						disabled={orgaoTreeOptions.length === 0}
					/>
				</div>
			</div>
		</header>

		<div class="thin-scroll flex flex-1 flex-col gap-4 overflow-y-auto px-5 py-4">
			{#if loadState === 'loading' && !data}
				<div
					role="status"
					aria-live="polite"
					class="flex items-center gap-2 py-2 text-sm text-text-secondary"
				>
					<span
						class="h-4 w-4 animate-spin rounded-full border-2 border-border-subtle border-t-primary-600"
						aria-hidden="true"
					></span>
					Carregando tarefas arquivadas…
				</div>
			{:else if loadState === 'error'}
				<div
					role="alert"
					class="flex flex-col gap-2 rounded-md border border-danger bg-surface px-4 py-3 text-sm text-text-primary"
				>
					<p class="m-0">{errorMessage}</p>
					<button
						type="button"
						onclick={() => void load()}
						class="self-start rounded-md border border-border-subtle bg-surface px-3 py-1.5 text-xs font-semibold text-text-secondary transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
					>
						Tentar novamente
					</button>
				</div>
			{:else if isEmpty}
				<div class="flex flex-col items-center gap-2 py-10 text-center">
					<i class="fas fa-box-open text-2xl text-text-muted" aria-hidden="true"></i>
					<p class="m-0 text-sm font-medium text-text-primary">Nenhuma tarefa arquivada.</p>
					<p class="m-0 max-w-[26rem] text-xs text-text-muted">
						Tarefas arquivadas (individualmente ou via "Arquivar finalizados") ficam
						guardadas aqui e podem ser restauradas a qualquer momento.
					</p>
				</div>
			{:else}
				{#each groups as group (group.key)}
					{#if group.tasks.length > 0}
						<section class="flex flex-col gap-2" aria-label={`Arquivadas de ${group.project_titulo}`}>
							<div class="flex min-w-0 items-baseline gap-1.5">
								{#if group.project_id !== null}
									<a
										href={`${base}/projetos/${group.project_id}`}
										class="flex min-w-0 items-baseline gap-1.5 text-sm font-semibold text-brand no-underline transition-colors duration-fast hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
										title={group.project_titulo}
									>
										<span class="shrink-0 font-mono text-xs font-bold text-text-muted">{group.project_id}</span>
										<span class="shrink-0 text-text-muted" aria-hidden="true">–</span>
										<span class="truncate">{group.project_titulo}</span>
									</a>
								{:else}
									<span class="truncate text-sm font-semibold text-text-secondary">{group.project_titulo}</span>
								{/if}
								{#if group.project_orgao_sigla}
									<span class="shrink-0 text-xs text-text-muted">· {group.project_orgao_sigla}</span>
								{/if}
							</div>

							<ul class="m-0 flex list-none flex-col overflow-hidden rounded-lg border border-border-subtle p-0">
								{#each group.tasks as task (task.id)}
									{@const archivedAt = archivedAtLabel(task)}
									<li class="flex items-center gap-3 border-b border-border-subtle px-3 py-2.5 last:border-0">
										<div class="flex min-w-0 flex-1 flex-col gap-1">
											<button
												type="button"
												onclick={() => onOpenTask(task.id)}
												title="Abrir tarefa"
												class="m-0 w-fit max-w-full truncate rounded-sm text-left text-sm text-text-primary transition-colors duration-fast hover:text-brand hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
											>
												{task.descricao}
											</button>
											<div class="flex flex-wrap items-center gap-x-2 gap-y-1">
												{#if task.etapa_titulo}
													<span class="truncate text-2xs text-text-muted" title={task.etapa_titulo}>
														{task.etapa_display_id ? `${task.etapa_display_id} - ` : ''}{task.etapa_titulo}
													</span>
												{/if}
												{#if archivedAt}
													<span class="whitespace-nowrap text-2xs text-text-muted">
														Arquivada em {archivedAt}
													</span>
												{/if}
											</div>
										</div>
										<button
											type="button"
											onclick={() => void unarchive(task)}
											disabled={unarchivingId !== null}
											title="Desarquivar tarefa"
											class="inline-flex shrink-0 items-center gap-1.5 rounded-md border border-border-subtle bg-surface px-2.5 py-1.5 text-xs font-semibold text-brand transition-colors duration-fast hover:border-brand hover:bg-wash-neutral focus:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-50"
										>
											{#if unarchivingId === task.id}
												<span
													class="h-3 w-3 animate-spin rounded-full border-2 border-border-subtle border-t-primary-600"
													aria-hidden="true"
												></span>
											{:else}
												<i class="fas fa-rotate-left text-2xs" aria-hidden="true"></i>
											{/if}
											Desarquivar
										</button>
									</li>
								{/each}
							</ul>
						</section>
					{/if}
				{/each}
			{/if}
		</div>

		{#if loadState === 'ready' && (data?.pagination.total_pages ?? 0) > 1}
			<footer class="shrink-0 border-t border-border-subtle bg-surface-elevated px-5 py-3">
				<PaginationBar
					page={data?.pagination.page ?? 1}
					totalPages={data?.pagination.total_pages ?? 1}
					label="Paginação de tarefas arquivadas"
					total={totalItems}
					perPage={data?.pagination.per_page}
					itemLabel="tarefas"
					showEdges={false}
					onChange={goToPage}
				/>
			</footer>
		{/if}
	</div>
{/if}

<style>
	/* O painel do OrgaoTreeSelect ancora à esquerda (até 420px) e estouraria a
	   borda direita do drawer — aqui ancora à direita do trigger. */
	.archived-orgao-select :global(.ots-panel) {
		left: auto;
		right: 0;
	}
</style>
