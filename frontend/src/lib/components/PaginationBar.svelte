<script lang="ts">
	/**
	 * Pager numerado PADRÃO do app (Projetos, Projetos Pendentes, Hub de Tarefas).
	 * Controlado por callback: o pai guarda a página e re-busca no `onChange`.
	 * Some quando há 0/1 página.
	 *
	 * Largura ESTÁVEL: a janela tem contagem de slots fixa (`PAGER_SLOTS`), com
	 * primeira/última sempre visíveis e reticências (`…`) ocupando o mesmo box de
	 * um número. Isso impede o controle de mudar de tamanho ao paginar — sem isso
	 * a janela encolhia nas bordas e a contagem de botões oscilava (7→8→9).
	 */
	interface Props {
		page: number;
		totalPages: number;
		/** Rótulo do `<nav>` (ex.: "Paginação de projetos"). */
		label?: string;
		/** Desabilita os botões durante o re-fetch. */
		disabled?: boolean;
		/** Mostra as setas «« / »» (primeira/última página). */
		showEdges?: boolean;
		/** Total de itens (para o texto "Mostrando X - Y de N"). */
		total?: number;
		/** Itens por página (idem). */
		perPage?: number | null;
		/** Substantivo do item, ex.: "projetos" → "… de 42 projetos". */
		itemLabel?: string;
		onChange: (page: number) => void;
	}

	let {
		page,
		totalPages,
		label = 'Paginação',
		disabled = false,
		showEdges = true,
		total,
		perPage,
		itemLabel = 'itens',
		onChange
	}: Props = $props();

	/**
	 * Página efetiva. O pai pode passar uma página fora de faixa (deep-link
	 * antigo, itens apagados sob os pés do usuário); sem o clamp o pager fica
	 * sem nenhum botão ativo e a contagem imprime "Mostrando 321 - 320 de 320".
	 */
	const safePage = $derived(Math.min(Math.max(page, 1), Math.max(totalPages, 1)));

	// "Mostrando X - Y de N <itemLabel>" — só quando há contagem disponível.
	const showCount = $derived(total != null && perPage != null && perPage > 0);
	const fromItem = $derived(perPage ? (safePage - 1) * perPage + 1 : 0);
	const toItem = $derived(perPage ? Math.min(safePage * perPage, total ?? 0) : 0);

	/** Ignora alvos fora de faixa e no-ops — o pai nunca recebe página inválida. */
	function requestPage(target: number): void {
		if (target < 1 || target > totalPages || target === safePage) return;
		onChange(target);
	}

	// Setas discretas com realce azul no hover; página ativa = primary-600 (cor
	// do CTA primário). A transição cobre só background-color/border-color — nunca
	// `color`: animar o texto junto causaria flicker branco-sobre-branco na troca
	// de página ativa.
	const ARROW =
		'inline-flex h-8 min-w-8 items-center justify-center rounded-md border border-border-subtle bg-surface px-2 text-sm font-semibold text-text-secondary transition-[background-color,border-color] duration-fast ease-out hover:border-brand hover:bg-wash-neutral hover:text-brand focus:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:border-border-subtle disabled:hover:bg-surface disabled:hover:text-text-secondary';
	const PAGE_BASE =
		'inline-flex h-8 min-w-9 items-center justify-center rounded-md border px-2.5 text-sm font-semibold tabular-nums transition-[background-color,border-color,box-shadow] duration-fast ease-out focus:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed';
	const PAGE_ACTIVE = 'border-transparent bg-brand text-white shadow-sm';
	const PAGE_IDLE =
		'border-border-subtle bg-surface text-text-secondary hover:border-brand hover:bg-wash-neutral hover:text-brand';
	// Reticências: mesmo box (h-8 min-w-9) que um número, sem borda/hover — mantém
	// a largura idêntica quando o gap surge/some.
	const ELLIPSIS =
		'inline-flex h-8 min-w-9 select-none items-center justify-center px-2.5 text-sm font-semibold text-text-muted';

	// Contagem FIXA de slots numéricos (números + reticências). `null` = reticências.
	const PAGER_SLOTS = 7;

	/**
	 * Janela de páginas com contagem de slots ESTÁVEL: primeira e última sempre
	 * visíveis, miolo deslizante de ±1 ao redor da atual e `null` (…) quando há
	 * gap. Para total_pages > PAGER_SLOTS o resultado tem sempre 7 itens — o pager
	 * nunca redimensiona. Algoritmo canônico (MUI usePagination).
	 */
	const window = $derived.by<(number | null)[]>(() => {
		const tp = totalPages;
		const range = (lo: number, hi: number): number[] =>
			Array.from({ length: hi - lo + 1 }, (_, i) => lo + i);

		if (tp <= PAGER_SLOTS) return range(1, tp);

		const left = Math.max(safePage - 1, 1);
		const right = Math.min(safePage + 1, tp);
		const showLeftDots = left > 2;
		const showRightDots = right < tp - 1;

		// 5 = primeira + última + atual + 2 vizinhos (sem reticências de um dos lados).
		if (!showLeftDots && showRightDots) return [...range(1, 5), null, tp];
		if (showLeftDots && !showRightDots) return [1, null, ...range(tp - 4, tp)];
		return [1, null, ...range(left, right), null, tp];
	});
</script>

{#if totalPages > 1}
	<!-- Card único do app: info "Mostrando…" à esquerda, pager à direita. -->
	<section
		class="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border-subtle bg-surface px-3 py-2 shadow-sm"
	>
		<div class="text-sm font-medium text-text-secondary">
			{#if showCount}
				Mostrando {fromItem} - {toItem} de {total} {itemLabel}
			{/if}
		</div>
		<nav aria-label={label}>
			<ul class="m-0 flex list-none items-center gap-1 p-0">
			{#if showEdges}
				<li>
					<button
						type="button"
						class={ARROW}
						disabled={disabled || safePage <= 1}
						onclick={() => requestPage(1)}
						aria-label="Primeira página"
					>
						««
					</button>
				</li>
			{/if}
			<li>
				<button
					type="button"
					class={ARROW}
					disabled={disabled || safePage <= 1}
					onclick={() => requestPage(safePage - 1)}
					aria-label="Página anterior"
				>
					«
				</button>
			</li>
			{#each window as p, i (p === null ? `gap-${i}` : `p-${p}`)}
				<li>
					{#if p === null}
						<span class={ELLIPSIS} aria-hidden="true">…</span>
					{:else}
						<button
							type="button"
							class="{PAGE_BASE} {p === safePage ? PAGE_ACTIVE : PAGE_IDLE}"
							disabled={disabled && p !== safePage}
							onclick={() => requestPage(p)}
							aria-label={`Página ${p}`}
							aria-current={p === safePage ? 'page' : undefined}
						>
							{p}
						</button>
					{/if}
				</li>
			{/each}
			<li>
				<button
					type="button"
					class={ARROW}
					disabled={disabled || safePage >= totalPages}
					onclick={() => requestPage(safePage + 1)}
					aria-label="Próxima página"
				>
					»
				</button>
			</li>
			{#if showEdges}
				<li>
					<button
						type="button"
						class={ARROW}
						disabled={disabled || safePage >= totalPages}
						onclick={() => requestPage(totalPages)}
						aria-label="Última página"
					>
						»»
					</button>
				</li>
			{/if}
			</ul>
		</nav>
	</section>
{/if}
