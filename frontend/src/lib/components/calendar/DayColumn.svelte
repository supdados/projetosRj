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

	/** Hora sob o cursor (faixa de pre-visualizacao do clique). `null` = sem hover. */
	let hoverHour = $state<number | null>(null);

	/** Hora cheia correspondente ao Y do mouse, clampada na faixa visivel. */
	function hourAt(e: MouseEvent): number {
		const target = e.currentTarget as HTMLElement;
		const relY = e.clientY - target.getBoundingClientRect().top;
		return Math.min(Math.max(Math.floor(relY / pxPerHour) + startHour, startHour), endHour - 1);
	}

	function handleColumnClick(e: MouseEvent) {
		if (!onCreateAt) return;
		// Snap na HORA CHEIA: o usuario refina o horario exato ao abrir o modal.
		const hour = hourAt(e);
		const d = new Date(day.getFullYear(), day.getMonth(), day.getDate(), hour, 0);
		onCreateAt(d);
	}

	function handleColumnMouseMove(e: MouseEvent) {
		if (!onCreateAt) return;
		// Sobre um evento existente o clique seleciona (nao cria): sem previa.
		if ((e.target as HTMLElement).closest('button')) {
			hoverHour = null;
			return;
		}
		hoverHour = hourAt(e);
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
	onmousemove={handleColumnMouseMove}
	onmouseleave={() => (hoverHour = null)}
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
			class="pointer-events-none absolute inset-0 bg-primary-500/10 dark:bg-primary-500/20"
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

	<!-- Previa do clique: realca a faixa da hora cheia sob o cursor (paridade
	     com o hover das celulas do mes). Fica atras dos eventos e nao captura
	     o ponteiro, para nao interferir no clique/selecao. -->
	{#if hoverHour !== null}
		<div
			class="pointer-events-none absolute inset-x-0 z-0 bg-primary-500/10 ring-1 ring-inset ring-primary-500/30"
			style="top: {(hoverHour - startHour) * pxPerHour}px; height: {pxPerHour}px;"
			aria-hidden="true"
		></div>
	{/if}

	{#each positioned as p (p.ev.id)}
		{@const colors = eventColorClasses(p.ev)}
		<button
			type="button"
			class="absolute overflow-hidden rounded px-1.5 py-0.5 text-left transition-opacity hover:opacity-90 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand {colors.block}"
			style="top: {p.topPx}px; height: {p.heightPx}px; left: {p.leftPct}%; width: {p.widthPct}%;"
			onclick={(e) => handleEventClick(e, p.ev)}
			onkeydown={(e) => handleEventKeydown(e, p.ev)}
			aria-label="{p.ev.title} — {fmtTime(p.ev.starts_at)} até {fmtTime(p.ev.ends_at)}"
		>
			<span class="block truncate text-2xs font-semibold leading-tight">
				{p.ev.title}
			</span>
			{#if p.heightPx >= 32}
				<span class="block truncate text-2xs opacity-75">
					{fmtTime(p.ev.starts_at)} – {fmtTime(p.ev.ends_at)}
				</span>
			{/if}
		</button>
	{/each}
</div>
