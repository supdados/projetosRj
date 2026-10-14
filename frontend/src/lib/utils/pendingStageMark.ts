import type { EtapaBucket, PendingEtapa } from '$lib/types/pendentes';
import { formatIsoDateBR } from '$lib/utils/dateFormat';

/**
 * Marca de prazo de uma etapa no card de Pendentes. Só o atraso ganha cor
 * (vermelho = risco, regra da régua); as demais ficam neutras para não competir
 * com o chip azul de Status ("Iniciada") da mesma linha. O vocabulário é só de
 * datas ("Termina"/"Começa"): "Em andamento" ao lado do Status "Não iniciada"
 * se contradiria na mesma linha.
 */
export interface PendingStageMark {
	label: string;
	chipClass: 'chip--danger' | 'chip--neutral';
	/** Tooltip com a data exata, só quando o rótulo não a mostra. */
	title: string | null;
}

const UPCOMING_BUCKETS: ReadonlySet<EtapaBucket> = new Set(['7dias', '14dias', '21dias']);
const DAY_MS = 86_400_000;

/** Dias de `fromIso` até `toIso` (ISO `YYYY-MM-DD`), sem fuso: só a data conta. */
function daysBetween(fromIso: string, toIso: string): number {
	return Math.round((Date.parse(toIso) - Date.parse(fromIso)) / DAY_MS);
}

function inDays(days: number): string {
	if (days <= 0) return 'hoje';
	if (days === 1) return 'amanhã';
	return `em ${days} dias`;
}

interface UpcomingMilestone {
	verb: 'Começa' | 'Termina';
	days: number;
}

function upcomingMilestone(
	etapa: Pick<PendingEtapa, 'data_inicio' | 'data_fim'>,
	hoje: string
): UpcomingMilestone | null {
	// Etapa legada sem início entra na janela pelo fim (mesma regra do backend).
	if (etapa.data_inicio && etapa.data_inicio > hoje) {
		return { verb: 'Começa', days: daysBetween(hoje, etapa.data_inicio) };
	}
	if (etapa.data_fim) return { verb: 'Termina', days: daysBetween(hoje, etapa.data_fim) };
	return null;
}

/**
 * Marca exibida ao lado da descrição da etapa; `null` para etapas fora das
 * faixas (futuro/sem data), que não pedem destaque.
 *
 * Exemplo: `pendingStageMark('7dias', { data_inicio: '2026-10-18', data_fim: '2026-12-31' }, '2026-10-13')`
 * devolve `{ label: 'Começa em 5 dias', chipClass: 'chip--neutral', title: null }`.
 */
export function pendingStageMark(
	bucket: EtapaBucket,
	etapa: Pick<PendingEtapa, 'data_inicio' | 'data_fim'>,
	hoje: string
): PendingStageMark | null {
	if (bucket === 'atrasada' && etapa.data_fim) {
		const days = daysBetween(etapa.data_fim, hoje);
		const title = `Venceu há ${days} ${days === 1 ? 'dia' : 'dias'} (${formatIsoDateBR(etapa.data_fim)})`;
		return { label: 'Atrasada', chipClass: 'chip--danger', title };
	}
	if (bucket === 'andamento') {
		const title = etapa.data_inicio
			? `Em andamento desde ${formatIsoDateBR(etapa.data_inicio)}`
			: null;
		const label = etapa.data_fim
			? `Termina ${inDays(daysBetween(hoje, etapa.data_fim))}`
			: 'Sem data de fim';
		return { label, chipClass: 'chip--neutral', title };
	}
	if (!UPCOMING_BUCKETS.has(bucket)) return null;
	const next = upcomingMilestone(etapa, hoje);
	if (!next) return null;
	return { label: `${next.verb} ${inDays(next.days)}`, chipClass: 'chip--neutral', title: null };
}
