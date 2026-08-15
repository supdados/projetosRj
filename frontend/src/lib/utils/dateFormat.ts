// `timeZone: 'UTC'` porque `new Date('2026-08-05')` é meia-noite UTC e sem isso imprimiria 04/08 em America/Sao_Paulo.
const BR_DATE_UTC = new Intl.DateTimeFormat('pt-BR', {
	day: '2-digit',
	month: '2-digit',
	year: 'numeric',
	timeZone: 'UTC'
});

const BR_DATE_LOCAL_TZ = new Intl.DateTimeFormat('pt-BR', {
	day: '2-digit',
	month: '2-digit',
	year: 'numeric'
});

/** Formata um `Date` já validado em dd/mm/aaaa lendo os campos em UTC. */
export function formatDateBR(date: Date): string {
	return BR_DATE_UTC.format(date);
}

/** ISO → dd/mm/aaaa (UTC); vazio ou inválido devolve `fallback`. */
export function formatIsoDateBR(iso: string | null | undefined, fallback = ''): string {
	if (!iso) return fallback;
	const parsed = new Date(iso);
	if (Number.isNaN(parsed.getTime())) return fallback;
	return BR_DATE_UTC.format(parsed);
}

/** Timestamp ISO → dd/mm/aaaa no fuso local; vazio ou inválido devolve `null`. */
export function formatIsoDateBRLocalTz(iso: string | null | undefined): string | null {
	if (!iso) return null;
	const parsed = new Date(iso);
	if (Number.isNaN(parsed.getTime())) return null;
	return BR_DATE_LOCAL_TZ.format(parsed);
}

/** `YYYY-MM-DD` → `dd/mm/aaaa` por troca de posições; qualquer outra string volta intacta. */
export function formatIsoDatePartsBR(iso: string | null | undefined): string {
	if (!iso || iso.length !== 10) return iso || '';
	const [year, month, day] = iso.split('-');
	return `${day}/${month}/${year}`;
}
