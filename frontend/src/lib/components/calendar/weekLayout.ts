/**
 * Layout de eventos no time-grid da visao semanal/diaria.
 *
 * Algoritmo de column packing:
 *   1. Filtra eventos que nao sao all-day e que interceptam o dia.
 *   2. Agrupa por colisao de intervalo (grafo de adjacencia).
 *   3. Dentro de cada grupo, aloca colunas por ordem de inicio (earliest-deadline).
 *   4. Calcula left/width como porcentagens de 100 / total_colunas_do_grupo.
 */
import type { CalendarEvent } from '$lib/types/calendar';
import { parseLocal } from './weekDates';

export interface PositionedEvent {
	ev: CalendarEvent;
	/** Distancia do topo da grade em pixels. */
	topPx: number;
	/** Altura do bloco em pixels (minimo 20px para legibilidade). */
	heightPx: number;
	/** Posicao horizontal em % (0..100). */
	leftPct: number;
	/** Largura em % (0..100). */
	widthPct: number;
	/** Indice da coluna dentro do grupo de colisao (0-based). */
	col: number;
	/** Total de colunas no grupo de colisao. */
	cols: number;
}

interface LayoutOpts {
	startHour: number;
	endHour: number;
	pxPerHour: number;
}

interface EventInterval {
	index: number;
	startMin: number; // minutos desde meia-noite
	endMin: number;
}

/** Verdadeiro quando dois intervalos se sobrepoem (exclusive no fim). */
function overlaps(a: EventInterval, b: EventInterval): boolean {
	return a.startMin < b.endMin && b.startMin < a.endMin;
}

/** Converte hora fracionaria para pixels a partir de startHour. */
function toPx(totalMinutes: number, startHour: number, pxPerHour: number): number {
	return ((totalMinutes - startHour * 60) / 60) * pxPerHour;
}

/**
 * Agrupa indices de eventos em componentes conectados (colisao transitiva).
 * A∩B e B∩C implica que A, B, C ficam no mesmo grupo — assim o numero de
 * colunas do grupo e determinado pelo maximo de sobreposicoes simultaneas.
 */
function buildCollisionGroups(intervals: EventInterval[]): number[][] {
	const n = intervals.length;
	const parent = Array.from({ length: n }, (_, i) => i);

	function find(x: number): number {
		while (parent[x] !== x) {
			parent[x] = parent[parent[x]];
			x = parent[x];
		}
		return x;
	}
	function union(a: number, b: number): void {
		const ra = find(a);
		const rb = find(b);
		if (ra !== rb) parent[ra] = rb;
	}

	for (let i = 0; i < n; i++) {
		for (let j = i + 1; j < n; j++) {
			if (overlaps(intervals[i], intervals[j])) union(i, j);
		}
	}

	const groups = new Map<number, number[]>();
	for (let i = 0; i < n; i++) {
		const root = find(i);
		if (!groups.has(root)) groups.set(root, []);
		groups.get(root)!.push(i);
	}
	return [...groups.values()];
}

/**
 * Para um grupo de indices, atribui uma coluna a cada evento usando
 * greedy slot allocation (ordena por inicio; coluna mais cedo disponivel).
 * Retorna Map<indiceOriginal, coluna>.
 */
function assignColumns(group: number[], intervals: EventInterval[]): Map<number, number> {
	const sorted = [...group].sort(
		(a, b) => intervals[a].startMin - intervals[b].startMin
	);
	const colEnds: number[] = []; // colEnds[c] = minuto em que coluna c fica livre
	const assignment = new Map<number, number>();

	for (const idx of sorted) {
		const iv = intervals[idx];
		let col = colEnds.findIndex((end) => end <= iv.startMin);
		if (col === -1) {
			col = colEnds.length;
			colEnds.push(0);
		}
		colEnds[col] = iv.endMin;
		assignment.set(idx, col);
	}
	return assignment;
}

/**
 * Calcula layout de eventos para um unico dia no time-grid.
 *
 * Eventos `is_all_day` sao ignorados (vao numa faixa all-day separada).
 * Eventos fora da faixa [startHour, endHour] sao clampados (nao excluidos).
 *
 * @param events - Todos os eventos do usuario (a funcao filtra pelo dia).
 * @param day - Data do dia a renderizar.
 * @param opts - Parametros do grid.
 */
export function layoutDayEvents(
	events: CalendarEvent[],
	day: Date,
	opts: LayoutOpts
): PositionedEvent[] {
	const { startHour, endHour, pxPerHour } = opts;
	const gridStartMin = startHour * 60;
	const gridEndMin = endHour * 60;
	const dayStart = new Date(day.getFullYear(), day.getMonth(), day.getDate()).getTime();
	const dayEnd = dayStart + 86_400_000;

	// Filtra eventos relevantes para o dia (exclui all-day)
	const relevant = events.filter((ev) => {
		if (ev.is_all_day) return false;
		const s = parseLocal(ev.starts_at).getTime();
		const e = parseLocal(ev.ends_at).getTime();
		// Intercepta o dia se começa antes do fim e termina depois do inicio
		return s < dayEnd && e > dayStart;
	});

	if (relevant.length === 0) return [];

	// Calcula intervalos em minutos desde a meia-noite DO DIA RENDERIZADO.
	// Recorta ao segmento que intersecta o dia (essencial p/ eventos que cruzam
	// a meia-noite: no 1o dia vai ate o fim do dia, no 2o comeca na meia-noite),
	// depois clampa na faixa visivel [gridStartMin, gridEndMin].
	const intervals: EventInterval[] = relevant.map((ev, index) => {
		const sMs = parseLocal(ev.starts_at).getTime();
		const eMs = parseLocal(ev.ends_at).getTime();
		// Minutos do segmento que cai DENTRO do dia (0..1440): eventos que cruzam
		// a meia-noite sao recortados ao dia antes de virar minutos.
		const segStartMin = (Math.max(sMs, dayStart) - dayStart) / 60_000;
		const segEndMin = (Math.min(eMs, dayEnd) - dayStart) / 60_000;
		// Clamp na faixa visivel; garante pelo menos 15 min de altura apos clamp.
		const startMin = Math.max(segStartMin, gridStartMin);
		const endMin = Math.min(Math.max(segEndMin, startMin + 15), gridEndMin);
		return { index, startMin, endMin };
	});

	const groups = buildCollisionGroups(intervals);

	// Mapa indiceOriginal -> { col, cols }
	const colMap = new Map<number, { col: number; cols: number }>();
	for (const group of groups) {
		const assignment = assignColumns(group, intervals);
		const cols = Math.max(...[...assignment.values()]) + 1;
		for (const [idx, col] of assignment) {
			colMap.set(idx, { col, cols });
		}
	}

	const MIN_HEIGHT_PX = 20;

	return relevant.map((ev, i) => {
		const iv = intervals[i];
		const { col, cols } = colMap.get(i)!;
		const topPx = toPx(iv.startMin, startHour, pxPerHour);
		const rawHeight = toPx(iv.endMin - iv.startMin, 0, pxPerHour);
		const heightPx = Math.max(rawHeight, MIN_HEIGHT_PX);
		const widthPct = 100 / cols;
		const leftPct = col * widthPct;
		return { ev, topPx, heightPx, leftPct, widthPct, col, cols };
	});
}
