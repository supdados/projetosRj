<script lang="ts">
	/**
	 * Modal de criacao/edicao de evento do calendario (paridade v4.5:
	 * templates/partials/calendar_event_modal.html + calendar-event-modal.js +
	 * cal-datetime-picker.js). CONTROLADO por callbacks.
	 *
	 * O componente NAO chama API: recebe `event` (null = criar) e emite
	 * `onSave(input)` / `onDelete(id)` / `onGenerateMeet(id)`. A pagina chama os
	 * endpoints /api e RE-BUSCA o hub. Salvar e EXPLICITO (sem autosave).
	 *
	 * Reproduz as micro-interacoes do original:
	 *   - Layout estilo Google: titulo com borda inferior; linhas com icone.
	 *   - Toggle "Dia inteiro" troca entre par data+hora e par so-data.
	 *   - DATE/TIME PICKERS proprios (cal-datetime-picker): calendario popover em
	 *     PT (semana iniciando na segunda, "Hoje", min-date desabilitada) e lista
	 *     de horarios de 30 em 30 min com scroll ate o selecionado. Inputs aceitam
	 *     digitacao livre (DD/MM/AAAA, HH:MM) com mascara.
	 *   - Sincronizacao inicio->fim: ao mover o inicio, o fim acompanha mantendo a
	 *     duracao; o fim nunca fica antes do inicio.
	 *   - Bloco Google Meet: toggle (criar) ou bloco "existente" com link, copiar
	 *     e "Gerar novo link" / cancelar (regen). Toast "Link copiado!".
	 *
	 * Acessibilidade: dialogo modal (`role="dialog"`, `aria-modal`, `tabindex=-1`),
	 * titulo rotulando o dialogo, Escape fecha, fundo clicavel fecha, foco preso
	 * via `use:focusTrap`. Os pickers tem fallback de digitacao (input de texto).
	 */
	import type { CalendarEvent, CalendarEventInput } from '$lib/types/calendar';
	import { focusTrap } from '$lib/actions/focusTrap';
	import { tick } from 'svelte';

	interface Props {
		open: boolean;
		event: CalendarEvent | null;
		/** Data base (YYYY-MM-DD) ao criar a partir de um dia da grade. */
		createDate?: string;
		/** Datetime-local "YYYY-MM-DDTHH:MM" do clique no time-grid — prefill preciso ao criar. */
		createStart?: string;
		/** Ha conexao Google? Habilita o toggle/gerar Meet. */
		hasGoogle?: boolean;
		busy?: boolean;
		error?: string | null;
		onSave: (input: CalendarEventInput) => void;
		onDelete?: (id: number) => void;
		onGenerateMeet?: (id: number) => void;
		onClose: () => void;
	}

	let {
		open,
		event,
		createDate = '',
		createStart = '',
		hasGoogle = false,
		busy = false,
		error = null,
		onSave,
		onDelete,
		onGenerateMeet,
		onClose
	}: Props = $props();

	const MONTHS_PT = [
		'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
		'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'
	];
	const WEEKDAYS_PT = ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom'];

	function pad(n: number): string {
		return String(n).padStart(2, '0');
	}
	function todayStr(): string {
		const d = new Date();
		return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
	}
	function formatDateBR(iso: string): string {
		if (!iso || iso.length !== 10) return iso || '';
		const p = iso.split('-');
		return `${p[2]}/${p[1]}/${p[0]}`;
	}
	function parseDateBR(display: string): string {
		const raw = (display || '').trim();
		if (!raw) return '';
		const m = raw.match(/^(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})$/);
		if (!m) return '';
		const day = parseInt(m[1], 10);
		const mon = parseInt(m[2], 10);
		const year = parseInt(m[3], 10);
		if (mon < 1 || mon > 12 || day < 1 || day > 31 || year < 1900) return '';
		return `${year}-${pad(mon)}-${pad(day)}`;
	}

	// Estado do formulario. Datas e horas separadas (ISO interno).
	let title = $state('');
	let description = $state('');
	let location = $state('');
	let allDay = $state(false);
	// Par com hora.
	let startDate = $state('');
	let startTime = $state('');
	let endDate = $state('');
	let endTime = $state('');
	// Par dia-inteiro (so data).
	let allDayStartDate = $state('');
	let allDayEndDate = $state('');

	let createConference = $state(false);
	let clientError = $state<string | null>(null);

	// Meet (modo editar).
	let regenMeet = $state(false);
	let copied = $state(false);

	const isEdit = $derived(event !== null);
	const meetLink = $derived(event?.meet_link ?? '');
	const showSyncWarning = $derived(event?.sync_status === 'error' && !!event?.sync_error);
	const canGenerateMeet = $derived(isEdit && !meetLink && typeof onGenerateMeet === 'function');

	function composeIso(d: string, t: string): string {
		if (!d || !t) return '';
		return `${d}T${t}`;
	}
	function parseDt(d: string, t: string): Date | null {
		const c = composeIso(d, t);
		if (!c) return null;
		const parsed = new Date(c);
		return Number.isNaN(parsed.getTime()) ? null : parsed;
	}
	function toLocalParts(date: Date): { date: string; time: string } {
		return {
			date: `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`,
			time: `${pad(date.getHours())}:${pad(date.getMinutes())}`
		};
	}

	// Ao abrir, preenche a partir do evento (ou reseta para criar).
	$effect(() => {
		if (!open) {
			closeDatePicker();
			closeTimePicker();
			return;
		}
		title = event?.title ?? '';
		description = event?.description ?? '';
		location = event?.location ?? '';
		allDay = event?.is_all_day ?? false;
		createConference = false;
		clientError = null;
		regenMeet = false;
		copied = false;

		if (event) {
			if (event.is_all_day) {
				const sd = (event.starts_at || '').slice(0, 10);
				const ed = (event.ends_at || '').slice(0, 10);
				allDayStartDate = sd;
				allDayEndDate = ed || sd;
				startDate = sd;
				startTime = '09:00';
				endDate = ed || sd;
				endTime = '10:00';
			} else {
				const sv = (event.starts_at || '').slice(0, 16);
				const ev = (event.ends_at || '').slice(0, 16);
				startDate = sv.slice(0, 10);
				startTime = sv.slice(11, 16) || '09:00';
				endDate = ev.slice(0, 10);
				endTime = ev.slice(11, 16) || '10:00';
				allDayStartDate = startDate;
				allDayEndDate = endDate;
			}
		} else {
			if (createStart) {
				// Prefill a partir do clique no time-grid; fim = inicio + 1h.
				const parsed = new Date(createStart);
				const startParts = toLocalParts(parsed);
				const endParts = toLocalParts(new Date(parsed.getTime() + 3600000));
				startDate = startParts.date;
				startTime = startParts.time;
				endDate = endParts.date;
				endTime = endParts.time;
				allDayStartDate = startParts.date;
				allDayEndDate = endParts.date;
			} else {
				const base = createDate || todayStr();
				startDate = base;
				startTime = '09:00';
				endDate = base;
				endTime = '10:00';
				allDayStartDate = base;
				allDayEndDate = base;
			}
		}
	});

	// Sincroniza fim->inicio mantendo duracao (par com hora).
	function onStartChanged(): void {
		const newStart = parseDt(startDate, startTime);
		if (!newStart) return;
		const curEnd = parseDt(endDate, endTime);
		if (!curEnd) {
			const np = toLocalParts(new Date(newStart.getTime() + 3600000));
			endDate = np.date;
			endTime = np.time;
		} else if (curEnd <= newStart) {
			const np = toLocalParts(new Date(newStart.getTime() + 3600000));
			endDate = np.date;
			endTime = np.time;
		}
	}
	function onEndChanged(): void {
		const s = parseDt(startDate, startTime);
		const e = parseDt(endDate, endTime);
		if (s && e && e <= s) {
			const np = toLocalParts(new Date(s.getTime() + 3600000));
			endDate = np.date;
			endTime = np.time;
		}
	}
	function onAllDayStartChanged(): void {
		if (allDayEndDate && allDayEndDate < allDayStartDate) {
			allDayEndDate = allDayStartDate;
		}
	}
	function onAllDayEndChanged(): void {
		if (allDayEndDate && allDayStartDate && allDayEndDate < allDayStartDate) {
			allDayEndDate = allDayStartDate;
		}
	}

	function validate(): string | null {
		if (title.trim() === '') return 'Informe um título para o evento.';
		if (allDay) {
			if (!allDayStartDate) return 'Informe a data de início.';
			if ((allDayEndDate || allDayStartDate) < allDayStartDate) {
				return 'A data de fim não pode ser anterior à de início.';
			}
			return null;
		}
		const s = composeIso(startDate, startTime);
		const e = composeIso(endDate, endTime);
		if (!s || !e) return 'Informe data e hora de início e fim.';
		if (new Date(e) <= new Date(s)) {
			return 'O horário de fim deve ser posterior ao de início.';
		}
		return null;
	}

	function save(): void {
		if (busy) return;
		const problem = validate();
		if (problem) {
			clientError = problem;
			return;
		}
		clientError = null;
		const starts_at = allDay
			? `${allDayStartDate}T00:00`
			: composeIso(startDate, startTime);
		const ends_at = allDay
			? `${allDayEndDate || allDayStartDate}T23:59`
			: composeIso(endDate, endTime);
		onSave({
			title: title.trim(),
			description,
			location,
			starts_at,
			ends_at,
			is_all_day: allDay,
			// Criar com Meet OU gerar novo link (regen) ao editar.
			create_conference: (!isEdit && createConference) || (isEdit && regenMeet)
		});
	}

	function remove(): void {
		if (busy || !event || !onDelete) return;
		if (!confirm('Excluir este evento? Esta ação não pode ser desfeita.')) return;
		onDelete(event.id);
	}
	function generateMeet(): void {
		if (busy || !event || !onGenerateMeet) return;
		onGenerateMeet(event.id);
	}

	async function copyMeet(): Promise<void> {
		try {
			await navigator.clipboard.writeText(meetLink);
		} catch {
			const ta = document.createElement('textarea');
			ta.value = meetLink;
			ta.style.cssText = 'position:fixed;opacity:0;';
			document.body.appendChild(ta);
			ta.select();
			document.execCommand('copy');
			ta.remove();
		}
		copied = true;
		setTimeout(() => (copied = false), 1700);
	}

	const meetUrlDisplay = $derived.by(() => {
		if (!meetLink) return '';
		try {
			const u = new URL(meetLink);
			return u.host + u.pathname;
		} catch {
			return meetLink;
		}
	});

	function onKeydown(keyEvent: KeyboardEvent): void {
		if (keyEvent.key === 'Escape') {
			keyEvent.preventDefault();
			if (datePicker || timePicker) {
				closeDatePicker();
				closeTimePicker();
				return;
			}
			onClose();
		}
	}

	/* ── Date picker ──────────────────────────────────────────────────── */
	type DateField = 'start' | 'end' | 'allDayStart' | 'allDayEnd';
	let datePicker = $state<{ field: DateField; x: number; y: number; year: number; month: number } | null>(null);
	let timePicker = $state<{ field: 'start' | 'end'; x: number; y: number } | null>(null);

	function dateValueOf(field: DateField): string {
		if (field === 'start') return startDate;
		if (field === 'end') return endDate;
		if (field === 'allDayStart') return allDayStartDate;
		return allDayEndDate;
	}
	function dateMinOf(field: DateField): string {
		if (field === 'end') return startDate;
		if (field === 'allDayEnd') return allDayStartDate;
		return '';
	}
	function setDateValue(field: DateField, iso: string): void {
		if (field === 'start') {
			startDate = iso;
			onStartChanged();
		} else if (field === 'end') {
			endDate = iso;
			onEndChanged();
		} else if (field === 'allDayStart') {
			allDayStartDate = iso;
			onAllDayStartChanged();
		} else {
			allDayEndDate = iso;
			onAllDayEndChanged();
		}
	}

	async function openDatePicker(field: DateField, e: MouseEvent): Promise<void> {
		closeTimePicker();
		if (datePicker?.field === field) {
			closeDatePicker();
			return;
		}
		const val = dateValueOf(field) || todayStr();
		const [y, m] = val.split('-').map(Number);
		datePicker = { field, x: 0, y: 0, year: y, month: m - 1 };
		await tick();
		positionPicker('.cdp-calendar', e.currentTarget as HTMLElement, 'date');
	}
	function closeDatePicker(): void {
		datePicker = null;
	}
	function pickerPrevMonth(): void {
		if (!datePicker) return;
		let { year, month } = datePicker;
		if (--month < 0) { month = 11; year--; }
		datePicker = { ...datePicker, year, month };
	}
	function pickerNextMonth(): void {
		if (!datePicker) return;
		let { year, month } = datePicker;
		if (++month > 11) { month = 0; year++; }
		datePicker = { ...datePicker, year, month };
	}
	function selectDate(iso: string): void {
		if (!datePicker) return;
		setDateValue(datePicker.field, iso);
		closeDatePicker();
	}

	interface PickerDay {
		day: number;
		dateStr: string;
		outside: boolean;
	}
	const pickerCells = $derived.by<PickerDay[]>(() => {
		if (!datePicker) return [];
		const { year, month } = datePicker;
		const firstDay = new Date(year, month, 1).getDay();
		const startOffset = (firstDay + 6) % 7;
		const daysInMonth = new Date(year, month + 1, 0).getDate();
		const daysInPrev = new Date(year, month, 0).getDate();
		const cells: PickerDay[] = [];
		for (let p = startOffset - 1; p >= 0; p--) {
			const d = daysInPrev - p;
			let pm = month - 1;
			let py = year;
			if (pm < 0) { pm = 11; py--; }
			cells.push({ day: d, dateStr: `${py}-${pad(pm + 1)}-${pad(d)}`, outside: true });
		}
		for (let d = 1; d <= daysInMonth; d++) {
			cells.push({ day: d, dateStr: `${year}-${pad(month + 1)}-${pad(d)}`, outside: false });
		}
		const remaining = 7 - (cells.length % 7);
		if (remaining < 7) {
			for (let n = 1; n <= remaining; n++) {
				let nm = month + 1;
				let ny = year;
				if (nm > 11) { nm = 0; ny++; }
				cells.push({ day: n, dateStr: `${ny}-${pad(nm + 1)}-${pad(n)}`, outside: true });
			}
		}
		return cells;
	});
	const pickerMonthLabel = $derived(
		datePicker ? `${MONTHS_PT[datePicker.month]} ${datePicker.year}` : ''
	);

	/* ── Time picker ─────────────────────────────────────────────────── */
	const TIME_SLOTS: string[] = (() => {
		const slots: string[] = [];
		for (let h = 0; h < 24; h++) {
			for (let m = 0; m < 60; m += 30) slots.push(`${pad(h)}:${pad(m)}`);
		}
		return slots;
	})();

	function timeValueOf(field: 'start' | 'end'): string {
		return field === 'start' ? startTime : endTime;
	}
	function timeMinOf(field: 'start' | 'end'): string {
		if (field === 'end' && startDate && endDate && startDate === endDate) return startTime;
		return '';
	}
	function setTimeValue(field: 'start' | 'end', t: string): void {
		if (field === 'start') {
			startTime = t;
			onStartChanged();
		} else {
			endTime = t;
			onEndChanged();
		}
	}
	async function openTimePicker(field: 'start' | 'end', e: MouseEvent): Promise<void> {
		closeDatePicker();
		if (timePicker?.field === field) {
			closeTimePicker();
			return;
		}
		timePicker = { field, x: 0, y: 0 };
		await tick();
		positionPicker('.cdp-timelist', e.currentTarget as HTMLElement, 'time');
		// Scroll ate o selecionado.
		const sel = document.querySelector('.cdp-time-option--selected') as HTMLElement | null;
		sel?.scrollIntoView({ block: 'center' });
	}
	function closeTimePicker(): void {
		timePicker = null;
	}
	function selectTime(t: string): void {
		if (!timePicker) return;
		setTimeValue(timePicker.field, t);
		closeTimePicker();
	}

	function positionPicker(selector: string, anchor: HTMLElement, kind: 'date' | 'time'): void {
		const pop = document.querySelector(selector) as HTMLElement | null;
		if (!pop) return;
		const rect = anchor.getBoundingClientRect();
		const pw = pop.offsetWidth;
		const ph = pop.offsetHeight;
		const vw = window.innerWidth;
		const vh = window.innerHeight;
		let top = rect.bottom + 6;
		let left = rect.left;
		if (left + pw > vw - 12) left = vw - pw - 12;
		if (left < 12) left = 12;
		if (top + ph > vh - 12 && rect.top - ph - 6 >= 12) top = rect.top - ph - 6;
		top = Math.max(12, top);
		if (kind === 'date' && datePicker) {
			datePicker = { ...datePicker, x: left, y: top };
		} else if (kind === 'time' && timePicker) {
			timePicker = { ...timePicker, x: left, y: top };
		}
	}

	// Mascara de digitacao de data (DD/MM/AAAA) -> ISO interno.
	function onDateInput(field: DateField, e: Event): void {
		const el = e.target as HTMLInputElement;
		let raw = el.value.replace(/\D/g, '').slice(0, 8);
		let formatted: string;
		if (raw.length > 4) formatted = `${raw.slice(0, 2)}/${raw.slice(2, 4)}/${raw.slice(4)}`;
		else if (raw.length > 2) formatted = `${raw.slice(0, 2)}/${raw.slice(2)}`;
		else formatted = raw;
		el.value = formatted;
		if (formatted.length === 10) {
			const iso = parseDateBR(formatted);
			if (iso) setDateValue(field, iso);
		}
	}
	function onDateBlur(field: DateField, e: Event): void {
		const el = e.target as HTMLInputElement;
		const iso = parseDateBR(el.value);
		if (iso) setDateValue(field, iso);
		else el.value = formatDateBR(dateValueOf(field));
	}
	function onTimeBlur(field: 'start' | 'end', e: Event): void {
		const el = e.target as HTMLInputElement;
		const raw = el.value.trim();
		const m = raw.match(/^(\d{1,2}):?(\d{2})$/);
		if (m) {
			const h = Math.min(23, Math.max(0, parseInt(m[1], 10)));
			const mi = Math.min(59, Math.max(0, parseInt(m[2], 10)));
			setTimeValue(field, `${pad(h)}:${pad(mi)}`);
		} else {
			el.value = timeValueOf(field);
		}
	}

	// Fecha pickers ao clicar fora (scrim transparente cobre o modal).
	function onPickerScrim(): void {
		closeDatePicker();
		closeTimePicker();
	}
</script>

{#if open}
	<!-- Fundo: clicar fora fecha. Overlay rgba(0,0,0,0.3) + fade do original. -->
	<div
		class="cal-modal-overlay"
		role="presentation"
		onclick={onClose}
		onkeydown={onKeydown}
	>
		<!-- Dialogo: para o clique de borbulhar. Slide/scale-in do original. -->
		<div
			role="dialog"
			aria-modal="true"
			aria-labelledby="calendar-event-title"
			class="cal-modal"
			onclick={(e) => e.stopPropagation()}
			onkeydown={onKeydown}
			tabindex="-1"
			use:focusTrap
		>
			<header class="cal-modal-header">
				<h2 id="calendar-event-title" class="cal-modal-title">
					{isEdit ? 'Editar evento' : 'Novo evento'}
				</h2>
				<button type="button" class="cal-modal-close" aria-label="Fechar" onclick={onClose}>
					<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" aria-hidden="true"><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></svg>
				</button>
			</header>

			<div class="cal-modal-body">
				{#if showSyncWarning}
					<p class="cal-modal-sync-warn" role="status" aria-live="polite">
						Falha de sincronização com o Google: {event?.sync_error}
					</p>
				{/if}

				<!-- Titulo (cal-field-title). -->
				<div class="cal-field-title">
					<label for="event-title" class="sr-only">Título</label>
					<input
						bind:value={title}
						id="event-title"
						type="text"
						placeholder="Título do evento"
						required
						maxlength="200"
						autocomplete="off"
						disabled={busy}
					/>
				</div>

				<!-- Inicio/Fim com icone de calendario (cal-field-row). -->
				<div class="cal-field-row">
					<div class="cal-field-icon">
						<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="18" rx="2" /><line x1="16" y1="2" x2="16" y2="6" /><line x1="8" y1="2" x2="8" y2="6" /><line x1="3" y1="10" x2="21" y2="10" /></svg>
					</div>
					<div class="cal-field-content">
						<label class="cal-allday-row">
							<span class="cal-switch">
								<input bind:checked={allDay} type="checkbox" disabled={busy} />
								<span class="cal-switch-track"></span>
							</span>
							<span class="cal-allday-label">Dia inteiro</span>
						</label>

						{#if !allDay}
							<div class="cal-datetime-pair cal-datetime-pair--timed">
								<div class="cal-datetime-col">
									<span class="cal-datetime-sublabel">Início</span>
									<div class="cal-datetime-inline">
										<input
											class="cal-field-input cdp-trigger"
											class:cdp-active={datePicker?.field === 'start'}
											type="text"
											placeholder="DD/MM/AAAA"
											maxlength="10"
											aria-label="Data de início"
											disabled={busy}
											value={formatDateBR(startDate)}
											oninput={(e) => onDateInput('start', e)}
											onblur={(e) => onDateBlur('start', e)}
											onclick={(e) => openDatePicker('start', e)}
										/>
										<input
											class="cal-field-input cal-field-time cdp-trigger"
											class:cdp-active={timePicker?.field === 'start'}
											type="text"
											placeholder="HH:MM"
											maxlength="5"
											aria-label="Hora de início"
											disabled={busy}
											bind:value={startTime}
											onblur={(e) => onTimeBlur('start', e)}
											onclick={(e) => openTimePicker('start', e)}
										/>
									</div>
								</div>
								<div class="cal-datetime-col">
									<span class="cal-datetime-sublabel">Fim</span>
									<div class="cal-datetime-inline">
										<input
											class="cal-field-input cdp-trigger"
											class:cdp-active={datePicker?.field === 'end'}
											type="text"
											placeholder="DD/MM/AAAA"
											maxlength="10"
											aria-label="Data de fim"
											disabled={busy}
											value={formatDateBR(endDate)}
											oninput={(e) => onDateInput('end', e)}
											onblur={(e) => onDateBlur('end', e)}
											onclick={(e) => openDatePicker('end', e)}
										/>
										<input
											class="cal-field-input cal-field-time cdp-trigger"
											class:cdp-active={timePicker?.field === 'end'}
											type="text"
											placeholder="HH:MM"
											maxlength="5"
											aria-label="Hora de fim"
											disabled={busy}
											bind:value={endTime}
											onblur={(e) => onTimeBlur('end', e)}
											onclick={(e) => openTimePicker('end', e)}
										/>
									</div>
								</div>
							</div>
						{:else}
							<div class="cal-datetime-pair cal-datetime-pair--all-day">
								<div class="cal-datetime-col">
									<span class="cal-datetime-sublabel">Início</span>
									<input
										class="cal-field-input cdp-trigger"
										class:cdp-active={datePicker?.field === 'allDayStart'}
										type="text"
										placeholder="DD/MM/AAAA"
										maxlength="10"
										aria-label="Data de início"
										disabled={busy}
										value={formatDateBR(allDayStartDate)}
										oninput={(e) => onDateInput('allDayStart', e)}
										onblur={(e) => onDateBlur('allDayStart', e)}
										onclick={(e) => openDatePicker('allDayStart', e)}
									/>
								</div>
								<div class="cal-datetime-col">
									<span class="cal-datetime-sublabel">Fim</span>
									<input
										class="cal-field-input cdp-trigger"
										class:cdp-active={datePicker?.field === 'allDayEnd'}
										type="text"
										placeholder="DD/MM/AAAA"
										maxlength="10"
										aria-label="Data de fim"
										disabled={busy}
										value={formatDateBR(allDayEndDate)}
										oninput={(e) => onDateInput('allDayEnd', e)}
										onblur={(e) => onDateBlur('allDayEnd', e)}
										onclick={(e) => openDatePicker('allDayEnd', e)}
									/>
								</div>
							</div>
						{/if}
					</div>
				</div>

				<!-- Google Meet — toggle (criar) ou bloco existente (editar). -->
				{#if hasGoogle && !isEdit}
					<div class="cal-field-row">
						<div class="cal-field-icon">
							<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M23 7l-7 5 7 5V7z" /><rect x="1" y="5" width="15" height="14" rx="2" /></svg>
						</div>
						<div class="cal-field-content">
							<label class="cal-meet-row" class:is-active={createConference}>
								<span class="cal-meet-icon-wrap">
									<svg width="14" height="14" viewBox="0 0 24 24" fill="white" aria-hidden="true"><path d="M17 10.5V7a1 1 0 0 0-1-1H4a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-3.5l4 4v-11l-4 4z" /></svg>
								</span>
								<span class="cal-meet-text">
									<span class="cal-meet-label">Google Meet</span>
									<span class="cal-meet-sub">
										{createConference ? 'Link será gerado ao salvar' : 'Adicionar videochamada'}
									</span>
								</span>
								<span class="cal-switch">
									<input bind:checked={createConference} type="checkbox" disabled={busy} />
									<span class="cal-switch-track"></span>
								</span>
							</label>
						</div>
					</div>
				{/if}

				{#if isEdit && meetLink}
					<div class="cal-field-row">
						<div class="cal-field-icon">
							<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M23 7l-7 5 7 5V7z" /><rect x="1" y="5" width="15" height="14" rx="2" /></svg>
						</div>
						<div class="cal-field-content">
							<div class="cal-meet-existing" class:is-regen={regenMeet}>
								<div class="cal-meet-info-row">
									<a class="cal-meet-existing-info" href={meetLink} target="_blank" rel="noopener noreferrer">
										<span class="cal-meet-icon-wrap">
											<svg width="14" height="14" viewBox="0 0 24 24" fill="white" aria-hidden="true"><path d="M17 10.5V7a1 1 0 0 0-1-1H4a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-3.5l4 4v-11l-4 4z" /></svg>
										</span>
										<span class="cal-meet-existing-text">
											<span class="cal-meet-label">Google Meet</span>
											<span class="cal-meet-url">{meetUrlDisplay}</span>
										</span>
									</a>
									<button type="button" class="cal-meet-copy-btn" title="Copiar link" aria-label="Copiar link" onclick={copyMeet}>
										<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="9" y="9" width="13" height="13" rx="2" /><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" /></svg>
									</button>
								</div>
								<div class="cal-meet-existing-actions">
									<button type="button" class="cal-meet-action-btn" disabled={busy} onclick={() => (regenMeet = true)}>
										Gerar novo link
									</button>
								</div>
								<div class="cal-meet-regen-msg">
									<span>Novo link será gerado ao salvar.</span>
									<button type="button" class="cal-meet-action-btn cal-meet-action-btn--subtle" onclick={() => (regenMeet = false)}>
										Cancelar
									</button>
								</div>
							</div>
						</div>
					</div>
				{/if}

				<!-- Local (cal-field-row). -->
				<div class="cal-field-row">
					<div class="cal-field-icon">
						<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" /><circle cx="12" cy="10" r="3" /></svg>
					</div>
					<div class="cal-field-content">
						<label for="event-location" class="sr-only">Local</label>
						<input
							bind:value={location}
							id="event-location"
							type="text"
							placeholder="Adicionar local"
							class="cal-field-input"
							maxlength="255"
							autocomplete="off"
							disabled={busy}
						/>
					</div>
				</div>

				<!-- Descricao (cal-field-row). -->
				<div class="cal-field-row">
					<div class="cal-field-icon">
						<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="17" y1="10" x2="3" y2="10" /><line x1="21" y1="6" x2="3" y2="6" /><line x1="21" y1="14" x2="3" y2="14" /><line x1="17" y1="18" x2="3" y2="18" /></svg>
					</div>
					<div class="cal-field-content">
						<label for="event-description" class="sr-only">Descrição</label>
						<textarea
							bind:value={description}
							id="event-description"
							rows="3"
							placeholder="Adicionar descrição"
							class="cal-field-textarea"
							disabled={busy}
						></textarea>
					</div>
				</div>

				{#if clientError}
					<p role="alert" class="cal-modal-error">{clientError}</p>
				{:else if error}
					<p role="alert" class="cal-modal-error">{error}</p>
				{/if}
			</div>

			<footer class="cal-modal-footer">
				<div>
					{#if isEdit && onDelete}
						<button type="button" class="cal-btn-delete" disabled={busy} onclick={remove}>
							<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="3 6 5 6 21 6" /><path d="M19 6l-1 14H6L5 6" /><path d="M10 11v6m4-6v6" /><path d="M9 6V4h6v2" /></svg>
							Excluir
						</button>
					{/if}
				</div>
				<div class="cal-modal-footer-right">
					{#if canGenerateMeet}
						<button type="button" class="cal-btn-cancel" disabled={busy} onclick={generateMeet}>
							Gerar Meet
						</button>
					{/if}
					<button type="button" class="cal-btn-cancel" disabled={busy} onclick={onClose}>Cancelar</button>
					<button type="button" class="cal-btn-save" disabled={busy} onclick={save}>
						{busy ? 'Salvando…' : 'Salvar'}
					</button>
				</div>
			</footer>

			<!-- Toast "Link copiado!" (cal-meet-toast). -->
			{#if copied}
				<div class="cal-meet-toast" role="status" aria-live="polite">Link copiado!</div>
			{/if}
		</div>
	</div>

	<!-- Scrim para fechar pickers ao clicar fora deles. -->
	{#if datePicker || timePicker}
		<button type="button" class="cdp-scrim" aria-label="Fechar seletor" onclick={onPickerScrim}></button>
	{/if}

	<!-- Date picker popover (cdp-calendar). -->
	{#if datePicker}
		{@const min = dateMinOf(datePicker.field)}
		{@const sel = dateValueOf(datePicker.field)}
		{@const tdy = todayStr()}
		<div
			class="cdp-popover cdp-calendar is-open"
			style="left: {datePicker.x}px; top: {datePicker.y}px;"
			role="dialog"
			aria-label="Selecionar data"
		>
			<div class="cdp-calendar-header">
				<button type="button" class="cdp-nav-btn" aria-label="Mês anterior" onclick={pickerPrevMonth}>
					<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6" /></svg>
				</button>
				<span class="cdp-month-label">{pickerMonthLabel}</span>
				<button type="button" class="cdp-nav-btn" aria-label="Próximo mês" onclick={pickerNextMonth}>
					<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 6 15 12 9 18" /></svg>
				</button>
			</div>
			<div class="cdp-weekdays">
				{#each WEEKDAYS_PT as wd (wd)}<span>{wd}</span>{/each}
			</div>
			<div class="cdp-days">
				{#each pickerCells as c (c.dateStr)}
					{@const disabled = !!min && c.dateStr < min}
					<button
						type="button"
						class="cdp-day"
						class:cdp-day--outside={c.outside}
						class:cdp-day--today={c.dateStr === tdy}
						class:cdp-day--selected={c.dateStr === sel}
						class:cdp-day--disabled={disabled}
						{disabled}
						onclick={() => selectDate(c.dateStr)}
					>
						{c.day}
					</button>
				{/each}
			</div>
			<div class="cdp-calendar-footer">
				<button type="button" class="cdp-today-btn" onclick={() => selectDate(todayStr())}>Hoje</button>
			</div>
		</div>
	{/if}

	<!-- Time picker popover (cdp-timelist). -->
	{#if timePicker}
		{@const min = timeMinOf(timePicker.field)}
		{@const sel = timeValueOf(timePicker.field)}
		<div
			class="cdp-popover cdp-timelist is-open"
			style="left: {timePicker.x}px; top: {timePicker.y}px;"
			role="dialog"
			aria-label="Selecionar hora"
		>
			<div class="cdp-timelist-scroll">
				{#each TIME_SLOTS as slot (slot)}
					{@const disabled = !!min && slot < min}
					<button
						type="button"
						class="cdp-time-option"
						class:cdp-time-option--selected={slot === sel}
						class:cdp-time-option--disabled={disabled}
						{disabled}
						onclick={() => selectTime(slot)}
					>
						{slot}
					</button>
				{/each}
			</div>
		</div>
	{/if}
{/if}

<style>
	/* ════════════════════════════════════════════════════════════════════
	   Modal de evento — portado 1:1 de calendar-event-modal.css + cal-datetime-
	   picker.css (v4.5), com os tokens --app-color-* mapeados para os tokens
	   semanticos da SPA (--color-*, --ds-color-*) para o dark trocar sozinho.
	   ════════════════════════════════════════════════════════════════════ */
	.cal-modal-overlay {
		position: fixed;
		inset: 0;
		background: rgba(0, 0, 0, 0.3);
		display: flex;
		align-items: center;
		justify-content: center;
		z-index: 1050;
		padding: 1rem;
		animation: cal-overlay-in 0.16s ease both;
	}
	.cal-modal {
		background: var(--color-surface);
		border-radius: 0.85rem;
		width: 100%;
		max-width: 31rem;
		box-shadow: 0 24px 64px rgba(0, 0, 0, 0.16), 0 4px 16px rgba(0, 0, 0, 0.08);
		display: flex;
		flex-direction: column;
		max-height: calc(100vh - 2rem);
		overflow: hidden;
		position: relative;
		animation: cal-modal-in 0.16s ease both;
	}
	@keyframes cal-overlay-in {
		from { opacity: 0; }
		to { opacity: 1; }
	}
	@keyframes cal-modal-in {
		from { transform: translateY(10px) scale(0.99); }
		to { transform: translateY(0) scale(1); }
	}

	.cal-modal-header {
		display: flex;
		align-items: center;
		padding: 1rem 1.1rem 0.75rem;
		border-bottom: 1px solid var(--color-border);
	}
	.cal-modal-title {
		flex: 1;
		font-size: 0.95rem;
		font-weight: 600;
		color: var(--color-text-primary);
		margin: 0;
	}
	.cal-modal-close {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 1.7rem;
		height: 1.7rem;
		border-radius: 50%;
		border: none;
		background: none;
		color: var(--color-text-muted);
		cursor: pointer;
		transition: background 0.12s;
	}
	.cal-modal-close:hover {
		background: var(--color-surface-muted);
	}

	.cal-modal-body {
		padding: 1rem 1.1rem;
		overflow-y: auto;
		display: flex;
		flex-direction: column;
		gap: 0.8rem;
	}
	.cal-modal-sync-warn {
		font-size: 0.84rem;
		color: var(--ds-color-warning-600);
		border: 1px solid rgba(202, 138, 4, 0.3);
		background: var(--color-surface-muted);
		border-radius: 0.4rem;
		padding: 0.4rem 0.6rem;
	}
	.cal-modal-error {
		font-size: 0.84rem;
		color: var(--ds-color-danger-600);
	}

	.cal-field-title input {
		width: 100%;
		border: none;
		border-bottom: 2px solid var(--color-border);
		border-radius: 0;
		padding: 0.3rem 0;
		font-size: 1.05rem;
		font-weight: 500;
		color: var(--color-text-primary);
		background: transparent;
		outline: none;
		transition: border-color 0.14s;
		font-family: inherit;
	}
	.cal-field-title input:focus {
		border-bottom-color: var(--ds-color-primary-600);
	}
	.cal-field-title input::placeholder {
		color: var(--color-text-muted);
		font-weight: 400;
	}

	.cal-field-row {
		display: flex;
		align-items: flex-start;
		gap: 0.6rem;
	}
	.cal-field-icon {
		flex-shrink: 0;
		width: 1.2rem;
		color: var(--color-text-muted);
		margin-top: 0.52rem;
		display: flex;
		align-items: center;
		justify-content: center;
	}
	.cal-field-content {
		flex: 1;
		min-width: 0;
	}

	.cal-allday-row {
		display: inline-flex;
		align-items: center;
		gap: 0.45rem;
		margin-bottom: 0.55rem;
		cursor: pointer;
	}
	.cal-allday-label {
		font-size: 0.82rem;
		color: var(--color-text-secondary);
		user-select: none;
	}

	.cal-datetime-pair {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 0.5rem;
	}
	.cal-datetime-pair--timed {
		gap: 0.65rem;
		min-height: 3.8rem;
	}
	.cal-datetime-pair--all-day {
		min-height: 3.8rem;
	}
	.cal-datetime-col {
		display: flex;
		flex-direction: column;
		gap: 0.2rem;
	}
	.cal-datetime-inline {
		display: grid;
		grid-template-columns: minmax(0, 1fr) minmax(4.9rem, 5.7rem);
		gap: 0.45rem;
	}
	.cal-datetime-sublabel {
		font-size: 0.72rem;
		color: var(--color-text-muted);
	}

	.cal-field-input {
		width: 100%;
		border: 1px solid var(--color-border);
		border-radius: 0.38rem;
		padding: 0.38rem 0.55rem;
		font-size: 0.84rem;
		color: var(--color-text-primary);
		background: var(--color-surface);
		outline: none;
		transition: border-color 0.14s, box-shadow 0.14s;
		font-family: inherit;
	}
	.cal-field-input:focus {
		border-color: var(--ds-color-primary-600);
		box-shadow: 0 0 0 3px rgba(0, 90, 146, 0.09);
	}
	.cal-field-time {
		font-variant-numeric: tabular-nums;
		min-width: 0;
	}

	.cal-switch {
		position: relative;
		width: 2.1rem;
		height: 1.2rem;
		flex-shrink: 0;
		display: inline-block;
	}
	.cal-switch input {
		opacity: 0;
		width: 0;
		height: 0;
		position: absolute;
	}
	.cal-switch-track {
		position: absolute;
		inset: 0;
		border-radius: 999px;
		background: var(--color-border);
		cursor: pointer;
		transition: background 0.16s;
	}
	.cal-switch-track::before {
		content: '';
		position: absolute;
		width: 0.85rem;
		height: 0.85rem;
		border-radius: 50%;
		background: #fff;
		left: 0.175rem;
		top: 50%;
		transform: translateY(-50%);
		transition: left 0.16s;
		box-shadow: 0 1px 3px rgba(0, 0, 0, 0.22);
	}
	.cal-switch input:checked + .cal-switch-track {
		background: var(--ds-color-primary-600);
	}
	.cal-switch input:checked + .cal-switch-track::before {
		left: calc(100% - 0.175rem - 0.85rem);
	}

	.cal-meet-row {
		display: flex;
		align-items: center;
		gap: 0.55rem;
		padding: 0.5rem 0.6rem;
		border: 1px solid var(--color-border);
		border-radius: 0.48rem;
		cursor: pointer;
		transition: background 0.12s, border-color 0.12s;
	}
	.cal-meet-row:hover {
		background: var(--color-surface-muted);
	}
	.cal-meet-row.is-active {
		border-color: #1a73e8;
		background: rgba(26, 115, 232, 0.05);
	}
	.cal-meet-icon-wrap {
		width: 1.4rem;
		height: 1.4rem;
		border-radius: 0.28rem;
		background: #00832d;
		display: flex;
		align-items: center;
		justify-content: center;
		flex-shrink: 0;
	}
	.cal-meet-text {
		flex: 1;
		display: flex;
		flex-direction: column;
		gap: 0.05rem;
	}
	.cal-meet-label {
		font-size: 0.84rem;
		color: var(--color-text-primary);
	}
	.cal-meet-sub {
		font-size: 0.73rem;
		color: var(--color-text-muted);
	}

	.cal-meet-existing {
		border: 1px solid var(--color-border);
		border-radius: 0.48rem;
		overflow: hidden;
	}
	.cal-meet-info-row {
		position: relative;
	}
	.cal-meet-existing-info {
		display: flex;
		align-items: center;
		gap: 0.55rem;
		padding: 0.5rem 2.4rem 0.5rem 0.6rem;
		background: var(--color-surface-muted);
		cursor: pointer;
		text-decoration: none;
		color: inherit;
		transition: filter 0.12s;
	}
	.cal-meet-existing-info:hover {
		filter: brightness(0.96);
	}
	.cal-meet-existing-text {
		display: flex;
		flex-direction: column;
		min-width: 0;
	}
	.cal-meet-copy-btn {
		position: absolute;
		top: 50%;
		right: 0.45rem;
		transform: translateY(-50%);
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 1.55rem;
		height: 1.55rem;
		border-radius: 0.3rem;
		border: 1px solid var(--color-border);
		background: var(--color-surface);
		color: var(--color-text-muted);
		cursor: pointer;
		opacity: 0;
		transition: opacity 0.12s, background 0.12s;
	}
	.cal-meet-info-row:hover .cal-meet-copy-btn {
		opacity: 1;
	}
	.cal-meet-copy-btn:hover {
		background: var(--color-surface-muted);
		color: var(--color-text-primary);
	}
	.cal-meet-url {
		display: block;
		font-size: 0.72rem;
		color: var(--color-text-muted);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
		max-width: 16rem;
		margin-top: 0.05rem;
	}
	.cal-meet-existing-actions {
		display: none;
		align-items: center;
		gap: 0.3rem;
		padding: 0.3rem 0.5rem;
	}
	.cal-meet-existing:not(.is-regen) .cal-meet-existing-actions {
		display: flex;
	}
	.cal-meet-regen-msg {
		display: none;
		align-items: center;
		gap: 0.55rem;
		padding: 0.3rem 0.5rem;
	}
	.cal-meet-existing.is-regen .cal-meet-regen-msg {
		display: flex;
	}
	.cal-meet-regen-msg span {
		font-size: 0.78rem;
		color: var(--color-text-secondary);
	}
	.cal-meet-action-btn {
		display: inline-flex;
		align-items: center;
		gap: 0.25rem;
		padding: 0.28rem 0.6rem;
		font-size: 0.78rem;
		font-weight: 500;
		border-radius: 0.35rem;
		border: 1px solid var(--color-border);
		background: var(--color-surface);
		color: var(--color-text-secondary);
		cursor: pointer;
		transition: background 0.12s, border-color 0.12s;
		white-space: nowrap;
	}
	.cal-meet-action-btn:hover {
		background: var(--color-surface-muted);
		color: var(--color-text-primary);
	}
	.cal-meet-action-btn--subtle {
		border-color: transparent;
		color: var(--color-text-muted);
	}
	.cal-meet-action-btn--subtle:hover {
		border-color: var(--color-border);
		color: var(--color-text-primary);
	}

	.cal-meet-toast {
		position: absolute;
		top: 50%;
		left: 50%;
		transform: translate(-50%, -50%);
		background: var(--color-text-primary);
		color: var(--color-surface);
		padding: 0.45rem 1rem;
		border-radius: 0.45rem;
		font-size: 0.82rem;
		font-weight: 500;
		pointer-events: none;
		z-index: 10;
		white-space: nowrap;
		animation: cal-meet-toast-in 1.6s ease forwards;
	}
	@keyframes cal-meet-toast-in {
		0% { opacity: 0; transform: translate(-50%, calc(-50% + 6px)); }
		15% { opacity: 1; transform: translate(-50%, -50%); }
		70% { opacity: 1; transform: translate(-50%, -50%); }
		100% { opacity: 0; transform: translate(-50%, -50%); }
	}

	.cal-field-textarea {
		width: 100%;
		border: 1px solid var(--color-border);
		border-radius: 0.38rem;
		padding: 0.4rem 0.55rem;
		font-size: 0.84rem;
		color: var(--color-text-primary);
		background: var(--color-surface);
		resize: vertical;
		min-height: 3.5rem;
		outline: none;
		font-family: inherit;
		transition: border-color 0.14s;
	}
	.cal-field-textarea:focus {
		border-color: var(--ds-color-primary-600);
		box-shadow: 0 0 0 3px rgba(0, 90, 146, 0.09);
	}

	.cal-modal-footer {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.5rem;
		padding: 0.7rem 1.1rem 0.9rem;
		border-top: 1px solid var(--color-border);
	}
	.cal-modal-footer-right {
		display: flex;
		gap: 0.45rem;
	}
	.cal-btn-delete {
		display: inline-flex;
		align-items: center;
		gap: 0.3rem;
		padding: 0.38rem 0.65rem;
		background: none;
		border: none;
		border-radius: 0.38rem;
		font-size: 0.82rem;
		color: var(--ds-color-danger-600);
		cursor: pointer;
		transition: background 0.12s;
	}
	.cal-btn-delete:hover {
		background: rgba(220, 38, 38, 0.07);
	}
	.cal-btn-cancel {
		padding: 0.4rem 0.85rem;
		background: none;
		border: 1px solid var(--color-border);
		border-radius: 0.38rem;
		font-size: 0.84rem;
		color: var(--color-text-secondary);
		cursor: pointer;
		transition: background 0.12s;
	}
	.cal-btn-cancel:hover {
		background: var(--color-surface-muted);
	}
	.cal-btn-save {
		padding: 0.4rem 1rem;
		background: var(--ds-color-primary-600);
		color: #fff;
		border: none;
		border-radius: 0.38rem;
		font-size: 0.84rem;
		font-weight: 500;
		cursor: pointer;
		transition: background 0.12s;
	}
	.cal-btn-save:hover {
		background: var(--ds-color-primary-700);
	}
	.cal-btn-delete:disabled,
	.cal-btn-cancel:disabled,
	.cal-btn-save:disabled,
	.cal-meet-action-btn:disabled {
		opacity: 0.6;
		cursor: default;
	}

	/* ── Date / Time picker (cdp-*) ─────────────────────────────────── */
	.cdp-scrim {
		position: fixed;
		inset: 0;
		z-index: 1100;
		background: transparent;
		border: none;
		padding: 0;
		cursor: default;
	}
	.cdp-popover {
		position: fixed;
		z-index: 1110;
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: 0.65rem;
		box-shadow: 0 12px 32px rgba(0, 0, 0, 0.12), 0 2px 8px rgba(0, 0, 0, 0.06);
		overflow: hidden;
	}
	.cdp-popover.is-open {
		animation: cdp-in 0.14s ease both;
	}
	@keyframes cdp-in {
		from { opacity: 0; transform: translateY(-4px); }
		to { opacity: 1; transform: translateY(0); }
	}
	.cdp-calendar {
		width: 17rem;
	}
	.cdp-calendar-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 0.55rem 0.55rem 0.35rem;
	}
	.cdp-month-label {
		font-size: 0.84rem;
		font-weight: 600;
		color: var(--color-text-primary);
		user-select: none;
	}
	.cdp-nav-btn {
		width: 1.6rem;
		height: 1.6rem;
		border-radius: 50%;
		border: none;
		background: none;
		color: var(--color-text-muted);
		cursor: pointer;
		display: flex;
		align-items: center;
		justify-content: center;
		transition: background 0.12s, color 0.12s;
	}
	.cdp-nav-btn:hover {
		background: var(--color-surface-muted);
		color: var(--color-text-primary);
	}
	.cdp-weekdays {
		display: grid;
		grid-template-columns: repeat(7, 1fr);
		padding: 0 0.4rem;
	}
	.cdp-weekdays span {
		text-align: center;
		font-size: 0.66rem;
		color: var(--color-text-muted);
		font-weight: 500;
		padding: 0.18rem 0;
		text-transform: uppercase;
		letter-spacing: 0.02em;
	}
	.cdp-days {
		display: grid;
		grid-template-columns: repeat(7, 1fr);
		padding: 0.1rem 0.4rem 0.4rem;
		gap: 0.08rem;
	}
	.cdp-day {
		width: 2rem;
		height: 2rem;
		margin: auto;
		display: flex;
		align-items: center;
		justify-content: center;
		font-size: 0.78rem;
		border-radius: 50%;
		cursor: pointer;
		border: none;
		background: none;
		color: var(--color-text-primary);
		transition: background 0.1s, color 0.1s, box-shadow 0.1s;
		font-family: inherit;
		padding: 0;
		line-height: 1;
	}
	.cdp-day:hover:not(.cdp-day--selected):not(.cdp-day--disabled):not(.cdp-day--outside) {
		background: var(--color-surface-muted);
	}
	.cdp-day--today:not(.cdp-day--selected) {
		font-weight: 600;
		color: var(--ds-color-primary-600);
		box-shadow: inset 0 0 0 1.5px var(--ds-color-primary-600);
	}
	.cdp-day--selected {
		background: var(--ds-color-primary-600);
		color: #fff;
		font-weight: 600;
	}
	.cdp-day--selected:hover {
		background: var(--ds-color-primary-700);
	}
	.cdp-day--outside {
		color: var(--color-text-muted);
		opacity: 0.35;
	}
	.cdp-day--disabled {
		opacity: 0.25;
		cursor: default;
		pointer-events: none;
	}
	.cdp-calendar-footer {
		padding: 0.25rem 0.55rem 0.45rem;
		border-top: 1px solid var(--color-border);
		display: flex;
		justify-content: center;
	}
	.cdp-today-btn {
		font-size: 0.76rem;
		font-weight: 500;
		color: var(--ds-color-primary-600);
		background: none;
		border: none;
		cursor: pointer;
		padding: 0.22rem 0.65rem;
		border-radius: 0.3rem;
		transition: background 0.12s;
		font-family: inherit;
	}
	.cdp-today-btn:hover {
		background: rgba(0, 90, 146, 0.07);
	}

	.cdp-timelist {
		width: 5.6rem;
	}
	.cdp-timelist-scroll {
		max-height: 14rem;
		overflow-y: auto;
		padding: 0.25rem;
		scroll-behavior: smooth;
	}
	.cdp-timelist-scroll::-webkit-scrollbar {
		width: 4px;
	}
	.cdp-timelist-scroll::-webkit-scrollbar-thumb {
		background: var(--color-border);
		border-radius: 4px;
	}
	.cdp-time-option {
		display: block;
		width: 100%;
		padding: 0.34rem 0.5rem;
		font-size: 0.82rem;
		font-variant-numeric: tabular-nums;
		color: var(--color-text-primary);
		border-radius: 0.3rem;
		cursor: pointer;
		border: none;
		background: none;
		text-align: left;
		transition: background 0.1s;
		font-family: inherit;
		line-height: 1.3;
	}
	.cdp-time-option:hover:not(.cdp-time-option--selected):not(.cdp-time-option--disabled) {
		background: var(--color-surface-muted);
	}
	.cdp-time-option--selected {
		background: var(--ds-color-primary-600);
		color: #fff;
		font-weight: 500;
	}
	.cdp-time-option--disabled {
		opacity: 0.3;
		cursor: default;
		pointer-events: none;
	}

	.cdp-trigger {
		cursor: pointer;
		text-align: left;
	}
	.cdp-trigger.cdp-active {
		border-color: var(--ds-color-primary-600);
		box-shadow: 0 0 0 3px rgba(0, 90, 146, 0.09);
	}

	@media (max-width: 600px) {
		.cal-datetime-pair {
			grid-template-columns: 1fr;
		}
		.cal-datetime-inline {
			grid-template-columns: 1fr;
		}
		.cdp-calendar {
			width: auto;
			min-width: 16rem;
		}
		.cdp-timelist {
			width: 6rem;
		}
	}

	@media (prefers-reduced-motion: reduce) {
		.cal-modal-overlay,
		.cal-modal,
		.cdp-popover.is-open,
		.cal-meet-toast {
			animation: none;
		}
		.cal-switch-track::before {
			transition: none;
		}
	}
</style>
