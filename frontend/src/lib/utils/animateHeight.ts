/**
 * Animação de altura por MEDIÇÃO (WAAPI) para o corpo do modal de importação:
 * o wrapper troca de conteúdo, medimos `offsetHeight` antes/depois e animamos
 * entre os dois valores — sem layout shift e sem altura mágica no CSS.
 */

const HEIGHT_DURATION_MS = 300;
const HEIGHT_EASING = 'cubic-bezier(0.05, 0.7, 0.1, 1)';

/** `true` quando o usuário pediu menos movimento no sistema operacional. */
export function prefersReducedMotion(): boolean {
	return typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches;
}

/**
 * Anima `el` de `from` para `to` pixels de altura e limpa `style.height` ao fim.
 *
 * Retorna `null` — e não anima nada — sob `prefers-reduced-motion`, quando as
 * alturas são iguais ou quando o ambiente não tem WAAPI (o estado final já está
 * no DOM, então o resultado visual é o mesmo, só sem transição).
 *
 * @example
 * const antes = box.offsetHeight;
 * await tick();
 * animateHeight(box, antes, box.offsetHeight);
 */
export function animateHeight(el: HTMLElement, from: number, to: number): Animation | null {
	if (from === to || prefersReducedMotion()) return null;
	if (typeof el.animate !== 'function') return null;

	el.style.height = `${to}px`;
	const animation = el.animate(
		[{ height: `${from}px` }, { height: `${to}px` }],
		{ duration: HEIGHT_DURATION_MS, easing: HEIGHT_EASING }
	);
	const clearInlineHeight = () => {
		el.style.height = '';
	};
	animation.onfinish = clearInlineHeight;
	animation.oncancel = clearInlineHeight;
	return animation;
}
