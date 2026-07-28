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
 *   - app + ok   -> wash brand (azul)
 *   - google     -> wash success (verde)
 *   - pending    -> cinza/muted
 *   - error      -> wash danger (vermelho)
 *
 * Usa degraus wash/soft nomeados — deslocam sozinhos no dark, sem variante dark:.
 */
export function eventColorClasses(ev: CalendarEvent): EventColorClasses {
	if (ev.sync_status === 'error') {
		return {
			block: ['bg-wash-danger', 'text-danger', 'border border-danger-soft'].join(' '),
			dot: 'bg-danger',
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
		// Verde = "evento veio do Google": acoplar ao papel success e uma decisao
		// consciente (plano §6 commit 7), nao um estado de sucesso do dominio.
		return {
			block: ['bg-wash-success', 'text-success', 'border border-success-soft'].join(' '),
			dot: 'bg-success',
		};
	}

	// app + ok (padrao)
	return {
		block: ['bg-wash-brand', 'text-brand', 'border border-brand-soft'].join(' '),
		dot: 'bg-brand',
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
