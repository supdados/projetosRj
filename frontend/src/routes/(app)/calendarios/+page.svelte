<script lang="ts">
	/**
	 * Tela "Calendario" — HUB completo (paridade v4.5).
	 *
	 * Reproduz o hub legado (templates/calendars + static/js/pages/calendars.js):
	 *   - Header compacto: badge Google, navegacao de periodo, toggle de visao
	 *     (dia/semana/mes), acoes de conexao (sync/renovar/desconectar via
	 *     <CalendarConnectionBanner>) e botao "Novo evento".
	 *   - Visao MES: grade mensal com celulas, pilulas de evento de um dia,
	 *     barras de span (eventos multi-dia) sobrepostas em lanes, "+N mais" com
	 *     densidade calculada pela altura disponivel da celula, popover do dia e
	 *     popover de detalhe do evento (estilo Google).
	 *   - Visoes SEMANA/DIA: grade de horarios (time grid) com criacao por clique.
	 *
	 * O CRUD de evento e delegado ao <CalendarEventModal>; a pagina chama os
	 * endpoints /api dedicados (lib/api/calendars.ts) e recarrega o hub. A geracao
	 * de Meet no popover de detalhe usa `generateMeet` e atualiza o evento local.
	 *
	 * `localStorage('cal_view')` persiste a visao escolhida (paridade legado).
	 */
	import { onMount, tick } from 'svelte';
	import { browser } from '$app/environment';
	import {
		getCalendarHub,
		disconnectGoogle,
		syncNow,
		renewWatch,
		createEvent,
		updateEvent,
		deleteEvent,
		generateMeet,
		fetchCalendarMembers
	} from '$lib/api/calendars';
	import { ApiClientError } from '$lib/api/client';
	import type {
		CalendarEvent,
		CalendarEventInput,
		CalendarEventMutationResult,
		CalendarEventDeleteResult,
		CalendarHub,
		CalendarMember
	} from '$lib/types/calendar';
	import PageHeader from '$lib/components/PageHeader.svelte';
	import CalendarConnectionBanner from '$lib/components/CalendarConnectionBanner.svelte';
	import CalendarEventModal from '$lib/components/CalendarEventModal.svelte';
	import LoadErrorState from '$lib/components/LoadErrorState.svelte';
	import CalendarWeekGrid from '$lib/components/calendar/CalendarWeekGrid.svelte';
	import CalendarRightPanel from '$lib/components/calendar/CalendarRightPanel.svelte';
	import {
		startOfWeek,
		fmtWeekRangeLabel,
		addDays,
		isoDayKey
	} from '$lib/components/calendar/weekDates';

	type LoadState = 'loading' | 'ready' | 'error';
	type ViewMode = 'day' | 'week' | 'month';

	const MONTHS = [
		'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
		'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'
	];
	const WDAYS = ['Dom', 'Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb'];

	let loadState = $state<LoadState>('loading');
	let hub = $state<CalendarHub | null>(null);
	let errorMessage = $state<string>('');
	let connectionBusy = $state<boolean>(false);

	const today = new Date();
	let curYear = $state(today.getFullYear());
	let curMonth = $state(today.getMonth());
	let curView = $state<ViewMode>('week');
	// Data foco das visoes Semana/Dia e do painel direito (mini-mes/Esta semana).
	let anchorDate = $state(new Date());
	let members = $state<CalendarMember[]>([]);

	// Modal.
	let modalOpen = $state<boolean>(false);
	let modalEvent = $state<CalendarEvent | null>(null);
	let modalBusy = $state<boolean>(false);
	let modalError = $state<string | null>(null);
	let modalCreateDate = $state<string>('');
	// datetime-local "YYYY-MM-DDTHH:MM" do clique no time-grid (prefill do horario).
	let modalCreateStart = $state<string>('');

	let actionNotice = $state<{ message: string; tone: 'success' | 'warning' } | null>(null);
	let noticeTimer: ReturnType<typeof setTimeout> | null = null;

	function showNotice(message: string, tone: 'success' | 'warning'): void {
		if (noticeTimer) clearTimeout(noticeTimer);
		actionNotice = { message, tone };
		noticeTimer = setTimeout(() => {
			actionNotice = null;
			noticeTimer = null;
		}, 2200);
	}

	let inFlight: AbortController | null = null;

	function readErrorMessage(err: unknown, fallback: string): string {
		if (err instanceof Error && err.message) return err.message;
		return fallback;
	}

	async function load(): Promise<void> {
		loadState = hub ? loadState : 'loading';
		errorMessage = '';
		inFlight?.abort();
		const controller = new AbortController();
		inFlight = controller;
		try {
			const next = await getCalendarHub(controller.signal);
			if (controller.signal.aborted) return;
			hub = next;
			loadState = 'ready';
		} catch (err) {
			if (controller.signal.aborted) return;
			if (err instanceof ApiClientError && err.code === 'unauthenticated') return;
			errorMessage = readErrorMessage(err, 'Falha ao carregar o calendario.');
			loadState = 'error';
		}
	}

	async function loadMembers(): Promise<void> {
		try {
			const res = await fetchCalendarMembers();
			members = res.members;
		} catch {
			members = [];
		}
	}

	onMount(() => {
		if (browser) {
			const saved = localStorage.getItem('cal_view');
			// Migra valores legados ('calendar' e a visao 'list' descontinuada) -> 'month';
			// valida contra o set atual.
			const migrated = saved === 'calendar' || saved === 'list' ? 'month' : saved;
			if (migrated === 'day' || migrated === 'week' || migrated === 'month') {
				curView = migrated;
			}
		}
		void load();
		void loadMembers();
		return () => {
			inFlight?.abort();
			if (noticeTimer) clearTimeout(noticeTimer);
		};
	});

	const events = $derived<CalendarEvent[]>(hub?.events ?? []);
	const eventCount = $derived(events.length);
	const hasGoogle = $derived(hub?.connection != null);

	// --- View toggle ---
	function switchView(v: ViewMode): void {
		closeDayPopover();
		closeEventPopover();
		curView = v;
		if (browser) localStorage.setItem('cal_view', v);
	}

	function prevMonth(): void {
		closeDayPopover();
		closeEventPopover();
		if (--curMonth < 0) { curMonth = 11; curYear--; }
	}
	function nextMonth(): void {
		closeDayPopover();
		closeEventPopover();
		if (++curMonth > 11) { curMonth = 0; curYear++; }
	}
	function goToToday(): void {
		closeDayPopover();
		closeEventPopover();
		curYear = today.getFullYear();
		curMonth = today.getMonth();
		anchorDate = new Date();
	}

	// Navegacao do header adaptada a visao: mes (month), semana (week), dia (day).
	function prevPeriod(): void {
		closeDayPopover();
		closeEventPopover();
		if (curView === 'week') anchorDate = addDays(anchorDate, -7);
		else if (curView === 'day') anchorDate = addDays(anchorDate, -1);
		else prevMonth();
	}
	function nextPeriod(): void {
		closeDayPopover();
		closeEventPopover();
		if (curView === 'week') anchorDate = addDays(anchorDate, 7);
		else if (curView === 'day') anchorDate = addDays(anchorDate, 1);
		else nextMonth();
	}

	// Mini-calendario do painel direito.
	function miniPrevMonth(): void {
		anchorDate = new Date(anchorDate.getFullYear(), anchorDate.getMonth() - 1, 1);
	}
	function miniNextMonth(): void {
		anchorDate = new Date(anchorDate.getFullYear(), anchorDate.getMonth() + 1, 1);
	}
	function selectDay(date: Date): void {
		anchorDate = date;
		if (curView === 'month') switchView('week');
	}

	// Acoes do time-grid (Semana/Dia): abre o modal JA no horario clicado.
	function openCreateAt(date: Date): void {
		const pad = (n: number): string => String(n).padStart(2, '0');
		modalEvent = null;
		modalCreateDate = isoDayKey(date);
		modalCreateStart = `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(
			date.getDate()
		)}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
		modalError = null;
		modalBusy = false;
		modalOpen = true;
	}

	// Mini-calendario: modo de destaque conforme a visao ativa.
	const miniMode = $derived<'week' | 'day'>(curView === 'week' ? 'week' : 'day');

	// --- Date math (1:1 com calendars.js) ---
	function dayTs(dateStr: string): number {
		const d = new Date(dateStr);
		return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
	}
	function isMultiDay(ev: CalendarEvent): boolean {
		return dayTs(ev.starts_at) < dayTs(ev.ends_at);
	}
	function eventCoversFullDayOn(dayStartMs: number, ev: CalendarEvent): boolean {
		const dayEndExclusiveMs = dayStartMs + 86400000;
		const fullDayToleranceMs = 60000;
		const evStartMs = new Date(ev.starts_at).getTime();
		const evEndMs = new Date(ev.ends_at).getTime();
		const segStartMs = Math.max(evStartMs, dayStartMs);
		const segEndMs = Math.min(evEndMs, dayEndExclusiveMs);
		return segStartMs <= dayStartMs && segEndMs >= dayEndExclusiveMs - fullDayToleranceMs;
	}
	function pillClass(ev: CalendarEvent): string {
		if (ev.sync_status === 'error') return 'cal-pill--error';
		if (ev.sync_status === 'pending') return 'cal-pill--pending';
		if (ev.source === 'google') return 'cal-pill--google';
		return '';
	}

	// --- Month grid model ---
	interface DayCell {
		y: number;
		m: number;
		d: number;
		outside: boolean;
		isToday: boolean;
		dateStr: string;
		dayStartMs: number;
		singleEvents: CalendarEvent[];
		dayEvents: CalendarEvent[];
		spanH: number;
	}
	interface SpanBar {
		ev: CalendarEvent;
		lane: number;
		colStart: number;
		colEnd: number;
		startsInWeek: boolean;
		endsInWeek: boolean;
	}
	interface WeekRow {
		cells: DayCell[];
		spans: SpanBar[];
	}

	function pad(n: number): string {
		return String(n).padStart(2, '0');
	}

	const monthLabel = $derived(`${MONTHS[curMonth]} ${curYear}`);

	// Visoes Semana/Dia + painel direito derivam de anchorDate.
	const weekStart = $derived(startOfWeek(anchorDate, 1));
	const weekRangeLabel = $derived(fmtWeekRangeLabel(weekStart));
	const miniMonthDate = $derived(new Date(anchorDate.getFullYear(), anchorDate.getMonth(), 1));
	const dayLabel = $derived(
		anchorDate.toLocaleDateString('pt-BR', {
			weekday: 'long',
			day: 'numeric',
			month: 'long',
			year: 'numeric'
		})
	);

	const weeks = $derived.by<WeekRow[]>(() => {
		const evs = events;
		const firstWday = new Date(curYear, curMonth, 1).getDay();
		const daysInMon = new Date(curYear, curMonth + 1, 0).getDate();
		const daysInPrev = new Date(curYear, curMonth, 0).getDate();
		const weekCount = Math.ceil((firstWday + daysInMon) / 7);
		const totalCells = weekCount * 7;

		const raw: Array<{ y: number; m: number; d: number; outside: boolean; isToday: boolean }> = [];
		for (let i = firstWday - 1; i >= 0; i--)
			raw.push({ y: curYear, m: curMonth - 1, d: daysInPrev - i, outside: true, isToday: false });
		for (let d = 1; d <= daysInMon; d++) {
			const isT =
				curYear === today.getFullYear() && curMonth === today.getMonth() && d === today.getDate();
			raw.push({ y: curYear, m: curMonth, d, outside: false, isToday: isT });
		}
		let nextD = 1;
		while (raw.length < totalCells)
			raw.push({ y: curYear, m: curMonth + 1, d: nextD++, outside: true, isToday: false });

		const result: WeekRow[] = [];
		for (let w = 0; w < weekCount; w++) {
			result.push(buildWeek(raw.slice(w * 7, w * 7 + 7), evs));
		}
		return result;
	});

	function buildWeek(
		week: Array<{ y: number; m: number; d: number; outside: boolean; isToday: boolean }>,
		evs: CalendarEvent[]
	): WeekRow {
		const weekStartMs = new Date(week[0].y, week[0].m, week[0].d, 0, 0, 0).getTime();
		const weekEndMs = new Date(week[6].y, week[6].m, week[6].d, 23, 59, 59).getTime();

		const spanEvs = evs.filter((ev) => {
			const isSpanLike = isMultiDay(ev) || ev.is_all_day;
			if (!isSpanLike) return false;
			return (
				new Date(ev.starts_at).getTime() <= weekEndMs &&
				new Date(ev.ends_at).getTime() > weekStartMs
			);
		});

		const spans: SpanBar[] = [];
		const laneEnds: number[] = [];
		if (spanEvs.length) {
			const sorted = [...spanEvs].sort(
				(a, b) => new Date(a.starts_at).getTime() - new Date(b.starts_at).getTime()
			);
			sorted.forEach((ev) => {
				const evStartMs = new Date(ev.starts_at).getTime();
				const evEndMs = new Date(ev.ends_at).getTime();
				let lane = laneEnds.findIndex((endMs) => endMs <= evStartMs);
				if (lane === -1) {
					lane = laneEnds.length;
					laneEnds.push(0);
				}
				laneEnds[lane] = evEndMs;

				let colStart = 8;
				let colEnd = 0;
				week.forEach((day, i) => {
					const dMs = new Date(day.y, day.m, day.d, 0, 0, 0).getTime();
					const dEnd = new Date(day.y, day.m, day.d, 23, 59, 59).getTime();
					if (evStartMs <= dEnd && evEndMs > dMs) {
						if (i + 1 < colStart) colStart = i + 1;
						if (i + 2 > colEnd) colEnd = i + 2;
					}
				});
				spans.push({
					ev,
					lane,
					colStart,
					colEnd,
					startsInWeek: evStartMs >= weekStartMs,
					endsInWeek: evEndMs <= weekEndMs
				});
			});
		}

		const colLanes = new Array(7).fill(0);
		spans.forEach(({ lane, colStart, colEnd }) => {
			for (let c = colStart - 1; c < colEnd - 1 && c < 7; c++)
				colLanes[c] = Math.max(colLanes[c], lane + 1);
		});

		const cells: DayCell[] = week.map((day, dayIdx) => {
			const dayStartMs = new Date(day.y, day.m, day.d, 0, 0, 0).getTime();
			const dayEndMs = new Date(day.y, day.m, day.d, 23, 59, 59).getTime();

			const singleEvents = day.outside
				? []
				: evs
						.filter((ev) => {
							if (isMultiDay(ev) || ev.is_all_day) return false;
							return dayTs(ev.starts_at) === dayStartMs;
						})
						.sort((a, b) => a.starts_at.localeCompare(b.starts_at));

			const dayEvents = day.outside
				? []
				: evs
						.filter((ev) => {
							const s = new Date(ev.starts_at).getTime();
							const e = new Date(ev.ends_at).getTime();
							return s <= dayEndMs && e > dayStartMs;
						})
						.sort((a, b) => {
							const aFull = eventCoversFullDayOn(dayStartMs, a);
							const bFull = eventCoversFullDayOn(dayStartMs, b);
							if (aFull !== bFull) return aFull ? -1 : 1;
							return a.starts_at.localeCompare(b.starts_at);
						});

			const n = colLanes[dayIdx];
			const spanH = n > 0 ? n * 1.2 + (n - 1) * 0.125 + 0.25 : 0;

			return {
				...day,
				dateStr: `${day.y}-${pad(day.m + 1)}-${pad(day.d)}`,
				dayStartMs,
				singleEvents,
				dayEvents,
				spanH
			};
		});

		return { cells, spans };
	}

	const gridTemplateRows = $derived(`auto repeat(${weeks.length}, minmax(0, 1fr))`);

	// --- Density: quantas pilulas cabem por celula. ---
	//
	// O original media as alturas com um probe escondido (calendars.js
	// measureMonthCellEventMetrics). Aqui os valores sao FIXOS pois derivam de
	// constantes do CSS (px @ 16px/rem), e o CSS scoped do Svelte nao se aplica a
	// um probe criado por JS — medir seria pior do que usar o valor de projeto:
	//   - pilula regular/all-day: font 0.69rem (~11px) + paddings -> ~17-19px;
	//   - "+N mais": font 0.67rem + padding 0.05rem -> ~13px;
	//   - gap entre pilulas: 0.18rem -> ~2.9px.
	const REM = browser ? parseFloat(getComputedStyle(document.documentElement).fontSize) || 16 : 16;
	const metrics = {
		regular: Math.round(0.69 * REM * 1.3 + 0.12 * REM), // ~17px
		allDay: Math.round(1.2 * REM), // height fixo 1.2rem
		more: Math.round(0.67 * REM * 1.3 + 0.1 * REM), // ~13px
		gap: Math.round(0.18 * REM) // ~3px
	};

	// Altura disponivel medida por celula (atualizada via ResizeObserver).
	let cellAvailHeights = $state<Record<string, number>>({});

	function visibleLayout(cell: DayCell): { count: number; height: number } {
		const avail = cellAvailHeights[cell.dateStr] ?? 0;
		const singles = cell.singleEvents;
		if (!singles.length || avail <= 0) return { count: 0, height: 0 };
		let count = 0;
		let height = 0;
		const limit = avail + 0.5;
		for (let i = 0; i < singles.length; i++) {
			const evHeight =
				eventCoversFullDayOn(cell.dayStartMs, singles[i]) || singles[i].is_all_day
					? metrics.allDay
					: metrics.regular;
			const nextHeight = height + (count > 0 ? metrics.gap : 0) + evHeight;
			if (nextHeight > limit) break;
			height = nextHeight;
			count += 1;
		}
		return { count, height };
	}

	function cellVisibleCount(cell: DayCell): number {
		return visibleLayout(cell).count;
	}
	function cellHiddenCount(cell: DayCell): number {
		return cell.singleEvents.length - cellVisibleCount(cell);
	}
	function cellMoreOverlay(cell: DayCell): boolean {
		const layout = visibleLayout(cell);
		if (cell.singleEvents.length <= layout.count) return false;
		const avail = cellAvailHeights[cell.dateStr] ?? 0;
		const inlineMoreHeight = metrics.more + (layout.count > 0 ? metrics.gap : 0);
		const remaining = avail - layout.height;
		return remaining + 0.5 < inlineMoreHeight;
	}

	// Acao Svelte: observa a altura do host de eventos para recomputar densidade.
	function observeCellHeight(node: HTMLElement, dateStr: string) {
		const update = () => {
			cellAvailHeights = { ...cellAvailHeights, [dateStr]: node.clientHeight };
		};
		update();
		const ro = new ResizeObserver(update);
		ro.observe(node);
		return {
			update(next: string) {
				dateStr = next;
				update();
			},
			destroy() {
				ro.disconnect();
			}
		};
	}

	function timeLabel(ev: CalendarEvent): string {
		return new Date(ev.starts_at).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
	}
	function monthPillLabel(cell: DayCell, ev: CalendarEvent): string {
		const isAllDayBar = ev.is_all_day || eventCoversFullDayOn(cell.dayStartMs, ev);
		const showTime = !isAllDayBar && ev.starts_at.slice(11) !== '00:00';
		return (showTime ? `${timeLabel(ev)} ` : '') + ev.title;
	}
	function isAllDayBar(cell: DayCell, ev: CalendarEvent): boolean {
		return ev.is_all_day || eventCoversFullDayOn(cell.dayStartMs, ev);
	}

	function spanBorderRadius(span: SpanBar): string {
		const r = '0.22rem';
		if (span.startsInWeek && span.endsInWeek) return r;
		if (span.startsInWeek) return `${r} 0 0 ${r}`;
		if (span.endsInWeek) return `0 ${r} ${r} 0`;
		return '0';
	}

	// --- Day popover (estilo Google) ---
	let dayPopover = $state<{
		day: DayCell;
		x: number;
		y: number;
	} | null>(null);
	let eventPopover = $state<{
		ev: CalendarEvent;
		x: number;
		y: number;
	} | null>(null);
	let meetGenBusy = $state<number | null>(null);
	let copiedPopover = $state(false);

	function closeDayPopover(): void {
		dayPopover = null;
	}
	function closeEventPopover(): void {
		eventPopover = null;
		copiedPopover = false;
	}

	async function openDayPopover(day: DayCell, anchor: HTMLElement): Promise<void> {
		closeEventPopover();
		dayPopover = { day, x: 0, y: 0 };
		await tick();
		positionPopover('.cal-day-popover', anchor, false);
	}

	async function openEventPopover(ev: CalendarEvent, anchor: HTMLElement): Promise<void> {
		const dayPop = anchor.closest('.cal-day-popover') as HTMLElement | null;
		const refEl = dayPop ?? anchor;
		closeDayPopover();
		closeEventPopover();
		eventPopover = { ev, x: 0, y: 0 };
		await tick();
		positionPopover('.cal-event-popover', refEl, !!dayPop);
	}

	function positionPopover(selector: string, anchor: HTMLElement, alignTop: boolean): void {
		const pop = document.querySelector(selector) as HTMLElement | null;
		if (!pop) return;
		const rect = anchor.getBoundingClientRect();
		const pw = pop.offsetWidth || 320;
		const ph = pop.offsetHeight || 220;
		const vw = window.innerWidth;
		const vh = window.innerHeight;
		let left = rect.left;
		let top = alignTop ? rect.top : rect.bottom + 8;
		if (left + pw > vw - 8) left = vw - pw - 8;
		if (left < 8) left = 8;
		if (top + ph > vh - 8) top = rect.top - ph - 8;
		if (top < 8) top = 8;
		const state = selector === '.cal-day-popover' ? dayPopover : eventPopover;
		if (state) {
			state.x = left;
			state.y = top;
		}
	}

	function popoverDateTime(ev: CalendarEvent): string {
		const s = new Date(ev.starts_at);
		const e = new Date(ev.ends_at);
		const sameDay = s.toDateString() === e.toDateString();
		const dateFmt = (dt: Date) =>
			dt.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit', year: 'numeric' });
		const timeFmt = (dt: Date) =>
			dt.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
		if (ev.is_all_day) {
			if (sameDay) return `${dateFmt(s)} · Dia inteiro`;
			return `${dateFmt(s)} até ${dateFmt(e)} · Dia inteiro`;
		}
		if (sameDay) return `${dateFmt(s)} · ${timeFmt(s)} - ${timeFmt(e)}`;
		return `${dateFmt(s)} ${timeFmt(s)} até ${dateFmt(e)} ${timeFmt(e)}`;
	}

	function popoverDayWeekday(day: DayCell): string {
		return new Date(day.y, day.m, day.d)
			.toLocaleDateString('pt-BR', { weekday: 'short' })
			.toUpperCase();
	}

	interface PopoverItem {
		ev: CalendarEvent;
		isSpan: boolean;
		cut: '' | 'left' | 'right' | 'both';
		time: string;
	}
	function dayPopoverItems(day: DayCell): PopoverItem[] {
		const dayStartMs = day.dayStartMs;
		const dayEndExclusiveMs = dayStartMs + 86400000;
		return day.dayEvents.map((ev) => {
			const evStartMs = new Date(ev.starts_at).getTime();
			const evEndMs = new Date(ev.ends_at).getTime();
			const occupiesFullDay = eventCoversFullDayOn(dayStartMs, ev);
			const continuesFromPrev = evStartMs < dayStartMs;
			const continuesToNext = evEndMs > dayEndExclusiveMs;
			let cut: PopoverItem['cut'] = '';
			if (occupiesFullDay) {
				if (continuesFromPrev && continuesToNext) cut = 'both';
				else if (continuesFromPrev) cut = 'left';
				else if (continuesToNext) cut = 'right';
			}
			const showTime = !occupiesFullDay && !ev.is_all_day && ev.starts_at.slice(11) !== '00:00';
			return {
				ev,
				isSpan: occupiesFullDay,
				cut,
				time: showTime ? `${timeLabel(ev)} ` : ''
			};
		});
	}

	async function copyMeet(link: string): Promise<void> {
		try {
			await navigator.clipboard.writeText(link);
		} catch {
			const ta = document.createElement('textarea');
			ta.value = link;
			ta.style.cssText = 'position:fixed;opacity:0;';
			document.body.appendChild(ta);
			ta.select();
			document.execCommand('copy');
			ta.remove();
		}
		copiedPopover = true;
		setTimeout(() => (copiedPopover = false), 1500);
	}

	async function generateMeetFromPopover(ev: CalendarEvent): Promise<void> {
		meetGenBusy = ev.id;
		try {
			const result = await generateMeet(ev.id);
			const link = result.event.meet_link;
			if (hub) {
				const idx = hub.events.findIndex((e) => e.id === ev.id);
				if (idx >= 0) hub.events[idx] = result.event;
			}
			if (eventPopover) eventPopover = { ...eventPopover, ev: result.event };
			if (link) showNotice('Link do Meet gerado.', 'success');
		} catch (err) {
			if (!(err instanceof ApiClientError && err.code === 'unauthenticated')) {
				showNotice(readErrorMessage(err, 'Falha ao gerar o link do Meet.'), 'warning');
			}
		} finally {
			meetGenBusy = null;
		}
	}

	// --- Connection actions ---
	async function runConnectionAction(action: () => Promise<unknown>, fallback: string): Promise<void> {
		if (connectionBusy) return;
		connectionBusy = true;
		errorMessage = '';
		try {
			await action();
			await load();
		} catch (err) {
			if (err instanceof ApiClientError && err.code === 'unauthenticated') return;
			errorMessage = readErrorMessage(err, fallback);
			loadState = 'error';
		} finally {
			connectionBusy = false;
		}
	}
	function handleSync(): void {
		void runConnectionAction(() => syncNow(), 'Falha ao sincronizar com o Google.');
	}
	function handleRenewWatch(): void {
		void runConnectionAction(() => renewWatch(), 'Falha ao renovar o watch.');
	}
	function handleDisconnect(): void {
		void runConnectionAction(() => disconnectGoogle(), 'Falha ao desconectar a conta Google.');
	}

	// --- Modal ---
	function openCreate(dateStr = ''): void {
		modalEvent = null;
		modalCreateDate = dateStr;
		modalCreateStart = '';
		modalError = null;
		modalBusy = false;
		modalOpen = true;
	}
	function openEdit(ev: CalendarEvent): void {
		closeDayPopover();
		closeEventPopover();
		modalEvent = ev;
		modalCreateDate = '';
		modalError = null;
		modalBusy = false;
		modalOpen = true;
	}
	function closeModal(): void {
		if (modalBusy) return;
		modalOpen = false;
		modalEvent = null;
		modalError = null;
	}

	async function runModalAction<T>(action: () => Promise<T>, fallback: string): Promise<T | null> {
		if (modalBusy) return null;
		modalBusy = true;
		modalError = null;
		try {
			const result = await action();
			await load();
			modalBusy = false;
			modalOpen = false;
			modalEvent = null;
			return result;
		} catch (err) {
			modalBusy = false;
			if (err instanceof ApiClientError && err.code === 'unauthenticated') return null;
			modalError = readErrorMessage(err, fallback);
			return null;
		}
	}

	function noticeToneFor(result: CalendarEventMutationResult): 'success' | 'warning' {
		return result.sync_outcome === 'sync_error' ? 'warning' : 'success';
	}

	function handleSave(input: CalendarEventInput): void {
		const editing = modalEvent;
		const action = editing ? () => updateEvent(editing.id, input) : () => createEvent(input);
		const fallback = editing
			? 'Nao foi possivel salvar o evento.'
			: 'Nao foi possivel criar o evento.';
		void runModalAction(action, fallback).then((result) => {
			if (result) showNotice(result.sync_message, noticeToneFor(result));
		});
	}

	function handleDelete(id: number): void {
		void runModalAction<CalendarEventDeleteResult>(
			() => deleteEvent(id),
			'Nao foi possivel excluir o evento.'
		).then((result) => {
			if (!result) return;
			if (result.remote_warning) {
				showNotice(
					`Evento removido localmente, mas falhou no Google: ${result.remote_warning}`,
					'warning'
				);
			} else {
				showNotice('Evento removido com sucesso.', 'success');
			}
		});
	}

	function handleGenerateMeet(id: number): void {
		void runModalAction<{ event: CalendarEvent }>(
			() => generateMeet(id),
			'Nao foi possivel gerar o Google Meet.'
		).then(async (result) => {
			const link = result?.event.meet_link;
			if (!link) return;
			try {
				await navigator.clipboard?.writeText(link);
				showNotice('Link copiado!', 'success');
			} catch {
				showNotice('Link do Meet gerado com sucesso.', 'success');
			}
		});
	}

	// Delete a partir dos popovers/lista (sem abrir modal).
	function deleteFromUi(id: number): void {
		if (!confirm('Excluir este evento?')) return;
		closeEventPopover();
		handleDelete(id);
	}

	// Esc fecha popovers; clique fora tambem.
	function onWindowKeydown(e: KeyboardEvent): void {
		if (e.key === 'Escape') {
			closeDayPopover();
			closeEventPopover();
		}
	}
	function onWindowClick(): void {
		closeDayPopover();
		closeEventPopover();
	}
</script>

<svelte:head>
	<title>Calendario — ProjetosRJ</title>
</svelte:head>

<svelte:window onkeydown={onWindowKeydown} />

<section class="cal-page" aria-labelledby="calendarios-title">
	<!--
		Header padrao (PageHeader) — mesma identidade visual/altura das demais
		telas. A toolbar do calendario (navegacao de periodo, toggle de visao,
		acoes de conexao Google e "Novo evento") vive DENTRO das `actions`, e o
		status Google vira uma pilula ao lado do titulo: integra-se ao header sem
		empilhar uma linha extra de controles (sem expandir a altura da tela).
	-->
	<PageHeader subtitle="Eventos e reunioes da equipe" labelId="calendarios-title">
		{#snippet titleContent()}
			<span>Calendario</span>
			{#if hub?.connection}
				<span class="cal-google-badge cal-google-badge--on ml-2 align-middle">
					<svg width="6" height="6" viewBox="0 0 8 8" aria-hidden="true"><circle cx="4" cy="4" r="4" fill="currentColor" /></svg>
					Google
				</span>
			{:else if hub?.google_calendar_enabled}
				<span class="cal-google-badge cal-google-badge--off ml-2 align-middle">
					<svg width="6" height="6" viewBox="0 0 8 8" aria-hidden="true"><circle cx="4" cy="4" r="4" fill="currentColor" /></svg>
					Google
				</span>
			{/if}
		{/snippet}
		{#snippet actions()}
			{#if hub}
				<div class="cal-toolbar">
					<!-- Acoes de conexao Google (sync / renovar / desconectar) -->
					<CalendarConnectionBanner
						connection={hub.connection}
						googleEnabled={hub.google_calendar_enabled}
						onSync={handleSync}
						onRenewWatch={handleRenewWatch}
						onDisconnect={handleDisconnect}
						busy={connectionBusy}
					/>

					<button class="cal-btn-new" type="button" onclick={() => openCreate()}>
						<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" /></svg>
						Novo evento
					</button>
				</div>
			{/if}
		{/snippet}
	</PageHeader>

	{#if loadState === 'loading'}
		<p role="status" aria-live="polite" class="text-text-secondary">Carregando calendario…</p>
	{:else if loadState === 'error'}
		<LoadErrorState message={errorMessage} onRetry={() => load()} />
	{:else if hub}
		{#if !hub.google_calendar_enabled}
			<div class="cal-alert" role="alert">
				<i class="fas fa-exclamation-triangle" aria-hidden="true"></i>
				Integração Google Calendar desabilitada neste servidor.
			</div>
		{/if}

		{#if actionNotice}
			<p
				role={actionNotice.tone === 'warning' ? 'alert' : 'status'}
				aria-live={actionNotice.tone === 'warning' ? 'assertive' : 'polite'}
				class="cal-action-notice"
				class:cal-action-notice--warning={actionNotice.tone === 'warning'}
			>
				{actionNotice.message}
			</p>
		{/if}

		<!-- ── Conteudo: visao ativa (centro) + painel direito ──────────── -->
		<div class="cal-layout">
			<div class="cal-main-col">
			<!-- Seletor de datas: cabecalho preso ao topo do card do calendario
			     (mes/semana/dia) — formam um unico item. -->
			<div
				class="cal-nav-bar"
				class:cal-nav-bar--gutter={curView === 'week' || curView === 'day'}
			>
				<div class="cal-month-nav">
					<button class="cal-nav-btn" type="button" onclick={prevPeriod} title="Anterior" aria-label="Período anterior">
						<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6" /></svg>
					</button>
					<span class="cal-month-label">
						{#if curView === 'week'}{weekRangeLabel}{:else if curView === 'day'}{dayLabel}{:else}{monthLabel}{/if}
					</span>
					<button class="cal-nav-btn" type="button" onclick={nextPeriod} title="Próximo" aria-label="Próximo período">
						<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6" /></svg>
					</button>
				</div>
				<!-- "Hoje" fora do fluxo: nao entra na centralizacao do seletor (so
				     o grupo ‹ data › fica centralizado em relacao a coluna abaixo). -->
				<button class="cal-today-btn cal-today-btn--float" type="button" onclick={goToToday}>Hoje</button>
			</div>
			{#if curView === 'week'}
				<CalendarWeekGrid {weekStart} {events} onSelectEvent={openEdit} onCreateAt={openCreateAt} />
			{:else if curView === 'day'}
				<CalendarWeekGrid weekStart={anchorDate} days={[anchorDate]} {events} onSelectEvent={openEdit} onCreateAt={openCreateAt} />
			{:else}
			<div class="cal-view cal-view--calendar is-active">
				<div class="cal-grid-wrap">
					<div class="cal-grid" style="grid-template-rows: {gridTemplateRows};">
						<div class="cal-grid-headers">
							{#each WDAYS as wd (wd)}
								<div class="cal-day-header">{wd}</div>
							{/each}
						</div>

						{#each weeks as week, wi (wi)}
							<div class="cal-week">
								<div class="cal-week-cells">
									{#each week.cells as cell (cell.dateStr)}
										{@const visCount = cellVisibleCount(cell)}
										{@const hidden = cellHiddenCount(cell)}
										<div
											class="cal-cell"
											class:cal-cell--outside={cell.outside}
											class:cal-cell--today={cell.isToday}
											role={cell.outside ? undefined : 'button'}
											tabindex={cell.outside ? undefined : 0}
											aria-label={cell.outside ? undefined : `Criar evento em ${cell.dateStr}`}
											onclick={(e) => {
												if (cell.outside) return;
												const t = e.target as HTMLElement;
												if (t.closest('.cal-event-pill') || t.closest('.cal-more-pills')) return;
												openCreate(cell.dateStr);
											}}
											onkeydown={(e) => {
												if (cell.outside) return;
												if (e.key === 'Enter' || e.key === ' ') {
													e.preventDefault();
													openCreate(cell.dateStr);
												}
											}}
										>
											<div class="cal-cell-num">{cell.d}</div>
											{#if cell.spanH > 0}
												<div class="cal-span-spacer" style="height: {cell.spanH}rem;"></div>
											{/if}
											<div class="cal-cell-events" use:observeCellHeight={cell.dateStr}>
												{#if !cell.outside}
													{#each cell.singleEvents.slice(0, visCount) as ev (ev.id)}
														<div
															class="cal-event-pill {pillClass(ev)}"
															class:cal-event-pill--all-day={isAllDayBar(cell, ev)}
															title={ev.title}
															role="button"
															tabindex="0"
															onclick={(e) => { e.stopPropagation(); openEventPopover(ev, e.currentTarget as HTMLElement); }}
															onkeydown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openEventPopover(ev, e.currentTarget as HTMLElement); } }}
														>
															{monthPillLabel(cell, ev)}
														</div>
													{/each}
													{#if hidden > 0}
														<div
															class="cal-more-pills"
															class:cal-more-pills--overlay={cellMoreOverlay(cell)}
															role="button"
															tabindex="0"
															onclick={(e) => { e.stopPropagation(); openDayPopover(cell, e.currentTarget as HTMLElement); }}
															onkeydown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openDayPopover(cell, e.currentTarget as HTMLElement); } }}
														>
															+{hidden} mais
														</div>
													{/if}
												{/if}
											</div>
										</div>
									{/each}
								</div>

								{#if week.spans.length}
									<div class="cal-week-spans">
										{#each week.spans as span (span.ev.id + '-' + span.lane)}
											<div
												class="cal-span-bar {pillClass(span.ev)}"
												style="grid-column: {span.colStart} / {span.colEnd}; grid-row: {span.lane + 1}; border-radius: {spanBorderRadius(span)}; margin-right: {span.endsInWeek ? '0.5rem' : '0'};"
												title={span.ev.title}
												role="button"
												tabindex="0"
												onclick={(e) => { e.stopPropagation(); openEventPopover(span.ev, e.currentTarget as HTMLElement); }}
												onkeydown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openEventPopover(span.ev, e.currentTarget as HTMLElement); } }}
											>
												{span.ev.title}
											</div>
										{/each}
									</div>
								{/if}
							</div>
						{/each}
					</div>
				</div>
			</div>
			{/if}
			</div>
			<div class="cal-side-col">
				<!-- Toggle de visao acima do mini calendario (coluna direita). -->
				<div class="cal-view-toggle" role="group" aria-label="Alternar visão">
					<button class="cal-toggle-btn" class:is-active={curView === 'day'} type="button" aria-pressed={curView === 'day'} onclick={() => switchView('day')}>Dia</button>
					<button class="cal-toggle-btn" class:is-active={curView === 'week'} type="button" aria-pressed={curView === 'week'} onclick={() => switchView('week')}>Semana</button>
					<button class="cal-toggle-btn" class:is-active={curView === 'month'} type="button" aria-pressed={curView === 'month'} onclick={() => switchView('month')}>Mês</button>
				</div>
				<CalendarRightPanel
					mode={miniMode}
					{weekStart}
					selectedDay={anchorDate}
					month={miniMonthDate}
					{events}
					{members}
					onSelectEvent={openEdit}
					onSelectDay={selectDay}
					onPrevMonth={miniPrevMonth}
					onNextMonth={miniNextMonth}
				/>
			</div>
		</div>
	{/if}
</section>

<!-- ── Day popover (estilo Google) ──────────────────────────────────── -->
{#if dayPopover}
	{@const items = dayPopoverItems(dayPopover.day)}
	<div
		class="cal-day-popover"
		style="left: {dayPopover.x}px; top: {dayPopover.y}px;"
		role="dialog"
		aria-label="Eventos do dia"
		onclick={(e) => e.stopPropagation()}
		onkeydown={(e) => { if (e.key === 'Escape') closeDayPopover(); }}
		tabindex="-1"
	>
		<div class="cal-popover-header">
			<div class="cal-popover-date">
				<div class="cal-popover-weekday">{popoverDayWeekday(dayPopover.day)}</div>
				<div class="cal-popover-daynum">{dayPopover.day.d}</div>
			</div>
			<button class="cal-popover-close" type="button" aria-label="Fechar" onclick={closeDayPopover}>×</button>
		</div>
		<div class="cal-popover-list">
			{#each items as item (item.ev.id)}
				<div
					class="cal-popover-item {pillClass(item.ev)}"
					class:cal-popover-item--span={item.isSpan}
					class:cal-popover-item--cut-left={item.cut === 'left'}
					class:cal-popover-item--cut-right={item.cut === 'right'}
					class:cal-popover-item--cut-both={item.cut === 'both'}
					title={item.ev.title}
					role="button"
					tabindex="0"
					onclick={(e) => { e.stopPropagation(); openEventPopover(item.ev, e.currentTarget as HTMLElement); }}
					onkeydown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openEventPopover(item.ev, e.currentTarget as HTMLElement); } }}
				>
					<span class="cal-popover-item-label">
						{#if item.time}<span>{item.time}</span>{/if}<strong>{item.ev.title}</strong>
					</span>
				</div>
			{/each}
		</div>
	</div>
{/if}

<!-- ── Event detail popover (estilo Google) ─────────────────────────── -->
{#if eventPopover}
	{@const ev = eventPopover.ev}
	<div
		class="cal-event-popover"
		style="left: {eventPopover.x}px; top: {eventPopover.y}px;"
		role="dialog"
		aria-label="Detalhes do evento"
		onclick={(e) => e.stopPropagation()}
		onkeydown={(e) => { if (e.key === 'Escape') closeEventPopover(); }}
		tabindex="-1"
	>
		<div class="cal-event-popover-head">
			<div class="cal-event-popover-title">{ev.title || 'Sem título'}</div>
			<button class="cal-event-popover-close" type="button" aria-label="Fechar" onclick={closeEventPopover}>×</button>
		</div>
		<div class="cal-event-popover-body">
			<div class="cal-event-popover-info">
				<i class="fas fa-clock" aria-hidden="true"></i>
				<span>{popoverDateTime(ev)}</span>
			</div>
			{#if ev.location}
				<div class="cal-event-popover-info">
					<i class="fas fa-map-marker-alt" aria-hidden="true"></i>
					<span>{ev.location}</span>
				</div>
			{/if}
			{#if ev.description}
				<div class="cal-event-popover-description">{ev.description}</div>
			{/if}

			<div class="cal-event-popover-meet-area">
				{#if ev.meet_link}
					<a
						class="cal-event-popover-meet-btn"
						href={ev.meet_link}
						target="_blank"
						rel="noopener noreferrer"
						onclick={(e) => e.stopPropagation()}
					>
						<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 10l4.553-2.069A1 1 0 0 1 21 8.82v6.36a1 1 0 0 1-1.447.889L15 14" /><rect x="3" y="6" width="12" height="12" rx="2" /></svg>
						<span>Abrir Meet</span>
					</a>
					<button
						class="cal-event-popover-copy-btn"
						class:cal-event-popover-copy-btn--copied={copiedPopover}
						type="button"
						title="Copiar link do Meet"
						aria-label="Copiar link do Meet"
						onclick={(e) => { e.stopPropagation(); copyMeet(ev.meet_link); }}
					>
						<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" /><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" /></svg>
					</button>
				{:else if hasGoogle}
					<button
						class="cal-event-popover-gen-meet-btn"
						type="button"
						disabled={meetGenBusy === ev.id}
						onclick={(e) => { e.stopPropagation(); generateMeetFromPopover(ev); }}
					>
						<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 10l4.553-2.069A1 1 0 0 1 21 8.82v6.36a1 1 0 0 1-1.447.889L15 14" /><rect x="3" y="6" width="12" height="12" rx="2" /></svg>
						<span>{meetGenBusy === ev.id ? 'Gerando…' : 'Gerar link do Meet'}</span>
					</button>
				{/if}
			</div>

			<div class="cal-event-popover-actions">
				<button
					class="cal-event-popover-action"
					type="button"
					onclick={(e) => { e.stopPropagation(); openEdit(ev); }}
				>
					<i class="fas fa-pen" aria-hidden="true"></i> Editar
				</button>
				<button
					class="cal-event-popover-action cal-event-popover-action--danger"
					type="button"
					onclick={(e) => { e.stopPropagation(); deleteFromUi(ev.id); }}
				>
					<i class="fas fa-trash" aria-hidden="true"></i> Apagar
				</button>
			</div>
		</div>
	</div>
{/if}

<!-- Camada para fechar popovers ao clicar fora (sem capturar cliques internos). -->
{#if dayPopover || eventPopover}
	<button
		type="button"
		class="cal-popover-scrim"
		aria-label="Fechar"
		onclick={onWindowClick}
	></button>
{/if}

<CalendarEventModal
	open={modalOpen}
	event={modalEvent}
	createDate={modalCreateDate}
	createStart={modalCreateStart}
	hasGoogle={hasGoogle}
	busy={modalBusy}
	error={modalError}
	onSave={handleSave}
	onDelete={handleDelete}
	onGenerateMeet={handleGenerateMeet}
	onClose={closeModal}
/>

<style>
	/* ════════════════════════════════════════════════════════════════════
	   Calendario hub — portado 1:1 de static/css/calendars/calendars.css (v4.5),
	   com os tokens --app-color-* mapeados para os tokens semanticos da SPA
	   (--color-*, --ds-color-*) para o dark mode trocar sozinho.
	   ════════════════════════════════════════════════════════════════════ */
	.cal-page {
		--app-color-surface: var(--color-surface);
		--app-color-surface-muted: var(--color-surface-muted);
		--app-color-border: var(--color-border);
		--app-color-text-primary: var(--color-text-primary);
		--app-color-text-secondary: var(--color-text-secondary);
		--app-color-text-muted: var(--color-text-muted);
		--app-color-primary: var(--ds-color-primary-600);
		--app-color-primary-hover: var(--ds-color-primary-700);
		--app-color-danger: var(--ds-color-danger-600);
		--app-color-success: var(--ds-color-success-600);

		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	/* ── Toolbar (dentro das `actions` do PageHeader) ───────────────────
	   Cluster de controles do calendario alinhado a direita do titulo. O
	   flex-wrap mantem o respiro responsivo do header legado quando o espaco
	   aperta, sem forcar uma linha extra de altura no caso comum (desktop). */
	.cal-toolbar {
		display: flex;
		align-items: center;
		justify-content: flex-end;
		gap: 0.5rem;
		flex-wrap: wrap;
		min-width: 0;
	}
	.cal-google-badge {
		display: inline-flex;
		align-items: center;
		gap: 0.3rem;
		font-size: 0.72rem;
		font-weight: 500;
		padding: 0.2rem 0.5rem;
		border-radius: 999px;
		border: 1px solid transparent;
		line-height: 1;
		white-space: nowrap;
		flex-shrink: 0;
	}
	.cal-google-badge--on {
		color: var(--app-color-success);
		background: rgba(22, 163, 74, 0.1);
		border-color: rgba(22, 163, 74, 0.22);
	}
	.cal-google-badge--off {
		color: var(--app-color-text-muted);
		background: var(--app-color-surface-muted);
		border-color: var(--app-color-border);
	}

	/* ── View toggle ────────────────────────────────────────────────────
	   Vive no topo da coluna direita (acima do mini calendario); ocupa a
	   largura do painel, com os 4 botoes distribuidos igualmente. */
	.cal-view-toggle {
		display: flex;
		width: 100%;
		border: 1px solid var(--app-color-border);
		border-radius: 0.45rem;
		overflow: hidden;
		background: var(--app-color-surface);
	}
	.cal-toggle-btn {
		flex: 1;
		display: flex;
		align-items: center;
		justify-content: center;
		padding: 0.38rem 0.7rem;
		background: none;
		border: none;
		cursor: pointer;
		font-size: 0.82rem;
		font-weight: 500;
		color: var(--app-color-text-muted);
		transition: background 0.13s, color 0.13s;
	}

	/* Layout 2-colunas: visao ativa (fluida) + painel direito (~320px).
	   Stacka em telas <1024px. Vive dentro do respiro do <main> — sem 100vh
	   nem overflow proprio (a pagina e o unico scroller). */
	.cal-layout {
		display: flex;
		gap: 1.25rem;
		align-items: flex-start;
		margin-top: 0.75rem;
	}
	.cal-main-col {
		flex: 1 1 0;
		min-width: 0;
	}
	/* Coluna direita: toggle de visao + painel (mini calendario, eventos,
	   equipe). Largura fixa = mesma do <aside> interno (lg:w-80 = 20rem). */
	.cal-side-col {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
		width: 20rem;
		flex-shrink: 0;
	}
	@media (max-width: 1024px) {
		.cal-side-col {
			width: 100%;
		}
		.cal-layout {
			flex-direction: column;
		}
	}
	.cal-toggle-btn:hover {
		background: var(--app-color-surface-muted);
		color: var(--app-color-text-primary);
	}
	.cal-toggle-btn.is-active {
		background: var(--app-color-primary);
		color: #fff;
	}

	/* ── Buttons ────────────────────────────────────────────────────── */
	.cal-btn-new {
		display: inline-flex;
		align-items: center;
		gap: 0.3rem;
		padding: 0.42rem 0.85rem;
		background: var(--app-color-primary);
		color: #fff;
		border: none;
		border-radius: 0.45rem;
		font-size: 0.84rem;
		font-weight: 500;
		cursor: pointer;
		transition: background 0.13s;
		white-space: nowrap;
		flex-shrink: 0;
	}
	.cal-btn-new:hover {
		background: var(--app-color-primary-hover);
	}

	.cal-btn-sm {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		gap: 0.28rem;
		padding: 0.36rem 0.65rem;
		background: none;
		border: 1px solid var(--app-color-border);
		border-radius: 0.4rem;
		font-size: 0.8rem;
		color: var(--app-color-text-secondary);
		cursor: pointer;
		white-space: nowrap;
		transition: background 0.12s, border-color 0.12s;
	}
	.cal-btn-sm:hover {
		background: var(--app-color-surface-muted);
	}
	.cal-btn-sm--danger {
		color: var(--app-color-danger);
		border-color: transparent;
	}
	.cal-btn-sm--danger:hover {
		background: rgba(220, 38, 38, 0.07);
		border-color: rgba(220, 38, 38, 0.18);
	}

	/* ── Alert / notice ─────────────────────────────────────────────── */
	.cal-alert {
		font-size: 0.84rem;
		padding: 0.5rem 0.75rem;
		border-radius: 0.5rem;
		border: 1px solid var(--app-color-border);
		background: rgba(202, 138, 4, 0.1);
		color: var(--app-color-text-secondary);
	}
	.cal-action-notice {
		font-size: 0.84rem;
		padding: 0.5rem 1rem;
		border-radius: 0.5rem;
		border: 1px solid rgba(22, 163, 74, 0.22);
		background: rgba(22, 163, 74, 0.1);
		color: var(--app-color-success);
	}
	.cal-action-notice--warning {
		border-color: rgba(202, 138, 4, 0.3);
		background: var(--app-color-surface-muted);
		color: var(--app-color-warning, #ca8a04);
	}

	/* ── Views ──────────────────────────────────────────────────────── */
	.cal-view {
		display: none;
	}
	.cal-view.is-active {
		display: block;
	}
	.cal-view--calendar.is-active {
		display: flex;
		flex-direction: column;
		/* Preenche a mesma altura aproximada da visao Semana (13h * 44px + headers). */
		min-height: 42rem;
	}

	/* ── Month nav ──────────────────────────────────────────────────────
	   Cabecalho preso ao topo do card do calendario: mesma superficie/borda
	   da grade, cantos arredondados so no topo e divisor inferior. A grade
	   abaixo perde a borda/raio do topo (ver .cal-grid-wrap e .cal-grid-card),
	   entao os dois leem como um UNICO card. */
	.cal-nav-bar {
		position: relative;
		display: flex;
		justify-content: center;
		align-items: center;
		padding: 0.5rem 0.75rem;
		background: var(--app-color-surface);
		border: 1px solid var(--app-color-border);
		border-radius: 0.75rem 0.75rem 0 0;
	}
	/* Semana/dia: a grade tem uma coluna de horas a esquerda (w-14 = 3.5rem).
	   Desloca o centro do seletor para alinhar com as colunas de DIAS (e nao
	   com a largura total do card). 4.25rem = 0.75rem (padding base) + 3.5rem. */
	.cal-nav-bar--gutter {
		padding-left: 4.25rem;
	}
	/* Grade de semana/dia (CalendarWeekGrid): cola no cabecalho acima. */
	.cal-main-col :global(.cal-grid-card) {
		border-top: none;
		border-top-left-radius: 0;
		border-top-right-radius: 0;
	}
	.cal-month-nav {
		display: flex;
		align-items: center;
		gap: 0.4rem;
		flex-shrink: 0;
	}
	.cal-month-label {
		font-size: 0.88rem;
		font-weight: 600;
		color: var(--app-color-text-primary);
		min-width: 7rem;
		text-align: center;
	}
	.cal-nav-btn {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 1.9rem;
		height: 1.9rem;
		border-radius: 0.4rem;
		border: 1px solid var(--app-color-border);
		background: var(--app-color-surface);
		color: var(--app-color-text-secondary);
		cursor: pointer;
		transition: background 0.12s;
	}
	.cal-nav-btn:hover {
		background: var(--app-color-surface-muted);
	}
	.cal-today-btn {
		padding: 0.27rem 0.6rem;
		font-size: 0.78rem;
		border-radius: 0.38rem;
		border: 1px solid var(--app-color-border);
		background: var(--app-color-surface);
		color: var(--app-color-text-secondary);
		cursor: pointer;
		transition: background 0.12s;
	}
	.cal-today-btn:hover {
		background: var(--app-color-surface-muted);
	}
	/* Fora do fluxo: ancorado a direita, sem deslocar o centro do seletor. */
	.cal-today-btn--float {
		position: absolute;
		right: 0.75rem;
		top: 50%;
		transform: translateY(-50%);
	}

	/* ── Grid ───────────────────────────────────────────────────────── */
	.cal-grid-wrap {
		border: 1px solid var(--app-color-border);
		/* Cola no cabecalho .cal-nav-bar acima: sem borda/raio no topo. */
		border-top: none;
		border-radius: 0 0 0.75rem 0.75rem;
		overflow: hidden;
		background: var(--app-color-surface);
		display: flex;
		flex-direction: column;
		flex: 1;
		min-height: 0;
	}
	.cal-grid {
		display: grid;
		grid-template-rows: auto repeat(6, minmax(0, 1fr));
		flex: 1;
		min-height: 0;
	}
	.cal-grid-headers {
		display: grid;
		grid-template-columns: repeat(7, minmax(0, 1fr));
	}
	.cal-day-header {
		padding: 0.45rem 0.2rem;
		text-align: center;
		font-size: 0.72rem;
		font-weight: 600;
		color: var(--app-color-text-muted);
		text-transform: uppercase;
		letter-spacing: 0.05em;
		border-bottom: 1px solid var(--app-color-border);
		background: var(--app-color-surface-muted);
	}
	.cal-week {
		position: relative;
	}
	.cal-week-cells {
		display: grid;
		grid-template-columns: repeat(7, minmax(0, 1fr));
		height: 100%;
	}
	.cal-week-spans {
		position: absolute;
		top: calc(0.3rem + 1.5rem + 0.18rem);
		left: 0;
		right: 0;
		display: grid;
		grid-template-columns: repeat(7, minmax(0, 1fr));
		row-gap: 2px;
		pointer-events: none;
		z-index: 1;
	}
	.cal-span-spacer {
		flex-shrink: 0;
	}
	.cal-cell-events {
		display: flex;
		flex: 1;
		min-height: 0;
		flex-direction: column;
		gap: 0.18rem;
		overflow: hidden;
		position: relative;
	}
	.cal-span-bar {
		height: 1.2rem;
		line-height: 1.2rem;
		padding: 0 0.35rem;
		font-size: 0.69rem;
		font-weight: 500;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
		cursor: pointer;
		pointer-events: auto;
		color: #fff;
		background: var(--app-color-primary);
		transition: filter 0.1s;
	}
	.cal-span-bar:hover {
		filter: brightness(1.1);
	}
	.cal-span-bar.cal-pill--google {
		background: #0f9d58;
	}
	.cal-span-bar.cal-pill--pending {
		background: #94a3b8;
	}
	.cal-span-bar.cal-pill--error {
		background: var(--app-color-danger);
	}
	.cal-cell {
		border-right: 1px solid var(--app-color-border);
		border-bottom: 1px solid var(--app-color-border);
		padding: 0.3rem 0.3rem 0.4rem;
		min-height: 0;
		display: flex;
		flex-direction: column;
		gap: 0.18rem;
		cursor: default;
		transition: background 0.1s;
		overflow: hidden;
	}
	.cal-cell:hover {
		background: var(--app-color-surface-muted);
	}
	.cal-week-cells .cal-cell:nth-child(7n) {
		border-right: none;
	}
	.cal-cell--outside {
		opacity: 0.35;
		pointer-events: none;
	}
	.cal-cell-num {
		font-size: 0.8rem;
		font-weight: 500;
		color: var(--app-color-text-muted);
		width: 1.5rem;
		height: 1.5rem;
		display: flex;
		align-items: center;
		justify-content: center;
		border-radius: 50%;
		cursor: pointer;
		transition: background 0.1s, color 0.1s;
		flex-shrink: 0;
		align-self: center;
	}
	.cal-cell:hover .cal-cell-num {
		background: var(--app-color-border);
		color: var(--app-color-text-primary);
	}
	.cal-cell--today .cal-cell-num {
		background: var(--app-color-primary);
		color: #fff;
	}
	.cal-cell--today:hover .cal-cell-num {
		background: var(--app-color-primary);
		color: #fff;
		filter: brightness(1.08);
	}
	.cal-event-pill {
		display: flex;
		align-items: center;
		gap: 0.28rem;
		padding: 0.06rem 0.25rem;
		border-radius: 0.28rem;
		font-size: 0.69rem;
		font-weight: 500;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
		cursor: pointer;
		color: var(--app-color-text-primary);
		background: none;
		transition: background 0.1s;
	}
	.cal-event-pill:hover {
		background: var(--app-color-surface-muted);
	}
	.cal-event-pill::before {
		content: '';
		flex-shrink: 0;
		width: 0.5rem;
		height: 0.5rem;
		border-radius: 50%;
		background: var(--app-color-primary);
	}
	.cal-event-pill.cal-pill--google::before {
		background: #0f9d58;
	}
	.cal-event-pill.cal-pill--pending::before {
		background: #94a3b8;
	}
	.cal-event-pill.cal-pill--error::before {
		background: var(--app-color-danger);
	}
	.cal-event-pill--all-day {
		display: block;
		box-sizing: border-box;
		background: var(--app-color-primary);
		color: #fff;
		min-height: 1.2rem;
		height: 1.2rem;
		line-height: 1.2rem;
		gap: 0;
		padding: 0 0.35rem;
		margin-right: 0.5rem;
		border-radius: 0.22rem;
	}
	.cal-event-pill--all-day::before {
		display: none;
	}
	.cal-event-pill--all-day:hover {
		background: var(--app-color-primary);
		filter: brightness(1.06);
	}
	.cal-event-pill--all-day.cal-pill--google {
		background: #0f9d58;
	}
	.cal-event-pill--all-day.cal-pill--pending {
		background: #94a3b8;
	}
	.cal-event-pill--all-day.cal-pill--error {
		background: var(--app-color-danger);
	}
	.cal-more-pills {
		font-size: 0.67rem;
		color: var(--app-color-text-muted);
		padding: 0.05rem 0.3rem;
		cursor: pointer;
		border-radius: 0.22rem;
		transition: background 0.1s, color 0.1s;
		user-select: none;
	}
	.cal-more-pills:hover {
		background: var(--app-color-surface-muted);
		color: var(--app-color-text-primary);
	}
	.cal-more-pills--overlay {
		position: absolute;
		left: 0;
		right: 0;
		bottom: -0.34rem;
		z-index: 2;
		padding-top: 0.46rem;
		padding-bottom: 0.12rem;
		background: linear-gradient(180deg, transparent 0%, var(--app-color-surface) 48%);
	}
	.cal-cell:hover .cal-more-pills--overlay {
		background: linear-gradient(180deg, transparent 0%, var(--app-color-surface-muted) 48%);
	}

	/* ── Day popover ────────────────────────────────────────────────── */
	.cal-day-popover {
		position: fixed;
		z-index: 800;
		display: flex;
		flex-direction: column;
		gap: 0.65rem;
		padding: 0.7rem 0.85rem 0.85rem;
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: 1.6rem;
		box-shadow: 0 8px 28px rgba(0, 0, 0, 0.14), 0 2px 8px rgba(0, 0, 0, 0.07);
		min-width: 15rem;
		max-width: min(19rem, calc(100vw - 1rem));
		overflow: hidden;
	}
	.cal-popover-header {
		position: relative;
		display: flex;
		align-items: flex-start;
		justify-content: center;
		padding: 0.1rem 2.25rem 0 2.25rem;
	}
	.cal-popover-date {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 0.48rem;
		min-width: 0;
	}
	.cal-popover-weekday {
		font-size: 0.76rem;
		font-weight: 500;
		letter-spacing: 0.14em;
		text-transform: uppercase;
		color: var(--color-text-muted);
	}
	.cal-popover-daynum {
		width: 3rem;
		height: 3rem;
		border-radius: 50%;
		display: grid;
		place-items: center;
		font-size: 1.9rem;
		line-height: 1;
		font-weight: 500;
		color: var(--ds-color-primary-600);
		background: rgba(0, 90, 146, 0.18);
	}
	.cal-popover-close {
		position: absolute;
		top: 0;
		right: 0;
		display: grid;
		place-items: center;
		width: 2rem;
		height: 2rem;
		background: none;
		border: none;
		border-radius: 999px;
		font-size: 1.9rem;
		line-height: 1;
		cursor: pointer;
		color: var(--color-text-muted);
		padding: 0;
		transition: color 0.1s, background 0.1s;
	}
	.cal-popover-close:hover {
		color: var(--color-text-primary);
		background: var(--color-surface-muted);
	}
	.cal-popover-list {
		display: flex;
		flex-direction: column;
		gap: 0.12rem;
	}
	.cal-popover-item {
		display: flex;
		align-items: center;
		gap: 0.62rem;
		min-width: 0;
		padding: 0.26rem 0.18rem;
		font-size: 0.78rem;
		line-height: 1.3;
		cursor: pointer;
		--cal-popover-dot: var(--ds-color-primary-600);
		color: var(--color-text-secondary);
		border-radius: 0.42rem;
		transition: background 0.1s, color 0.1s;
		text-align: left;
	}
	.cal-popover-item::before {
		content: '';
		width: 0.52rem;
		height: 0.52rem;
		border-radius: 50%;
		background: var(--cal-popover-dot);
		flex-shrink: 0;
	}
	.cal-popover-item-label {
		min-width: 0;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.cal-popover-item:hover {
		background: var(--color-surface-muted);
	}
	.cal-popover-item.cal-pill--google {
		--cal-popover-dot: #0f9d58;
	}
	.cal-popover-item.cal-pill--pending {
		--cal-popover-dot: #94a3b8;
	}
	.cal-popover-item.cal-pill--error {
		--cal-popover-dot: var(--ds-color-danger-600);
	}
	.cal-popover-item--span {
		display: block;
		padding: 0.34rem 0.72rem;
		color: #fff;
		background: var(--ds-color-primary-600);
		border-radius: 0.72rem;
		position: relative;
	}
	.cal-popover-item--span::before {
		display: none;
	}
	.cal-popover-item--span .cal-popover-item-label {
		display: block;
	}
	.cal-popover-item--span:hover {
		filter: brightness(1.06);
		background: var(--ds-color-primary-600);
	}
	.cal-popover-item--span.cal-pill--google {
		background: #0f9d58;
	}
	.cal-popover-item--span.cal-pill--pending {
		background: #94a3b8;
	}
	.cal-popover-item--span.cal-pill--error {
		background: var(--ds-color-danger-600);
	}
	.cal-popover-item--span.cal-popover-item--cut-right {
		clip-path: polygon(0 0, calc(100% - 0.8rem) 0, 100% 50%, calc(100% - 0.8rem) 100%, 0 100%);
	}
	.cal-popover-item--span.cal-popover-item--cut-left {
		clip-path: polygon(0.8rem 0, 100% 0, 100% 100%, 0.8rem 100%, 0 50%);
	}
	.cal-popover-item--span.cal-popover-item--cut-both {
		clip-path: polygon(0.8rem 0, calc(100% - 0.8rem) 0, 100% 50%, calc(100% - 0.8rem) 100%, 0.8rem 100%, 0 50%);
	}

	/* ── Event detail popover ───────────────────────────────────────── */
	.cal-event-popover {
		position: fixed;
		z-index: 820;
		width: min(22rem, calc(100vw - 1rem));
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: 0.72rem;
		box-shadow: 0 10px 28px rgba(0, 0, 0, 0.16), 0 3px 10px rgba(0, 0, 0, 0.08);
		overflow: hidden;
	}
	.cal-event-popover-head {
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		gap: 0.55rem;
		padding: 0.62rem 0.72rem 0.5rem;
		border-bottom: 1px solid var(--color-border);
		background: var(--color-surface-muted);
	}
	.cal-event-popover-title {
		font-size: 0.91rem;
		font-weight: 700;
		color: var(--color-text-primary);
		line-height: 1.32;
		word-break: break-word;
	}
	.cal-event-popover-close {
		border: none;
		background: none;
		color: var(--color-text-muted);
		font-size: 1.15rem;
		line-height: 1;
		cursor: pointer;
		padding: 0 0.18rem;
		flex-shrink: 0;
	}
	.cal-event-popover-close:hover {
		color: var(--color-text-primary);
	}
	.cal-event-popover-body {
		padding: 0.62rem 0.72rem 0.72rem;
		display: flex;
		flex-direction: column;
		gap: 0.45rem;
	}
	.cal-event-popover-info {
		display: flex;
		align-items: flex-start;
		gap: 0.42rem;
		font-size: 0.79rem;
		color: var(--color-text-secondary);
		line-height: 1.42;
	}
	.cal-event-popover-info i {
		width: 0.9rem;
		margin-top: 0.12rem;
		color: var(--color-text-muted);
		text-align: center;
		flex-shrink: 0;
	}
	.cal-event-popover-description {
		margin-top: 0.08rem;
		font-size: 0.78rem;
		color: var(--color-text-secondary);
		line-height: 1.45;
		white-space: pre-wrap;
		word-break: break-word;
	}
	.cal-event-popover-meet-area {
		display: flex;
		align-items: center;
		gap: 0.4rem;
		margin-top: 0.42rem;
	}
	.cal-event-popover-meet-btn,
	.cal-event-popover-gen-meet-btn {
		display: inline-flex;
		width: fit-content;
		align-items: center;
		gap: 0.36rem;
		padding: 0.3rem 0.7rem 0.3rem 0.55rem;
		font-size: 0.76rem;
		font-weight: 500;
		border-radius: 0.4rem;
		cursor: pointer;
		transition: background 0.12s, border-color 0.12s;
		text-decoration: none;
		white-space: nowrap;
	}
	.cal-event-popover-meet-btn {
		background: #00832d;
		color: #fff;
		border: none;
	}
	.cal-event-popover-meet-btn:hover {
		background: #006625;
		color: #fff;
		text-decoration: none;
	}
	.cal-event-popover-gen-meet-btn {
		background: transparent;
		color: var(--ds-color-primary-600);
		border: 1px solid var(--color-border);
	}
	.cal-event-popover-gen-meet-btn:hover {
		background: var(--color-surface-muted);
		border-color: var(--ds-color-primary-600);
	}
	.cal-event-popover-gen-meet-btn:disabled {
		opacity: 0.6;
		cursor: default;
	}
	.cal-event-popover-copy-btn {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 1.7rem;
		height: 1.7rem;
		border-radius: 0.35rem;
		border: 1px solid var(--color-border);
		background: transparent;
		color: var(--color-text-muted);
		cursor: pointer;
		transition: background 0.12s, color 0.12s;
		flex-shrink: 0;
	}
	.cal-event-popover-copy-btn:hover {
		background: var(--color-surface-muted);
		color: var(--color-text-primary);
	}
	.cal-event-popover-copy-btn--copied {
		color: var(--ds-color-success-600);
		border-color: var(--ds-color-success-600);
	}
	.cal-event-popover-actions {
		margin-top: 0.32rem;
		display: flex;
		justify-content: flex-end;
		gap: 0.36rem;
	}
	.cal-event-popover-action {
		border: 1px solid var(--color-border);
		background: var(--color-surface);
		color: var(--color-text-secondary);
		border-radius: 0.4rem;
		padding: 0.3rem 0.52rem;
		font-size: 0.75rem;
		display: inline-flex;
		align-items: center;
		gap: 0.32rem;
		cursor: pointer;
		transition: background 0.12s, border-color 0.12s, color 0.12s;
	}
	.cal-event-popover-action:hover {
		background: var(--color-surface-muted);
		color: var(--color-text-primary);
	}
	.cal-event-popover-action--danger {
		border-color: rgba(220, 38, 38, 0.26);
		color: var(--ds-color-danger-600);
	}
	.cal-event-popover-action--danger:hover {
		background: rgba(220, 38, 38, 0.08);
		border-color: rgba(220, 38, 38, 0.42);
		color: var(--ds-color-danger-600);
	}

	.cal-popover-scrim {
		position: fixed;
		inset: 0;
		z-index: 790;
		background: transparent;
		border: none;
		padding: 0;
		cursor: default;
	}

	/* ── Responsive ─────────────────────────────────────────────────── */
	@media (max-width: 600px) {
		.cal-cell {
			min-height: 0;
			padding: 0.2rem;
		}
		.cal-event-pill {
			font-size: 0.62rem;
			padding: 0.04rem 0.18rem;
			gap: 0.22rem;
		}
		.cal-event-pill::before {
			width: 0.42rem;
			height: 0.42rem;
		}
		.cal-span-bar {
			font-size: 0.62rem;
			height: 1rem;
			line-height: 1rem;
		}
		.cal-month-nav {
			gap: 0.3rem;
		}
		.cal-month-label {
			min-width: 7rem;
			font-size: 0.82rem;
		}
	}

	@media (prefers-reduced-motion: reduce) {
		.cal-toggle-btn,
		.cal-btn-new,
		.cal-nav-btn,
		.cal-today-btn,
		.cal-cell,
		.cal-cell-num,
		.cal-event-pill,
		.cal-span-bar {
			transition: none;
		}
	}
</style>
