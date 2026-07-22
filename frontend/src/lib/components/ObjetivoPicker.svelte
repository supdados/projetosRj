<script lang="ts">
	/**
	 * Picker progressivo de Objetivo → Resultado esperado → Indicadores EEGD
	 * (CriarProjetoModal). Summary card que se monta conforme o usuário escolhe,
	 * com lápis "Alterar" por linha. Todo o estado de dados vive no modal; aqui
	 * só há estado de apresentação (modo edição + celebração).
	 */
	import { tick } from 'svelte';
	import type {
		ObjetivoCatalogo,
		ResultadoCatalogo,
		IndicadorCatalogo
	} from '$lib/api/projects';

	interface Props {
		objetivos: ObjetivoCatalogo[];
		objetivoId: string;
		resultados: ResultadoCatalogo[];
		resultadoId: string;
		resultadosLoading: boolean;
		indicadores: IndicadorCatalogo[];
		indicadoresLoading: boolean;
		selectedIndicadores: number[];
		/** IDs já revelados pela animação escalonada (estado do modal). */
		revealedIndicadores: Set<number>;
		onObjetivoSelect: (id: string) => void;
		onResultadoSelect: (id: string) => void;
		onToggleIndicador: (id: number) => void;
	}

	let {
		objetivos,
		objetivoId,
		resultados,
		resultadoId,
		resultadosLoading,
		indicadores,
		indicadoresLoading,
		selectedIndicadores,
		revealedIndicadores,
		onObjetivoSelect,
		onResultadoSelect,
		onToggleIndicador
	}: Props = $props();

	interface ObjetivoTheme {
		hue: string;
		icon: string;
	}

	// 8 temas mapeados por índice (módulo) — tokens semânticos do app, nunca hex.
	const THEMES: ObjetivoTheme[] = [
		{
			hue: 'var(--ds-color-primary-600)',
			icon: 'M17 21v-2a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v2 M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8 M23 21v-2a4 4 0 0 0-3-3.87 M16 3.13a4 4 0 0 1 0 7.75'
		},
		{
			hue: 'var(--ds-color-success-600)',
			icon: 'M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01z'
		},
		{
			hue: 'var(--ds-color-violet-600)',
			icon: 'M8.5 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8 M2 21v-2a4 4 0 0 1 4-4h5 M16 16l2 2 4-4'
		},
		{
			hue: 'var(--ds-color-danger-600)',
			icon: 'M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z'
		},
		{
			hue: 'var(--ds-color-info-600)',
			icon: 'M3 3v18h18 M7 14v4 M12 9v9 M17 5v13'
		},
		{
			hue: 'var(--ds-color-pending)',
			icon: 'M2 4h20v6H2z M2 14h20v6H2z M6 7h.01 M6 17h.01'
		},
		{
			hue: 'var(--ds-color-warning-600)',
			icon: 'M9 18h6 M10 22h4 M12 2a7 7 0 0 0-4 12.7c.6.5 1 1.4 1 2.3h6c0-.9.4-1.8 1-2.3A7 7 0 0 0 12 2z'
		},
		{
			hue: 'var(--ds-color-orange-600)',
			icon: 'M23 4v6h-6 M1 20v-6h6 M3.5 9a9 9 0 0 1 14.85-3.36L23 10 M1 14l4.65 4.36A9 9 0 0 0 20.5 15'
		}
	];

	function themeFor(index: number): ObjetivoTheme {
		return THEMES[((index % THEMES.length) + THEMES.length) % THEMES.length];
	}

	function tintOf(theme: ObjetivoTheme): string {
		return `color-mix(in srgb, ${theme.hue} 12%, transparent)`;
	}

	let editObj = $state(false);
	let editRes = $state(false);
	let celebrating = $state(false);
	let celebrateTimer: ReturnType<typeof setTimeout> | null = null;
	let objPencilEl = $state<HTMLButtonElement | null>(null);
	let resPencilEl = $state<HTMLButtonElement | null>(null);
	let objZoneEl = $state<HTMLDivElement | null>(null);
	let resZoneEl = $state<HTMLDivElement | null>(null);

	const selectedObjIndex = $derived(objetivos.findIndex((o) => String(o.id) === objetivoId));
	const selectedObj = $derived(selectedObjIndex >= 0 ? objetivos[selectedObjIndex] : null);
	const objTheme = $derived(themeFor(Math.max(0, selectedObjIndex)));
	const selectedRes = $derived(resultados.find((r) => String(r.id) === resultadoId) ?? null);
	const hasObj = $derived(selectedObj !== null);
	const showObjPicker = $derived(!hasObj || editObj);
	const showResPicker = $derived(!showObjPicker && (resultadoId === '' || editRes));
	const showIndRow = $derived(!showObjPicker && !showResPicker && resultadoId !== '');
	const hasResRow = $derived(selectedRes !== null && !editRes && !showObjPicker);

	function celebrate(): void {
		if (celebrateTimer) clearTimeout(celebrateTimer);
		// Remove e recoloca a classe num tick para reiniciar em escolhas seguidas.
		celebrating = false;
		void tick().then(() => (celebrating = true));
		celebrateTimer = setTimeout(() => (celebrating = false), 900);
	}

	// O elemento focado desmonta nas trocas de zona; sem refocar num nó que
	// permanece montado, o foco cai no body e escapa do focus trap do modal.
	function focusAfterTick(target: () => HTMLElement | null | undefined): void {
		void tick().then(() => target()?.focus());
	}

	function firstCardIn(zone: HTMLDivElement | null): HTMLElement | null {
		return zone?.querySelector<HTMLElement>('button') ?? null;
	}

	function pickObjetivo(objetivo: ObjetivoCatalogo): void {
		const id = String(objetivo.id);
		const changed = id !== objetivoId;
		editObj = false;
		editRes = false;
		celebrate();
		// Reclicar o mesmo objetivo não reseta resultado/indicadores.
		if (changed) onObjetivoSelect(id);
		focusAfterTick(() => objPencilEl);
	}

	function pickResultado(resultado: ResultadoCatalogo): void {
		const id = String(resultado.id);
		const changed = id !== resultadoId;
		editRes = false;
		if (changed) onResultadoSelect(id);
		focusAfterTick(() => resPencilEl);
	}

	function startEditResultado(): void {
		editRes = true;
		focusAfterTick(() => firstCardIn(resZoneEl));
	}

	function clearObjetivo(): void {
		editObj = false;
		editRes = false;
		onObjetivoSelect('');
		focusAfterTick(() => firstCardIn(objZoneEl));
	}

	function clearResultado(): void {
		editRes = false;
		onResultadoSelect('');
		focusAfterTick(() => firstCardIn(resZoneEl));
	}

	const questionClass = 'text-sm font-semibold text-text-primary';
	const microLabelClass = 'text-2xs font-semibold uppercase tracking-caps text-text-muted';
	const pencilBtnClass =
		'grid h-8 w-8 flex-none place-items-center rounded-md border border-border-subtle bg-surface text-text-muted transition-colors duration-fast hover:border-primary-500 hover:bg-surface-muted hover:text-primary-600 active:scale-95 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500';
	const removeBtnClass =
		'grid h-8 w-8 flex-none place-items-center rounded-md border border-border-subtle bg-surface text-text-muted transition-colors duration-fast hover:border-danger hover:bg-surface-muted hover:text-danger active:scale-95 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500';
	const emptyBoxClass =
		'rounded-lg border border-dashed border-border-subtle bg-surface-muted px-4 py-3.5 text-sm text-text-muted';
</script>

{#snippet pencilIcon()}
	<svg
		viewBox="0 0 24 24"
		class="h-3.5 w-3.5"
		fill="none"
		stroke="currentColor"
		stroke-width="2"
		stroke-linecap="round"
		stroke-linejoin="round"
		aria-hidden="true"
	>
		<path d="M12 20h9" />
		<path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z" />
	</svg>
{/snippet}

{#snippet clearIcon()}
	<svg
		viewBox="0 0 24 24"
		class="h-3.5 w-3.5"
		fill="none"
		stroke="currentColor"
		stroke-width="2"
		stroke-linecap="round"
		aria-hidden="true"
	>
		<path d="M6 6l12 12M18 6L6 18" />
	</svg>
{/snippet}

{#snippet loadingRow(text: string)}
	<p role="status" aria-live="polite" class="flex items-center gap-2 text-sm text-text-secondary">
		<svg class="h-3.5 w-3.5 animate-spin" viewBox="0 0 24 24" fill="none" aria-hidden="true">
			<circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="3" class="opacity-25" />
			<path d="M22 12a10 10 0 0 0-10-10" stroke="currentColor" stroke-width="3" stroke-linecap="round" />
		</svg>
		{text}
	</p>
{/snippet}

<div class="flex flex-col gap-4">
	{#if hasObj && selectedObj}
		<div class="cp-op-card overflow-hidden rounded-lg border border-border-subtle bg-surface">
			<div class="flex items-center gap-3 px-4 py-3.5">
				<span
					class="grid h-10 w-10 flex-none place-items-center rounded-md"
					class:cp-op-dot-pop={celebrating}
					style:background={tintOf(objTheme)}
					style:color={objTheme.hue}
					aria-hidden="true"
				>
					<svg
						viewBox="0 0 24 24"
						class="h-5 w-5"
						fill="none"
						stroke="currentColor"
						stroke-width="2"
						stroke-linecap="round"
						stroke-linejoin="round"
					>
						<path d={objTheme.icon} />
					</svg>
				</span>
				<span class="flex min-w-0 flex-1 flex-col gap-0.5">
					<span
						class="text-2xs font-bold uppercase tracking-caps"
						style:color={objTheme.hue}
					>
						Objetivo {selectedObjIndex + 1}
					</span>
					<span class="text-sm font-semibold leading-snug text-text-primary">
						{selectedObj.descricao}
					</span>
				</span>
				<button
					type="button"
					bind:this={objPencilEl}
					title="Alterar objetivo"
					aria-label="Alterar objetivo"
					aria-expanded={editObj}
					onclick={() => (editObj = true)}
					class={pencilBtnClass}
				>
					{@render pencilIcon()}
				</button>
				<button
					type="button"
					title="Remover objetivo"
					aria-label="Remover objetivo"
					onclick={clearObjetivo}
					class={removeBtnClass}
				>
					{@render clearIcon()}
				</button>
			</div>

			{#if hasResRow && selectedRes}
				<div class="cp-op-row-in flex items-center gap-3 py-3 pl-[68px] pr-4 pt-0">
					<span class="flex min-w-0 flex-1 flex-col gap-0.5">
						<span class={microLabelClass}>Resultado esperado</span>
						<span class="text-sm font-medium leading-snug text-text-primary">
							{selectedRes.descricao}
						</span>
					</span>
					<button
						type="button"
						bind:this={resPencilEl}
						title="Alterar resultado esperado"
						aria-label="Alterar resultado esperado"
						aria-expanded={editRes}
						onclick={startEditResultado}
						class={pencilBtnClass}
					>
						{@render pencilIcon()}
					</button>
					<button
						type="button"
						title="Remover resultado esperado"
						aria-label="Remover resultado esperado"
						onclick={clearResultado}
						class={removeBtnClass}
					>
						{@render clearIcon()}
					</button>
				</div>
			{/if}

			{#if showIndRow}
				<div class="cp-op-row-in flex flex-col gap-2 pb-4 pl-[68px] pr-4 pt-0">
					<span class={microLabelClass}>
						Indicadores
						<span class="normal-case tracking-normal font-regular">· selecione um ou mais</span>
					</span>
					{#if indicadoresLoading}
						{@render loadingRow('Carregando indicadores...')}
					{:else if indicadores.length === 0}
						<p class="text-sm text-text-muted">
							Nenhum indicador disponível para este resultado esperado.
						</p>
					{:else}
						<div class="flex flex-wrap gap-2">
							{#each indicadores as ind (ind.id)}
								{@const checked = selectedIndicadores.includes(ind.id)}
								<button
									type="button"
									aria-pressed={checked}
									onclick={() => onToggleIndicador(ind.id)}
									class="inline-flex items-center gap-2 rounded-lg border py-2 pl-2.5 pr-3 text-left text-xs transition-[opacity,transform,color,background-color,border-color] duration-300 active:scale-[0.98] focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 {checked
										? 'border-primary-500 bg-primary-100 font-medium text-primary-700'
										: 'border-border-subtle bg-surface text-text-secondary hover:border-border-strong hover:text-text-primary'} {revealedIndicadores.has(
										ind.id
									)
										? 'translate-y-0 opacity-100'
										: 'translate-y-1 opacity-0'}"
								>
									<span
										class="grid h-4 w-4 flex-none place-items-center rounded border-[1.5px] transition-colors duration-fast {checked
											? 'border-success bg-success'
											: 'border-border-strong bg-surface'}"
										aria-hidden="true"
									>
										<svg
											viewBox="0 0 24 24"
											class="h-2.5 w-2.5 text-success-fg transition-opacity duration-fast {checked
												? 'opacity-100'
												: 'opacity-0'}"
											fill="none"
											stroke="currentColor"
											stroke-width="3.5"
											stroke-linecap="round"
											stroke-linejoin="round"
										>
											<path d="M5 13l4.5 4.5L19 7" />
										</svg>
									</span>
									{ind.descricao}
								</button>
							{/each}
						</div>
					{/if}
				</div>
			{/if}
		</div>
	{/if}

	{#if showObjPicker}
		<div bind:this={objZoneEl} class="cp-op-zone-in flex flex-col gap-3">
			{#if objetivos.length === 0}
				<p class={emptyBoxClass}>Nenhum objetivo disponível.</p>
			{:else}
				<div
					role="group"
					aria-label="Objetivos EEGD"
					class="grid grid-cols-1 gap-2.5 md:grid-cols-3"
				>
					{#each objetivos as objetivo, index (objetivo.id)}
						{@const theme = themeFor(index)}
						{@const selected = String(objetivo.id) === objetivoId}
						<button
							type="button"
							aria-pressed={selected}
							onclick={() => pickObjetivo(objetivo)}
							style="--op-hue: {theme.hue}; animation-delay: {index * 30}ms"
							style:border-color={selected ? theme.hue : undefined}
							style:background={selected ? tintOf(theme) : undefined}
							class="cp-op-opt-in flex items-center gap-3 rounded-lg border border-border-subtle bg-surface p-3 text-left transition-[border-color,box-shadow,transform] duration-fast hover:-translate-y-px hover:border-[color:var(--op-hue)] hover:shadow-md active:scale-[0.98] focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
						>
							<span
								class="grid h-9 w-9 flex-none place-items-center rounded-md"
								style:background={tintOf(theme)}
								style:color={theme.hue}
								aria-hidden="true"
							>
								<svg
									viewBox="0 0 24 24"
									class="h-[18px] w-[18px]"
									fill="none"
									stroke="currentColor"
									stroke-width="2"
									stroke-linecap="round"
									stroke-linejoin="round"
								>
									<path d={theme.icon} />
								</svg>
							</span>
							<span class="flex min-w-0 flex-col gap-0.5">
								<span class="text-2xs font-bold uppercase tracking-caps text-text-muted">
									Objetivo {index + 1}
								</span>
								<span class="text-xs font-semibold leading-snug text-text-primary">
									{objetivo.descricao}
								</span>
							</span>
						</button>
					{/each}
				</div>
			{/if}
		</div>
	{/if}

	{#if showResPicker}
		<div bind:this={resZoneEl} class="cp-op-zone-in flex flex-col gap-3">
			<p id="cp-op-res-question" class={questionClass}>Qual resultado esperado?</p>
			{#if resultadosLoading}
				{@render loadingRow('Carregando resultados...')}
			{:else if resultados.length === 0}
				<p class={emptyBoxClass}>
					Nenhum resultado esperado disponível para este objetivo.
				</p>
			{:else}
				<div
					role="group"
					aria-labelledby="cp-op-res-question"
					class="grid grid-cols-1 gap-2.5 md:grid-cols-3"
				>
					{#each resultados as resultado, index (resultado.id)}
						{@const selected = String(resultado.id) === resultadoId}
						<button
							type="button"
							aria-pressed={selected}
							onclick={() => pickResultado(resultado)}
							style="animation-delay: {index * 40}ms"
							class="cp-op-opt-in flex items-center gap-3 rounded-lg border p-3 text-left transition-[border-color,box-shadow,transform] duration-fast hover:-translate-y-px hover:border-primary-500 hover:shadow-md active:scale-[0.98] focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 {selected
								? 'border-primary-500 bg-primary-100'
								: 'border-border-subtle bg-surface'}"
						>
							<span
								class="grid h-7 w-7 flex-none place-items-center rounded-md text-xs font-bold tabular-nums {selected
									? 'bg-primary-600 text-primary-fg'
									: 'bg-surface-muted text-text-secondary'}"
								aria-hidden="true"
							>
								{index + 1}
							</span>
							<span class="text-xs font-semibold leading-snug text-text-primary">
								{resultado.descricao}
							</span>
						</button>
					{/each}
				</div>
			{/if}
		</div>
	{/if}
</div>

<style>
	.cp-op-card {
		animation: cp-op-opt-in 0.35s cubic-bezier(0.4, 0, 0.2, 1);
	}
	.cp-op-zone-in {
		animation: cp-op-opt-in 0.3s ease-out;
	}
	.cp-op-opt-in {
		animation: cp-op-opt-in 0.32s cubic-bezier(0.4, 0, 0.2, 1) both;
	}
	.cp-op-row-in {
		animation: cp-op-row-in 0.3s ease-out;
	}
	.cp-op-dot-pop {
		animation: cp-op-dot-pop 0.55s cubic-bezier(0.34, 1.56, 0.64, 1);
	}
	@keyframes cp-op-opt-in {
		from {
			opacity: 0;
			transform: translateY(10px) scale(0.97);
		}
		to {
			opacity: 1;
			transform: none;
		}
	}
	@keyframes cp-op-row-in {
		from {
			opacity: 0;
			transform: translateY(-4px);
		}
		to {
			opacity: 1;
			transform: none;
		}
	}
	@keyframes cp-op-dot-pop {
		0% {
			transform: scale(1);
		}
		35% {
			transform: scale(1.35);
		}
		65% {
			transform: scale(0.92);
		}
		100% {
			transform: scale(1);
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.cp-op-card,
		.cp-op-zone-in,
		.cp-op-opt-in,
		.cp-op-row-in,
		.cp-op-dot-pop {
			animation: none;
		}
	}
</style>
