<script lang="ts" module>
	import { fetchAreas, type AreaOption } from '$lib/api/areas';

	// Lista global de áreas: uma fetch por sessão de página; erro zera p/ retry.
	let areasPromise: Promise<AreaOption[]> | null = null;

	/** Candidato: `AreaOption` real ou o nó sintético "Outras" (value -1). */
	interface AreaCandidate {
		value: number;
		pai_id: number | null;
		sigla: string;
		nome: string;
		area_id: number | null;
	}

	const OUTRAS: AreaCandidate = {
		value: -1,
		pai_id: null,
		sigla: 'Outras',
		nome: 'Área não cadastrada',
		area_id: null
	};
</script>

<script lang="ts">
	/**
	 * Picker multi-select de ÁREAS responsáveis da etapa, BUSCA-FIRST: input com
	 * autofocus filtra a lista achatada (o caminho hierárquico aparece como texto
	 * secundário, sem árvore navegável) e a seção "Selecionadas" fica fixa no topo
	 * do painel, imune ao filtro, com remoção em 1 clique. Lista TODAS as áreas
	 * (sem filtro de escopo do usuário) + "Outras" (area_id null) por último.
	 *
	 * Painel no top layer (Popover API) — imune a overflow/transform de ancestrais
	 * (célula de tabela, drawers). Saves serializados single-flight latest-wins; o
	 * backend exige ≥1 área, então remover a última é bloqueado com aviso.
	 */
	import { tick } from 'svelte';
	import '$lib/styles/stage-chips.css';
	import { saveEtapaResponsaveis } from '$lib/api/areas';
	import { ApiClientError } from '$lib/api/client';
	import { flash } from '$lib/stores/flash';
	import type { EtapaDetail, EtapaResponsavelArea } from '$lib/types/projectDetail';
	import { buildOrgaoTree, flattenTreeWithPath, type OrgaoTreeRow } from '$lib/utils/orgaoTree';

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

	let open = $state(false);
	let term = $state('');
	let highlight = $state(0);
	let allCandidates = $state<AreaCandidate[]>([]);
	let candidatesLoaded = $state(false);
	let loadingCandidates = $state(false);

	interface PanelPos {
		top: number | null;
		bottom: number | null;
		left: number;
		width: number;
		maxHeight: number;
	}
	let pos = $state<PanelPos>({ top: 0, bottom: null, left: 0, width: 280, maxHeight: 400 });

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
	const selectedKeys = $derived(new Set(lista.map((s) => s.area_id ?? -1)));

	const listboxId = $derived(etapaId != null ? `arp-listbox-${etapaId}` : 'arp-listbox-local');
	const optId = (index: number): string => `${listboxId}-opt-${index}`;

	// Lista achatada com caminho hierárquico como `path`; `term` vazio = tudo.
	// Todas as áreas descendem de GOVRJ — a raiz sai do caminho exibido.
	const rows = $derived.by<OrgaoTreeRow<AreaCandidate>[]>(() =>
		flattenTreeWithPath(buildOrgaoTree(allCandidates), term, { omitRootAncestor: true })
	);

	// Nome completo do item selecionado (para a linha da seção "Selecionadas").
	const nomeByKey = $derived(new Map(allCandidates.map((c) => [c.area_id ?? -1, c.nome])));

	$effect(() => {
		term;
		highlight = 0;
	});

	async function ensureCandidates(): Promise<void> {
		if (candidatesLoaded || loadingCandidates) return;
		loadingCandidates = true;
		try {
			if (!areasPromise) areasPromise = fetchAreas().then((r) => r.areas);
			const areas = await areasPromise;
			allCandidates = [
				...areas.map((a) => ({
					value: a.id,
					pai_id: a.pai_id,
					sigla: a.sigla,
					nome: a.nome,
					area_id: a.id
				})),
				OUTRAS
			];
		} catch {
			allCandidates = [];
			areasPromise = null; // permite novo retry
		} finally {
			candidatesLoaded = true;
			loadingCandidates = false;
		}
	}

	// Painel no top layer via Popover API — mesmo padrão do SelectMenu.
	function activatePopover(node: HTMLElement): void {
		if (typeof node.showPopover === 'function') node.showPopover();
	}

	function computePosition(): void {
		if (!triggerEl) return;
		const r = triggerEl.getBoundingClientRect();
		const gap = 6;
		const margin = 8;
		const width = Math.min(448, Math.max(364, r.width), window.innerWidth - margin * 2);
		const spaceBelow = window.innerHeight - r.bottom - gap - margin;
		const spaceAbove = r.top - gap - margin;
		const flip = spaceBelow < 240 && spaceAbove > spaceBelow;
		pos = {
			top: flip ? null : r.bottom + gap,
			bottom: flip ? window.innerHeight - r.top + gap : null,
			left: Math.min(Math.max(margin, r.left), window.innerWidth - width - margin),
			width,
			maxHeight: Math.min(420, Math.max(160, flip ? spaceAbove : spaceBelow))
		};
	}

	async function openPicker(): Promise<void> {
		if (disabled) return;
		confirmed = [...lista];
		term = '';
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
				} catch (err) {
					flash.danger(
						err instanceof ApiClientError
							? err.message
							: 'Não foi possível salvar as áreas responsáveis.',
						{ key: 'etapa-areas-responsaveis' }
					);
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

	/** Aplica a nova seleção; o backend exige ≥1 área, então bloqueia esvaziar. */
	function applySelection(next: EtapaResponsavelArea[]): void {
		if (etapaId != null && next.length === 0) {
			flash.warning('A etapa precisa de ao menos uma área responsável.', {
				key: 'etapa-areas-responsaveis'
			});
			return;
		}
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

	function toggle(candidate: AreaCandidate): void {
		const key = candidate.area_id ?? -1;
		const has = selectedKeys.has(key);
		applySelection(
			has
				? lista.filter((s) => (s.area_id ?? -1) !== key)
				: [...lista, { area_id: candidate.area_id, label: candidate.sigla }]
		);
	}

	function removeSelected(item: EtapaResponsavelArea): void {
		const key = item.area_id ?? -1;
		applySelection(lista.filter((s) => (s.area_id ?? -1) !== key));
	}

	function moveHighlight(step: number): void {
		if (rows.length === 0) return;
		highlight = (highlight + step + rows.length) % rows.length;
		tick().then(() => {
			document.getElementById(optId(highlight))?.scrollIntoView({ block: 'nearest' });
		});
	}

	function onInputKeydown(event: KeyboardEvent): void {
		if (event.key === 'Escape') {
			event.preventDefault();
			closePicker();
			triggerEl?.focus();
			return;
		}
		if (event.key === 'Tab') {
			closePicker();
			return;
		}
		if (event.key === 'ArrowDown') {
			event.preventDefault();
			moveHighlight(1);
			return;
		}
		if (event.key === 'ArrowUp') {
			event.preventDefault();
			moveHighlight(-1);
			return;
		}
		if (event.key === 'Enter') {
			event.preventDefault();
			const row = rows[highlight];
			if (row) toggle(row.option);
			return;
		}
		if (event.key === 'Backspace' && term === '' && lista.length > 0) {
			event.preventDefault();
			removeSelected(lista[lista.length - 1]);
		}
	}

	// Fecha ao clicar fora; scroll/resize REPOSICIONAM o popover para seguir o
	// gatilho — fechar no scroll impedia até rolar a própria lista.
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
			class="group inline-flex items-center rounded-md p-0.5 transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:opacity-50"
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
			class="inline-flex h-7 w-full items-center justify-center gap-1 whitespace-nowrap rounded-md border border-dashed border-border-subtle px-2 text-2xs font-medium text-text-muted transition-colors duration-fast hover:border-brand-soft hover:bg-surface-muted hover:text-text-secondary focus:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:opacity-50"
		>
			<i class="fas fa-plus text-2xs" aria-hidden="true"></i>Áreas
		</button>
	{/if}
</div>

{#if open}
	<div
		bind:this={popoverEl}
		popover="manual"
		use:activatePopover
		class="arp-panel fixed z-dropdown flex flex-col overflow-hidden rounded-xl border border-border-subtle bg-surface shadow-lg"
		style:top={pos.top != null ? `${pos.top}px` : undefined}
		style:bottom={pos.bottom != null ? `${pos.bottom}px` : undefined}
		style:left="{pos.left}px"
		style:width="{pos.width}px"
		style:max-height="{pos.maxHeight}px"
	>
		{#if lista.length > 0}
			<div class="shrink-0 border-b border-border-subtle px-2 pb-1.5 pt-2">
				<div class="px-1 pb-1 text-2xs font-bold uppercase tracking-[0.08em] text-text-muted">
					Selecionadas
				</div>
				<ul class="thin-scroll flex max-h-[140px] flex-col overflow-y-auto">
					{#each lista as item (item.area_id ?? item.label)}
						<li class="flex items-center gap-2 rounded-md px-1.5 py-1 transition-colors duration-fast hover:bg-surface-muted">
							<span class="shrink-0 text-[12.5px] font-semibold text-text-primary">{item.label}</span>
							<span
								class="min-w-0 flex-1 truncate text-2xs text-text-muted"
								title={nomeByKey.get(item.area_id ?? -1) ?? undefined}
							>
								{nomeByKey.get(item.area_id ?? -1) ?? ''}
							</span>
							<button
								type="button"
								onclick={() => removeSelected(item)}
								aria-label={`Remover ${item.label}`}
								title={`Remover ${item.label}`}
								class="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded text-text-muted transition-colors duration-fast hover:bg-border-subtle hover:text-danger focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
							>
								<i class="fas fa-xmark text-2xs" aria-hidden="true"></i>
							</button>
						</li>
					{/each}
				</ul>
			</div>
		{/if}

		<div class="flex shrink-0 items-center gap-2 border-b border-border-subtle px-3 py-2">
			<i class="fas fa-magnifying-glass text-2xs text-text-muted" aria-hidden="true"></i>
			<input
				bind:this={inputEl}
				bind:value={term}
				onkeydown={onInputKeydown}
				type="text"
				role="combobox"
				aria-expanded="true"
				aria-controls={listboxId}
				aria-activedescendant={rows.length > 0 ? optId(highlight) : undefined}
				autocomplete="off"
				placeholder="Buscar área..."
				aria-label="Buscar áreas"
				class="w-full bg-transparent text-sm text-text-primary placeholder:text-text-muted focus:outline-none"
			/>
		</div>

		<!-- SEM flex-1: base 0 num flex-col de altura auto colapsa a lista para 0px;
		     com basis auto ela cresce pelo conteúdo e encolhe (shrink) só quando o
		     painel atinge o max-height. -->
		<ul
			id={listboxId}
			role="listbox"
			aria-multiselectable="true"
			aria-label="Áreas disponíveis"
			class="thin-scroll min-h-0 overflow-y-auto py-1"
		>
			{#if loadingCandidates}
				<li class="px-3 py-2 text-xs text-text-muted">Carregando…</li>
			{:else if rows.length === 0}
				<li class="px-3 py-2 text-xs text-text-muted">Nenhuma área encontrada.</li>
			{:else}
				{#each rows as row, index (row.value)}
					{@const selected = selectedKeys.has(row.option.area_id ?? -1)}
					<!-- Mesma tipografia das linhas do OrgaoTreeSelect: caminho muted
					     inline + sigla mono bold, sem chip/borda. -->
					<li
						id={optId(index)}
						role="option"
						aria-selected={selected}
						tabindex="-1"
						onclick={() => toggle(row.option)}
						onmouseenter={() => (highlight = index)}
						onkeydown={(e) => {
							if (e.key === 'Enter' || e.key === ' ') {
								e.preventDefault();
								toggle(row.option);
							}
						}}
						class="flex min-h-[30px] w-full cursor-pointer items-start gap-2 px-3 py-1.5 text-left transition-colors duration-fast {index ===
						highlight
							? 'bg-surface-muted'
							: ''}"
					>
						<span class="mt-0.5 flex h-[16px] w-[18px] shrink-0 items-center justify-center">
							{#if selected}
								<i class="fas fa-check text-xs text-brand" aria-hidden="true"></i>
							{/if}
						</span>
						<!-- Sem truncate: o caminho completo SEMPRE aparece, quebrando linha
						     quando não couber. -->
						<span class="min-w-0 flex-1 whitespace-normal break-words leading-snug" title={row.option.nome}>
							{#if row.path}<span class="text-[11.5px] text-text-muted">{row.path} › </span
								>{/if}<span class="text-[12.5px] font-medium text-text-primary"
								>{row.option.sigla}</span
							>
						</span>
					</li>
				{/each}
			{/if}
		</ul>

		<span class="sr-only" aria-live="polite">
			{lista.length} {lista.length === 1 ? 'área selecionada' : 'áreas selecionadas'}
		</span>
	</div>
{/if}

<style>
	/* Neutraliza a UA stylesheet de [popover] (inset:0 + margin:auto), que
	   competiria com as coordenadas inline calculadas em JS. */
	.arp-panel {
		margin: 0;
		inset: auto;
	}
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
		background: var(--ds-color-surface-base);
	}
	.stage-resp-chip--overflow {
		color: var(--stage-chip-text-hover);
		background: var(--stage-chip-bg-hover);
	}
	:global(html[data-theme='dark']) .stage-resp-chip {
		background: var(--ds-color-surface-raised);
		border-color: var(--ds-color-border-base);
		color: var(--ds-color-text-secondary);
	}
</style>
