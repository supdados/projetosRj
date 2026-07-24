import { describe, expect, it } from 'vitest';
import {
	NAV3D_SPRING,
	RELEASE_KICK,
	PRESS_SCALE,
	snapSpring,
	springSettled,
	stepSpring,
	type SpringState,
	type SpringTuning
} from './spring';

/** Integra `seconds` em passos de `dt` e devolve o histórico de x. */
function run(
	from: number,
	target: number,
	tuning: SpringTuning,
	dt: number,
	seconds: number,
	kick = 0
): { state: SpringState; peak: number; settleMs: number | null } {
	const state: SpringState = { x: from, v: kick };
	let peak = from;
	let settleMs: number | null = null;
	const steps = Math.round(seconds / dt);
	for (let i = 1; i <= steps; i += 1) {
		stepSpring(state, target, tuning, dt);
		peak = Math.max(peak, state.x);
		if (settleMs === null && springSettled(state, target)) settleMs = i * dt * 1000;
	}
	return { state, peak, settleMs };
}

describe('stepSpring', () => {
	it('chega ao mesmo lugar a 60Hz e a 144Hz (o lerp por frame do protótipo não)', () => {
		const a = run(0, 1, NAV3D_SPRING.route, 1 / 60, 0.3);
		const b = run(0, 1, NAV3D_SPRING.route, 1 / 144, 0.3);
		expect(Math.abs(a.state.x - b.state.x)).toBeLessThan(1e-2);
	});

	it('press (zeta=1) nunca ultrapassa o alvo', () => {
		const state: SpringState = { x: 1, v: 0 };
		let lowest = 1;
		for (let i = 0; i < 60; i += 1) {
			stepSpring(state, PRESS_SCALE, NAV3D_SPRING.press, 1 / 60);
			lowest = Math.min(lowest, state.x);
		}
		expect(lowest).toBeGreaterThanOrEqual(PRESS_SCALE - 1e-6);
	});

	it('press assenta em menos de 250ms', () => {
		const { settleMs } = run(1, PRESS_SCALE, NAV3D_SPRING.press, 1 / 60, 0.5);
		expect(settleMs).not.toBeNull();
		expect(settleMs as number).toBeLessThan(250);
	});

	it('release com impulso dá um pico visível (~1.05) e assenta em até 350ms', () => {
		const { peak, settleMs } = run(PRESS_SCALE, 1, NAV3D_SPRING.release, 1 / 120, 0.8, RELEASE_KICK);
		expect(peak).toBeGreaterThan(1.03);
		expect(peak).toBeLessThan(1.09);
		expect(settleMs).not.toBeNull();
		expect(settleMs as number).toBeLessThanOrEqual(350);
	});

	it('route cobre 90% do caminho antes da pílula terminar (300ms)', () => {
		const state: SpringState = { x: 0, v: 0 };
		let ms90: number | null = null;
		for (let i = 1; i <= 60; i += 1) {
			stepSpring(state, 1, NAV3D_SPRING.route, 1 / 120);
			if (ms90 === null && state.x >= 0.9) ms90 = (i / 120) * 1000;
		}
		expect(ms90).not.toBeNull();
		expect(ms90 as number).toBeLessThan(300);
	});

	it('color (zeta=1) não faz bounce — cor não pode piscar', () => {
		const { peak } = run(0, 1, NAV3D_SPRING.color, 1 / 60, 1);
		expect(peak).toBeLessThanOrEqual(1 + 1e-6);
	});

	it('dt patológico de 500ms não diverge', () => {
		const state: SpringState = { x: 0, v: 0 };
		for (let i = 0; i < 20; i += 1) stepSpring(state, 1, NAV3D_SPRING.press, 0.5);
		expect(Number.isFinite(state.x)).toBe(true);
		expect(Math.abs(state.x)).toBeLessThan(2);
	});

	it('dt zero ou negativo é no-op', () => {
		const state: SpringState = { x: 0.5, v: 3 };
		stepSpring(state, 1, NAV3D_SPRING.route, 0);
		stepSpring(state, 1, NAV3D_SPRING.route, -1);
		expect(state).toEqual({ x: 0.5, v: 3 });
	});
});

describe('snapSpring / springSettled', () => {
	it('snap zera a velocidade e satisfaz settled', () => {
		const state: SpringState = { x: 0.2, v: 9 };
		snapSpring(state, 1);
		expect(state).toEqual({ x: 1, v: 0 });
		expect(springSettled(state, 1)).toBe(true);
	});

	it('mola em movimento no alvo ainda não está assentada', () => {
		expect(springSettled({ x: 1, v: 5 }, 1)).toBe(false);
	});
});
