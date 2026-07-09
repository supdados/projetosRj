<script lang="ts" module>
	import { fetchAreas, type AreaOption } from '$lib/api/areas';

	// Lista global de áreas: uma fetch por sessão de página; erro zera p/ retry.
	let areasPromise: Promise<AreaOption[]> | null = null;

	interface AreaCandidate {
		area_id: number | null;
		label: string;
		sublabel: string;
	}
</script>

<script lang="ts">
	/**
	 * Picker multi-select de ÁREAS responsáveis da etapa (mudança #3).
	 *
	 * Adaptado do AssigneePicker: popover `position: fixed` que segue o gatilho
	 * no scroll, busca client-side (sigla/nome), checkbox, teclado ↑/↓/Enter/Esc
	 * e saves serializados single-flight latest-wins. A opção especial "Outras"
	 * (area_id null) é SEMPRE o último candidato.
	 */
	import { tick } from 'svelte';
	import '$lib/styles/stage-chips.css';
	import { saveEtapaResponsaveis } from '$lib/api/areas';
	import type { EtapaDetail, EtapaResponsavelArea } from '$lib/types/projectDetail';

	interface Props {
		/** Quando presente: modo PERSIST — cada toggle salva via POST /api/etapas/<id>/responsaveis. */
		etapaId?: number;
		/** Seleção atual ($bindable). Modo LOCAL (sem etapaId): só acumula (composer). */
		selecionadas?: EtapaResponsavelArea[];
		disabled?: boolean;
		/** Chamado com a nova lista após CADA mudança (local ou persist). */
		onChange?: (areas: EtapaResponsavelArea[]) => void;
		/** Chamado com a etapa confirmada pelo SERVIDOR após cada save (modo persist). */
		onSaved?: (etapa: EtapaDetail) => void;
	}

	let { etapaId, selecionadas = $bindable([]), disabled = false, onChange, onSaved }: Props = $props();

	const OUTRAS: AreaCandidate = { area_id: null, label: 'Outras', sublabel: 'Área não cadastrada' };

	let open = $state(false);
	let query = $state('');
	let allCandidates = $state<AreaCandidate[]>([]);
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

	let confirmed: EtapaResponsavelArea[] = [];
	let saving = false;
	let pendingAreas: EtapaResponsavelArea[] | null = null;

	// Estado de TRABALHO: a UI opera sobre `lista`; o prop one-way do StageRow
	// não pode sobrescrever toggles com valor stale do pai durante um save.
	let lista = $state<EtapaResponsavelArea[]>([...selecionadas]);
	let lastSynced: EtapaResponsavelArea[] = selecionadas;
	let localDirty = false;

	$effect(() => {
		const fromProp = selecionadas;
		if (fromProp === lastSynced) return;
		lastSynced = fromProp;
		if (localDirty || saving || pendingAreas !== null) return;
		lista = [...fromProp];
	});

	const MAX_CHIPS = 2;
	const visibleChips = $derived(lista.slice(0, MAX_CHIPS));
	const overflowCount = $derived(Math.max(0, lista.length - MAX_CHIPS));
	const selectedKeys = $derived(new Set(lista.map((s) => s.area_id ?? 'outras')));

	const filteredCandidates = $derived.by(() => {
		const q = query.trim().toLowerCase();
		if (!q) return allCandidates;
		return allCandidates.filter(
			(c) => c.label.toLowerCase().includes(q) || c.sublabel.toLowerCase().includes(q)
		);
	});

	async function ensureCandidates(): Promise<void> {
		if (candidatesLoaded || loadingCandidates) return;
		loadingCandidates = true;
		try {
			if (!areasPromise) areasPromise = fetchAreas().then((r) => r.areas);
			const areas = await areasPromise;
			const seen = new Set<string>();
			const unicos = areas.filter((a) => {
				if (seen.has(a.sigla)) return false;
				seen.add(a.sigla);
				return true;
			});
			allCandidates = [...unicos.map((a) => ({ area_id: a.id, label: a.sigla, sublabel: a.nome })), OUTRAS];
		} catch {
			allCandidates = [];
			areasPromise = null; // permite novo retry
		} finally {
			candidatesLoaded = true;
			loadingCandidates = false;
		}
	}

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
		confirmed = [...lista];
		query = '';
		highlight = 0;
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
	function scheduleSave(areas: EtapaResponsavelArea[]): void {
		if (etapaId == null) return;
		pendingAreas = areas;
		if (!saving) void runSaveLoop();
	}

	async function runSaveLoop(): Promise<void> {
		if (etapaId == null) return;
		saving = true;
		try {
			while (pendingAreas !== null) {
				const areas = pendingAreas;
				pendingAreas = null;
				try {
					const res = await saveEtapaResponsaveis(etapaId, areas);
					// O servidor APLICOU `areas`: atualiza a base de revert SEMPRE,
					// mesmo com toggle novo em voo (antes ficava stale e o revert
					// apagava seleções já persistidas).
					confirmed = res.etapa.responsaveis ?? areas;
					if (pendingAreas === null) {
						lista = [...confirmed];
						localDirty = false;
						onChange?.(lista);
						onSaved?.(res.etapa);
					}
				} catch {
					if (pendingAreas === null) {
						lista = [...confirmed]; // reverte ao último confirmado pelo servidor
						localDirty = false;
						onChange?.(lista);
					}
				}
			}
		} finally {
			saving = false;
		}
	}

	function toggle(candidate: AreaCandidate): void {
		const key = candidate.area_id ?? 'outras';
		const has = selectedKeys.has(key);
		const next = has
			? lista.filter((s) => (s.area_id ?? 'outras') !== key)
			: [...lista, { area_id: candidate.area_id, label: candidate.label }];
		lista = next;
		onChange?.(next);
		if (etapaId != null) {
			localDirty = true;
			scheduleSave(next);
		} else {
			// Modo LOCAL (composer): propaga ao bind: do pai.
			lastSynced = next;
			selecionadas = next;
		}
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
	{#if lista.length > 0}
		<button
			bind:this={triggerEl}
			type="button"
			{disabled}
			onclick={toggleOpen}
			aria-haspopup="listbox"
			aria-expanded={open}
			title="Áreas responsáveis"
			class="group inline-flex items-center rounded-md p-0.5 transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-50"
		>
			<span class="stage-resp-chips">
				{#each visibleChips as chip (chip.area_id ?? chip.label)}
					<span class="stage-resp-chip">{chip.label}</span>
				{/each}
				{#if overflowCount > 0}
					<span class="stage-resp-chip stage-resp-chip--overflow">+{overflowCount}</span>
				{/if}
			</span>
		</button>
	{:else}
		<button
			bind:this={triggerEl}
			type="button"
			{disabled}
			onclick={toggleOpen}
			aria-haspopup="listbox"
			aria-expanded={open}
			title="Selecionar áreas responsáveis"
			class="inline-flex h-7 w-full items-center justify-center gap-1 whitespace-nowrap rounded-md border border-dashed border-border-subtle px-2 text-2xs font-medium text-text-muted transition-colors duration-fast hover:border-primary-400 hover:bg-surface-muted hover:text-text-secondary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-50"
		>
			<i class="fas fa-plus text-2xs" aria-hidden="true"></i>Áreas
		</button>
	{/if}
</div>

{#if open}
	<div
		bind:this={popoverEl}
		role="listbox"
		aria-label="Selecionar áreas responsáveis"
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
				placeholder="Buscar área..."
				aria-label="Buscar áreas"
				class="w-full bg-transparent text-sm text-text-primary placeholder:text-text-muted focus:outline-none"
			/>
		</div>
		<ul class="max-h-[40vh] overflow-y-auto py-1">
			{#if loadingCandidates}
				<li class="px-3 py-2 text-xs text-text-muted">Carregando…</li>
			{:else if filteredCandidates.length === 0}
				<li class="px-3 py-2 text-xs text-text-muted">Nenhuma área encontrada.</li>
			{:else}
				{#each filteredCandidates as candidate, i (candidate.area_id ?? 'outras')}
					{@const selected = selectedKeys.has(candidate.area_id ?? 'outras')}
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
							<span class="min-w-0 flex-1">
								<span class="stage-resp-chip">{candidate.label}</span>
							</span>
							{#if selected}
								<i class="fas fa-check text-xs text-primary-600" aria-hidden="true"></i>
							{/if}
						</button>
					</li>
				{/each}
			{/if}
		</ul>
	</div>
{/if}

<style>
	.stage-resp-chips {
		display: inline-flex;
		flex-wrap: wrap;
		gap: 0.25rem;
		justify-content: center;
	}
	.stage-resp-chip {
		display: inline-flex;
		align-items: center;
		white-space: nowrap;
		border: 1px solid var(--stage-chip-border);
		border-radius: 6px;
		padding: 0.1rem 0.45rem;
		font-size: 0.75rem;
		font-weight: 600;
		color: var(--stage-chip-text);
		background: var(--color-surface);
	}
	.stage-resp-chip--overflow {
		color: var(--stage-chip-text-hover);
		background: var(--stage-chip-bg-hover);
	}
	:global(html[data-theme='dark']) .stage-resp-chip {
		background: var(--color-surface-elevated);
		border-color: var(--color-border);
		color: var(--color-text-secondary);
	}
</style>
