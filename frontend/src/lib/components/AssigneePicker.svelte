<script lang="ts" module>
	import type { TaskAssignee } from '$lib/types/tasks';

	// Cache da lista COMPLETA de candidatos por chave (tarefa OU projeto). Tarefas
	// de um mesmo projeto não compartilham chave (a fonte por-tarefa cobre tarefas
	// sem projeto), mas o cache evita refetch ao reabrir o mesmo picker e permite
	// saber `hasMore` (se há mais alguém p/ atribuir) já na montagem.
	const candidatesCache = new Map<string, Promise<TaskAssignee[]>>();
</script>

<script lang="ts">
	/**
	 * Picker de responsáveis MÚLTIPLOS estilo "membros".
	 *
	 * Na linha (coluna estreita) mostra avatares de iniciais empilhados; se ainda
	 * houver gente p/ atribuir, uma bolinha "+" tracejada aparece ATRÁS do último
	 * avatar. Ao abrir, um popover `position: fixed` (escapa do overflow-x da
	 * grade) traz busca (filtro client-side) + lista de candidatos com check.
	 *
	 * Saves são OTIMISTAS e SERIALIZADOS (single-flight latest-wins): só uma
	 * requisição em voo; toggles durante o voo são reenviados ao final, evitando
	 * que um POST antigo sobrescreva o estado do servidor. Acessível por teclado
	 * (setas/Enter/Esc) e com roles listbox/option.
	 */
	import { tick } from 'svelte';
	import type { TaskCard } from '$lib/types/tasks';
	import AssigneeAvatar from './AssigneeAvatar.svelte';
	import { fetchHubResponsaveis, fetchTaskCandidates, saveTaskAssignees } from '$lib/api/tasks';

	interface Props {
		/** Quando presente: modo PERSIST (salva e notifica a cada toggle). */
		taskId?: number;
		/** Modo LOCAL (sem taskId): candidatos vêm do projeto; sem save (quick-add). */
		projectValue?: string;
		assignees?: TaskAssignee[];
		disabled?: boolean;
		/** Chamado com a nova lista após cada mudança (parent atualiza o card). */
		onChange?: (assignees: TaskAssignee[]) => void;
		/** Chamado com o envelope `{task, detail}` confirmado pelo SERVIDOR após
		 *  cada save (modo persist) — permite ao pai reconciliar board/drawer. */
		onSaved?: (result: { task: TaskCard; detail: unknown }) => void;
	}

	let {
		taskId,
		projectValue,
		assignees = $bindable([]),
		disabled = false,
		onChange,
		onSaved
	}: Props = $props();

	let open = $state(false);
	let query = $state('');
	let allCandidates = $state<TaskAssignee[]>([]);
	let candidatesLoaded = $state(false);
	let loadingCandidates = $state(false);
	let highlight = $state(-1);
	let pos = $state<{ top: number; left: number; width: number; flip: boolean }>({
		top: 0,
		left: 0,
		width: 280,
		flip: false
	});

	let triggerEl = $state<HTMLButtonElement | null>(null);
	let popoverEl = $state<HTMLDivElement | null>(null);
	let inputEl = $state<HTMLInputElement | null>(null);

	let confirmed: TaskAssignee[] = [];
	let saving = false;
	let pendingIds: number[] | null = null;

	const MAX_AVATARS = 3;
	const visibleAvatars = $derived(assignees.slice(0, MAX_AVATARS));
	const overflowCount = $derived(Math.max(0, assignees.length - MAX_AVATARS));
	const selectedIds = $derived(new Set(assignees.map((a) => a.id)));

	// Só há "mais para adicionar" se conhecemos os candidatos E algum ainda não
	// está selecionado. Enquanto não carregou, NÃO mostramos o "+" (evita sugerir
	// adição quando já estão todos atribuídos — o que induzia ao erro).
	const hasMore = $derived(
		candidatesLoaded && allCandidates.some((c) => !selectedIds.has(c.id))
	);

	const filteredCandidates = $derived.by(() => {
		const q = query.trim().toLowerCase();
		if (!q) return allCandidates;
		return allCandidates.filter(
			(c) =>
				(c.name || '').toLowerCase().includes(q) ||
				(c.subtitle || '').toLowerCase().includes(q)
		);
	});

	function cacheKey(): string | null {
		if (taskId != null) return `t${taskId}`;
		if (projectValue) return `p${projectValue}`;
		return null;
	}

	function fetchCandidatesRaw(): Promise<TaskAssignee[]> {
		if (taskId != null) return fetchTaskCandidates(taskId).then((r) => r.users);
		if (projectValue) return fetchHubResponsaveis({ project: projectValue }).then((r) => r.users);
		return Promise.resolve([]);
	}

	async function ensureCandidates(): Promise<void> {
		if (candidatesLoaded || loadingCandidates) return;
		const key = cacheKey();
		if (!key) {
			candidatesLoaded = true;
			return;
		}
		loadingCandidates = true;
		try {
			let promise = candidatesCache.get(key);
			if (!promise) {
				promise = fetchCandidatesRaw();
				candidatesCache.set(key, promise);
			}
			allCandidates = await promise;
		} catch {
			allCandidates = [];
			candidatesCache.delete(key); // permite novo retry
		} finally {
			candidatesLoaded = true;
			loadingCandidates = false;
		}
	}

	// Carrega os candidatos na montagem QUANDO já há responsáveis — assim sabemos
	// `hasMore` (mostrar ou não o "+") sem precisar abrir o popover. Pickers vazios
	// carregam ao abrir.
	$effect(() => {
		if (assignees.length > 0 && !candidatesLoaded && !loadingCandidates) {
			void ensureCandidates();
		}
	});

	function computePosition(): void {
		if (!triggerEl) return;
		const r = triggerEl.getBoundingClientRect();
		const width = Math.min(320, Math.max(260, r.width));
		const estimatedHeight = 320;
		const flip = r.bottom + estimatedHeight > window.innerHeight && r.top > estimatedHeight;
		const left = Math.min(Math.max(8, r.left), window.innerWidth - width - 8);
		pos = { top: flip ? r.top : r.bottom + 4, left, width, flip };
	}

	async function openPicker(): Promise<void> {
		if (disabled) return;
		confirmed = [...assignees];
		query = '';
		highlight = 0;
		// Carrega os candidatos ANTES de abrir: o popover aparece já no tamanho
		// final (sem abrir com "Carregando…" e depois crescer). Cacheado = instantâneo.
		await ensureCandidates();
		computePosition();
		open = true;
		await tick();
		inputEl?.focus();
	}

	function closePicker(): void {
		open = false;
	}

	function toggleOpen(): void {
		if (open) closePicker();
		else void openPicker();
	}

	/** Enfileira a lista desejada e garante UM save em voo por vez (latest-wins). */
	function scheduleSave(ids: number[]): void {
		if (taskId == null) return;
		pendingIds = ids;
		if (!saving) void runSaveLoop();
	}

	async function runSaveLoop(): Promise<void> {
		if (taskId == null) return;
		saving = true;
		try {
			while (pendingIds !== null) {
				const ids = pendingIds;
				pendingIds = null;
				try {
					const res = await saveTaskAssignees(taskId, ids);
					// Só reconcilia com o servidor se NÃO entrou um toggle novo
					// enquanto salvávamos — senão o loop reenvia a seleção mais nova.
					if (pendingIds === null) {
						assignees = res.task.assignees ?? assignees;
						confirmed = [...assignees];
						onChange?.(assignees);
						onSaved?.(res);
					}
				} catch {
					if (pendingIds === null) {
						assignees = [...confirmed]; // reverte ao último confirmado
						onChange?.(assignees);
					}
				}
			}
		} finally {
			saving = false;
		}
	}

	function toggle(candidate: TaskAssignee): void {
		const has = selectedIds.has(candidate.id);
		const next = has
			? assignees.filter((a) => a.id !== candidate.id)
			: [...assignees, candidate];
		assignees = next;
		onChange?.(next);
		// Modo PERSIST salva e notifica; modo LOCAL (quick-add) só acumula a
		// seleção — a criação envia os ids e notifica no backend.
		if (taskId != null) scheduleSave(next.map((a) => a.id));
	}

	function onInputKeydown(event: KeyboardEvent): void {
		if (event.key === 'Escape') {
			event.preventDefault();
			closePicker();
			triggerEl?.focus();
			return;
		}
		if (event.key === 'ArrowDown') {
			event.preventDefault();
			highlight = Math.min(highlight + 1, filteredCandidates.length - 1);
			return;
		}
		if (event.key === 'ArrowUp') {
			event.preventDefault();
			highlight = Math.max(highlight - 1, 0);
			return;
		}
		if (event.key === 'Enter') {
			event.preventDefault();
			const candidate = filteredCandidates[highlight];
			if (candidate) toggle(candidate);
		}
	}

	// Fecha ao clicar fora; scroll/resize REPOSICIONAM o popover (fixed) para
	// seguir o gatilho — fechar no scroll impedia até rolar a própria lista.
	$effect(() => {
		if (!open) return;
		const onPointer = (e: MouseEvent) => {
			const target = e.target as Node;
			if (triggerEl?.contains(target) || popoverEl?.contains(target)) return;
			closePicker();
		};
		const onScroll = (e: Event) => {
			if (popoverEl && e.target instanceof Node && popoverEl.contains(e.target)) return;
			computePosition();
		};
		const onResize = () => computePosition();
		window.addEventListener('mousedown', onPointer, true);
		window.addEventListener('scroll', onScroll, true);
		window.addEventListener('resize', onResize);
		return () => {
			window.removeEventListener('mousedown', onPointer, true);
			window.removeEventListener('scroll', onScroll, true);
			window.removeEventListener('resize', onResize);
		};
	});
</script>

<div class="flex w-full items-center justify-center">
	{#if assignees.length > 0}
		<!-- Preenchido: avatares + (se houver mais p/ atribuir) uma bolinha "+"
		     tracejada ATRÁS do último avatar (z menor que os avatares). -->
		<button
			bind:this={triggerEl}
			type="button"
			{disabled}
			onclick={toggleOpen}
			aria-haspopup="listbox"
			aria-expanded={open}
			title="Responsáveis"
			class="group inline-flex items-center rounded-full p-0.5 transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:opacity-50"
		>
			<span class="flex -space-x-1.5">
				{#each visibleAvatars as a, i (a.id)}
					<!-- z decrescente por índice: o 1º avatar fica NA FRENTE do 2º, que
					     fica na frente do 3º (e todos na frente da bolinha "+" / "+N"). -->
					<span
						class="relative rounded-full ring-2 ring-surface"
						style="z-index: {visibleAvatars.length - i + 1}"
					>
						<AssigneeAvatar name={a.name} initials={a.initials} size="md" />
					</span>
				{/each}
				{#if overflowCount > 0}
					<span
						class="relative z-[1] inline-flex h-7 w-7 items-center justify-center rounded-full bg-surface-muted text-2xs font-semibold text-text-secondary ring-2 ring-surface"
					>
						+{overflowCount}
					</span>
				{/if}
				{#if hasMore}
					<span
						class="relative z-0 inline-flex h-7 w-7 items-center justify-center rounded-full border border-dashed border-border-subtle text-text-muted ring-2 ring-surface transition-colors duration-fast group-hover:border-brand-soft group-hover:text-brand"
					>
						<i class="fas fa-plus text-2xs" aria-hidden="true"></i>
					</span>
				{/if}
			</span>
		</button>
	{:else}
		<!-- Vazio: chip-placeholder no MESMO formato dos chips à esquerda
		     (mesma altura, cantos, largura cheia) — só que tracejado. -->
		<button
			bind:this={triggerEl}
			type="button"
			{disabled}
			onclick={toggleOpen}
			aria-haspopup="listbox"
			aria-expanded={open}
			title="Atribuir responsável"
			class="inline-flex h-7 w-full items-center justify-center gap-1 whitespace-nowrap rounded-md border border-dashed border-border-subtle px-2 text-2xs font-medium text-text-muted transition-colors duration-fast hover:border-brand-soft hover:bg-surface-muted hover:text-text-secondary focus:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:opacity-50"
		>
			<i class="fas fa-plus text-2xs" aria-hidden="true"></i>Atribuir
		</button>
	{/if}
</div>

{#if open}
	<div
		bind:this={popoverEl}
		role="listbox"
		aria-label="Selecionar responsáveis"
		class="fixed z-dropdown w-[280px] overflow-hidden rounded-xl border border-border-subtle bg-surface shadow-lg"
		style="left: {pos.left}px; width: {pos.width}px; {pos.flip
			? `bottom: ${window.innerHeight - pos.top + 4}px`
			: `top: ${pos.top}px`}"
	>
		<div class="flex items-center gap-2 border-b border-border-subtle px-3 py-2">
			<i class="fas fa-magnifying-glass text-2xs text-text-muted" aria-hidden="true"></i>
			<input
				bind:this={inputEl}
				bind:value={query}
				oninput={() => (highlight = 0)}
				onkeydown={onInputKeydown}
				type="text"
				placeholder="Adicionar responsável..."
				aria-label="Buscar pessoas"
				class="w-full bg-transparent text-sm text-text-primary placeholder:text-text-muted focus:outline-none"
			/>
		</div>
		<ul class="max-h-[40vh] overflow-y-auto py-1">
			{#if loadingCandidates}
				<li class="px-3 py-2 text-xs text-text-muted">Carregando…</li>
			{:else if filteredCandidates.length === 0}
				<li class="px-3 py-2 text-xs text-text-muted">Ninguém encontrado.</li>
			{:else}
				{#each filteredCandidates as candidate, i (candidate.id)}
					{@const selected = selectedIds.has(candidate.id)}
					<li role="option" aria-selected={selected}>
						<button
							type="button"
							onclick={() => toggle(candidate)}
							onmouseenter={() => (highlight = i)}
							class="flex w-full items-center gap-2.5 px-3 py-1.5 text-left transition-colors duration-fast focus:outline-none {i ===
							highlight
								? 'bg-primary-100/50'
								: 'hover:bg-surface-muted'}"
						>
							<AssigneeAvatar name={candidate.name} initials={candidate.initials} size="md" />
							<span class="min-w-0 flex-1">
								<span class="block truncate text-sm font-medium text-text-primary">{candidate.name}</span>
								{#if candidate.subtitle}
									<span class="block truncate text-xs text-text-muted">{candidate.subtitle}</span>
								{/if}
							</span>
							{#if selected}
								<i class="fas fa-check text-xs text-brand" aria-hidden="true"></i>
							{/if}
						</button>
					</li>
				{/each}
			{/if}
		</ul>
	</div>
{/if}
