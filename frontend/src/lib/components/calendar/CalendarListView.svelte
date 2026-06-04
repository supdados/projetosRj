<script lang="ts">
	import type { CalendarEvent } from '$lib/types/calendar';
	import { isoDayKey, parseLocal, isToday } from '$lib/components/calendar/weekDates';
	import { eventColorClasses } from '$lib/components/calendar/eventVisual';

	interface Props {
		events: CalendarEvent[];
		onSelectEvent?: (ev: CalendarEvent) => void;
	}

	let { events, onSelectEvent }: Props = $props();

	const PT_WEEKDAYS = [
		'Domingo', 'Segunda-feira', 'Terça-feira', 'Quarta-feira',
		'Quinta-feira', 'Sexta-feira', 'Sábado',
	];
	const PT_MONTHS = [
		'janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho',
		'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro',
	];

	interface DayGroup {
		key: string;
		label: string;
		isToday: boolean;
		events: CalendarEvent[];
	}

	const dayGroups = $derived.by<DayGroup[]>(() => {
		const sorted = [...events].sort((a, b) => a.starts_at.localeCompare(b.starts_at));

		const map = new Map<string, CalendarEvent[]>();
		for (const ev of sorted) {
			const key = isoDayKey(parseLocal(ev.starts_at));
			const bucket = map.get(key);
			if (bucket) bucket.push(ev);
			else map.set(key, [ev]);
		}

		const out: DayGroup[] = [];
		for (const [key, evs] of map) {
			const [y, m, d] = key.split('-').map(Number);
			const dateObj = new Date(y, m - 1, d);
			const wday = PT_WEEKDAYS[dateObj.getDay()];
			const label = `${wday}, ${d} de ${PT_MONTHS[m - 1]}`;
			out.push({ key, label, isToday: isToday(dateObj), events: evs });
		}
		return out;
	});

	function timeLabel(ev: CalendarEvent): string {
		if (ev.is_all_day) return 'Dia inteiro';

		const fmt = (s: string) => {
			const d = parseLocal(s);
			const hh = String(d.getHours()).padStart(2, '0');
			const mm = String(d.getMinutes()).padStart(2, '0');
			return `${hh}:${mm}`;
		};

		const start = fmt(ev.starts_at);
		const end = fmt(ev.ends_at);
		// Só mostrar o fim se for diferente do início (eventos com duração > 0)
		return start === end ? start : `${start} – ${end}`;
	}
</script>

<div class="flex flex-col gap-4">
	{#if dayGroups.length === 0}
		<div
			class="flex flex-col items-center justify-center gap-3 rounded-xl border border-border-subtle bg-surface px-6 py-14 text-center"
		>
			<span class="text-3xl" aria-hidden="true">📅</span>
			<p class="text-sm font-medium text-text-primary">Nenhum evento encontrado</p>
			<p class="text-xs text-text-muted">
				Crie um novo evento para começar a organizar sua agenda.
			</p>
		</div>
	{:else}
		{#each dayGroups as group (group.key)}
			<div class="flex flex-col gap-1">
				<!-- Cabeçalho do dia -->
				<div class="flex items-center gap-2 px-1 pb-1">
					{#if group.isToday}
						<span
							class="flex h-5 items-center rounded-full bg-primary-500 px-2 text-[11px] font-semibold text-white"
						>
							Hoje
						</span>
					{/if}
					<span
						class="text-xs font-semibold {group.isToday
							? 'text-primary-600 dark:text-primary-400'
							: 'text-text-secondary'} uppercase tracking-wide"
					>
						{group.label}
					</span>
				</div>

				<!-- Cartão contendo os eventos do dia -->
				<div class="rounded-lg border border-border-subtle bg-surface">
					{#each group.events as ev, i (ev.id)}
						{@const colors = eventColorClasses(ev)}
						{@const time = timeLabel(ev)}
						<button
							type="button"
							onclick={() => onSelectEvent?.(ev)}
							class="group flex w-full items-start gap-3 px-4 py-3 text-left transition-colors hover:bg-surface-muted
								{i > 0 ? 'border-t border-border-subtle' : ''}"
						>
							<!-- Bolinha de cor (status de sync / origem) — SEM barra lateral colorida -->
							<span
								class="mt-[3px] h-2.5 w-2.5 shrink-0 rounded-full {colors.dot}"
								aria-hidden="true"
							></span>

							<!-- Horário -->
							<span
								class="w-24 shrink-0 text-xs tabular-nums text-text-muted"
								aria-label={time}
							>
								{time}
							</span>

							<!-- Corpo: título + metadados -->
							<div class="min-w-0 flex-1">
								<p
									class="truncate text-sm font-medium text-text-primary group-hover:text-text-primary"
								>
									{ev.title}
								</p>

								{#if ev.location || ev.meet_link || ev.source === 'google' || ev.sync_status !== 'ok'}
									<div class="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1">
										{#if ev.location}
											<span class="truncate text-xs text-text-muted">
												{ev.location}
											</span>
										{/if}

										{#if ev.meet_link}
											<!-- stopPropagation: clicar no link não dispara onSelectEvent -->
											<a
												href={ev.meet_link}
												target="_blank"
												rel="noopener noreferrer"
												onclick={(e) => e.stopPropagation()}
												class="inline-flex items-center gap-1 text-xs text-primary-600 hover:text-primary-700 dark:text-primary-400 dark:hover:text-primary-300"
											>
												<svg
													width="10"
													height="10"
													viewBox="0 0 24 24"
													fill="none"
													stroke="currentColor"
													stroke-width="2.2"
													stroke-linecap="round"
													stroke-linejoin="round"
													aria-hidden="true"
												>
													<path
														d="M15 10l4.553-2.069A1 1 0 0 1 21 8.82v6.36a1 1 0 0 1-1.447.889L15 14"
													/>
													<rect x="3" y="6" width="12" height="12" rx="2" />
												</svg>
												Meet
											</a>
										{/if}

										{#if ev.sync_status === 'error'}
											<span
												class="rounded-full bg-red-500/15 px-2 py-0.5 text-[10px] font-medium text-red-600 dark:text-red-400"
											>
												Erro de sync
											</span>
										{:else if ev.sync_status === 'pending'}
											<span
												class="rounded-full bg-surface-muted px-2 py-0.5 text-[10px] font-medium text-text-muted"
											>
												Pendente
											</span>
										{:else if ev.source === 'google'}
											<span
												class="rounded-full bg-emerald-500/15 px-2 py-0.5 text-[10px] font-medium text-emerald-700 dark:text-emerald-400"
											>
												Google
											</span>
										{/if}
									</div>
								{/if}
							</div>
						</button>
					{/each}
				</div>
			</div>
		{/each}
	{/if}
</div>
