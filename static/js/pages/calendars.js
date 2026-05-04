/* ═══════════════════════════════════════════════════════════════════════════
   calendars.js — Lógica da página de calendário (mensal + lista)
   Configuração injetada pelo template via window.__CALENDAR_PAGE_CONFIG__
   ═══════════════════════════════════════════════════════════════════════════ */

const _cfg         = window.__CALENDAR_PAGE_CONFIG__;
const CAL_EVENTS   = _cfg.events;
const URL_CREATE   = _cfg.urlCreate;
const URL_EDIT_0   = _cfg.urlEdit;
const URL_DEL_0    = _cfg.urlDelete;
const URL_MEET_0   = _cfg.urlGenMeet;
const HAS_GOOGLE   = _cfg.hasGoogleConn;

function makeUrl(tpl, id) { return tpl.replace('/0/', '/' + id + '/'); }

const _today  = new Date();
let curYear   = _today.getFullYear();
let curMonth  = _today.getMonth();
let curView   = localStorage.getItem('cal_view') || 'calendar';
let editId    = null;

const MONTHS = ['Janeiro','Fevereiro','Março','Abril','Maio','Junho','Julho','Agosto','Setembro','Outubro','Novembro','Dezembro'];
const WDAYS  = ['Dom','Seg','Ter','Qua','Qui','Sex','Sáb'];

// ── Views ────────────────────────────────────────────────────────────────────
function switchView(v) {
  closeDayPopover();
  closeEventPopover();
  curView = v;
  localStorage.setItem('cal_view', v);
  document.getElementById('viewCalendar').classList.toggle('is-active', v === 'calendar');
  document.getElementById('viewList').classList.toggle('is-active', v === 'list');
  document.getElementById('btnViewCalendar').classList.toggle('is-active', v === 'calendar');
  document.getElementById('btnViewList').classList.toggle('is-active', v === 'list');
  document.getElementById('calMonthNav').classList.toggle('cal-month-nav--hidden', v !== 'calendar');
  v === 'calendar' ? renderCalendar() : renderList();
}

// ── Calendar ─────────────────────────────────────────────────────────────────
function prevMonth() { if (--curMonth < 0) { curMonth = 11; curYear--; } renderCalendar(); }
function nextMonth() { if (++curMonth > 11) { curMonth = 0; curYear++; } renderCalendar(); }
function goToToday() { curYear = _today.getFullYear(); curMonth = _today.getMonth(); renderCalendar(); }

function dayTs(dateStr) {
  const d = new Date(dateStr);
  return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
}

function isMultiDay(ev) {
  return dayTs(ev.starts_at) < dayTs(ev.ends_at);
}

function eventCoversFullDayOn(dayStartMs, ev) {
  const dayEndExclusiveMs = dayStartMs + 86400000;
  const fullDayToleranceMs = 60000; // 23:59 local também conta como dia inteiro
  const evStartMs = new Date(ev.starts_at).getTime();
  const evEndMs = new Date(ev.ends_at).getTime();
  const segStartMs = Math.max(evStartMs, dayStartMs);
  const segEndMs = Math.min(evEndMs, dayEndExclusiveMs);
  return segStartMs <= dayStartMs && segEndMs >= (dayEndExclusiveMs - fullDayToleranceMs);
}

function pillClass(ev) {
  if (ev.sync_status === 'error')   return 'cal-pill--error';
  if (ev.sync_status === 'pending') return 'cal-pill--pending';
  if (ev.source === 'google')       return 'cal-pill--google';
  return '';
}

let _calendarCellSyncRaf = null;

function makeMonthEventPill(ev, dayStartMs) {
  const pill = document.createElement('div');
  pill.className = 'cal-event-pill ' + pillClass(ev);
  const occupiesFullDay = eventCoversFullDayOn(dayStartMs, ev);
  const isAllDayBar = ev.is_all_day || occupiesFullDay;
  if (isAllDayBar) pill.classList.add('cal-event-pill--all-day');
  const showTime = !isAllDayBar && ev.starts_at.slice(11) !== '00:00';
  const hm = showTime ? new Date(ev.starts_at).toLocaleTimeString('pt-BR', {hour:'2-digit', minute:'2-digit'}) + ' ' : '';
  pill.textContent = hm + ev.title;
  pill.title = ev.title;
  pill.addEventListener('click', e => { e.stopPropagation(); openEventPopover(ev, pill); });
  return pill;
}

function makeMonthMorePills(day, dayEvs, hiddenCount) {
  const more = document.createElement('div');
  more.className = 'cal-more-pills';
  more.textContent = '+' + hiddenCount + ' mais';
  more.addEventListener('click', e => { e.stopPropagation(); openDayPopover(day, dayEvs, more); });
  return more;
}

function measureMonthCellEventMetrics() {
  const probe = document.createElement('div');
  probe.style.position = 'fixed';
  probe.style.left = '-9999px';
  probe.style.top = '-9999px';
  probe.style.visibility = 'hidden';
  probe.style.pointerEvents = 'none';

  const host = document.createElement('div');
  host.className = 'cal-cell-events';

  const regular = document.createElement('div');
  regular.className = 'cal-event-pill';
  regular.textContent = '09:00 Evento';

  const allDay = document.createElement('div');
  allDay.className = 'cal-event-pill cal-event-pill--all-day';
  allDay.textContent = 'Evento';

  const more = document.createElement('div');
  more.className = 'cal-more-pills';
  more.textContent = '+9 mais';

  host.appendChild(regular);
  host.appendChild(allDay);
  host.appendChild(more);
  probe.appendChild(host);
  document.body.appendChild(probe);

  const styles = window.getComputedStyle(host);
  const gap = parseFloat(styles.rowGap || styles.gap || '0') || 0;
  const metrics = {
    regular: regular.offsetHeight,
    allDay: allDay.offsetHeight,
    more: more.offsetHeight,
    gap
  };

  probe.remove();
  return metrics;
}

function getMonthEventRowsHeight(singleEvs, count, dayStartMs, metrics) {
  if (count <= 0) return 0;

  let needed = 0;
  for (let i = 0; i < count && i < singleEvs.length; i++) {
    const ev = singleEvs[i];
    needed += (eventCoversFullDayOn(dayStartMs, ev) || ev.is_all_day)
      ? metrics.allDay
      : metrics.regular;
  }

  if (count > 1) needed += metrics.gap * (count - 1);
  return needed;
}

function getVisibleMonthEventLayout(singleEvs, availableHeight, dayStartMs, metrics) {
  if (!singleEvs.length || availableHeight <= 0) return { count: 0, height: 0 };

  let count = 0;
  let height = 0;
  const limit = availableHeight + 0.5;

  for (let i = 0; i < singleEvs.length; i++) {
    const ev = singleEvs[i];
    const evHeight = (eventCoversFullDayOn(dayStartMs, ev) || ev.is_all_day)
      ? metrics.allDay
      : metrics.regular;
    const nextHeight = height + (count > 0 ? metrics.gap : 0) + evHeight;
    if (nextHeight > limit) break;
    height = nextHeight;
    count += 1;
  }

  return { count, height };
}

function renderMonthCellEvents(cell, metrics) {
  if (!cell || cell.classList.contains('cal-cell--outside') || !cell._eventsHost) return;

  const host = cell._eventsHost;
  const singleEvs = cell._singleEvents || [];
  host.textContent = '';

  if (!singleEvs.length) return;

  const visibleLayout = getVisibleMonthEventLayout(
    singleEvs,
    host.clientHeight,
    cell._dayStartMs,
    metrics
  );
  const visibleCount = visibleLayout.count;
  const visibleHeight = visibleLayout.height;

  singleEvs.slice(0, visibleCount).forEach(ev => {
    host.appendChild(makeMonthEventPill(ev, cell._dayStartMs));
  });

  if (singleEvs.length > visibleCount) {
    const more = makeMonthMorePills(cell._dayData, cell._dayEvents, singleEvs.length - visibleCount);
    const inlineMoreHeight = metrics.more + (visibleCount > 0 ? metrics.gap : 0);
    const remainingHeight = host.clientHeight - visibleHeight;
    if (remainingHeight + 0.5 < inlineMoreHeight) {
      more.classList.add('cal-more-pills--overlay');
    }
    host.appendChild(more);
  }
}

function syncCalendarCellEventDensity() {
  const grid = document.getElementById('calGrid');
  if (!grid || curView !== 'calendar') return;

  const metrics = measureMonthCellEventMetrics();
  grid.querySelectorAll('.cal-cell').forEach(cell => renderMonthCellEvents(cell, metrics));
}

function scheduleCalendarCellEventDensitySync() {
  if (curView !== 'calendar') return;
  if (_calendarCellSyncRaf) cancelAnimationFrame(_calendarCellSyncRaf);
  _calendarCellSyncRaf = requestAnimationFrame(() => {
    _calendarCellSyncRaf = null;
    syncCalendarCellEventDensity();
  });
}

function renderCalendar() {
  document.getElementById('monthLabel').textContent = MONTHS[curMonth] + ' ' + curYear;
  const grid = document.getElementById('calGrid');
  grid.textContent = '';

  const headers = document.createElement('div');
  headers.className = 'cal-grid-headers';
  WDAYS.forEach(wd => {
    const h = document.createElement('div');
    h.className = 'cal-day-header';
    h.textContent = wd;
    headers.appendChild(h);
  });
  grid.appendChild(headers);

  const firstWday  = new Date(curYear, curMonth, 1).getDay();
  const daysInMon  = new Date(curYear, curMonth + 1, 0).getDate();
  const daysInPrev = new Date(curYear, curMonth, 0).getDate();
  const weekCount  = Math.ceil((firstWday + daysInMon) / 7);
  const totalCells = weekCount * 7;

  const days = [];
  for (let i = firstWday - 1; i >= 0; i--)
    days.push({ y: curYear, m: curMonth - 1, d: daysInPrev - i, outside: true });
  for (let d = 1; d <= daysInMon; d++) {
    const isT = curYear === _today.getFullYear() && curMonth === _today.getMonth() && d === _today.getDate();
    days.push({ y: curYear, m: curMonth, d, outside: false, isToday: isT });
  }

  // Completa apenas as semanas necessárias do mês atual.
  let nextD = 1;
  while (days.length < totalCells)
    days.push({ y: curYear, m: curMonth + 1, d: nextD++, outside: true });

  grid.style.gridTemplateRows = 'auto repeat(' + weekCount + ', minmax(0, 1fr))';

  for (let w = 0; w < weekCount; w++)
    grid.appendChild(buildWeekRow(days.slice(w * 7, w * 7 + 7)));

  scheduleCalendarCellEventDensitySync();
}

function buildWeekRow(week) {
  const weekEl = document.createElement('div');
  weekEl.className = 'cal-week';

  const weekStartMs = new Date(week[0].y, week[0].m, week[0].d, 0, 0, 0).getTime();
  const weekEndMs   = new Date(week[6].y, week[6].m, week[6].d, 23, 59, 59).getTime();

  const spanEvs = CAL_EVENTS.filter(ev => {
    const isSpanLike = isMultiDay(ev) || ev.is_all_day;
    if (!isSpanLike) return false;
    return new Date(ev.starts_at).getTime() <= weekEndMs &&
           new Date(ev.ends_at).getTime()   >  weekStartMs;
  });

  // Pre-compute lanes so we know how much space to reserve inside cells
  const spanBars = [];
  const laneEnds = [];
  if (spanEvs.length) {
    const sorted = [...spanEvs].sort((a, b) => new Date(a.starts_at) - new Date(b.starts_at));
    sorted.forEach(ev => {
      const evStartMs = new Date(ev.starts_at).getTime();
      const evEndMs   = new Date(ev.ends_at).getTime();

      let lane = laneEnds.findIndex(endMs => endMs <= evStartMs);
      if (lane === -1) { lane = laneEnds.length; laneEnds.push(0); }
      laneEnds[lane] = evEndMs;

      let colStart = 8, colEnd = 0;
      week.forEach((day, i) => {
        const dMs  = new Date(day.y, day.m, day.d, 0, 0, 0).getTime();
        const dEnd = new Date(day.y, day.m, day.d, 23, 59, 59).getTime();
        if (evStartMs <= dEnd && evEndMs > dMs) {
          if (i + 1 < colStart) colStart = i + 1;
          if (i + 2 > colEnd)   colEnd   = i + 2;
        }
      });

      spanBars.push({ ev, lane, colStart, colEnd, evStartMs, evEndMs });
    });
  }

  // Para cada coluna (0-6), calcula quantas lanes de span bars passam por ela.
  const colLanes = new Array(7).fill(0);
  spanBars.forEach(({ lane, colStart, colEnd }) => {
    for (let c = colStart - 1; c < colEnd - 1 && c < 7; c++)
      colLanes[c] = Math.max(colLanes[c], lane + 1);
  });

  // ── Day cells (single-day events only) — rendered first in DOM ──
  const cellsEl = document.createElement('div');
  cellsEl.className = 'cal-week-cells';

  week.forEach((day, dayIdx) => {
    const singleEvs = day.outside ? [] : CAL_EVENTS.filter(ev => {
      if (isMultiDay(ev) || ev.is_all_day) return false;
      return dayTs(ev.starts_at) === new Date(day.y, day.m, day.d, 0, 0, 0).getTime();
    }).sort((a, b) => a.starts_at.localeCompare(b.starts_at));

    const n      = colLanes[dayIdx];
    const cellSH = n > 0 ? n * 1.2 + (n - 1) * 0.125 + 0.25 : 0;
    cellsEl.appendChild(makeCell(day, singleEvs, cellSH, n));
  });

  weekEl.appendChild(cellsEl);

  // ── Span bars (multi-day) — absolutely overlaid on top of cells ──
  if (spanBars.length) {
    const spansEl = document.createElement('div');
    spansEl.className = 'cal-week-spans';

    spanBars.forEach(({ ev, lane, colStart, colEnd, evStartMs, evEndMs }) => {
      const bar = document.createElement('div');
      bar.className = 'cal-span-bar ' + pillClass(ev);
      bar.style.gridColumn = colStart + ' / ' + colEnd;
      bar.style.gridRow    = String(lane + 1);

      const startsInWeek = evStartMs >= weekStartMs;
      const endsInWeek   = evEndMs   <= weekEndMs;
      const r = '0.22rem';
      if      (startsInWeek && endsInWeek)  bar.style.borderRadius = r;
      else if (startsInWeek)                bar.style.borderRadius = r + ' 0 0 ' + r;
      else if (endsInWeek)                  bar.style.borderRadius = '0 ' + r + ' ' + r + ' 0';
      else                                  bar.style.borderRadius = '0';

      bar.style.marginRight = endsInWeek ? '0.5rem' : '0';

      bar.textContent = ev.title;
      bar.title = ev.title;
      bar.addEventListener('click', e => { e.stopPropagation(); openEventPopover(ev, bar); });
      spansEl.appendChild(bar);
    });

    weekEl.appendChild(spansEl);
  }

  return weekEl;
}

function makeCell(day, singleEvs, spanH, nLanes) {
  if (spanH === undefined) spanH = 0;
  if (nLanes === undefined) nLanes = 0;
  const { y, m, d, outside, isToday } = day;
  const cell = document.createElement('div');
  cell.className = 'cal-cell'
    + (outside  ? ' cal-cell--outside' : '')
    + (isToday  ? ' cal-cell--today'   : '');

  const num = document.createElement('div');
  num.className = 'cal-cell-num';
  num.textContent = d;
  cell.appendChild(num);

  if (spanH > 0) {
    const spacer = document.createElement('div');
    spacer.className = 'cal-span-spacer';
    spacer.style.height = spanH + 'rem';
    cell.appendChild(spacer);
  }

  const eventsHost = document.createElement('div');
  eventsHost.className = 'cal-cell-events';
  cell.appendChild(eventsHost);

  if (!outside) {
    const pad = n => String(n).padStart(2, '0');
    const realDate = new Date(y, m, d);
    const dateStr  = realDate.getFullYear() + '-' + pad(realDate.getMonth() + 1) + '-' + pad(realDate.getDate());
    const dayStartMs = new Date(y, m, d, 0, 0, 0).getTime();
    const dayEndMs   = new Date(y, m, d, 23, 59, 59).getTime();
    const dayEvs = CAL_EVENTS.filter(ev => {
      const evStartMs = new Date(ev.starts_at).getTime();
      const evEndMs = new Date(ev.ends_at).getTime();
      return evStartMs <= dayEndMs && evEndMs > dayStartMs;
    }).sort((a, b) => {
      const aFull = eventCoversFullDayOn(dayStartMs, a);
      const bFull = eventCoversFullDayOn(dayStartMs, b);
      if (aFull !== bFull) return aFull ? -1 : 1;
      return a.starts_at.localeCompare(b.starts_at);
    });

    cell._dayData = day;
    cell._dayStartMs = dayStartMs;
    cell._dayEvents = dayEvs;
    cell._singleEvents = singleEvs;
    cell._eventsHost = eventsHost;

    cell.addEventListener('click', ev => {
      if (ev.target === cell || ev.target === num || ev.target === eventsHost) openCreateModal(dateStr);
    });
  }
  return cell;
}

// ── Day popover ───────────────────────────────────────────────────────────────
let _dayPopover = null;
let _eventPopover = null;

function closeDayPopover() {
  if (_dayPopover) { _dayPopover.remove(); _dayPopover = null; }
}

function closeEventPopover() {
  if (_eventPopover) { _eventPopover.remove(); _eventPopover = null; }
}

function formatEventDateTime(ev) {
  const startsAt = new Date(ev.starts_at);
  const endsAt = new Date(ev.ends_at);
  const sameDay = startsAt.toDateString() === endsAt.toDateString();
  const dateFmt = dt => dt.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit', year: 'numeric' });
  const timeFmt = dt => dt.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });

  if (ev.is_all_day) {
    if (sameDay) return dateFmt(startsAt) + ' \u00b7 Dia inteiro';
    return dateFmt(startsAt) + ' at\u00e9 ' + dateFmt(endsAt) + ' \u00b7 Dia inteiro';
  }
  if (sameDay) {
    return dateFmt(startsAt) + ' \u00b7 ' + timeFmt(startsAt) + ' - ' + timeFmt(endsAt);
  }
  return dateFmt(startsAt) + ' ' + timeFmt(startsAt) + ' at\u00e9 ' + dateFmt(endsAt) + ' ' + timeFmt(endsAt);
}

function _makeIconSpan(iconClass, text) {
  const wrap = document.createElement('div');
  const icon = document.createElement('i');
  icon.className = iconClass;
  icon.setAttribute('aria-hidden', 'true');
  const span = document.createElement('span');
  span.textContent = text;
  wrap.appendChild(icon);
  wrap.appendChild(span);
  return wrap;
}

function openEventPopover(ev, anchor) {
  if (!anchor) return;
  const dayPopoverAnchor = typeof anchor.closest === 'function'
    ? anchor.closest('.cal-day-popover')
    : null;
  const rect = typeof anchor.getBoundingClientRect === 'function'
    ? anchor.getBoundingClientRect()
    : anchor;
  const dayPopoverRect = dayPopoverAnchor && typeof dayPopoverAnchor.getBoundingClientRect === 'function'
    ? dayPopoverAnchor.getBoundingClientRect()
    : null;
  if (!rect) return;
  closeDayPopover();
  closeEventPopover();

  const pop = document.createElement('div');
  pop.className = 'cal-event-popover';
  _eventPopover = pop;

  const head = document.createElement('div');
  head.className = 'cal-event-popover-head';

  const title = document.createElement('div');
  title.className = 'cal-event-popover-title';
  title.style.fontWeight = 'bold';
  title.textContent = ev.title || 'Sem titulo';
  head.appendChild(title);

  const closeBtn = document.createElement('button');
  closeBtn.type = 'button';
  closeBtn.className = 'cal-event-popover-close';
  closeBtn.setAttribute('aria-label', 'Fechar');
  closeBtn.textContent = '\u00d7';
  closeBtn.addEventListener('click', e => { e.stopPropagation(); closeEventPopover(); });
  head.appendChild(closeBtn);
  pop.appendChild(head);

  const body = document.createElement('div');
  body.className = 'cal-event-popover-body';

  const when = _makeIconSpan('fas fa-clock', formatEventDateTime(ev));
  when.className = 'cal-event-popover-info';
  body.appendChild(when);

  if (ev.location) {
    const loc = _makeIconSpan('fas fa-map-marker-alt', ev.location);
    loc.className = 'cal-event-popover-info';
    body.appendChild(loc);
  }

  if (ev.description) {
    const desc = document.createElement('div');
    desc.className = 'cal-event-popover-description';
    desc.textContent = ev.description;
    body.appendChild(desc);
  }

  function _makeCamIcon() {
    const ic = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    ic.setAttribute('width', '13'); ic.setAttribute('height', '13');
    ic.setAttribute('viewBox', '0 0 24 24'); ic.setAttribute('fill', 'none');
    ic.setAttribute('stroke', 'currentColor'); ic.setAttribute('stroke-width', '2.2');
    ic.setAttribute('stroke-linecap', 'round'); ic.setAttribute('stroke-linejoin', 'round');
    const p = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    p.setAttribute('d', 'M15 10l4.553-2.069A1 1 0 0 1 21 8.82v6.36a1 1 0 0 1-1.447.889L15 14');
    const r = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    r.setAttribute('x', '3'); r.setAttribute('y', '6'); r.setAttribute('width', '12');
    r.setAttribute('height', '12'); r.setAttribute('rx', '2');
    ic.appendChild(p); ic.appendChild(r);
    return ic;
  }

  function _makeCopyIcon() {
    const ic = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    ic.setAttribute('width', '13'); ic.setAttribute('height', '13');
    ic.setAttribute('viewBox', '0 0 24 24'); ic.setAttribute('fill', 'none');
    ic.setAttribute('stroke', 'currentColor'); ic.setAttribute('stroke-width', '2');
    ic.setAttribute('stroke-linecap', 'round'); ic.setAttribute('stroke-linejoin', 'round');
    const r1 = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    r1.setAttribute('x', '9'); r1.setAttribute('y', '9'); r1.setAttribute('width', '13');
    r1.setAttribute('height', '13'); r1.setAttribute('rx', '2');
    const p = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    p.setAttribute('d', 'M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1');
    ic.appendChild(r1); ic.appendChild(p);
    return ic;
  }

  const meetArea = document.createElement('div');
  meetArea.className = 'cal-event-popover-meet-area';

  function buildMeetArea(meetLink) {
    while (meetArea.firstChild) meetArea.removeChild(meetArea.firstChild);
    if (meetLink) {
      const meet = document.createElement('a');
      meet.className = 'cal-event-popover-meet-btn';
      meet.href = meetLink;
      meet.target = '_blank';
      meet.rel = 'noopener noreferrer';
      meet.appendChild(_makeCamIcon());
      const lbl = document.createElement('span'); lbl.textContent = 'Abrir Meet';
      meet.appendChild(lbl);
      meet.addEventListener('click', e => e.stopPropagation());
      meetArea.appendChild(meet);

      const copyBtn = document.createElement('button');
      copyBtn.type = 'button';
      copyBtn.className = 'cal-event-popover-copy-btn';
      copyBtn.title = 'Copiar link do Meet';
      copyBtn.appendChild(_makeCopyIcon());
      copyBtn.addEventListener('click', e => {
        e.stopPropagation();
        navigator.clipboard.writeText(meetLink).then(() => {
          copyBtn.classList.add('cal-event-popover-copy-btn--copied');
          window.setTimeout(() => copyBtn.classList.remove('cal-event-popover-copy-btn--copied'), 1500);
        }).catch(() => {
          const ta = document.createElement('textarea');
          ta.value = meetLink; ta.style.cssText = 'position:fixed;opacity:0;';
          document.body.appendChild(ta); ta.select(); document.execCommand('copy');
          document.body.removeChild(ta);
          copyBtn.classList.add('cal-event-popover-copy-btn--copied');
          window.setTimeout(() => copyBtn.classList.remove('cal-event-popover-copy-btn--copied'), 1500);
        });
      });
      meetArea.appendChild(copyBtn);
    } else if (HAS_GOOGLE) {
      const genBtn = document.createElement('button');
      genBtn.type = 'button';
      genBtn.className = 'cal-event-popover-gen-meet-btn';
      genBtn.appendChild(_makeCamIcon());
      const genLbl = document.createElement('span'); genLbl.textContent = 'Gerar link do Meet';
      genBtn.appendChild(genLbl);
      genBtn.addEventListener('click', e => {
        e.stopPropagation();
        genBtn.disabled = true;
        genLbl.textContent = 'Gerando…';
        fetch(makeUrl(URL_MEET_0, ev.id), {
          method: 'POST',
          headers: {'Accept': 'application/json'}
        })
        .then(r => r.json())
        .then(data => {
          if (data.ok && data.event && data.event.meet_link) {
            const idx = CAL_EVENTS.findIndex(e => e.id === ev.id);
            if (idx >= 0) CAL_EVENTS[idx].meet_link = data.event.meet_link;
            ev.meet_link = data.event.meet_link;
            buildMeetArea(ev.meet_link);
            if (curView === 'calendar') renderCalendar(); else renderList();
          } else {
            genBtn.disabled = false; genLbl.textContent = 'Gerar link do Meet';
          }
        })
        .catch(() => { genBtn.disabled = false; genLbl.textContent = 'Gerar link do Meet'; });
      });
      meetArea.appendChild(genBtn);
    }
  }

  buildMeetArea(ev.meet_link);
  body.appendChild(meetArea);

  const actions = document.createElement('div');
  actions.className = 'cal-event-popover-actions';

  const editBtn = document.createElement('button');
  editBtn.type = 'button';
  editBtn.className = 'cal-event-popover-action';
  var editIcon = _makeIconSpan('fas fa-pen', 'Editar');
  editBtn.appendChild(editIcon.querySelector('i'));
  editBtn.appendChild(editIcon.querySelector('span'));
  editBtn.addEventListener('click', e => {
    e.stopPropagation();
    closeEventPopover();
    openEditModal(ev);
  });

  const delBtn = document.createElement('button');
  delBtn.type = 'button';
  delBtn.className = 'cal-event-popover-action cal-event-popover-action--danger';
  var delIcon = _makeIconSpan('fas fa-trash', 'Apagar');
  delBtn.appendChild(delIcon.querySelector('i'));
  delBtn.appendChild(delIcon.querySelector('span'));
  delBtn.addEventListener('click', e => {
    e.stopPropagation();
    closeEventPopover();
    deleteEvent(ev.id);
  });

  actions.appendChild(editBtn);
  actions.appendChild(delBtn);
  body.appendChild(actions);
  pop.appendChild(body);

  pop.addEventListener('click', e => e.stopPropagation());
  document.body.appendChild(pop);

  const popW = pop.offsetWidth || 320;
  const popH = pop.offsetHeight || 220;
  const viewW = window.innerWidth;
  const viewH = window.innerHeight;
  const posRefRect = dayPopoverRect || rect;

  let left = posRefRect.left;
  let top = dayPopoverRect ? posRefRect.top : (posRefRect.bottom + 8);

  if (left + popW > viewW - 8) left = viewW - popW - 8;
  if (left < 8) left = 8;
  if (top + popH > viewH - 8) top = posRefRect.top - popH - 8;
  if (top < 8) top = 8;

  pop.style.left = left + 'px';
  pop.style.top = top + 'px';

  setTimeout(() => document.addEventListener('click', closeEventPopover, { once: true }), 0);
}

function openDayPopover(day, evs, anchor) {
  closeEventPopover();
  closeDayPopover();

  const pop = document.createElement('div');
  pop.className = 'cal-day-popover';
  _dayPopover = pop;

  const hdr = document.createElement('div');
  hdr.className = 'cal-popover-header';
  const dt = new Date(day.y, day.m, day.d);

  const dateWrap = document.createElement('div');
  dateWrap.className = 'cal-popover-date';

  const weekday = document.createElement('div');
  weekday.className = 'cal-popover-weekday';
  weekday.textContent = dt.toLocaleDateString('pt-BR', { weekday: 'short' }).toUpperCase();
  dateWrap.appendChild(weekday);

  const dayNum = document.createElement('div');
  dayNum.className = 'cal-popover-daynum';
  dayNum.textContent = String(dt.getDate());
  dateWrap.appendChild(dayNum);

  hdr.appendChild(dateWrap);

  const closeBtn = document.createElement('button');
  closeBtn.type = 'button';
  closeBtn.className = 'cal-popover-close';
  closeBtn.setAttribute('aria-label', 'Fechar');
  closeBtn.textContent = '\u00d7';
  closeBtn.addEventListener('click', e => { e.stopPropagation(); closeDayPopover(); });
  hdr.appendChild(closeBtn);
  pop.appendChild(hdr);

  const list = document.createElement('div');
  list.className = 'cal-popover-list';
  pop.appendChild(list);

  const dayStartMs = new Date(day.y, day.m, day.d, 0, 0, 0).getTime();
  const dayEndExclusiveMs = dayStartMs + 86400000;

  evs.forEach(ev => {
    const item = document.createElement('div');
    item.className = 'cal-popover-item ' + pillClass(ev);
    const evStartMs = new Date(ev.starts_at).getTime();
    const evEndMs = new Date(ev.ends_at).getTime();
    const occupiesFullDay = eventCoversFullDayOn(dayStartMs, ev);
    const continuesFromPrev = evStartMs < dayStartMs;
    const continuesToNext = evEndMs > dayEndExclusiveMs;

    if (occupiesFullDay) {
      item.classList.add('cal-popover-item--span');
      if (continuesFromPrev && continuesToNext) {
        item.classList.add('cal-popover-item--cut-both');
      } else if (continuesFromPrev) {
        item.classList.add('cal-popover-item--cut-left');
      } else if (continuesToNext) {
        item.classList.add('cal-popover-item--cut-right');
      }
    }

    const showTime = !occupiesFullDay && !ev.is_all_day && ev.starts_at.slice(11) !== '00:00';
    const hm = showTime ? new Date(ev.starts_at).toLocaleTimeString('pt-BR', {hour:'2-digit', minute:'2-digit'}) + ' ' : '';
    const label = document.createElement('span');
    label.className = 'cal-popover-item-label';
    if (hm) {
      const timeSpan = document.createElement('span');
      timeSpan.textContent = hm;
      label.appendChild(timeSpan);
    }
    const titleStrong = document.createElement('strong');
    titleStrong.textContent = ev.title;
    label.appendChild(titleStrong);
    item.appendChild(label);
    item.title = ev.title;
    item.addEventListener('click', e => { e.stopPropagation(); openEventPopover(ev, item); });
    list.appendChild(item);
  });

  document.body.appendChild(pop);

  const r  = anchor.getBoundingClientRect();
  const pw = pop.offsetWidth  || 220;
  const ph = pop.offsetHeight || evs.length * 38 + 44;
  const vw = window.innerWidth;
  const vh = window.innerHeight;

  let left = r.left;
  let top  = r.bottom + 6;
  if (left + pw > vw - 8)  left = vw - pw - 8;
  if (left < 8)            left = 8;
  if (top  + ph > vh - 8)  top  = r.top - ph - 6;
  if (top  < 8)            top  = 8;

  pop.style.left = left + 'px';
  pop.style.top  = top  + 'px';

  setTimeout(() => document.addEventListener('click', closeDayPopover, { once: true }), 0);
}

// ── List ─────────────────────────────────────────────────────────────────────
function listBarClass(ev) {
  if (ev.sync_status === 'error')   return 'cal-list-bar--error';
  if (ev.sync_status === 'pending') return 'cal-list-bar--pending';
  if (ev.source === 'google')       return 'cal-list-bar--google';
  return '';
}

function renderList() {
  const list = document.getElementById('calList');
  list.textContent = '';

  if (!CAL_EVENTS.length) {
    const empty = document.createElement('div');
    empty.className = 'cal-list-empty';
    const strong = document.createElement('strong');
    strong.textContent = 'Novo evento';
    empty.append('Nenhum evento. Clique em ');
    empty.appendChild(strong);
    empty.append(' para come\u00e7ar.');
    list.appendChild(empty);
    return;
  }

  const sorted = [...CAL_EVENTS].sort((a, b) => a.starts_at.localeCompare(b.starts_at));
  const groups = {};
  sorted.forEach(ev => {
    const key = ev.starts_at.slice(0, 10);
    (groups[key] = groups[key] || []).push(ev);
  });

  Object.entries(groups).forEach(([key, evs]) => {
    const [y, m, d] = key.split('-').map(Number);
    const dateObj = new Date(y, m - 1, d);
    const wday = dateObj.toLocaleDateString('pt-BR', {weekday: 'long'});
    const grp = document.createElement('div');
    grp.className = 'cal-list-group';

    const dl = document.createElement('div');
    dl.className = 'cal-list-date-label';
    dl.textContent = wday.charAt(0).toUpperCase() + wday.slice(1) + ', ' + d + ' de ' + MONTHS[m - 1];
    grp.appendChild(dl);

    evs.forEach(ev => {
      const row = document.createElement('div');
      row.className = 'cal-list-event';
      row.addEventListener('click', e => { e.stopPropagation(); openEventPopover(ev, row); });

      const bar = document.createElement('div');
      bar.className = 'cal-list-bar ' + listBarClass(ev);
      row.appendChild(bar);

      const timeEl = document.createElement('div');
      timeEl.className = 'cal-list-time';
      if (ev.is_all_day || ev.starts_at.slice(11) === '00:00') {
        timeEl.textContent = 'Dia inteiro';
      } else {
        const s = new Date(ev.starts_at), e2 = new Date(ev.ends_at);
        const fmt = dt => dt.toLocaleTimeString('pt-BR', {hour:'2-digit', minute:'2-digit'});
        const start = document.createTextNode(fmt(s));
        const br = document.createElement('br');
        const end = document.createElement('span');
        end.className = 'cal-list-time-end';
        end.textContent = '\u2013 ' + fmt(e2);
        timeEl.appendChild(start);
        timeEl.appendChild(br);
        timeEl.appendChild(end);
      }
      row.appendChild(timeEl);

      const body = document.createElement('div');
      body.className = 'cal-list-body';

      const titleEl = document.createElement('div');
      titleEl.className = 'cal-list-title';
      titleEl.textContent = ev.title;
      body.appendChild(titleEl);

      const meta = document.createElement('div');
      meta.className = 'cal-list-meta';

      if (ev.location) {
        const locEl = document.createElement('span');
        locEl.className = 'cal-meta-item';
        locEl.textContent = ev.location;
        meta.appendChild(locEl);
      }

      if (ev.meet_link) {
        const meetA = document.createElement('a');
        meetA.className = 'cal-meta-meet';
        meetA.href = ev.meet_link;
        meetA.target = '_blank';
        meetA.rel = 'noopener noreferrer';
        const mIc = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        mIc.setAttribute('width', '11'); mIc.setAttribute('height', '11');
        mIc.setAttribute('viewBox', '0 0 24 24'); mIc.setAttribute('fill', 'none');
        mIc.setAttribute('stroke', 'currentColor'); mIc.setAttribute('stroke-width', '2.2');
        mIc.setAttribute('stroke-linecap', 'round'); mIc.setAttribute('stroke-linejoin', 'round');
        const mP = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        mP.setAttribute('d', 'M15 10l4.553-2.069A1 1 0 0 1 21 8.82v6.36a1 1 0 0 1-1.447.889L15 14');
        const mR = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
        mR.setAttribute('x', '3'); mR.setAttribute('y', '6');
        mR.setAttribute('width', '12'); mR.setAttribute('height', '12'); mR.setAttribute('rx', '2');
        mIc.appendChild(mP); mIc.appendChild(mR);
        const mLbl = document.createElement('span'); mLbl.textContent = 'Meet';
        meetA.appendChild(mIc); meetA.appendChild(mLbl);
        meetA.addEventListener('click', e => e.stopPropagation());
        meta.appendChild(meetA);
      }
      body.appendChild(meta);
      row.appendChild(body);

      const acts = document.createElement('div');
      acts.className = 'cal-list-actions';

      const editBtn = document.createElement('button');
      editBtn.type = 'button';
      editBtn.className = 'cal-btn-sm';
      editBtn.title = 'Editar';
      editBtn.setAttribute('aria-label', 'Editar');
      editBtn.textContent = '\u270e';
      editBtn.addEventListener('click', e => { e.stopPropagation(); openEditModal(ev); });

      const delBtn = document.createElement('button');
      delBtn.type = 'button';
      delBtn.className = 'cal-btn-sm cal-btn-sm--danger';
      delBtn.title = 'Excluir';
      delBtn.setAttribute('aria-label', 'Excluir');
      delBtn.textContent = '\u2715';
      delBtn.addEventListener('click', e => { e.stopPropagation(); deleteEvent(ev.id); });

      acts.appendChild(editBtn);
      acts.appendChild(delBtn);
      row.appendChild(acts);
      grp.appendChild(row);
    });

    list.appendChild(grp);
  });
}

// ── Modal ─────────────────────────────────────────────────────────────────────
const calendarModal = window.createCalendarEventModal({
  modalId: 'eventModal',
  createUrl: URL_CREATE,
  editUrlTemplate: URL_EDIT_0,
  createTitle: 'Novo evento',
  editTitle: 'Editar evento',
  onDelete: function (id, api) {
    deleteEvent(id, api);
  },
  onSubmit: function (event, api) {
    const form = api.getForm();
    const formData = new FormData(form);
    fetch(form.action, {method: 'POST', headers: {'Accept': 'application/json'}, body: formData})
      .then(r => r.json())
      .then(data => {
        if (!data.ok) { form.submit(); return; }
        api.clearPending();
        const ev = data.event;
        const idx = CAL_EVENTS.findIndex(e => e.id === ev.id);
        if (idx >= 0) CAL_EVENTS[idx] = ev; else CAL_EVENTS.push(ev);
        if (curView === 'calendar') renderCalendar(); else renderList();
        api.closeModal();
      })
      .catch(() => form.submit());
  },
  onMeetToggle: function (api) {
    const modal = api.getModal();
    const titleField = modal.querySelector('#fieldTitle');
    const fieldMeet  = modal.querySelector('#fieldMeet');
    function revertToggle() {
      if (fieldMeet) { fieldMeet.checked = false; fieldMeet.dispatchEvent(new Event('change')); }
    }
    if (!titleField || !titleField.value.trim()) {
      window.alert('Preencha o título do evento antes de gerar o link do Meet.');
      revertToggle(); return;
    }
    if (!api.prepareFormBeforeSubmit()) { revertToggle(); return; }
    const form = api.getForm();
    const formData = new FormData(form);
    formData.set('create_conference', 'on');
    fetch(URL_CREATE, {method: 'POST', headers: {'Accept': 'application/json'}, body: formData})
      .then(r => r.json())
      .then(data => {
        if (!data.ok || !data.event) { revertToggle(); return; }
        const ev = data.event;
        const idx = CAL_EVENTS.findIndex(e => e.id === ev.id);
        if (idx >= 0) CAL_EVENTS[idx] = ev; else CAL_EVENTS.push(ev);
        if (curView === 'calendar') renderCalendar(); else renderList();
        api.setPendingEvent(ev.id, URL_EDIT_0);
        api.resetMeetUI(ev.meet_link || null);
      })
      .catch(() => revertToggle());
  },
  onClose: function (pendingId) {
    const idx = CAL_EVENTS.findIndex(e => e.id === pendingId);
    if (idx >= 0) CAL_EVENTS.splice(idx, 1);
    if (curView === 'calendar') renderCalendar(); else renderList();
    fetch(makeUrl(URL_DEL_0, pendingId), {method: 'POST'}).catch(() => {});
  }
});

function openCreateModal(dateStr) {
  closeDayPopover();
  closeEventPopover();
  calendarModal.openCreateModal(dateStr);
}

function openEditModal(ev) {
  closeDayPopover();
  closeEventPopover();
  calendarModal.openEditModal(ev);
}

function closeModal() {
  calendarModal.closeModal();
}

function deleteEvent(id, api) {
  closeEventPopover();
  if (!confirm('Excluir este evento?')) return;
  if (api) api.closeModal();
  const f = document.getElementById('deleteForm');
  f.action = makeUrl(URL_DEL_0, id);
  f.submit();
}

// ── Init ──────────────────────────────────────────────────────────────────────
document.body.classList.add('cal-body');
switchView(curView);

window.addEventListener('resize', () => {
  if (curView === 'calendar') scheduleCalendarCellEventDensitySync();
});

if (document.fonts && document.fonts.ready) {
  document.fonts.ready.then(() => {
    if (curView === 'calendar') scheduleCalendarCellEventDensitySync();
  });
}

if (!document.body.classList.contains('page-ready')) {
  const _pageReadyObserver = new MutationObserver(() => {
    if (document.body.classList.contains('page-ready')) {
      _pageReadyObserver.disconnect();
      if (curView === 'calendar') scheduleCalendarCellEventDensitySync();
    }
  });
  _pageReadyObserver.observe(document.body, { attributeFilter: ['class'] });
}

document.addEventListener('keydown', e => {
  if (e.key === 'Escape' && document.getElementById('eventModal').classList.contains('is-open'))
    closeModal();
  if (e.key === 'Escape') {
    closeDayPopover();
    closeEventPopover();
  }
});
