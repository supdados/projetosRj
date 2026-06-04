/**
 * Helpers puros de data para o calendario semanal.
 * Sem dependencias de Svelte ou Flask — testavel em isolamento.
 *
 * Semana: segunda (weekStartsOn=1) a domingo por padrao.
 */

/** Retorna a segunda-feira (ou dia de inicio customizado) da semana que contem `date`. */
export function startOfWeek(date: Date, weekStartsOn: number = 1): Date {
	const d = new Date(date.getFullYear(), date.getMonth(), date.getDate());
	const dow = d.getDay(); // 0=Dom ... 6=Sab
	const diff = ((dow - weekStartsOn + 7) % 7);
	d.setDate(d.getDate() - diff);
	return d;
}

/** Retorna array de 7 datas [seg..dom] a partir de `weekStart`. */
export function weekDays(weekStart: Date): [Date, Date, Date, Date, Date, Date, Date] {
	return [0, 1, 2, 3, 4, 5, 6].map((n) => addDays(weekStart, n)) as [
		Date, Date, Date, Date, Date, Date, Date
	];
}

/** Formata uma data como "YYYY-MM-DD" (chave ISO de dia). */
export function isoDayKey(date: Date): string {
	const y = date.getFullYear();
	const m = String(date.getMonth() + 1).padStart(2, '0');
	const d = String(date.getDate()).padStart(2, '0');
	return `${y}-${m}-${d}`;
}

/** Retorna nova Date com `n` dias somados (n pode ser negativo). */
export function addDays(date: Date, n: number): Date {
	const d = new Date(date.getFullYear(), date.getMonth(), date.getDate());
	d.setDate(d.getDate() + n);
	return d;
}

/** Verdadeiro se `a` e `b` caem no mesmo dia calendario. */
export function isSameDay(a: Date, b: Date): boolean {
	return (
		a.getFullYear() === b.getFullYear() &&
		a.getMonth() === b.getMonth() &&
		a.getDate() === b.getDate()
	);
}

/** Verdadeiro se `date` e hoje (baseado na data local do cliente). */
export function isToday(date: Date): boolean {
	return isSameDay(date, new Date());
}

const PT_MONTHS_SHORT = [
	'jan', 'fev', 'mar', 'abr', 'mai', 'jun',
	'jul', 'ago', 'set', 'out', 'nov', 'dez',
];

/**
 * Label de intervalo semanal em PT-BR.
 * Ex.: "2 – 8 de jun de 2026" ou "30 jun – 6 jul de 2026" (meses diferentes).
 * `locale` reservado para expansao futura; atualmente so PT-BR.
 */
export function fmtWeekRangeLabel(weekStart: Date, _locale: string = 'pt'): string {
	const end = addDays(weekStart, 6);
	const sm = weekStart.getMonth();
	const em = end.getMonth();
	const sy = weekStart.getFullYear();
	const ey = end.getFullYear();

	if (sy === ey && sm === em) {
		return `${weekStart.getDate()} – ${end.getDate()} de ${PT_MONTHS_SHORT[sm]} de ${sy}`;
	}
	if (sy === ey) {
		return `${weekStart.getDate()} ${PT_MONTHS_SHORT[sm]} – ${end.getDate()} ${PT_MONTHS_SHORT[em]} de ${sy}`;
	}
	return (
		`${weekStart.getDate()} ${PT_MONTHS_SHORT[sm]} ${sy} – ` +
		`${end.getDate()} ${PT_MONTHS_SHORT[em]} ${ey}`
	);
}

/**
 * Faz parse de string datetime-local ("YYYY-MM-DDTHH:MM") como horario LOCAL
 * do cliente, igual a `new Date(str)` — evita interpretacao UTC acidental de
 * strings sem timezone.
 */
export function parseLocal(str: string): Date {
	return new Date(str);
}

/**
 * Array de horas inteiras no intervalo [start, end) — uteis para o time-grid.
 * Ex.: hoursRange(7, 20) -> [7, 8, ..., 19].
 */
export function hoursRange(start: number = 7, end: number = 20): number[] {
	const out: number[] = [];
	for (let h = start; h < end; h++) out.push(h);
	return out;
}

/**
 * Matriz de semanas para o mini-calendario mensal.
 * Cada linha e um array de 7 Dates; a semana comeca em `weekStartsOn` (1=seg).
 * Inclui dias do mes anterior/posterior para completar a grade.
 *
 * @example
 * monthMatrix(2026, 5, 1) // junho de 2026, semana seg-dom
 */
export function monthMatrix(
	year: number,
	monthIndex: number,
	weekStartsOn: number = 1
): Date[][] {
	const firstOfMonth = new Date(year, monthIndex, 1);
	const gridStart = startOfWeek(firstOfMonth, weekStartsOn);

	const rows: Date[][] = [];
	let cursor = gridStart;

	// Gera semanas ate cobrir todo o mes (max 6 semanas)
	while (true) {
		const week = weekDays(cursor);
		rows.push(week);
		// Para quando a proxima semana esta inteiramente apos o fim do mes
		const nextWeekStart = addDays(cursor, 7);
		if (nextWeekStart.getMonth() !== monthIndex && nextWeekStart > cursor) {
			const lastDayOfMonth = new Date(year, monthIndex + 1, 0);
			if (addDays(cursor, 6) >= lastDayOfMonth) break;
		}
		cursor = nextWeekStart;
		// Guarda contra loop infinito
		if (rows.length > 6) break;
	}

	return rows;
}
