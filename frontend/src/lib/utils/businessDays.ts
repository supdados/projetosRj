/**
 * Aritmética de dias ÚTEIS em UTC, espelhando `services/etapas_dates`
 * (`_normalize_to_business_day` + `_add_business_days`) do backend.
 *
 * Existe para que o preview de etapas do cliente bata com o que
 * `import_template_stages` grava — usar dias corridos aqui produz datas
 * diferentes das devolvidas pelo servidor.
 *
 * Exemplo:
 *   const inicio = nextBusinessDay(new Date('2026-07-25T00:00:00Z')); // sáb → seg 27
 *   const fim = addBusinessDays(inicio, 5);                            // 2026-08-03
 */

const SUNDAY = 0;
const SATURDAY = 6;

function isWeekendUtc(date: Date): boolean {
	const weekday = date.getUTCDay();
	return weekday === SUNDAY || weekday === SATURDAY;
}

/** Soma N dias úteis (pula sáb/dom) a uma data, em UTC, sem mutá-la. */
export function addBusinessDays(base: Date, days: number): Date {
	const result = new Date(base.getTime());
	let added = 0;
	while (added < days) {
		result.setUTCDate(result.getUTCDate() + 1);
		if (!isWeekendUtc(result)) added += 1;
	}
	return result;
}

/** Avança a data até o primeiro dia útil (>= ela mesma), em UTC, sem mutá-la. */
export function nextBusinessDay(base: Date): Date {
	const result = new Date(base.getTime());
	while (isWeekendUtc(result)) {
		result.setUTCDate(result.getUTCDate() + 1);
	}
	return result;
}
