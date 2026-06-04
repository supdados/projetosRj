<script lang="ts">
	import type { CalendarEvent } from '$lib/types/calendar';
	import { isoDayKey, addDays, parseLocal } from '$lib/components/calendar/weekDates';
	import { eventColorClasses } from '$lib/components/calendar/eventVisual';

	interface Props {
		events: CalendarEvent[];
		weekStart: Date;
		onSelectEvent?: (ev: CalendarEvent) => void;
	}

	let { events, weekStart, onSelectEvent }: Props = $props();

	const PT_DAYS_SHORT = ['Dom', 'Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb'];
	const PT_MONTHS_SHORT = [
		'jan', 'fev', 'mar', 'abr', 'mai', 'jun',
		'jul', 'ago', 'set', 'out', 'nov', 'dez',
	];

	// Chaves ISO dos 7 dias da semana
	const weekDayKeys = $derived(
		Array.from({ length: 7 }, (_, i) => isoDayKey(addDays(weekStart, i)))
	);

	// Eventos filtrados e ordenados pela data de inicio
	const weekEvents = $derived(
		events
			.filter((ev) => weekDayKeys.includes(isoDayKey(parseLocal(ev.starts_at))))
			.sort((a, b) => parseLocal(a.starts_at).getTime() - parseLocal(b.starts_at).getTime())
	);

	function formatEventDate(ev: CalendarEvent): string {
		const d = parseLocal(ev.starts_at);
		const dayName = PT_DAYS_SHORT[d.getDay()];
		const dayNum = d.getDate();
		const monthName = PT_MONTHS_SHORT[d.getMonth()];

		if (ev.is_all_day) {
			return `${dayName} ${dayNum} ${monthName} · dia inteiro`;
		}

		const hh = String(d.getHours()).padStart(2, '0');
		const mm = String(d.getMinutes()).padStart(2, '0');
		return `${dayName} ${dayNum} ${monthName} · ${hh}:${mm}`;
	}
</script>

<div>
	<h3 class="mb-3 text-xs font-semibold uppercase tracking-wide text-text-muted">
		Esta semana
	</h3>

	{#if weekEvents.length === 0}
		<p class="text-xs text-text-muted">Sem eventos esta semana.</p>
	{:else}
		<!-- max-height interno ao card — nao usa altura de viewport -->
		<ul class="max-h-60 overflow-y-auto pr-0.5 [scrollbar-width:thin]" role="list">
			{#each weekEvents as ev (ev.id)}
				{@const colors = eventColorClasses(ev)}
				<li>
					<button
						type="button"
						onclick={() => onSelectEvent?.(ev)}
						class="group flex w-full items-start gap-2.5 rounded px-1 py-1.5 text-left transition-colors hover:bg-surface-muted"
					>
						<!-- Bolinha de cor por status de sync — SEM barra lateral -->
						<span
							class="mt-1 h-2 w-2 shrink-0 rounded-full {colors.dot}"
							aria-hidden="true"
						></span>

						<div class="min-w-0 flex-1">
							<p class="truncate text-xs font-medium text-text-primary group-hover:text-text-primary">
								{ev.title}
							</p>
							<p class="mt-0.5 text-[11px] text-text-muted">
								{formatEventDate(ev)}
							</p>
						</div>
					</button>
				</li>
			{/each}
		</ul>
	{/if}
</div>
