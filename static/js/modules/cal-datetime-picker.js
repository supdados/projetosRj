(function () {
    'use strict';

    /* ── Helpers ─────────────────────────────────────────────────────── */
    var MONTHS_PT = [
        'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
        'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'
    ];
    var WEEKDAYS_PT = ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom'];

    function pad(n) { return String(n).padStart(2, '0'); }

    function todayStr() {
        var d = new Date();
        return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate());
    }

    function formatDateBR(isoStr) {
        if (!isoStr || isoStr.length !== 10) return isoStr || '';
        var p = isoStr.split('-');
        return p[2] + '/' + p[1] + '/' + p[0];
    }

    var nativeValueDesc = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value');

    function wrapDateInputValue(inputEl) {
        inputEl.dataset.cdpValue = inputEl.value || '';
        nativeValueDesc.set.call(inputEl, formatDateBR(inputEl.dataset.cdpValue));
        Object.defineProperty(inputEl, 'value', {
            get: function () {
                return inputEl.dataset.cdpValue || '';
            },
            set: function (v) {
                inputEl.dataset.cdpValue = v || '';
                nativeValueDesc.set.call(inputEl, formatDateBR(v));
            },
            configurable: true
        });
    }

    function dispatchChange(el) {
        el.dispatchEvent(new Event('change', { bubbles: true }));
    }

    function el(tag, cls, attrs) {
        var node = document.createElement(tag);
        if (cls) node.className = cls;
        if (attrs) {
            Object.keys(attrs).forEach(function (k) { node.setAttribute(k, attrs[k]); });
        }
        return node;
    }

    function svgChevron(direction) {
        var svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        svg.setAttribute('width', '14');
        svg.setAttribute('height', '14');
        svg.setAttribute('viewBox', '0 0 24 24');
        svg.setAttribute('fill', 'none');
        svg.setAttribute('stroke', 'currentColor');
        svg.setAttribute('stroke-width', '2.5');
        svg.setAttribute('stroke-linecap', 'round');
        svg.setAttribute('stroke-linejoin', 'round');
        var poly = document.createElementNS('http://www.w3.org/2000/svg', 'polyline');
        poly.setAttribute('points', direction === 'left' ? '15 18 9 12 15 6' : '9 6 15 12 9 18');
        svg.appendChild(poly);
        return svg;
    }

    function positionPopover(popover, anchor) {
        var rect = anchor.getBoundingClientRect();
        var pw = popover.offsetWidth;
        var ph = popover.offsetHeight;
        var vw = window.innerWidth;
        var vh = window.innerHeight;

        var top = rect.bottom + 6;
        var left = rect.left;

        if (left + pw > vw - 12) left = vw - pw - 12;
        if (left < 12) left = 12;
        if (top + ph > vh - 12 && rect.top - ph - 6 >= 12) top = rect.top - ph - 6;
        top = Math.max(12, top);

        popover.style.top = top + 'px';
        popover.style.left = left + 'px';
    }

    /* ── Date Picker ────────────────────────────────────────────────── */
    var datePopover = null;
    var dateAnchor = null;
    var dateMonthLabel = null;
    var dateDaysContainer = null;
    var dateState = { year: 2026, month: 0, selected: '', minDate: '' };

    function ensureDatePopover() {
        if (datePopover) return;
        datePopover = el('div', 'cdp-popover cdp-calendar');

        var header = el('div', 'cdp-calendar-header');
        var prevBtn = el('button', 'cdp-nav-btn', { type: 'button', 'aria-label': 'Mês anterior' });
        prevBtn.appendChild(svgChevron('left'));
        dateMonthLabel = el('span', 'cdp-month-label');
        var nextBtn = el('button', 'cdp-nav-btn', { type: 'button', 'aria-label': 'Próximo mês' });
        nextBtn.appendChild(svgChevron('right'));
        header.appendChild(prevBtn);
        header.appendChild(dateMonthLabel);
        header.appendChild(nextBtn);

        var weekdays = el('div', 'cdp-weekdays');
        WEEKDAYS_PT.forEach(function (d) {
            var span = el('span');
            span.textContent = d;
            weekdays.appendChild(span);
        });

        dateDaysContainer = el('div', 'cdp-days');

        var footer = el('div', 'cdp-calendar-footer');
        var todayBtn = el('button', 'cdp-today-btn', { type: 'button' });
        todayBtn.textContent = 'Hoje';
        footer.appendChild(todayBtn);

        datePopover.appendChild(header);
        datePopover.appendChild(weekdays);
        datePopover.appendChild(dateDaysContainer);
        datePopover.appendChild(footer);
        document.body.appendChild(datePopover);

        prevBtn.addEventListener('click', function (e) {
            e.stopPropagation();
            dateState.month--;
            if (dateState.month < 0) { dateState.month = 11; dateState.year--; }
            renderDateGrid();
        });
        nextBtn.addEventListener('click', function (e) {
            e.stopPropagation();
            dateState.month++;
            if (dateState.month > 11) { dateState.month = 0; dateState.year++; }
            renderDateGrid();
        });
        todayBtn.addEventListener('click', function (e) {
            e.stopPropagation();
            selectDate(todayStr());
        });
        dateDaysContainer.addEventListener('click', function (e) {
            var btn = e.target.closest('.cdp-day');
            if (!btn || btn.classList.contains('cdp-day--disabled')) return;
            var val = btn.getAttribute('data-date');
            if (val) selectDate(val);
        });
    }

    function renderDateGrid() {
        dateMonthLabel.textContent = MONTHS_PT[dateState.month] + ' ' + dateState.year;

        var today = todayStr();
        var year = dateState.year;
        var month = dateState.month;
        var selected = dateState.selected;
        var minDate = dateState.minDate;

        var firstDay = new Date(year, month, 1).getDay();
        var startOffset = (firstDay + 6) % 7;
        var daysInMonth = new Date(year, month + 1, 0).getDate();
        var daysInPrev = new Date(year, month, 0).getDate();

        var cells = [];

        for (var p = startOffset - 1; p >= 0; p--) {
            var prevDay = daysInPrev - p;
            var prevMonth = month - 1;
            var prevYear = year;
            if (prevMonth < 0) { prevMonth = 11; prevYear--; }
            cells.push({ day: prevDay, dateStr: prevYear + '-' + pad(prevMonth + 1) + '-' + pad(prevDay), outside: true });
        }
        for (var d = 1; d <= daysInMonth; d++) {
            cells.push({ day: d, dateStr: year + '-' + pad(month + 1) + '-' + pad(d), outside: false });
        }
        var remaining = 7 - (cells.length % 7);
        if (remaining < 7) {
            for (var n = 1; n <= remaining; n++) {
                var nextMonth = month + 1;
                var nextYear = year;
                if (nextMonth > 11) { nextMonth = 0; nextYear++; }
                cells.push({ day: n, dateStr: nextYear + '-' + pad(nextMonth + 1) + '-' + pad(n), outside: true });
            }
        }

        while (dateDaysContainer.firstChild) dateDaysContainer.removeChild(dateDaysContainer.firstChild);

        for (var i = 0; i < cells.length; i++) {
            var c = cells[i];
            var btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'cdp-day';
            if (c.outside) btn.classList.add('cdp-day--outside');
            if (c.dateStr === today) btn.classList.add('cdp-day--today');
            if (c.dateStr === selected) btn.classList.add('cdp-day--selected');
            if (minDate && c.dateStr < minDate) btn.classList.add('cdp-day--disabled');
            btn.setAttribute('data-date', c.dateStr);
            btn.textContent = String(c.day);
            dateDaysContainer.appendChild(btn);
        }
    }

    function selectDate(dateStr) {
        dateState.selected = dateStr;
        if (dateAnchor) {
            dateAnchor.value = dateStr;
            dispatchChange(dateAnchor);
        }
        closeDatePicker();
    }

    function openDatePicker(inputEl) {
        ensureDatePopover();
        if (dateAnchor && dateAnchor !== inputEl) {
            dateAnchor.classList.remove('cdp-active');
        }
        closeTimePicker();
        dateAnchor = inputEl;

        var val = inputEl.value || todayStr();
        var parts = val.split('-');
        dateState.year = parseInt(parts[0], 10);
        dateState.month = parseInt(parts[1], 10) - 1;
        dateState.selected = inputEl.value || '';
        dateState.minDate = inputEl.min || '';

        renderDateGrid();
        datePopover.classList.add('is-open');
        inputEl.classList.add('cdp-active');
        positionPopover(datePopover, inputEl);
    }

    function closeDatePicker() {
        if (!datePopover) return;
        datePopover.classList.remove('is-open');
        if (dateAnchor) {
            dateAnchor.classList.remove('cdp-active');
            dateAnchor = null;
        }
    }

    function initDatePicker(inputEl) {
        if (!inputEl) return;
        inputEl.type = 'text';
        inputEl.readOnly = true;
        inputEl.classList.add('cdp-trigger');
        wrapDateInputValue(inputEl);

        inputEl.addEventListener('click', function (e) {
            e.stopPropagation();
            if (datePopover && datePopover.classList.contains('is-open') && dateAnchor === inputEl) {
                closeDatePicker();
            } else {
                openDatePicker(inputEl);
            }
        });

        inputEl.addEventListener('keydown', function (e) {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                openDatePicker(inputEl);
            }
        });
    }

    /* ── Time Picker ────────────────────────────────────────────────── */
    var timePopover = null;
    var timeAnchor = null;
    var timeSlots = [];

    function buildTimeSlots() {
        if (timeSlots.length) return;
        for (var h = 0; h < 24; h++) {
            for (var m = 0; m < 60; m += 30) {
                timeSlots.push(pad(h) + ':' + pad(m));
            }
        }
    }

    function ensureTimePopover() {
        if (timePopover) return;
        buildTimeSlots();
        timePopover = el('div', 'cdp-popover cdp-timelist');
        var scroll = el('div', 'cdp-timelist-scroll');

        for (var i = 0; i < timeSlots.length; i++) {
            var btn = el('button', 'cdp-time-option', { type: 'button', 'data-time': timeSlots[i] });
            btn.textContent = timeSlots[i];
            scroll.appendChild(btn);
        }

        timePopover.appendChild(scroll);
        document.body.appendChild(timePopover);

        scroll.addEventListener('click', function (e) {
            var btn = e.target.closest('.cdp-time-option');
            if (!btn || btn.classList.contains('cdp-time-option--disabled')) return;
            var val = btn.getAttribute('data-time');
            if (val) selectTime(val);
        });
    }

    function renderTimeList(selected, minTime) {
        var scroll = timePopover.querySelector('.cdp-timelist-scroll');
        var buttons = scroll.querySelectorAll('.cdp-time-option');
        var scrollTarget = null;

        for (var i = 0; i < buttons.length; i++) {
            var btn = buttons[i];
            var t = btn.getAttribute('data-time');
            btn.classList.remove('cdp-time-option--selected', 'cdp-time-option--disabled');
            if (t === selected) {
                btn.classList.add('cdp-time-option--selected');
                scrollTarget = btn;
            }
            if (minTime && t < minTime) {
                btn.classList.add('cdp-time-option--disabled');
            }
        }

        if (!scrollTarget) {
            var target = selected || pad(new Date().getHours()) + ':' + pad(new Date().getMinutes());
            for (var j = 0; j < buttons.length; j++) {
                var time = buttons[j].getAttribute('data-time');
                if (!buttons[j].classList.contains('cdp-time-option--disabled') && time >= target) {
                    scrollTarget = buttons[j];
                    break;
                }
            }
            if (!scrollTarget) scrollTarget = buttons[0];
        }

        if (scrollTarget) {
            window.requestAnimationFrame(function () {
                scrollTarget.scrollIntoView({ block: 'center', behavior: 'instant' });
            });
        }
    }

    function selectTime(timeStr) {
        if (timeAnchor) {
            timeAnchor.value = timeStr;
            dispatchChange(timeAnchor);
        }
        closeTimePicker();
    }

    function openTimePicker(inputEl) {
        ensureTimePopover();
        if (timeAnchor && timeAnchor !== inputEl) {
            timeAnchor.classList.remove('cdp-active');
        }
        closeDatePicker();
        timeAnchor = inputEl;

        renderTimeList(inputEl.value || '', inputEl.min || '');
        timePopover.classList.add('is-open');
        inputEl.classList.add('cdp-active');
        positionPopover(timePopover, inputEl);
    }

    function closeTimePicker() {
        if (!timePopover) return;
        timePopover.classList.remove('is-open');
        if (timeAnchor) {
            timeAnchor.classList.remove('cdp-active');
            timeAnchor = null;
        }
    }

    function initTimePicker(inputEl) {
        if (!inputEl) return;
        inputEl.type = 'text';
        inputEl.readOnly = true;
        inputEl.removeAttribute('step');
        inputEl.classList.add('cdp-trigger');

        inputEl.addEventListener('click', function (e) {
            e.stopPropagation();
            if (timePopover && timePopover.classList.contains('is-open') && timeAnchor === inputEl) {
                closeTimePicker();
            } else {
                openTimePicker(inputEl);
            }
        });

        inputEl.addEventListener('keydown', function (e) {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                openTimePicker(inputEl);
            }
        });
    }

    /* ── Global listeners ───────────────────────────────────────────── */
    function closeAll() {
        closeDatePicker();
        closeTimePicker();
    }

    document.addEventListener('mousedown', function (e) {
        if (datePopover && datePopover.classList.contains('is-open')) {
            if (!datePopover.contains(e.target) && e.target !== dateAnchor) {
                closeDatePicker();
            }
        }
        if (timePopover && timePopover.classList.contains('is-open')) {
            if (!timePopover.contains(e.target) && e.target !== timeAnchor) {
                closeTimePicker();
            }
        }
    });

    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') closeAll();
    });

    window.addEventListener('resize', function () {
        if (datePopover && datePopover.classList.contains('is-open') && dateAnchor) {
            positionPopover(datePopover, dateAnchor);
        }
        if (timePopover && timePopover.classList.contains('is-open') && timeAnchor) {
            positionPopover(timePopover, timeAnchor);
        }
    });

    window.addEventListener('scroll', function (e) {
        if (timePopover && timePopover.contains(e.target)) return;
        if (datePopover && datePopover.contains(e.target)) return;
        closeAll();
    }, true);

    /* ── Public API ─────────────────────────────────────────────────── */
    window.CalDatetimePicker = {
        initDatePicker: initDatePicker,
        initTimePicker: initTimePicker,
        closeAll: closeAll
    };
})();
