<script lang="ts">
	import type { CalendarEvent } from '$lib/types/calendar';
	import { layoutDayEvents } from '$lib/components/calendar/weekLayout';
	import { eventColorClasses } from '$lib/components/calendar/eventVisual';
	import { isToday, hoursRange, parseLocal } from '$lib/components/calendar/weekDates';

	interface Props {
		day: Date;
		events: CalendarEvent[];
		startHour?: number;
		endHour?: number;
		pxPerHour?: number;
		onSelectEvent?: (ev: CalendarEvent) => void;
		onCreateAt?: (date: Date) => void;
	}

	let {
		day,
		events,
		startHour = 7,
		endHour = 20,
		pxPerHour = 48,
		onSelectEvent,
		onCreateAt,
	}: Props = $props();

	const totalHeight = $derived((endHour - startHour) * pxPerHour);
	const hours = $derived(hoursRange(startHour, endHour));
	const positioned = $derived(layoutDayEvents(events, day, { startHour, endHour, pxPerHour }));
	const todayCol = $derived(isToday(day));

	function handleColumnClick(e: MouseEvent) {
		if (!onCreateAt) return;
		const target = e.currentTarget as HTMLElement;
		const rect = target.getBoundingClientRect();
		const relY = e.clientY - rect.top;
		// Snap na HORA CHEIA: o usuario refina o horario exato ao abrir o modal.
		const hour = Math.min(Math.max(Math.floor(relY / pxPerHour) + startHour, startHour), endHour - 1);
		const d = new Date(day.getFullYear(), day.getMonth(), day.getDate(), hour, 0);
		onCreateAt(d);
	}

	// Ativacao por teclado nao tem coordenada Y: abre num horario padrao (9h,
	// clampado na faixa visivel) — sem reusar a logica de posicao do mouse (NaN).
	function handleKeyboardCreate() {
		if (!onCreateAt) return;
		const hour = Math.min(Math.max(9, startHour), endHour - 1);
		onCreateAt(new Date(day.getFullYear(), day.getMonth(), day.getDate(), hour, 0));
	}

	function handleEventClick(e: MouseEvent, ev: CalendarEvent) {
		e.stopPropagation();
		onSelectEvent?.(ev);
	}

	function handleEventKeydown(e: KeyboardEvent, ev: CalendarEvent) {
		if (e.key === 'Enter' || e.key === ' ') {
			e.preventDefault();
			onSelectEvent?.(ev);
		}
	}

	function fmtTime(str: string): string {
		const d = parseLocal(str);
		return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
	}
</script>

<div
	class="relative w-full select-none"
	style="height: {totalHeight}px;"
	role="gridcell"
	aria-label={day.toLocaleDateString('pt-BR', { weekday: 'long', day: 'numeric', month: 'long' })}
	onclick={handleColumnClick}
	onkeydown={(e) => {
		if (e.key === 'Enter' || e.key === ' ') {
			e.preventDefault();
			handleKeyboardCreate();
		}
	}}
	tabindex={onCreateAt ? 0 : -1}
>
	{#if todayCol}
		<div
			class="pointer-events-none absolute inset-0 bg-primary-500/5 dark:bg-primary-500/8"
			aria-hidden="true"
		></div>
	{/if}

	{#each hours as hour}
		<div
			class="pointer-events-none absolute inset-x-0 border-t border-border-subtle"
			style="top: {(hour - startHour) * pxPerHour}px;"
			aria-hidden="true"
		></div>
	{/each}

	{#each positioned as p (p.ev.id)}
		{@const colors = eventColorClasses(p.ev)}
		<button
			type="button"
			class="absolute overflow-hidden rounded px-1.5 py-0.5 text-left transition-opacity hover:opacity-90 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 {colors.block}"
			style="top: {p.topPx}px; height: {p.heightPx}px; left: {p.leftPct}%; width: {p.widthPct}%;"
			onclick={(e) => handleEventClick(e, p.ev)}
			onkeydown={(e) => handleEventKeydown(e, p.ev)}
			aria-label="{p.ev.title} — {fmtTime(p.ev.starts_at)} até {fmtTime(p.ev.ends_at)}"
		>
			<span class="block truncate text-[11px] font-semibold leading-tight">
				{p.ev.title}
			</span>
			{#if p.heightPx >= 32}
				<span class="block truncate text-[10px] opacity-75">
					{fmtTime(p.ev.starts_at)} – {fmtTime(p.ev.ends_at)}
				</span>
			{/if}
		</button>
	{/each}
</div>
