/**
 * Action `use:stickyHeader` — compacta o cabeçalho do projeto ao rolar.
 *
 * Espelha o comportamento de static/js/pages/projects/detail/10-compact-header.js:
 * usa um elemento "sentinela" posicionado logo acima do cabeçalho principal e um
 * IntersectionObserver. Enquanto o sentinela está visível (topo da página), o
 * cabeçalho está expandido; quando o sentinela sai da viewport (usuário rolou
 * para baixo), o cabeçalho vira compacto.
 *
 * A action é aplicada AO SENTINELA. Ela apenas observa a interseção e invoca o
 * callback `onChange(isCompact)` — a decisão de classes/ARIA fica no componente
 * controlado (ProjectHeader), respeitando o padrão "controlado por callback".
 *
 * Acessibilidade/robustez:
 *   - Em ambientes sem IntersectionObserver (SSR/jsdom), faz no-op seguro.
 *   - `rootMargin` opcional permite descontar a altura do topnav fixo.
 *
 * Exemplo:
 *   <div use:stickyHeader={{ onChange: (c) => (compact = c), topOffset: 64 }} />
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

	function connect(): void {
		if (typeof IntersectionObserver === 'undefined') {
			// SSR/jsdom: começa expandido e não observa.
			notify(false);
			return;
		}
		observer = new IntersectionObserver(
			(entries) => {
				const entry = entries[0];
				if (!entry) return;
				// Sentinela visível => expandido; fora da viewport => compacto.
				notify(!entry.isIntersecting);
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
