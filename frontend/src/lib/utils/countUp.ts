/**
 * Contagem animada de um número inteiro (0 → n) via rAF, com desaceleração
 * cúbica — usada no total de projetos importados da tela de conclusão.
 */
import { prefersReducedMotion } from './animateHeight';

export interface CountUpOptions {
	/** Força o atalho sem movimento (default: consulta `prefers-reduced-motion`). */
	reducedMotion?: boolean;
	/** Agendador de quadro injetável (testes passam uma fila fake). */
	requestFrame?: (callback: (time: number) => void) => void;
}

/** Desaceleração cúbica: 1 - (1 - t)³. */
export function easeOutCubic(t: number): number {
	return 1 - (1 - t) ** 3;
}

/** Valor inteiro do quadro em `t` (0..1), exato no alvo quando `t === 1`. */
export function countUpValueAt(from: number, to: number, t: number): number {
	if (t >= 1) return to;
	return Math.round(from + (to - from) * easeOutCubic(t));
}

/**
 * Chama `onFrame` a cada quadro com o valor entre `from` e `to` durante
 * `durationMs`, terminando exatamente em `to`. Sob movimento reduzido (ou
 * duração não positiva) entrega `to` de uma vez.
 *
 * Retorna o cancelador (chamar ao desmontar).
 *
 * @example
 * const cancelar = countUp(0, 42, 600, (n) => (total = n));
 */
export function countUp(
	from: number,
	to: number,
	durationMs: number,
	onFrame: (value: number) => void,
	options: CountUpOptions = {}
): () => void {
	const reducedMotion = options.reducedMotion ?? prefersReducedMotion();
	const requestFrame =
		options.requestFrame ??
		(typeof requestAnimationFrame === 'function' ? requestAnimationFrame : null);

	if (reducedMotion || durationMs <= 0 || requestFrame === null) {
		onFrame(to);
		return () => {};
	}

	let cancelled = false;
	let startTime: number | null = null;

	const step = (time: number): void => {
		if (cancelled) return;
		if (startTime === null) startTime = time;
		const t = Math.min((time - startTime) / durationMs, 1);
		onFrame(countUpValueAt(from, to, t));
		if (t < 1) requestFrame(step);
	};

	requestFrame(step);
	return () => {
		cancelled = true;
	};
}
