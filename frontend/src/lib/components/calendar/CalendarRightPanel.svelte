<script lang="ts">
	import type { CalendarEvent, CalendarMember } from '$lib/types/calendar';
	import MiniMonth from '$lib/components/calendar/MiniMonth.svelte';
	import WeekEventList from '$lib/components/calendar/WeekEventList.svelte';
	import TeamMembersList from '$lib/components/calendar/TeamMembersList.svelte';

	interface Props {
		/** Modo de destaque do mini-mes: 'week' (faixa) ou 'day' (so o dia). */
		mode?: 'week' | 'day';
		weekStart: Date;
		/** Dia focado (usado no mini-mes em mode='day'). */
		selectedDay?: Date;
		month: Date;
		events: CalendarEvent[];
		members: CalendarMember[];
		onSelectEvent?: (ev: CalendarEvent) => void;
		onSelectDay?: (date: Date) => void;
		onPrevMonth?: () => void;
		onNextMonth?: () => void;
	}

	let {
		mode = 'week',
		weekStart,
		selectedDay,
		month,
		events,
		members,
		onSelectEvent,
		onSelectDay,
		onPrevMonth,
		onNextMonth,
	}: Props = $props();
</script>

<aside class="flex w-full flex-col gap-4 lg:w-80 lg:shrink-0">
	<!-- Mini calendario mensal -->
	<div class="rounded-xl border border-border-subtle bg-surface p-4 shadow-sm">
		<MiniMonth
			{mode}
			{weekStart}
			{selectedDay}
			{month}
			{events}
			{onPrevMonth}
			{onNextMonth}
			{onSelectDay}
		/>
	</div>

	<!-- Lista de eventos da semana -->
	<div class="rounded-xl border border-border-subtle bg-surface p-4 shadow-sm">
		<WeekEventList {events} {weekStart} {onSelectEvent} />
	</div>

	<!-- Lista de membros da equipe (Agente D) -->
	<div class="rounded-xl border border-border-subtle bg-surface p-4 shadow-sm">
		<TeamMembersList {members} />
	</div>
</aside>
