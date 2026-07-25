/**
 * Helpers visuais de evento para o calendario redesenhado.
 *
 * Cor por STATUS DE SYNC (nao por pessoa, nao por barra lateral).
 * Tokens semanticos dark-safe — sem hex fixo.
 */
import type { CalendarEvent } from '$lib/types/calendar';

export interface EventColorClasses {
	/** Classes Tailwind de fundo + texto + borda para o bloco/pill do evento. */
	block: string;
	/** Classe de cor da bolinha indicadora (bg-...). */
	dot: string;
}

/**
 * Retorna as classes de cor Tailwind para um evento baseado em seu status de sync.
 *
 * Paleta:
 *   - app + ok   -> primary suave (azul)
 *   - google     -> verde suave
 *   - pending    -> cinza/muted
 *   - error      -> vermelho suave
 *
 * Usa bg translucido (/15) para dark-mode sem conflito com tokens de superficie.
 */
export function eventColorClasses(ev: CalendarEvent): EventColorClasses {
	if (ev.sync_status === 'error') {
		return {
			block: [
				'bg-red-500/15 dark:bg-red-500/20',
				'text-red-700 dark:text-red-300',
				'border border-red-300/60 dark:border-red-500/30',
			].join(' '),
			dot: 'bg-red-500',
		};
	}

	if (ev.sync_status === 'pending') {
		return {
			block: [
				'bg-surface-muted',
				'text-text-secondary',
				'border border-border-subtle',
			].join(' '),
			dot: 'bg-text-muted',
		};
	}

	if (ev.source === 'google') {
		return {
			block: [
				'bg-emerald-500/15 dark:bg-emerald-500/20',
				'text-emerald-700 dark:text-emerald-300',
				'border border-emerald-300/60 dark:border-emerald-500/30',
			].join(' '),
			dot: 'bg-emerald-500',
		};
	}

	// app + ok (padrao)
	return {
		block: [
			'bg-primary-500/15 dark:bg-primary-500/20',
			'text-primary-700 dark:text-primary-500',
			'border border-primary-500/30',
		].join(' '),
		dot: 'bg-primary-500',
	};
}

/**
 * Verdadeiro quando o evento cobre o dia inteiro ou virtualmente todo o dia
 * (tolerancia de 1 minuto nas bordas), para fins de renderizacao.
 *
 * @param ev - Evento a verificar.
 * @param day - Qualquer instancia de Date dentro do dia alvo (usa meia-noite local).
 */
export function eventCoversFullDayOn(ev: CalendarEvent, day: Date): boolean {
	const dayStartMs = new Date(day.getFullYear(), day.getMonth(), day.getDate()).getTime();
	const dayEndExclusiveMs = dayStartMs + 86_400_000;
	const fullDayToleranceMs = 60_000;
	const evStartMs = new Date(ev.starts_at).getTime();
	const evEndMs = new Date(ev.ends_at).getTime();
	const segStartMs = Math.max(evStartMs, dayStartMs);
	const segEndMs = Math.min(evEndMs, dayEndExclusiveMs);
	return segStartMs <= dayStartMs && segEndMs >= dayEndExclusiveMs - fullDayToleranceMs;
}
