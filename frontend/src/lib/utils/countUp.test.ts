/**
 * Testes da contagem animada com fila de quadros fake: a desaceleração cúbica
 * termina exatamente no alvo e o movimento reduzido pula direto para o final.
 */
import { describe, it, expect } from 'vitest';

import { countUp, countUpValueAt, easeOutCubic } from './countUp';

/** Fila de rAF controlada pelo teste (cada `run` entrega um timestamp). */
class QuadrosFake {
	private fila: ((time: number) => void)[] = [];

	requestFrame = (callback: (time: number) => void): void => {
		this.fila.push(callback);
	};

	get pendentes(): number {
		return this.fila.length;
	}

	run(tempos: number[]): void {
		for (const tempo of tempos) {
			const callback = this.fila.shift();
			if (!callback) return;
			callback(tempo);
		}
	}
}

describe('easeOutCubic', () => {
	it('vai de 0 a 1 desacelerando', () => {
		expect(easeOutCubic(0)).toBe(0);
		expect(easeOutCubic(1)).toBe(1);
		expect(easeOutCubic(0.5)).toBeCloseTo(0.875, 5);
	});
});

describe('countUpValueAt', () => {
	it('arredonda o meio do caminho e crava o alvo no fim', () => {
		expect(countUpValueAt(0, 42, 0)).toBe(0);
		expect(countUpValueAt(0, 42, 0.5)).toBe(37);
		expect(countUpValueAt(0, 42, 1)).toBe(42);
	});
});

describe('countUp', () => {
	it('emite quadros crescentes e chega exatamente no alvo', () => {
		const quadros = new QuadrosFake();
		const valores: number[] = [];

		countUp(0, 42, 600, (v) => valores.push(v), {
			reducedMotion: false,
			requestFrame: quadros.requestFrame
		});
		quadros.run([0, 300, 600]);

		expect(valores).toEqual([0, 37, 42]);
		expect(quadros.pendentes).toBe(0);
	});

	it('pula direto para o alvo sob movimento reduzido', () => {
		const quadros = new QuadrosFake();
		const valores: number[] = [];

		countUp(0, 42, 600, (v) => valores.push(v), {
			reducedMotion: true,
			requestFrame: quadros.requestFrame
		});

		expect(valores).toEqual([42]);
		expect(quadros.pendentes).toBe(0);
	});

	it('para de emitir depois de cancelado', () => {
		const quadros = new QuadrosFake();
		const valores: number[] = [];

		const cancelar = countUp(0, 42, 600, (v) => valores.push(v), {
			reducedMotion: false,
			requestFrame: quadros.requestFrame
		});
		quadros.run([0, 150]);
		cancelar();
		quadros.run([300, 600]);

		expect(valores).toEqual([0, 24]);
	});
});
