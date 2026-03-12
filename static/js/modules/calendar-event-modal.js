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

        function toggleAllDay(checked) {
            if (datetimePair) datetimePair.style.display = checked ? 'none' : '';
            if (datePair) datePair.style.display = checked ? '' : 'none';
            if (fieldStartsAt) fieldStartsAt.required = !checked;
            if (fieldEndsAt) fieldEndsAt.required = !checked;

            if (!checked) {
                const startDate = fieldStartsAtDate ? fieldStartsAtDate.value : '';
                const endDate = fieldEndsAtDate ? fieldEndsAtDate.value : '';
                if (startDate && fieldStartsAt) {
                    fieldStartsAt.value = startDate + (fieldStartsAt.value ? 'T' + fieldStartsAt.value.slice(11) : 'T09:00');
                }
                if (endDate && fieldEndsAt) {
                    fieldEndsAt.value = endDate + (fieldEndsAt.value ? 'T' + fieldEndsAt.value.slice(11) : 'T10:00');
                }
                return;
            }

            if (fieldStartsAt && fieldStartsAt.value && fieldStartsAtDate) {
                fieldStartsAtDate.value = fieldStartsAt.value.slice(0, 10);
            }
            if (fieldEndsAt && fieldEndsAt.value && fieldEndsAtDate) {
                fieldEndsAtDate.value = fieldEndsAt.value.slice(0, 10);
            }
            if (fieldEndsAtDate && fieldStartsAtDate) {
                fieldEndsAtDate.min = fieldStartsAtDate.value || '';
            }
        }

        function toggleMeet(checked) {
            if (meetGenerateRow) meetGenerateRow.classList.toggle('is-active', checked);
            if (meetSub) meetSub.textContent = checked ? 'Link será gerado ao salvar' : 'Adicionar videochamada';
        }

        function toDatetimeLocal(date) {
            const pad = function (value) { return String(value).padStart(2, '0'); };
            return date.getFullYear() + '-' + pad(date.getMonth() + 1) + '-' + pad(date.getDate())
                + 'T' + pad(date.getHours()) + ':' + pad(date.getMinutes());
        }

        function setupDateSync() {
            if (!fieldStartsAt || !fieldEndsAt || !fieldStartsAtDate || !fieldEndsAtDate) {
                return;
            }

            fieldStartsAt.addEventListener('focus', function () { fieldStartsAt._prev = fieldStartsAt.value; });
            fieldStartsAt.addEventListener('change', function () {
                if (!fieldStartsAt.value) return;
                const newStart = new Date(fieldStartsAt.value);
                if (!fieldEndsAt.value) {
                    fieldEndsAt.value = toDatetimeLocal(new Date(newStart.getTime() + 3600000));
                } else {
                    const oldStart = fieldStartsAt._prev ? new Date(fieldStartsAt._prev) : null;
                    const currentEnd = new Date(fieldEndsAt.value);
                    let duration = (oldStart && !isNaN(oldStart.getTime())) ? currentEnd - oldStart : 3600000;
                    if (duration <= 0) duration = 3600000;
                    fieldEndsAt.value = toDatetimeLocal(new Date(newStart.getTime() + duration));
                }
                fieldStartsAt._prev = fieldStartsAt.value;
                fieldEndsAt.min = fieldStartsAt.value;
            });

            fieldEndsAt.addEventListener('change', function () {
                if (!fieldEndsAt.value || !fieldStartsAt.value) return;
                if (new Date(fieldEndsAt.value) <= new Date(fieldStartsAt.value)) {
                    fieldEndsAt.value = toDatetimeLocal(new Date(new Date(fieldStartsAt.value).getTime() + 3600000));
                }
            });

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

            const startValue = fieldStartsAt ? fieldStartsAt.value : '';
            const endValue = fieldEndsAt ? fieldEndsAt.value : '';
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
            if (fieldStartsAt) {
                fieldStartsAt.value = baseDate + 'T09:00';
                fieldStartsAt.min = '';
                fieldStartsAt._prev = fieldStartsAt.value;
            }
            if (fieldEndsAt) {
                fieldEndsAt.value = baseDate + 'T10:00';
                fieldEndsAt.min = baseDate + 'T09:00';
            }
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
            if (fieldAllDay) fieldAllDay.checked = !!eventData.is_all_day;
            toggleAllDay(!!eventData.is_all_day);

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
            } else {
                const startValue = eventData.starts_at && eventData.starts_at.length === 16 ? eventData.starts_at : String(eventData.starts_at || '').slice(0, 16);
                const endValue = eventData.ends_at && eventData.ends_at.length === 16 ? eventData.ends_at : String(eventData.ends_at || '').slice(0, 16);
                if (fieldStartsAt) {
                    fieldStartsAt.value = startValue;
                    fieldStartsAt._prev = startValue;
                }
                if (fieldEndsAt) {
                    fieldEndsAt.value = endValue;
                    fieldEndsAt.min = startValue;
                }
            }

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
