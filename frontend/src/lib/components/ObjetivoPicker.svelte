<script lang="ts">
	/**
	 * Picker progressivo de Objetivo → Resultado esperado → Indicadores EEGD
	 * (CriarProjetoModal). Card único que acumula: as etapas seguintes aparecem
	 * dentro do card do objetivo escolhido, separadas por divisórias finas.
	 *
	 * Transição: NENHUM bloco monta/desmonta na troca de etapa — todos vivem no
	 * DOM e colapsam via `.cp-collapse` (grid-template-rows 1fr↔0fr). Todos os
	 * irmãos compartilham duração e curva, então a altura do card interpola
	 * monotonicamente entre o estado anterior e o novo (sem salto, sem pinch).
	 * Blocos colapsados recebem `inert`; por isso TODA ação que colapsa
	 * reposiciona o foco.
	 */
	import { tick } from 'svelte';
	import { prefetchIndicadores, prefetchResultados } from '$lib/api/eegdCatalogCache';
	import type { ObjetivoCatalogo, ResultadoCatalogo, IndicadorCatalogo } from '$lib/api/projects';

	interface Props {
		objetivos: ObjetivoCatalogo[];
		objetivoId: string;
		resultados: ResultadoCatalogo[];
		resultadoId: string;
		resultadosLoading: boolean;
		resultadosErro: boolean;
		indicadores: IndicadorCatalogo[];
		indicadoresLoading: boolean;
		indicadoresErro: boolean;
		selectedIndicadores: number[];
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
		resultadosErro,
		indicadores,
		indicadoresLoading,
		indicadoresErro,
		selectedIndicadores,
		onObjetivoSelect,
		onResultadoSelect,
		onToggleIndicador
	}: Props = $props();

	/** Linhas do skeleton = geometria do item real (46px/42px + gap). */
	const RES_SKELETON_ROWS = 3;
	const IND_SKELETON_ROWS = 3;

	// Numeração já aparece no numeral fantasma do card.
	function semNumeroInicial(descricao: string): string {
		return descricao.replace(/^\s*\d+\s*[.)\-–—:]*\s*/, '');
	}

	let editObj = $state(false);
	let editRes = $state(false);
	let celebrating = $state(false);
	let celebrateTimer: ReturnType<typeof setTimeout> | null = null;
	let rootEl = $state<HTMLDivElement | null>(null);
	let objPencilEl = $state<HTMLButtonElement | null>(null);
	let resPencilEl = $state<HTMLButtonElement | null>(null);
	let objZoneEl = $state<HTMLDivElement | null>(null);
	let resZoneEl = $state<HTMLDivElement | null>(null);

	const selectedObjIndex = $derived(objetivos.findIndex((o) => String(o.id) === objetivoId));
	const selectedObj = $derived(selectedObjIndex >= 0 ? objetivos[selectedObjIndex] : null);
	const selectedRes = $derived(resultados.find((r) => String(r.id) === resultadoId) ?? null);

	// Snapshots do último escolhido: como o bloco NÃO desmonta, ele precisa de
	// conteúdo legível durante o colapso — sem isso o texto some no primeiro
	// frame e sobra uma caixa vazia encolhendo.
	let objSnap = $state<{ obj: ObjetivoCatalogo; index: number } | null>(null);
	let resSnap = $state<ResultadoCatalogo | null>(null);
	$effect(() => {
		if (selectedObj) objSnap = { obj: selectedObj, index: selectedObjIndex };
	});
	$effect(() => {
		if (selectedRes) resSnap = selectedRes;
	});

	const objChosen = $derived(selectedObj !== null);
	const gridOpen = $derived(!objChosen || editObj);
	const resListOpen = $derived(objChosen && !editObj && (resultadoId === '' || editRes));
	const resRowOpen = $derived(objChosen && !editObj && !editRes && selectedRes !== null);
	// Indicadores pertencem ao resultado escolhido e continuam abertos durante o
	// "Trocar": menos movimento, e nada some sob o cursor.
	const indOpen = $derived(objChosen && !editObj && resultadoId !== '');

	type ZonaState = 'loading' | 'error' | 'empty' | 'list';
	const resState = $derived<ZonaState>(
		resultadosLoading
			? 'loading'
			: resultadosErro
				? 'error'
				: resultados.length === 0
					? 'empty'
					: 'list'
	);
	const indState = $derived<ZonaState>(
		indicadoresLoading
			? 'loading'
			: indicadoresErro
				? 'error'
				: indicadores.length === 0
					? 'empty'
					: 'list'
	);
	const resMsgOpen = $derived(resState === 'error' || resState === 'empty');
	const indMsgOpen = $derived(indState === 'error' || indState === 'empty');

	const anuncioZonas = $derived.by(() => {
		if (resListOpen) {
			if (resState === 'loading') return 'Carregando resultados esperados.';
			if (resState === 'error') return 'Não foi possível carregar os resultados esperados.';
			if (resState === 'empty') return 'Nenhum resultado esperado disponível para este objetivo.';
		}
		if (!indOpen) return '';
		if (indState === 'loading') return 'Carregando indicadores.';
		if (indState === 'error') return 'Não foi possível carregar os indicadores.';
		if (indState === 'empty') return 'Nenhum indicador disponível para este resultado esperado.';
		return `${indicadores.length} indicadores disponíveis para selecionar.`;
	});

	function celebrate(): void {
		if (celebrateTimer) clearTimeout(celebrateTimer);
		// Remove e recoloca a classe num tick para reiniciar em escolhas seguidas.
		celebrating = false;
		void tick().then(() => (celebrating = true));
		celebrateTimer = setTimeout(() => (celebrating = false), 900);
	}
	$effect(() => () => {
		if (celebrateTimer) clearTimeout(celebrateTimer);
	});

	/**
	 * Foca DEPOIS do flush: `inert` só sai do bloco alvo no DOM novo, e focar nó
	 * inerte é no-op silencioso — o foco cairia no `document.body`, fora do
	 * focus trap (`focusTrap.ts` escuta keydown NO diálogo), desligando Esc e
	 * deixando o Tab escapar. `rootEl` (tabindex="-1", nunca inerte) é a reserva.
	 * `preventScroll`: quem decide o scroll é o encolhimento gradual do card,
	 * não um scroll-into-view no meio da transição.
	 */
	function focarDepoisDoTick(alvo: () => HTMLElement | null | undefined): void {
		void tick().then(() => {
			const el = alvo();
			if (el && !el.closest('[inert]')) {
				el.focus({ preventScroll: true });
				return;
			}
			rootEl?.focus({ preventScroll: true });
		});
	}

	/** Alvo de foco por índice, sem `bind:this` em array (evita refs obsoletas). */
	function botaoDoIndice(zone: HTMLElement | null, index: number): HTMLElement | null {
		if (!zone || index < 0) return null;
		return zone.querySelector<HTMLElement>(`button[data-idx="${index}"]`);
	}

	function pickObjetivo(objetivo: ObjetivoCatalogo): void {
		const id = String(objetivo.id);
		const changed = id !== objetivoId;
		editObj = false;
		editRes = false;
		celebrate();
		// Reclicar o mesmo objetivo não reseta resultado/indicadores.
		if (changed) onObjetivoSelect(id);
		// A grade colapsa e fica inerte COM o botão clicado dentro dela.
		focarDepoisDoTick(() => objPencilEl);
	}

	function startEditObjetivo(): void {
		editObj = true;
		focarDepoisDoTick(
			() => botaoDoIndice(objZoneEl, selectedObjIndex) ?? botaoDoIndice(objZoneEl, 0)
		);
	}

	function clearObjetivo(): void {
		editObj = false;
		editRes = false;
		onObjetivoSelect('');
		focarDepoisDoTick(() => botaoDoIndice(objZoneEl, 0));
	}

	function pickResultado(resultado: ResultadoCatalogo): void {
		const id = String(resultado.id);
		const changed = id !== resultadoId;
		editRes = false;
		if (changed) onResultadoSelect(id);
		focarDepoisDoTick(() => resPencilEl);
	}

	function startEditResultado(): void {
		editRes = true;
		const idx = resultados.findIndex((r) => String(r.id) === resultadoId);
		focarDepoisDoTick(() => botaoDoIndice(resZoneEl, idx) ?? botaoDoIndice(resZoneEl, 0));
	}

	const microLabelClass = 'text-2xs font-semibold uppercase tracking-caps text-text-muted';
	const pencilBtnClass =
		'grid h-7 w-7 flex-none place-items-center rounded-md text-text-muted transition-colors duration-fast hover:bg-surface-muted hover:text-brand active:scale-95 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand';
	const removeBtnClass =
		'grid h-7 w-7 flex-none place-items-center rounded-md text-text-muted transition-colors duration-fast hover:bg-surface-muted hover:text-danger active:scale-95 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand';
	const emptyBoxClass =
		'rounded-lg border border-dashed border-border-subtle bg-surface-muted px-4 py-3.5 text-sm text-text-muted';
	// Sem animação de entrada: as seções não montam mais, e uma animação
	// disparando junto com o colapso é justamente o "pisca" que queremos matar.
	const sectionClass = 'relative mt-4 border-t border-border-subtle pt-3.5';
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

<div bind:this={rootEl} tabindex="-1" class="flex flex-col outline-none">
	<p class="sr-only" role="status" aria-live="polite">{anuncioZonas}</p>

	<!-- CARD do objetivo — sempre montado; colapsa quando não há objetivo. -->
	<div class="cp-collapse" data-collapsed={!objChosen} inert={!objChosen}>
		<div class="cp-collapse__in pb-4">
			<div
				class="relative overflow-hidden rounded-lg border border-border-subtle bg-surface px-5 py-4"
			>
				{#if objSnap}
					<span
						class="pointer-events-none absolute -top-5 right-2.5 text-[88px] font-extralight leading-none tabular-nums text-[color-mix(in_srgb,var(--ds-color-primary-600)_9%,transparent)]"
						aria-hidden="true"
					>
						{String(objSnap.index + 1).padStart(2, '0')}
					</span>

					<div class="relative flex items-center gap-1.5">
						<span class="flex min-w-0 flex-col gap-0.5" class:cp-op-dot-pop={celebrating}>
							<span class="text-2xs font-semibold uppercase tracking-caps text-brand">
								Objetivo {String(objSnap.index + 1).padStart(2, '0')}
							</span>
							<span class="text-sm font-medium leading-snug text-text-primary">
								{semNumeroInicial(objSnap.obj.descricao)}
							</span>
						</span>
						<button
							type="button"
							bind:this={objPencilEl}
							title="Alterar objetivo"
							aria-label="Alterar objetivo"
							aria-expanded={gridOpen}
							aria-controls="cp-op-obj-grid"
							onclick={startEditObjetivo}
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
				{/if}

				<!-- ZONA RESULTADOS: 3 irmãos exclusivos (skeleton | mensagem | lista) -->
				<div class="cp-collapse" data-collapsed={!resListOpen} inert={!resListOpen}>
					<div bind:this={resZoneEl} class="cp-collapse__in {sectionClass}">
						<p id="cp-op-res-question" class={microLabelClass}>Qual o resultado esperado?</p>

						<div
							class="cp-collapse"
							data-collapsed={resState !== 'loading'}
							inert
							aria-hidden="true"
						>
							<div class="cp-collapse__in mt-2 flex flex-col gap-1.5">
								{#each Array.from({ length: RES_SKELETON_ROWS }) as _, i (i)}
									<div class="skeleton-shimmer h-[46px] rounded-lg"></div>
								{/each}
							</div>
						</div>

						<div class="cp-collapse" data-collapsed={!resMsgOpen} inert={!resMsgOpen}>
							<p class="cp-collapse__in mt-2 text-sm text-text-muted">
								{resState === 'error'
									? 'Não foi possível carregar os resultados esperados. Escolha o objetivo novamente para tentar de novo.'
									: 'Nenhum resultado esperado disponível para este objetivo.'}
							</p>
						</div>

						<div
							class="cp-collapse"
							data-collapsed={resState !== 'list'}
							inert={resState !== 'list'}
						>
							<div
								role="group"
								aria-labelledby="cp-op-res-question"
								class="cp-collapse__in mt-0.5 flex flex-col"
							>
								{#each resultados as resultado, index (resultado.id)}
									{@const selected = String(resultado.id) === resultadoId}
									<button
										type="button"
										data-idx={index}
										aria-pressed={selected}
										onclick={() => pickResultado(resultado)}
										onpointerenter={() => prefetchIndicadores(String(resultado.id))}
										onfocus={() => prefetchIndicadores(String(resultado.id))}
										style="--i: {Math.min(index, 5)}"
										class="cp-op-opt-in group flex items-baseline gap-3.5 border-b border-border-subtle py-3 text-left last:border-b-0 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
									>
										<span
											class="w-6 flex-none text-xl font-light leading-none tabular-nums {selected
												? 'text-brand'
												: 'text-text-muted opacity-60'}"
											aria-hidden="true"
										>
											{index + 1}
										</span>
										<span
											class="text-sm font-medium leading-snug transition-colors duration-fast {selected
												? 'text-brand'
												: 'text-text-primary group-hover:text-brand'}"
										>
											{resultado.descricao}
										</span>
									</button>
								{/each}
							</div>
						</div>
					</div>
				</div>

				<!-- LINHA COMPACTA do resultado escolhido -->
				<div class="cp-collapse" data-collapsed={!resRowOpen} inert={!resRowOpen}>
					<div class="cp-collapse__in {sectionClass} flex items-center gap-1.5">
						<span class="flex min-w-0 flex-col gap-0.5">
							<span class={microLabelClass}>Resultado esperado</span>
							<span class="text-sm font-medium leading-snug text-text-primary">
								{resSnap?.descricao ?? ''}
							</span>
						</span>
						<button
							type="button"
							bind:this={resPencilEl}
							aria-expanded={resListOpen}
							onclick={startEditResultado}
							class="flex-none self-end whitespace-nowrap rounded-md px-2 py-1 text-xs font-medium text-brand transition-colors duration-fast hover:bg-surface-muted hover:text-brand active:scale-95 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
						>
							Trocar
						</button>
					</div>
				</div>

				<!-- ZONA INDICADORES: mesmos 3 irmãos exclusivos -->
				<div class="cp-collapse" data-collapsed={!indOpen} inert={!indOpen}>
					<div class="cp-collapse__in {sectionClass} flex flex-col gap-2.5">
						<span class={microLabelClass}>
							Indicadores
							<span class="font-regular normal-case tracking-normal">· selecione um ou mais</span>
						</span>

						<div class="cp-collapse" data-collapsed={indState !== 'loading'} inert aria-hidden="true">
							<div class="cp-collapse__in flex flex-col gap-1.5">
								{#each Array.from({ length: IND_SKELETON_ROWS }) as _, i (i)}
									<div class="skeleton-shimmer h-[42px] rounded-lg"></div>
								{/each}
							</div>
						</div>

						<div class="cp-collapse" data-collapsed={!indMsgOpen} inert={!indMsgOpen}>
							<p class="cp-collapse__in text-sm text-text-muted">
								{indState === 'error'
									? 'Não foi possível carregar os indicadores deste resultado esperado.'
									: 'Nenhum indicador disponível para este resultado esperado.'}
							</p>
						</div>

						<div
							class="cp-collapse"
							data-collapsed={indState !== 'list'}
							inert={indState !== 'list'}
						>
							<div class="cp-collapse__in flex flex-col gap-1.5">
								{#each indicadores as ind, index (ind.id)}
									{@const checked = selectedIndicadores.includes(ind.id)}
									<button
										type="button"
										aria-pressed={checked}
										onclick={() => onToggleIndicador(ind.id)}
										style="--i: {Math.min(index, 5)}"
										class="cp-op-ind-in flex w-full items-center gap-2.5 rounded-lg border px-3 py-2.5 text-left text-sm transition-[color,background-color,border-color] duration-fast active:scale-[0.99] focus:outline-none focus-visible:ring-2 focus-visible:ring-brand {checked
											? 'border-brand bg-wash-brand font-medium text-brand'
											: 'border-border-subtle bg-surface text-text-secondary hover:border-border-strong hover:text-text-primary'}"
									>
										<span
											class="grid h-4 w-4 flex-none place-items-center rounded border-[1.5px] transition-colors duration-fast {checked
												? 'border-brand bg-brand'
												: 'border-border-strong bg-surface'}"
											aria-hidden="true"
										>
											<svg
												viewBox="0 0 24 24"
												class="h-2.5 w-2.5 text-on-brand transition-opacity duration-fast {checked
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
						</div>
					</div>
				</div>
			</div>
		</div>
	</div>

	<!-- GRADE DE OBJETIVOS — sempre montada; colapsa quando há escolha. -->
	<div class="cp-collapse cp-collapse--grid" data-collapsed={!gridOpen} inert={!gridOpen}>
		<div bind:this={objZoneEl} class="cp-collapse__in flex flex-col gap-3">
			{#if objetivos.length === 0}
				<p class={emptyBoxClass}>Nenhum objetivo disponível.</p>
			{:else}
				<div
					id="cp-op-obj-grid"
					role="group"
					aria-label="Objetivos EEGD"
					class="grid grid-cols-1 gap-3 md:grid-cols-3 md:min-w-[var(--cp-grid-w,880px)] md:[contain:layout]"
				>
					{#each objetivos as objetivo, index (objetivo.id)}
						{@const selected = String(objetivo.id) === objetivoId}
						<button
							type="button"
							data-idx={index}
							aria-pressed={selected}
							onclick={() => pickObjetivo(objetivo)}
							onpointerenter={() => prefetchResultados(String(objetivo.id))}
							onfocus={() => prefetchResultados(String(objetivo.id))}
							style="--i: {Math.min(index, 5)}"
							class="cp-op-opt-in relative min-h-[90px] overflow-hidden rounded-lg border-[1.5px] px-4 py-4 pr-10 text-left transition-[border-color,box-shadow,transform] duration-fast hover:-translate-y-px hover:border-brand hover:shadow-md active:scale-[0.98] focus:outline-none focus-visible:ring-2 focus-visible:ring-brand {selected
								? 'border-brand bg-wash-brand'
								: 'border-border-subtle bg-surface'}"
						>
							<span
								class="pointer-events-none absolute -bottom-4 right-2 text-[64px] font-extralight leading-none tabular-nums {selected
									? 'text-[color-mix(in_srgb,var(--ds-color-primary-600)_22%,transparent)]'
									: 'text-[color-mix(in_srgb,var(--ds-color-text-primary)_7%,transparent)]'}"
								aria-hidden="true"
							>
								{String(index + 1).padStart(2, '0')}
							</span>
							<span
								class="relative block max-w-[86%] text-md font-semibold leading-snug text-text-primary"
							>
								<span class="sr-only">Objetivo {index + 1}:</span>
								{semNumeroInicial(objetivo.descricao)}
							</span>
						</button>
					{/each}
				</div>
			{/if}
		</div>
	</div>
</div>

<style>
	.cp-collapse {
		/* Duração/curva ÚNICAS: blocos irmãos precisam do MESMO e(t), senão a
		   soma das alturas afunda e volta (pinch) no meio da transição. */
		--cp-dur: 260ms;
		--cp-ease: cubic-bezier(0.4, 0, 0.2, 1);
		display: grid;
		grid-template-rows: 1fr;
		transition:
			grid-template-rows var(--cp-dur) var(--cp-ease),
			opacity var(--cp-dur) var(--cp-ease);
	}
	.cp-collapse[data-collapsed='true'] {
		grid-template-rows: 0fr;
		opacity: 0;
	}
	.cp-collapse__in {
		min-height: 0;
		/* Clip só no eixo Y; a margem preserva o focus-visible:ring-2 e a sombra
		   de hover dos itens de borda. */
		overflow-x: visible;
		overflow-y: clip;
		overflow-clip-margin: var(--cp-clip, 8px);
	}
	.cp-collapse--grid {
		--cp-clip: 14px;
	}
	.cp-op-opt-in {
		animation: cp-op-opt-in 0.22s cubic-bezier(0.4, 0, 0.2, 1) both;
		animation-delay: calc(var(--i, 0) * 28ms);
	}
	.cp-op-ind-in {
		/* Estado invisível vem SÓ do keyframe (`both`): com `animation: none` sob
		   reduced-motion os itens ficam visíveis, em vez de presos em opacity 0. */
		animation: cp-op-opt-in 0.18s cubic-bezier(0.4, 0, 0.2, 1) both;
		animation-delay: calc(var(--i, 0) * 24ms);
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
		.cp-collapse,
		.cp-collapse[data-collapsed='true'] {
			/* 1ms (não `none`): preserva ordem e eventos `transitionend`. */
			transition-duration: 1ms;
		}
		.cp-op-opt-in,
		.cp-op-ind-in,
		.cp-op-dot-pop {
			animation: none;
		}
	}
</style>
