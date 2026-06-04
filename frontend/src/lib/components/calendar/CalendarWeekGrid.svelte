<script lang="ts">
	import type { CalendarEvent } from '$lib/types/calendar';
	import {
		weekDays,
		hoursRange,
		isToday,
		isSameDay,
		parseLocal,
	} from '$lib/components/calendar/weekDates';
	import { eventColorClasses } from '$lib/components/calendar/eventVisual';
	import DayColumn from '$lib/components/calendar/DayColumn.svelte';

	interface Props {
		weekStart: Date;
		events: CalendarEvent[];
		/** Dias a exibir; default = a semana de `weekStart`. Day view passa [dia]. */
		days?: Date[];
		onSelectEvent?: (ev: CalendarEvent) => void;
		onCreateAt?: (date: Date) => void;
	}

	let { weekStart, events, days: propDays, onSelectEvent, onCreateAt }: Props = $props();

	const START_HOUR = 7;
	const END_HOUR = 20;
	// 44px/hora: equilibrio entre caber sem scroll de pagina e nao ficar baixo demais.
	const PX_PER_HOUR = 44;

	const SHORT_NAMES = ['Dom', 'Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb'];
	const shortName = (d: Date): string => SHORT_NAMES[d.getDay()];

	const days = $derived(propDays ?? weekDays(weekStart));
	const hours = $derived(hoursRange(START_HOUR, END_HOUR));

	// Eventos all-day agrupados por dia (como pills de faixa)
	function allDayEventsForDay(day: Date): CalendarEvent[] {
		return events.filter((ev) => {
			if (!ev.is_all_day) return false;
			const s = parseLocal(ev.starts_at);
			const e = parseLocal(ev.ends_at);
			// Cobre o dia se começa em ou antes do dia e termina em ou depois
			const dayMs = new Date(day.getFullYear(), day.getMonth(), day.getDate()).getTime();
			const nextDayMs = dayMs + 86_400_000;
			return s.getTime() < nextDayMs && e.getTime() > dayMs;
		});
	}

	// Quantidade máxima de all-day lanes na semana (altura dinâmica da faixa)
	const maxAllDayLanes = $derived(
		Math.max(1, ...days.map((d) => allDayEventsForDay(d).length))
	);

	// Altura da faixa all-day em px (24px por lane + padding)
	const allDayRowHeight = $derived(maxAllDayLanes * 24 + 8);

	function fmtTime(str: string): string {
		const d = parseLocal(str);
		return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
	}
</script>

<!--
	Grid de semana completa (Seg–Dom).
	Altura = conteúdo natural — nenhum height:100vh nem overflow-y interno.
	O <main> da página é o único scroller.
-->
<div
	class="w-full min-w-0 rounded-lg border border-border-subtle bg-surface text-text-primary"
	role="grid"
	aria-label="Grade semanal de eventos"
>
	<!-- ============================================================
	     HEADER STICKY — nomes dos dias + números
	     ============================================================ -->
	<div
		class="sticky top-0 z-10 flex border-b border-border-subtle bg-surface"
		role="row"
	>
		<!-- Gutter de hora (esquerda) -->
		<div class="w-14 shrink-0 border-r border-border-subtle" aria-hidden="true"></div>

		<!-- Faixa all-day label -->
		<div class="hidden"></div>

		{#each days as day, i}
			{@const today = isToday(day)}
			<div
				class="flex min-w-0 flex-1 flex-col items-center gap-0.5 py-2 text-center"
				class:border-l={i > 0}
				class:border-border-subtle={i > 0}
				role="columnheader"
				aria-label={day.toLocaleDateString('pt-BR', { weekday: 'long', day: 'numeric', month: 'long' })}
			>
				<span class="text-[11px] font-medium uppercase tracking-wide text-text-muted">
					{shortName(day)}
				</span>
				<span
					class="flex h-7 w-7 items-center justify-center rounded-full text-sm font-semibold leading-none transition-colors"
					class:bg-primary-600={today}
					class:text-white={today}
					class:text-text-primary={!today}
				>
					{day.getDate()}
				</span>
			</div>
		{/each}
	</div>

	<!-- ============================================================
	     FAIXA ALL-DAY
	     ============================================================ -->
	<div
		class="flex border-b border-border-subtle"
		role="row"
		aria-label="Eventos de dia inteiro"
	>
		<!-- Gutter label -->
		<div
			class="flex w-14 shrink-0 items-start justify-end border-r border-border-subtle px-1 pt-1"
			aria-hidden="true"
		>
			<span class="text-[9px] font-medium uppercase tracking-wide text-text-muted">
				dia int.
			</span>
		</div>

		{#each days as day, i}
			{@const pills = allDayEventsForDay(day)}
			<div
				class="relative min-w-0 flex-1 overflow-hidden px-0.5 py-1"
				class:border-l={i > 0}
				class:border-border-subtle={i > 0}
				style="min-height: {allDayRowHeight}px;"
				role="gridcell"
				aria-label="{day.toLocaleDateString('pt-BR', { day: 'numeric', month: 'long' })} — {pills.length} evento{pills.length !== 1 ? 's' : ''} de dia inteiro"
			>
				{#each pills as ev (ev.id)}
					{@const colors = eventColorClasses(ev)}
					<button
						type="button"
						class="mb-0.5 block w-full truncate rounded px-1.5 py-0.5 text-left text-[11px] font-medium leading-tight transition-opacity hover:opacity-90 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 {colors.block}"
						onclick={() => onSelectEvent?.(ev)}
						aria-label="{ev.title} — dia inteiro"
					>
						{ev.title}
					</button>
				{/each}
			</div>
		{/each}
	</div>

	<!-- ============================================================
	     TIME GRID — gutter de horas + 7 DayColumns
	     ============================================================ -->
	<div class="flex" role="row">
		<!-- Gutter de horas -->
		<div
			class="relative w-14 shrink-0 border-r border-border-subtle"
			style="height: {(END_HOUR - START_HOUR) * PX_PER_HOUR}px;"
			aria-hidden="true"
		>
			{#each hours as hour}
				<div
					class="absolute right-0 flex w-full items-start justify-end pr-1.5"
					style="top: {(hour - START_HOUR) * PX_PER_HOUR - 7}px;"
				>
					<span class="text-[10px] font-medium text-text-muted">
						{String(hour).padStart(2, '0')}:00
					</span>
				</div>
			{/each}
		</div>

		<!-- Uma DayColumn por dia da semana -->
		{#each days as day, i}
			<div
				class="min-w-0 flex-1"
				class:border-l={i > 0}
				class:border-border-subtle={i > 0}
			>
				<DayColumn
					{day}
					{events}
					startHour={START_HOUR}
					endHour={END_HOUR}
					pxPerHour={PX_PER_HOUR}
					{onSelectEvent}
					{onCreateAt}
				/>
			</div>
		{/each}
	</div>
</div>
