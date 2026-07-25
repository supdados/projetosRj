/**
 * Integrador de mola (Euler semi-implícito) para os ícones 3D do topnav.
 * Passo em tempo real com substep fixo: independe da taxa de quadros.
 *
 * Exemplo:
 *     const s: SpringState = { x: 1, v: 0 };
 *     stepSpring(s, 0.9, NAV3D_SPRING.press, 1 / 60); // afunda para 0.9
 */

export interface SpringState {
	x: number;
	v: number;
}

export interface SpringTuning {
	/** Amortecimento. 1 = crítico (sem overshoot); < 1 dá o "pop". */
	zeta: number;
	/** Rigidez. Tempo de acomodação ≈ 4 / (zeta * sqrt(k)). */
	k: number;
}

/**
 * Calibragens por canal. `route` e `color` acompanham a pílula da navbar
 * (`.nav-pill--slide`, 300ms) — um ícone que assenta em 100ms chegaria sozinho.
 */
export const NAV3D_SPRING = {
	/** pointerdown: afunda sem overshoot; 90% do movimento em ~30ms. */
	press: { zeta: 1.0, k: 2800 },
	/** pointerup: o "pop" de acionamento, pico ~1.05. */
	release: { zeta: 0.6, k: 800 },
	/** troca de rota: pose idle <-> ativo, 90% em ~160ms. */
	route: { zeta: 0.9, k: 500 },
	/** cor idle <-> ativo. zeta=1 obrigatório: cor com bounce vira piscada. */
	color: { zeta: 1.0, k: 500 }
} as const satisfies Record<string, SpringTuning>;

/**
 * Impulso injetado no release; sem ele o overshoot de 0.9→1 seria invisível
 * (0.01 de excesso). Valor medido em `spring.test.ts`, não calculado.
 */
export const RELEASE_KICK = 7;
/** Escala do ícone enquanto pressionado. */
export const PRESS_SCALE = 0.9;
/** Rotação extra (rad) enquanto pressionado — gira "para dentro". */
export const PRESS_YAW = 0.16;

/** Aba em segundo plano devolve dt gigante; acima disso a mola daria salto. */
const MAX_DT = 1 / 30;
/** k=2800 (ω0≈52,9) só é estável até dt < 2/ω0 ≈ 37,8ms. */
const SUBSTEP = 1 / 120;
/**
 * Abaixo disto a mola está parada para efeito de render: 0.002 em rad/escala
 * é menos de um décimo de pixel num ícone de 26px — apertar mais só mantém o
 * rAF vivo pintando frames idênticos.
 */
const EPS_X = 0.002;
const EPS_V = 0.01;

/**
 * Avança a mola `state` rumo a `target` por `dt` segundos.
 *
 * Exemplo:
 *     stepSpring({ x: 0, v: 0 }, 1, NAV3D_SPRING.route, 0.016);
 */
export function stepSpring(
	state: SpringState,
	target: number,
	tuning: SpringTuning,
	dt: number
): void {
	if (!(dt > 0)) return;
	const omega = Math.sqrt(tuning.k);
	const damping = 2 * tuning.zeta * omega;
	let remaining = Math.min(dt, MAX_DT);
	while (remaining > 0) {
		const h = Math.min(SUBSTEP, remaining);
		remaining -= h;
		const accel = tuning.k * (target - state.x) - damping * state.v;
		state.v += accel * h;
		state.x += state.v * h;
	}
}

/** Mola parada no alvo? Usado para decidir se o loop de render pode dormir. */
export function springSettled(state: SpringState, target: number): boolean {
	return Math.abs(target - state.x) < EPS_X && Math.abs(state.v) < EPS_V;
}

/** Cola a mola no alvo (reduced-motion, aba oculta, reconciliação). */
export function snapSpring(state: SpringState, target: number): void {
	state.x = target;
	state.v = 0;
}
