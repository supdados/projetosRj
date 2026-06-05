/**
 * Action `use:stickyHeader` — compacta o cabeçalho do projeto ao rolar.
 *
 * Aplicada ao PRÓPRIO header e usa um IntersectionObserver para disparar a
 * reavaliação nos cruzamentos. A decisão é DIRECIONAL: o cabeçalho só compacta
 * quando a BASE do header já passou ACIMA da linha do topnav fixo — ou seja,
 * exatamente quando o header deixa de estar aparente. Não basta o header estar
 * "fora da viewport" — em telas/janelas baixas a base pode estar abaixo da dobra
 * com o cabeçalho inteiro ainda visível, o que fazia o compacto surgir cedo
 * demais (header principal e compacto apareciam juntos).
 *
 * Observa-se o próprio header (e não um sentinela separado) porque um sentinela
 * irmão sofre o `gap` do flex container da página, ficando alguns px abaixo da
 * base real do header e atrasando o gatilho.
 *
 * Invoca o callback `onChange(isCompact)` — a decisão de classes/ARIA fica no
 * componente controlado (ProjectHeader), padrão "controlado por callback".
 *
 * Acessibilidade/robustez:
 *   - Em ambientes sem IntersectionObserver (SSR/jsdom), faz no-op seguro.
 *   - `topOffset` desconta a altura do topnav fixo no topo da viewport.
 *
 * Exemplo:
 *   <header use:stickyHeader={{ onChange: (c) => (compact = c), topOffset: 64 }} />
 */

/** Parâmetros da action (reativos via `update`). */
export interface StickyHeaderParams {
	/** Chamado quando o estado compacto muda. `true` => cabeçalho compacto. */
	onChange: (isCompact: boolean) => void;
	/** Altura do topnav fixo (px) a descontar no topo da viewport. */
	topOffset?: number;
}

/** Contrato mínimo de uma Svelte action com parâmetros. */
interface ActionReturn {
	update(params: StickyHeaderParams): void;
	destroy(): void;
}

/** Monta o `rootMargin` que desconta o topnav fixo do topo da viewport. */
function buildRootMargin(topOffset: number): string {
	// Margem negativa no topo: o sentinela é considerado "fora" assim que passa
	// por baixo do topnav fixo (mesma ideia do --project-compact-top no JS legado).
	return `-${Math.max(0, Math.round(topOffset))}px 0px 0px 0px`;
}

/**
 * Aplica a observação de sticky/compacto ao nó sentinela.
 *
 * @param node Elemento sentinela (renderizado logo acima do cabeçalho).
 * @param params Callback + offset do topnav.
 */
export function stickyHeader(node: HTMLElement, params: StickyHeaderParams): ActionReturn {
	let current = params;
	let observer: IntersectionObserver | null = null;

	function notify(isCompact: boolean): void {
		current.onChange(isCompact);
	}

	/**
	 * Decide o estado compacto de forma DIRECIONAL: só compacta quando a base do
	 * sentinela já rolou ACIMA da linha do topnav. Comparar apenas com
	 * `isIntersecting` mostraria o compacto também quando o sentinela está abaixo
	 * da dobra (telas baixas), com o cabeçalho inteiro ainda visível.
	 */
	function evaluate(): void {
		const top = Math.max(0, Math.round(current.topOffset ?? 0));
		notify(node.getBoundingClientRect().bottom <= top);
	}

	function connect(): void {
		if (typeof IntersectionObserver === 'undefined') {
			// SSR/jsdom: começa expandido e não observa.
			notify(false);
			return;
		}
		observer = new IntersectionObserver(
			(entries) => {
				if (!entries[0]) return;
				// O observer só dispara nos cruzamentos da linha do topnav e da
				// dobra; a decisão de mostrar/esconder é sempre direcional.
				evaluate();
			},
			{ root: null, rootMargin: buildRootMargin(current.topOffset ?? 0), threshold: 0 }
		);
		observer.observe(node);
	}

	function disconnect(): void {
		if (observer) {
			observer.disconnect();
			observer = null;
		}
	}

	connect();

	return {
		update(next: StickyHeaderParams): void {
			const topOffsetChanged = (next.topOffset ?? 0) !== (current.topOffset ?? 0);
			current = next;
			// Só recria o observer quando o rootMargin muda (offset do topnav).
			if (topOffsetChanged) {
				disconnect();
				connect();
			}
		},
		destroy(): void {
			disconnect();
		}
	};
}
