import { describe, it, expect } from 'vitest';
import { layoutDayEvents } from './weekLayout';
import type { CalendarEvent } from '$lib/types/calendar';

const MONDAY = new Date(2026, 5, 1); // 2026-06-01, segunda
const OPTS = { startHour: 7, endHour: 20, pxPerHour: 60 };

function makeEvent(overrides: Partial<CalendarEvent> & { starts_at: string; ends_at: string }): CalendarEvent {
	return {
		id: Math.floor(Math.random() * 10000),
		title: 'Evento',
		description: '',
		location: '',
		starts_at_display: '',
		ends_at_display: '',
		is_all_day: false,
		source: 'app',
		sync_status: 'ok',
		meet_link: '',
		...overrides,
	};
}

describe('layoutDayEvents', () => {
	it('sem sobreposicao: 1 coluna, widthPct=100', () => {
		const evA = makeEvent({ starts_at: '2026-06-01T09:00', ends_at: '2026-06-01T10:00' });
		const evB = makeEvent({ starts_at: '2026-06-01T11:00', ends_at: '2026-06-01T12:00' });
		const result = layoutDayEvents([evA, evB], MONDAY, OPTS);

		expect(result).toHaveLength(2);
		result.forEach((p) => {
			expect(p.cols).toBe(1);
			expect(p.widthPct).toBe(100);
			expect(p.leftPct).toBe(0);
		});
	});

	it('duas sobrepostas: 2 colunas, widthPct=50', () => {
		const evA = makeEvent({ starts_at: '2026-06-01T09:00', ends_at: '2026-06-01T10:30' });
		const evB = makeEvent({ starts_at: '2026-06-01T09:30', ends_at: '2026-06-01T11:00' });
		const result = layoutDayEvents([evA, evB], MONDAY, OPTS);

		expect(result).toHaveLength(2);
		result.forEach((p) => {
			expect(p.cols).toBe(2);
			expect(p.widthPct).toBeCloseTo(50);
		});
		// colunas distintas
		const cols = result.map((p) => p.col).sort();
		expect(cols).toEqual([0, 1]);
	});

	it('cadeia parcial A∩B, B∩C, A∩C vazio: mesmo grupo, 2 colunas', () => {
		// A: 09:00-10:00, B: 09:30-10:30, C: 10:15-11:00
		// A∩B sim, B∩C sim, A∩C nao (A termina 10:00, C começa 10:15)
		// Todos no mesmo grupo transitivo; max colunas simultaneas = 2
		const evA = makeEvent({ starts_at: '2026-06-01T09:00', ends_at: '2026-06-01T10:00' });
		const evB = makeEvent({ starts_at: '2026-06-01T09:30', ends_at: '2026-06-01T10:30' });
		const evC = makeEvent({ starts_at: '2026-06-01T10:15', ends_at: '2026-06-01T11:00' });
		const result = layoutDayEvents([evA, evB, evC], MONDAY, OPTS);

		expect(result).toHaveLength(3);
		// Todos no mesmo grupo transitivo
		result.forEach((p) => expect(p.cols).toBe(2));
		// A e C nao se sobrepõem -> podem ficar na mesma coluna (greedy)
		const pA = result.find((p) => p.ev.id === evA.id)!;
		const pC = result.find((p) => p.ev.id === evC.id)!;
		expect(pA.col).toBe(pC.col); // A libera col antes de C comecar
	});

	it('clamp: evento que comeca antes de startHour entra com topPx=0', () => {
		const ev = makeEvent({ starts_at: '2026-06-01T05:00', ends_at: '2026-06-01T09:00' });
		const result = layoutDayEvents([ev], MONDAY, OPTS);

		expect(result).toHaveLength(1);
		expect(result[0].topPx).toBe(0); // clampado para startHour=7
		// altura = (09:00 - 07:00) em px = 2h * 60px = 120px
		expect(result[0].heightPx).toBe(120);
	});

	it('evento all-day e ignorado', () => {
		const ev = makeEvent({
			starts_at: '2026-06-01T00:00',
			ends_at: '2026-06-02T00:00',
			is_all_day: true,
		});
		const result = layoutDayEvents([ev], MONDAY, OPTS);
		expect(result).toHaveLength(0);
	});

	it('evento de outro dia e ignorado', () => {
		const outrodia = makeEvent({ starts_at: '2026-06-02T09:00', ends_at: '2026-06-02T10:00' });
		const result = layoutDayEvents([outrodia], MONDAY, OPTS);
		expect(result).toHaveLength(0);
	});

	it('evento cruzando a meia-noite: recortado ao dia (dia 1 ate o fim, dia 2 do inicio)', () => {
		const ev = makeEvent({ starts_at: '2026-06-01T19:00', ends_at: '2026-06-02T08:00' });
		const TUESDAY = new Date(2026, 5, 2);

		const day1 = layoutDayEvents([ev], MONDAY, OPTS);
		expect(day1).toHaveLength(1);
		expect(day1[0].topPx).toBe(720); // 19:00 = (19-7)*60
		expect(day1[0].heightPx).toBe(60); // 19:00 -> 20:00 (clamp em endHour)

		const day2 = layoutDayEvents([ev], TUESDAY, OPTS);
		expect(day2).toHaveLength(1);
		expect(day2[0].topPx).toBe(0); // clamp em startHour 07:00
		expect(day2[0].heightPx).toBe(60); // 07:00 -> 08:00
	});

	it('topPx e heightPx calculados corretamente para evento dentro da grade', () => {
		// startHour=7, pxPerHour=60 -> 08:00 = (8-7)*60 = 60px do topo; duracao 1h = 60px
		const ev = makeEvent({ starts_at: '2026-06-01T08:00', ends_at: '2026-06-01T09:00' });
		const result = layoutDayEvents([ev], MONDAY, OPTS);

		expect(result[0].topPx).toBe(60);
		expect(result[0].heightPx).toBe(60);
	});
});
