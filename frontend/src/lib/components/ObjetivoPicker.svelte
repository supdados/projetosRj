<script lang="ts">
	/**
	 * Picker progressivo de Objetivo → Resultado esperado → Indicadores EEGD
	 * (CriarProjetoModal). Card único que acumula: as etapas seguintes aparecem
	 * dentro do card do objetivo escolhido, separadas por divisórias finas.
	 * Todo o estado de dados vive no modal; aqui só há estado de apresentação
	 * (modo edição + celebração).
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

	// Numeração já aparece no numeral fantasma do card.
	function semNumeroInicial(descricao: string): string {
		return descricao.replace(/^\s*\d+\s*[.)\-–—:]*\s*/, '');
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

	const microLabelClass = 'text-2xs font-semibold uppercase tracking-caps text-text-muted';
	const pencilBtnClass =
		'grid h-7 w-7 flex-none place-items-center rounded-md text-text-muted transition-colors duration-fast hover:bg-surface-muted hover:text-primary-600 active:scale-95 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500';
	const removeBtnClass =
		'grid h-7 w-7 flex-none place-items-center rounded-md text-text-muted transition-colors duration-fast hover:bg-surface-muted hover:text-danger active:scale-95 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500';
	const emptyBoxClass =
		'rounded-lg border border-dashed border-border-subtle bg-surface-muted px-4 py-3.5 text-sm text-text-muted';
	const sectionClass = 'cp-op-row-in relative mt-4 border-t border-border-subtle pt-3.5';
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
		<div
			class="cp-op-card relative overflow-hidden rounded-lg border border-border-subtle bg-surface px-5 py-4"
		>
			<span
				class="pointer-events-none absolute -top-5 right-2.5 text-[88px] font-extralight leading-none tabular-nums text-[color-mix(in_srgb,var(--ds-color-primary-600)_9%,transparent)]"
				aria-hidden="true"
			>
				{String(selectedObjIndex + 1).padStart(2, '0')}
			</span>

			<div class="relative flex items-center gap-1.5">
				<span class="flex min-w-0 flex-col gap-0.5" class:cp-op-dot-pop={celebrating}>
					<span class="text-2xs font-semibold uppercase tracking-caps text-primary-600">
						Objetivo {String(selectedObjIndex + 1).padStart(2, '0')}
					</span>
					<span class="text-sm font-medium leading-snug text-text-primary">
						{semNumeroInicial(selectedObj.descricao)}
					</span>
				</span>
				<button
					type="button"
					bind:this={objPencilEl}
					title="Alterar objetivo"
					aria-label="Alterar objetivo"
					aria-expanded={editObj}
					onclick={() => (editObj = true)}
					class="{pencilBtnClass} self-end"
				>
					{@render pencilIcon()}
				</button>
				<button
					type="button"
					title="Remover objetivo"
					aria-label="Remover objetivo"
					onclick={clearObjetivo}
					class="{removeBtnClass} self-end"
				>
					{@render clearIcon()}
				</button>
			</div>

			{#if showResPicker}
				<div bind:this={resZoneEl} class={sectionClass}>
					<p id="cp-op-res-question" class={microLabelClass}>Qual o resultado esperado?</p>
					{#if resultadosLoading}
						<div class="mt-2">
							{@render loadingRow('Carregando resultados...')}
						</div>
					{:else if resultados.length === 0}
						<p class="mt-2 text-sm text-text-muted">
							Nenhum resultado esperado disponível para este objetivo.
						</p>
					{:else}
						<div role="group" aria-labelledby="cp-op-res-question" class="mt-0.5 flex flex-col">
							{#each resultados as resultado, index (resultado.id)}
								{@const selected = String(resultado.id) === resultadoId}
								<button
									type="button"
									aria-pressed={selected}
									onclick={() => pickResultado(resultado)}
									style="animation-delay: {index * 40}ms"
									class="cp-op-opt-in group flex items-baseline gap-3.5 border-b border-border-subtle py-3 text-left last:border-b-0 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
								>
									<span
										class="w-6 flex-none text-xl font-light leading-none tabular-nums {selected
											? 'text-primary-600'
											: 'text-text-muted opacity-60'}"
										aria-hidden="true"
									>
										{index + 1}
									</span>
									<span
										class="text-sm font-medium leading-snug transition-colors duration-fast {selected
											? 'text-primary-700'
											: 'text-text-primary group-hover:text-primary-600'}"
									>
										{resultado.descricao}
									</span>
								</button>
							{/each}
						</div>
					{/if}
				</div>
			{/if}

			{#if hasResRow && selectedRes}
				<div class="{sectionClass} flex items-center gap-1.5">
					<span class="flex min-w-0 flex-col gap-0.5">
						<span class={microLabelClass}>Resultado esperado</span>
						<span class="text-sm font-medium leading-snug text-text-primary">
							{selectedRes.descricao}
						</span>
					</span>
					<button
						type="button"
						bind:this={resPencilEl}
						aria-expanded={editRes}
						onclick={startEditResultado}
						class="flex-none self-end whitespace-nowrap rounded-md px-2 py-1 text-xs font-medium text-primary-600 transition-colors duration-fast hover:bg-surface-muted hover:text-primary-700 active:scale-95 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
					>
						Trocar
					</button>
				</div>
			{/if}

			{#if showIndRow}
				<div class="{sectionClass} flex flex-col gap-2.5">
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
						<div class="flex flex-col gap-1.5">
							{#each indicadores as ind (ind.id)}
								{@const checked = selectedIndicadores.includes(ind.id)}
								<button
									type="button"
									aria-pressed={checked}
									onclick={() => onToggleIndicador(ind.id)}
									class="flex w-full items-center gap-2.5 rounded-lg border px-3 py-2.5 text-left text-sm transition-[opacity,transform,color,background-color,border-color] duration-300 active:scale-[0.99] focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 {checked
										? 'border-primary-500 bg-[color-mix(in_srgb,var(--ds-color-primary-600)_4%,transparent)] font-medium text-primary-700'
										: 'border-border-subtle bg-surface text-text-secondary hover:border-border-strong hover:text-text-primary'} {revealedIndicadores.has(
										ind.id
									)
										? 'translate-y-0 opacity-100'
										: 'translate-y-1 opacity-0'}"
								>
									<span
										class="grid h-4 w-4 flex-none place-items-center rounded border-[1.5px] transition-colors duration-fast {checked
											? 'border-primary-600 bg-primary-600'
											: 'border-border-strong bg-surface'}"
										aria-hidden="true"
									>
										<svg
											viewBox="0 0 24 24"
											class="h-2.5 w-2.5 text-primary-fg transition-opacity duration-fast {checked
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
					class="grid grid-cols-1 gap-3 md:grid-cols-3 md:min-w-[var(--cp-grid-w,880px)] md:[contain:layout]"
				>
					{#each objetivos as objetivo, index (objetivo.id)}
						{@const selected = String(objetivo.id) === objetivoId}
						<button
							type="button"
							aria-pressed={selected}
							onclick={() => pickObjetivo(objetivo)}
							style="animation-delay: {index * 30}ms"
							class="cp-op-opt-in relative min-h-[90px] overflow-hidden rounded-lg border-[1.5px] px-4 py-4 pr-10 text-left transition-[border-color,box-shadow,transform] duration-fast hover:-translate-y-px hover:border-primary-500 hover:shadow-md active:scale-[0.98] focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 {selected
								? 'border-primary-600 bg-primary-100'
								: 'border-border-subtle bg-surface'}"
						>
							<span
								class="absolute right-3 top-3 z-10 grid h-5 w-5 place-items-center rounded-full border-[1.5px] transition-colors duration-fast {selected
									? 'border-primary-600 bg-primary-600'
									: 'border-border-strong bg-surface'}"
								aria-hidden="true"
							>
								<svg
									viewBox="0 0 24 24"
									class="h-3 w-3 text-primary-fg transition-opacity duration-fast {selected
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
							<span
								class="pointer-events-none absolute -bottom-4 right-2 text-[64px] font-extralight leading-none tabular-nums {selected
									? 'text-[color-mix(in_srgb,var(--ds-color-primary-600)_22%,transparent)]'
									: 'text-[color-mix(in_srgb,var(--color-text-primary)_7%,transparent)]'}"
								aria-hidden="true"
							>
								{String(index + 1).padStart(2, '0')}
							</span>
							<span
								class="relative block max-w-[86%] text-[13.5px] font-semibold leading-snug text-text-primary"
							>
								<span class="sr-only">Objetivo {index + 1}:</span>
								{semNumeroInicial(objetivo.descricao)}
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
			transform: scale(1.02);
		}
		65% {
			transform: scale(0.99);
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
