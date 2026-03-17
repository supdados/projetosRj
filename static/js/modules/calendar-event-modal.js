(function () {
    function createCalendarEventModal(config) {
        const modal = document.getElementById(config.modalId || 'eventModal');
        if (!modal) {
            return null;
        }

        const form = modal.querySelector('form');
        const modalTitle = modal.querySelector('#modalTitle');
        const deleteButton = modal.querySelector('#btnDelete');
        const fieldTitle = modal.querySelector('#fieldTitle');
        const fieldLocation = modal.querySelector('#fieldLocation');
        const fieldDescription = modal.querySelector('#fieldDescription');
        const fieldAllDay = modal.querySelector('#fieldAllDay');
        const fieldStartsAt = modal.querySelector('#fieldStartsAt');
        const fieldEndsAt = modal.querySelector('#fieldEndsAt');
        const fieldStartsAtDatePart = modal.querySelector('#fieldStartsAtDatePart');
        const fieldStartsAtTimePart = modal.querySelector('#fieldStartsAtTimePart');
        const fieldEndsAtDatePart = modal.querySelector('#fieldEndsAtDatePart');
        const fieldEndsAtTimePart = modal.querySelector('#fieldEndsAtTimePart');
        const fieldStartsAtDate = modal.querySelector('#fieldStartsAtDate');
        const fieldEndsAtDate = modal.querySelector('#fieldEndsAtDate');
        const datetimePair = modal.querySelector('#datetimePair');
        const datePair = modal.querySelector('#datePair');
        const fieldMeet = modal.querySelector('#fieldMeet');
        const meetGenerateRow = modal.querySelector('#meetGenerateRow');
        const meetExistingRow = modal.querySelector('#meetExistingRow');
        const meetExistingActions = modal.querySelector('#meetExistingActions');
        const meetRegenMsg = modal.querySelector('#meetRegenMsg');
        const meetSub = modal.querySelector('#meetSub');
        const meetUrlDisplay = modal.querySelector('#meetUrlDisplay');
        const meetOpenLink = modal.querySelector('#meetOpenLink');
        let editId = null;

        function makeUrl(tpl, id) {
            return String(tpl || '').replace('/0/', '/' + id + '/');
        }

        function notifyInvalid(message) {
            if (typeof config.onInvalid === 'function') {
                config.onInvalid(message);
                return;
            }
            window.alert(message);
        }

        function resetMeetUI(existingLink) {
            if (!fieldMeet) {
                return;
            }
            fieldMeet.checked = false;

            if (existingLink) {
                if (meetGenerateRow) meetGenerateRow.style.display = 'none';
                if (meetExistingRow) meetExistingRow.style.display = '';
                if (meetOpenLink) meetOpenLink.href = existingLink;
                if (meetUrlDisplay) {
                    try {
                        const parsed = new URL(existingLink);
                        meetUrlDisplay.textContent = parsed.host + parsed.pathname;
                    } catch (error) {
                        meetUrlDisplay.textContent = existingLink;
                    }
                }
                if (meetExistingActions) meetExistingActions.style.display = '';
                if (meetRegenMsg) meetRegenMsg.style.display = 'none';
                return;
            }

            if (meetGenerateRow) {
                meetGenerateRow.style.display = '';
                meetGenerateRow.classList.remove('is-active');
            }
            if (meetExistingRow) meetExistingRow.style.display = 'none';
            if (meetSub) meetSub.textContent = 'Adicionar videochamada';
        }

        function copyMeetLink(trigger) {
            if (!meetOpenLink) {
                return;
            }
            const url = meetOpenLink.href;
            const button = trigger || document.activeElement;
            const original = button && button.textContent ? button.textContent : 'Copiar link';
            navigator.clipboard.writeText(url).then(function () {
                if (button) button.textContent = 'Copiado!';
                window.setTimeout(function () {
                    if (button) button.textContent = original;
                }, 1500);
            }).catch(function () {
                const textarea = document.createElement('textarea');
                textarea.value = url;
                textarea.style.cssText = 'position:fixed;opacity:0;';
                document.body.appendChild(textarea);
                textarea.select();
                document.execCommand('copy');
                document.body.removeChild(textarea);
                if (button) button.textContent = 'Copiado!';
                window.setTimeout(function () {
                    if (button) button.textContent = original;
                }, 1500);
            });
        }

        function requestNewMeetLink() {
            if (meetExistingActions) meetExistingActions.style.display = 'none';
            if (meetRegenMsg) meetRegenMsg.style.display = '';
            if (fieldMeet) fieldMeet.checked = true;
        }

        function cancelNewMeetLink() {
            if (meetExistingActions) meetExistingActions.style.display = '';
            if (meetRegenMsg) meetRegenMsg.style.display = 'none';
            if (fieldMeet) fieldMeet.checked = false;
        }

        function closeModal() {
            modal.classList.remove('is-open');
        }

        function handleOverlayClick(event) {
            if (event.target === modal) {
                closeModal();
            }
        }

        function toggleMeet(checked) {
            if (meetGenerateRow) meetGenerateRow.classList.toggle('is-active', checked);
            if (meetSub) meetSub.textContent = checked ? 'Link será gerado ao salvar' : 'Adicionar videochamada';
        }

        function splitDatetimeValue(value) {
            const raw = String(value || '').trim();
            if (!raw) {
                return { date: '', time: '' };
            }
            const chunks = raw.split('T');
            return {
                date: chunks[0] || '',
                time: (chunks[1] || '').slice(0, 5),
            };
        }

        function composeDatetimeValue(dateValue, timeValue) {
            const datePart = String(dateValue || '').trim();
            const timePart = String(timeValue || '').trim().slice(0, 5);
            if (!datePart || !timePart) {
                return '';
            }
            return datePart + 'T' + timePart;
        }

        function parseDateTimeParts(dateValue, timeValue) {
            const combined = composeDatetimeValue(dateValue, timeValue);
            if (!combined) {
                return null;
            }
            const parsed = new Date(combined);
            if (isNaN(parsed.getTime())) {
                return null;
            }
            return parsed;
        }

        function toDatetimeLocal(date) {
            const pad = function (value) { return String(value).padStart(2, '0'); };
            return date.getFullYear() + '-' + pad(date.getMonth() + 1) + '-' + pad(date.getDate())
                + 'T' + pad(date.getHours()) + ':' + pad(date.getMinutes());
        }

        function setTimedStartParts(value) {
            const parts = splitDatetimeValue(value);
            if (fieldStartsAtDatePart) fieldStartsAtDatePart.value = parts.date;
            if (fieldStartsAtTimePart) fieldStartsAtTimePart.value = parts.time;
        }

        function setTimedEndParts(value) {
            const parts = splitDatetimeValue(value);
            if (fieldEndsAtDatePart) fieldEndsAtDatePart.value = parts.date;
            if (fieldEndsAtTimePart) fieldEndsAtTimePart.value = parts.time;
        }

        function syncHiddenDatetimeFields() {
            if (fieldStartsAt) {
                fieldStartsAt.value = composeDatetimeValue(
                    fieldStartsAtDatePart ? fieldStartsAtDatePart.value : '',
                    fieldStartsAtTimePart ? fieldStartsAtTimePart.value : ''
                );
            }
            if (fieldEndsAt) {
                fieldEndsAt.value = composeDatetimeValue(
                    fieldEndsAtDatePart ? fieldEndsAtDatePart.value : '',
                    fieldEndsAtTimePart ? fieldEndsAtTimePart.value : ''
                );
            }
        }

        function syncTimedMinConstraints() {
            const startDate = fieldStartsAtDatePart ? fieldStartsAtDatePart.value : '';
            const startTime = fieldStartsAtTimePart ? fieldStartsAtTimePart.value : '';
            const endDate = fieldEndsAtDatePart ? fieldEndsAtDatePart.value : '';

            if (fieldEndsAtDatePart) {
                fieldEndsAtDatePart.min = startDate || '';
            }
            if (fieldEndsAtTimePart) {
                if (startDate && endDate && startDate === endDate) {
                    fieldEndsAtTimePart.min = startTime || '';
                } else {
                    fieldEndsAtTimePart.min = '';
                }
            }
        }

        function toggleAllDay(checked) {
            if (datetimePair) datetimePair.style.display = checked ? 'none' : '';
            if (datePair) datePair.style.display = checked ? '' : 'none';
            if (fieldStartsAt) fieldStartsAt.required = true;
            if (fieldEndsAt) fieldEndsAt.required = true;

            if (checked) {
                if (fieldStartsAtDatePart && fieldStartsAtDate && fieldStartsAtDatePart.value) {
                    fieldStartsAtDate.value = fieldStartsAtDatePart.value;
                }
                if (fieldEndsAtDatePart && fieldEndsAtDate && fieldEndsAtDatePart.value) {
                    fieldEndsAtDate.value = fieldEndsAtDatePart.value;
                }
                if (fieldEndsAtDate && fieldStartsAtDate) {
                    fieldEndsAtDate.min = fieldStartsAtDate.value || '';
                }
                return;
            }

            const startDate = fieldStartsAtDate ? fieldStartsAtDate.value : '';
            const endDate = fieldEndsAtDate ? fieldEndsAtDate.value : '';
            if (startDate && fieldStartsAtDatePart) {
                fieldStartsAtDatePart.value = startDate;
            }
            if (endDate && fieldEndsAtDatePart) {
                fieldEndsAtDatePart.value = endDate;
            }
            if (fieldStartsAtTimePart && !fieldStartsAtTimePart.value) {
                fieldStartsAtTimePart.value = '09:00';
            }
            if (fieldEndsAtTimePart && !fieldEndsAtTimePart.value) {
                fieldEndsAtTimePart.value = '10:00';
            }
            syncTimedMinConstraints();
            syncHiddenDatetimeFields();
        }

        function setupDateSync() {
            if (!fieldStartsAt || !fieldEndsAt || !fieldStartsAtDate || !fieldEndsAtDate) {
                return;
            }

            const hasTimedSplitInputs = fieldStartsAtDatePart && fieldStartsAtTimePart && fieldEndsAtDatePart && fieldEndsAtTimePart;

            if (hasTimedSplitInputs) {
                const handleTimedStartChange = function () {
                    const newStart = parseDateTimeParts(fieldStartsAtDatePart.value, fieldStartsAtTimePart.value);
                    if (!newStart) {
                        syncHiddenDatetimeFields();
                        return;
                    }

                    const oldStart = fieldStartsAt.value ? new Date(fieldStartsAt.value) : null;
                    const currentEnd = parseDateTimeParts(fieldEndsAtDatePart.value, fieldEndsAtTimePart.value);

                    if (!currentEnd) {
                        setTimedEndParts(toDatetimeLocal(new Date(newStart.getTime() + 3600000)));
                    } else {
                        let duration = (oldStart && !isNaN(oldStart.getTime())) ? currentEnd - oldStart : 3600000;
                        if (duration <= 0) duration = 3600000;
                        setTimedEndParts(toDatetimeLocal(new Date(newStart.getTime() + duration)));
                    }

                    syncTimedMinConstraints();
                    syncHiddenDatetimeFields();
                };

                const handleTimedEndChange = function () {
                    const start = parseDateTimeParts(fieldStartsAtDatePart.value, fieldStartsAtTimePart.value);
                    const end = parseDateTimeParts(fieldEndsAtDatePart.value, fieldEndsAtTimePart.value);
                    if (start && end && end <= start) {
                        setTimedEndParts(toDatetimeLocal(new Date(start.getTime() + 3600000)));
                    }
                    syncTimedMinConstraints();
                    syncHiddenDatetimeFields();
                };

                fieldStartsAtDatePart.addEventListener('change', handleTimedStartChange);
                fieldStartsAtTimePart.addEventListener('change', handleTimedStartChange);
                fieldEndsAtDatePart.addEventListener('change', handleTimedEndChange);
                fieldEndsAtTimePart.addEventListener('change', handleTimedEndChange);
            }

            fieldStartsAtDate.addEventListener('focus', function () { fieldStartsAtDate._prev = fieldStartsAtDate.value; });
            fieldStartsAtDate.addEventListener('change', function () {
                if (!fieldStartsAtDate.value) return;
                fieldEndsAtDate.min = fieldStartsAtDate.value;
                if (!fieldEndsAtDate.value || fieldEndsAtDate.value < fieldStartsAtDate.value) {
                    const oldStart = fieldStartsAtDate._prev ? new Date(fieldStartsAtDate._prev + 'T00:00') : null;
                    const currentEnd = fieldEndsAtDate.value ? new Date(fieldEndsAtDate.value + 'T00:00') : null;
                    const newStart = new Date(fieldStartsAtDate.value + 'T00:00');
                    let durationDays = (oldStart && currentEnd && !isNaN(oldStart)) ? Math.round((currentEnd - oldStart) / 86400000) : 0;
                    if (durationDays < 0) durationDays = 0;
                    const newEnd = new Date(newStart.getTime() + durationDays * 86400000);
                    const pad = function (value) { return String(value).padStart(2, '0'); };
                    fieldEndsAtDate.value = newEnd.getFullYear() + '-' + pad(newEnd.getMonth() + 1) + '-' + pad(newEnd.getDate());
                }
                fieldStartsAtDate._prev = fieldStartsAtDate.value;
            });

            fieldEndsAtDate.addEventListener('change', function () {
                if (!fieldEndsAtDate.value || !fieldStartsAtDate.value) return;
                if (fieldEndsAtDate.value < fieldStartsAtDate.value) {
                    fieldEndsAtDate.value = fieldStartsAtDate.value;
                }
            });
        }

        function prepareFormBeforeSubmit() {
            if (fieldAllDay && fieldAllDay.checked) {
                const startDate = fieldStartsAtDate.value;
                const endDate = fieldEndsAtDate.value || startDate;
                if (!startDate) {
                    notifyInvalid('Informe a data de início.');
                    return false;
                }
                if (endDate < startDate) {
                    notifyInvalid('A data de fim não pode ser anterior à data de início.');
                    return false;
                }
                fieldStartsAt.value = startDate + 'T00:00';
                fieldEndsAt.value = (endDate || startDate) + 'T23:59';
                fieldStartsAt.required = false;
                fieldEndsAt.required = false;
                return true;
            }

            syncHiddenDatetimeFields();
            const startValue = fieldStartsAt ? fieldStartsAt.value : '';
            const endValue = fieldEndsAt ? fieldEndsAt.value : '';
            if (!startValue || !endValue) {
                notifyInvalid('Informe data e hora de início e fim.');
                return false;
            }
            if (startValue && endValue && new Date(endValue) <= new Date(startValue)) {
                notifyInvalid('O horário de fim deve ser posterior ao horário de início.');
                return false;
            }
            return true;
        }

        function openCreateModal(dateStr) {
            editId = null;
            if (modalTitle) modalTitle.textContent = config.createTitle || 'Novo evento';
            if (form) form.action = config.createUrl || form.action;
            if (deleteButton) deleteButton.style.display = 'none';
            if (form) form.reset();

            const pad = function (value) { return String(value).padStart(2, '0'); };
            const baseDate = dateStr || (function () {
                const now = new Date();
                return now.getFullYear() + '-' + pad(now.getMonth() + 1) + '-' + pad(now.getDate());
            })();
            if (fieldStartsAtDatePart) {
                fieldStartsAtDatePart.value = baseDate;
            }
            if (fieldStartsAtTimePart) {
                fieldStartsAtTimePart.value = '09:00';
            }
            if (fieldEndsAtDatePart) {
                fieldEndsAtDatePart.value = baseDate;
            }
            if (fieldEndsAtTimePart) {
                fieldEndsAtTimePart.value = '10:00';
            }
            if (fieldStartsAtDate) {
                fieldStartsAtDate.value = baseDate;
                fieldStartsAtDate._prev = baseDate;
            }
            if (fieldEndsAtDate) {
                fieldEndsAtDate.value = baseDate;
                fieldEndsAtDate.min = baseDate;
            }
            syncTimedMinConstraints();
            syncHiddenDatetimeFields();
            toggleAllDay(false);
            resetMeetUI(null);
            modal.classList.add('is-open');
            window.setTimeout(function () {
                if (fieldTitle) fieldTitle.focus();
            }, 60);
        }

        function openEditModal(eventData) {
            editId = eventData.id;
            if (modalTitle) modalTitle.textContent = config.editTitle || 'Editar evento';
            if (form && config.editUrlTemplate) form.action = makeUrl(config.editUrlTemplate, eventData.id);
            if (deleteButton) deleteButton.style.display = typeof config.onDelete === 'function' ? '' : 'none';

            if (fieldTitle) fieldTitle.value = eventData.title || '';
            if (fieldLocation) fieldLocation.value = eventData.location || '';
            if (fieldDescription) fieldDescription.value = eventData.description || '';

            if (eventData.is_all_day) {
                const startDate = (eventData.starts_at || '').slice(0, 10);
                const endDate = (eventData.ends_at || '').slice(0, 10);
                if (fieldStartsAtDate) {
                    fieldStartsAtDate.value = startDate;
                    fieldStartsAtDate._prev = startDate;
                }
                if (fieldEndsAtDate) {
                    fieldEndsAtDate.value = endDate;
                    fieldEndsAtDate.min = startDate;
                }

                setTimedStartParts(startDate + 'T09:00');
                setTimedEndParts((endDate || startDate) + 'T10:00');
            } else {
                const startValue = eventData.starts_at && eventData.starts_at.length === 16 ? eventData.starts_at : String(eventData.starts_at || '').slice(0, 16);
                const endValue = eventData.ends_at && eventData.ends_at.length === 16 ? eventData.ends_at : String(eventData.ends_at || '').slice(0, 16);
                if (fieldStartsAtDate) {
                    fieldStartsAtDate.value = startValue.slice(0, 10);
                    fieldStartsAtDate._prev = startValue.slice(0, 10);
                }
                if (fieldEndsAtDate) {
                    fieldEndsAtDate.value = endValue.slice(0, 10);
                    fieldEndsAtDate.min = startValue.slice(0, 10);
                }
                setTimedStartParts(startValue);
                setTimedEndParts(endValue);
            }

            syncTimedMinConstraints();
            syncHiddenDatetimeFields();
            if (fieldAllDay) fieldAllDay.checked = !!eventData.is_all_day;
            toggleAllDay(!!eventData.is_all_day);
            resetMeetUI(eventData.meet_link || null);
            modal.classList.add('is-open');
            window.setTimeout(function () {
                if (fieldTitle) fieldTitle.focus();
            }, 60);
        }

        function deleteCurrentEvent() {
            if (!editId || typeof config.onDelete !== 'function') {
                return;
            }
            config.onDelete(editId, api);
        }

        modal.addEventListener('click', handleOverlayClick);
        modal.querySelectorAll('[data-calendar-modal-close]').forEach(function (button) {
            button.addEventListener('click', function () {
                closeModal();
            });
        });
        modal.querySelectorAll('[data-calendar-modal-action="copy-meet"]').forEach(function (button) {
            button.addEventListener('click', function () { copyMeetLink(button); });
        });
        modal.querySelectorAll('[data-calendar-modal-action="regen-meet"]').forEach(function (button) {
            button.addEventListener('click', requestNewMeetLink);
        });
        modal.querySelectorAll('[data-calendar-modal-action="cancel-regen-meet"]').forEach(function (button) {
            button.addEventListener('click', cancelNewMeetLink);
        });
        modal.querySelectorAll('[data-calendar-modal-action="delete-current"]').forEach(function (button) {
            button.addEventListener('click', deleteCurrentEvent);
        });
        if (fieldAllDay) {
            fieldAllDay.addEventListener('change', function () { toggleAllDay(fieldAllDay.checked); });
        }
        if (fieldMeet) {
            fieldMeet.addEventListener('change', function () { toggleMeet(fieldMeet.checked); });
        }

        if (form) {
            form.addEventListener('submit', function (event) {
                if (!prepareFormBeforeSubmit()) {
                    event.preventDefault();
                    return;
                }
                if (typeof config.onSubmit === 'function') {
                    event.preventDefault();
                    config.onSubmit(event, api);
                }
            });
        }

        setupDateSync();

        const api = {
            closeModal: closeModal,
            openCreateModal: openCreateModal,
            openEditModal: openEditModal,
            prepareFormBeforeSubmit: prepareFormBeforeSubmit,
            resetMeetUI: resetMeetUI,
            getEditId: function () { return editId; },
            getForm: function () { return form; },
            getModal: function () { return modal; },
        };
        return api;
    }

    window.createCalendarEventModal = createCalendarEventModal;
})();
