/**
 * Testes do indicador de pendência atrasada, com relógio e agendador fakes:
 * nada aparece antes do limiar, o que apareceu fica o mínimo visível e um
 * `stop()` cedo nunca chega a mostrar o spinner.
 */
import { describe, it, expect } from 'vitest';
import { get } from 'svelte/store';

import { delayedPending, type DelayedPending, type ScheduleTimer } from './delayedPending';

/** Relógio virtual: `advance` roda os callbacks vencidos em ordem de prazo. */
class RelogioFake {
	private agora = 0;
	private proximoId = 1;
	private agendados = new Map<number, { prazo: number; callback: () => void }>();

	now = (): number => this.agora;

	schedule: ScheduleTimer = (callback, ms) => {
		const id = this.proximoId++;
		this.agendados.set(id, { prazo: this.agora + ms, callback });
		return () => {
			this.agendados.delete(id);
		};
	};

	advance(ms: number): void {
		const alvo = this.agora + ms;
		for (;;) {
			const vencido = [...this.agendados.entries()]
				.filter(([, timer]) => timer.prazo <= alvo)
				.sort((a, b) => a[1].prazo - b[1].prazo)[0];
			if (!vencido) break;
			this.agendados.delete(vencido[0]);
			this.agora = vencido[1].prazo;
			vencido[1].callback();
		}
		this.agora = alvo;
	}
}

function criar(relogio: RelogioFake): DelayedPending {
	return delayedPending({
		showAfterMs: 150,
		minVisibleMs: 350,
		now: relogio.now,
		schedule: relogio.schedule
	});
}

describe('delayedPending', () => {
	it('não mostra antes de 150ms e mostra ao cruzar o limiar', () => {
		const relogio = new RelogioFake();
		const pendente = criar(relogio);

		pendente.start();
		relogio.advance(149);
		expect(get(pendente)).toBe(false);

		relogio.advance(1);
		expect(get(pendente)).toBe(true);
	});

	it('nunca mostra quando a operação termina antes do limiar', () => {
		const relogio = new RelogioFake();
		const pendente = criar(relogio);
		const historico: boolean[] = [];
		pendente.subscribe((visivel) => historico.push(visivel));

		pendente.start();
		relogio.advance(100);
		pendente.stop();
		relogio.advance(1000);

		expect(historico).toEqual([false]);
		expect(get(pendente)).toBe(false);
	});

	it('segura o indicador por 350ms depois de aparecer', () => {
		const relogio = new RelogioFake();
		const pendente = criar(relogio);

		pendente.start();
		relogio.advance(150);
		pendente.stop();

		relogio.advance(349);
		expect(get(pendente)).toBe(true);

		relogio.advance(1);
		expect(get(pendente)).toBe(false);
	});

	it('esconde na hora quando o mínimo visível já passou', () => {
		const relogio = new RelogioFake();
		const pendente = criar(relogio);

		pendente.start();
		relogio.advance(600);
		expect(get(pendente)).toBe(true);

		pendente.stop();
		expect(get(pendente)).toBe(false);
	});

	it('reset esconde imediatamente e cancela o timer pendente', () => {
		const relogio = new RelogioFake();
		const pendente = criar(relogio);

		pendente.start();
		relogio.advance(150);
		pendente.reset();
		expect(get(pendente)).toBe(false);

		relogio.advance(1000);
		expect(get(pendente)).toBe(false);
	});
});
