/**
 * Altura das visões do calendário: do topo do elemento até o fim da viewport.
 * Fonte única para Dia, Semana e Mês, que devem terminar na mesma linha.
 *
 * Exemplo:
 *     <div use:fillToBottom>…</div>            // define height inline
 *     const px = heightToViewportBottom(el);   // só o número
 */

/** Igual ao py-6 do <main>. */
export const CAL_BOTTOM_GAP = 24;
/** Abaixo disto a grade fica ilegível; aí sim a página rola. */
export const CAL_MIN_HEIGHT = 360;
export function heightToViewportBottom(el: HTMLElement, gap: number = CAL_BOTTOM_GAP): number {
	const top = el.getBoundingClientRect().top;
	const footer = document.querySelector('.app-shell footer');
	const footerHeight = footer ? footer.getBoundingClientRect().height : 0;
	return Math.max(CAL_MIN_HEIGHT, window.innerHeight - top - footerHeight - gap);
}

/**
 * Action: mantém `height` do elemento igual ao espaço até o fim da viewport,
 * remedindo em resize e quando o conteúdo acima muda de altura.
 */
export function fillToBottom(node: HTMLElement, gap: number = CAL_BOTTOM_GAP) {
	let currentGap = gap;

	const apply = (): void => {
		node.style.height = `${heightToViewportBottom(node, currentGap)}px`;
	};

	const onResize = (): void => apply();
	// O topo do elemento muda quando o que está acima cresce (ex.: a faixa de
	// eventos de dia inteiro ganhando uma linha).
	const observer = new ResizeObserver(() => apply());

	requestAnimationFrame(apply);
	window.addEventListener('resize', onResize);
	if (node.parentElement) observer.observe(node.parentElement);

	return {
		update(nextGap: number = CAL_BOTTOM_GAP): void {
			currentGap = nextGap;
			apply();
		},
		destroy(): void {
			window.removeEventListener('resize', onResize);
			observer.disconnect();
		}
	};
}
