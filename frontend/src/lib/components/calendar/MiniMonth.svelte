<script lang="ts">
	import type { CalendarEvent } from '$lib/types/calendar';
	import {
		monthMatrix,
		isoDayKey,
		isSameDay,
		isToday,
		addDays,
	} from '$lib/components/calendar/weekDates';

	interface Props {
		mode?: 'week' | 'day';
		weekStart: Date;
		selectedDay?: Date;
		month: Date;
		events?: CalendarEvent[];
		onPrevMonth?: () => void;
		onNextMonth?: () => void;
		onSelectDay?: (date: Date) => void;
	}

	let {
		mode = 'week',
		weekStart,
		selectedDay,
		month,
		events = [],
		onPrevMonth,
		onNextMonth,
		onSelectDay,
	}: Props = $props();

	const PT_MONTHS = [
		'janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho',
		'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro',
	];

	const headerLabel = $derived(
		`${PT_MONTHS[month.getMonth()]} ${month.getFullYear()}`
	);

	const matrix = $derived(monthMatrix(month.getFullYear(), month.getMonth(), 0));

	const daysWithEvent = $derived(
		new Set(events.map((ev) => isoDayKey(new Date(ev.starts_at))))
	);

	const weekEnd = $derived(addDays(weekStart, 6));

	function isInHighlightedWeek(date: Date): boolean {
		const t = date.getTime();
		return t >= weekStart.getTime() && t <= weekEnd.getTime();
	}

	function isCurrentMonth(date: Date): boolean {
		return date.getMonth() === month.getMonth() && date.getFullYear() === month.getFullYear();
	}

	// Retorna as classes de fundo para a celula-wrapper (faixa ou celula unica).
	// Em mode=week a faixa e continua com cantos apenas nas extremidades da semana;
	// em mode=day destaca so o dia selecionado como celula arredondada isolada.
	function cellHighlightClass(date: Date): string {
		const bg = 'bg-wash-brand';

		if (mode === 'day') {
			if (selectedDay && isSameDay(date, selectedDay)) return `${bg} rounded`;
			return '';
		}

		if (!isInHighlightedWeek(date)) return '';
		const isFirst = isSameDay(date, weekStart);
		const isLast = isSameDay(date, weekEnd);
		if (isFirst && isLast) return `${bg} rounded`;
		if (isFirst) return `${bg} rounded-l`;
		if (isLast) return `${bg} rounded-r`;
		return bg;
	}

	function isHighlighted(date: Date): boolean {
		if (mode === 'day') return !!selectedDay && isSameDay(date, selectedDay);
		return isInHighlightedWeek(date);
	}
</script>

<div class="select-none">
	<div class="mb-2 flex items-center justify-between px-1">
		<button
			type="button"
			onclick={onPrevMonth}
			class="flex h-6 w-6 items-center justify-center rounded text-text-secondary hover:bg-surface-muted hover:text-text-primary"
			aria-label="Mês anterior"
		>
			<svg class="h-3.5 w-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2">
				<path d="M10 12L6 8l4-4" stroke-linecap="round" stroke-linejoin="round" />
			</svg>
		</button>

		<span class="text-xs font-semibold capitalize text-text-primary">
			{headerLabel}
		</span>

		<button
			type="button"
			onclick={onNextMonth}
			class="flex h-6 w-6 items-center justify-center rounded text-text-secondary hover:bg-surface-muted hover:text-text-primary"
			aria-label="Próximo mês"
		>
			<svg class="h-3.5 w-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2">
				<path d="M6 12l4-4-4-4" stroke-linecap="round" stroke-linejoin="round" />
			</svg>
		</button>
	</div>

	<!-- Cabecalho de dias: S T Q Q S S D (seg..dom) -->
	<div class="mb-1 grid grid-cols-7 text-center">
		{#each ['S', 'T', 'Q', 'Q', 'S', 'S', 'D'] as label}
			<span class="text-2xs font-medium text-text-muted">{label}</span>
		{/each}
	</div>

	{#each matrix as week}
		<div class="grid grid-cols-7">
			{#each week as date}
				{@const highlighted = isHighlighted(date)}
				{@const today = isToday(date)}
				{@const inMonth = isCurrentMonth(date)}
				{@const hasEvent = daysWithEvent.has(isoDayKey(date))}
				{@const hlClass = cellHighlightClass(date)}

				<div class="relative flex items-center justify-center py-[1px] {hlClass}">
					<button
						type="button"
						onclick={() => onSelectDay?.(date)}
						class={[
							'relative flex h-6 w-6 flex-col items-center justify-center rounded-full text-2xs font-medium transition-colors',
							today
								? 'bg-brand text-white'
								: highlighted
									? 'font-semibold text-brand'
									: inMonth
										? 'text-text-primary hover:bg-surface-muted'
										: 'text-text-muted hover:bg-surface-muted',
						].join(' ')}
						aria-label={date.toLocaleDateString('pt-BR')}
						aria-current={today ? 'date' : undefined}
					>
						{date.getDate()}
					</button>

					<!-- Ponto indicador de evento (abaixo do numero) -->
					{#if hasEvent && !today}
						<span
							class="absolute bottom-0.5 left-1/2 h-1 w-1 -translate-x-1/2 rounded-full bg-brand"
							aria-hidden="true"
						></span>
					{/if}
				</div>
			{/each}
		</div>
	{/each}
</div>
