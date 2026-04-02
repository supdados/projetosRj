(function (global) {
    var registry = global.TaskItemsKanbanModules = global.TaskItemsKanbanModules || {};

    registry.drawerAnexos = function registerDrawerAnexos(ctx) {
        var refs = ctx.refs;
        var state = ctx.state;

        function openDrawerAnexos(itemId) {
            ctx.openDrawer(itemId);
            setTimeout(function () {
                if (refs.drawerAnexosToggle && refs.drawerAnexosToggle.getAttribute('aria-expanded') !== 'true') {
                    refs.drawerAnexosToggle.click();
                }
            }, 80);
        }

        function performQuickAnexoUpload(itemId, file) {
            if (!itemId || !file) return Promise.resolve(false);
            var formData = new FormData();
            formData.append('file', file);
            return fetch('/tarefas/' + itemId + '/anexos/add', {
                method: 'POST',
                headers: { 'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json' },
                body: formData,
            })
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    if (!data.success) throw new Error(data.message || 'Erro ao enviar anexo.');
                    var row = getTaskItemRowById(itemId);
                    if (row) setTaskItemAnexosCount(row, data.anexos_count);
                    if (window.taskItemsKanban && typeof window.taskItemsKanban.syncItemFromRow === 'function') {
                        window.taskItemsKanban.syncItemFromRow(itemId);
                    }
                    openDrawerAnexos(itemId);
                    return true;
                });
        }

        function requestQuickAnexoUpload(itemId) {
            if (!itemId) return;
            if (!refs.quickAnexoInput) {
                openDrawerAnexos(itemId);
                return;
            }
            state.quickUploadState.itemId = String(itemId);
            refs.quickAnexoInput.value = '';
            refs.quickAnexoInput.click();
        }

        function openItemAnexoAction(itemId) {
            if (!itemId) return;
            var row = getTaskItemRowById(itemId);
            if (!row) {
                openDrawerAnexos(itemId);
                return;
            }
            var anexosCount = getTaskItemAnexosCount(row);
            if (anexosCount > 0) {
                openDrawerAnexos(itemId);
                return;
            }
            requestQuickAnexoUpload(itemId);
        }

        function hasAnexoPreviewModal() {
            return !!(
                refs.anexoPreviewModal &&
                refs.anexoPreviewBackdrop &&
                refs.anexoPreviewDialog &&
                refs.anexoPreviewBody &&
                refs.anexoPreviewTitle &&
                refs.anexoPreviewOpen &&
                refs.anexoPreviewDownload
            );
        }

        function clearAnexoPreviewContent() {
            if (!hasAnexoPreviewModal()) return;
            refs.anexoPreviewBody.innerHTML = '';
            refs.anexoPreviewTitle.textContent = 'Anexo';
            refs.anexoPreviewOpen.setAttribute('href', '#');
            refs.anexoPreviewDownload.setAttribute('href', '#');
            refs.anexoPreviewDownload.removeAttribute('download');
        }

        function closeAnexoPreviewModal() {
            if (!hasAnexoPreviewModal() || !state.previewState.isOpen) return;
            state.previewState.isOpen = false;
            refs.anexoPreviewModal.classList.remove('is-open');
            refs.anexoPreviewBackdrop.classList.remove('is-open');
            refs.anexoPreviewModal.setAttribute('aria-hidden', 'true');
            if (state.previewState.hideTimer) clearTimeout(state.previewState.hideTimer);
            state.previewState.hideTimer = setTimeout(function () {
                if (state.previewState.isOpen) return;
                refs.anexoPreviewModal.setAttribute('hidden', '');
                refs.anexoPreviewBackdrop.setAttribute('hidden', '');
                clearAnexoPreviewContent();
                state.previewState.hideTimer = null;
            }, 150);
        }

        function openAnexoPreviewModal(payload) {
            if (!hasAnexoPreviewModal()) return;
            var data = payload || {};
            var url = data.url || '';
            if (!url) return;
            var filename = data.filename || 'Anexo';
            var contentType = String(data.contentType || '').toLowerCase();
            var isImage = !!data.isImage || contentType.indexOf('image/') === 0;
            var isPdf = contentType.indexOf('pdf') !== -1 || /\.pdf($|\?)/i.test(url);

            clearAnexoPreviewContent();
            refs.anexoPreviewTitle.textContent = filename;
            refs.anexoPreviewOpen.setAttribute('href', url);
            refs.anexoPreviewDownload.setAttribute('href', url);
            refs.anexoPreviewDownload.setAttribute('download', filename);

            if (isImage) {
                var img = document.createElement('img');
                img.className = 'task-anexo-preview-image';
                img.src = url;
                img.alt = filename;
                img.loading = 'lazy';
                refs.anexoPreviewBody.appendChild(img);
            } else if (isPdf) {
                var iframe = document.createElement('iframe');
                iframe.className = 'task-anexo-preview-pdf';
                iframe.src = url;
                iframe.setAttribute('title', filename);
                refs.anexoPreviewBody.appendChild(iframe);
            } else {
                var fallback = document.createElement('div');
                fallback.className = 'task-anexo-preview-fallback';
                fallback.innerHTML =
                    '<i class="fas fa-file" aria-hidden="true"></i>' +
                    '<p>Preview não disponível para este tipo de arquivo.</p>' +
                    '<span>' + escapeAnexoHtml(filename) + '</span>';
                refs.anexoPreviewBody.appendChild(fallback);
            }

            if (state.previewState.hideTimer) {
                clearTimeout(state.previewState.hideTimer);
                state.previewState.hideTimer = null;
            }
            state.previewState.isOpen = true;
            refs.anexoPreviewModal.removeAttribute('hidden');
            refs.anexoPreviewBackdrop.removeAttribute('hidden');
            refs.anexoPreviewModal.setAttribute('aria-hidden', 'false');
            requestAnimationFrame(function () {
                refs.anexoPreviewModal.classList.add('is-open');
                refs.anexoPreviewBackdrop.classList.add('is-open');
            });
        }

        function bindAnexoPreviewModalEvents() {
            if (!hasAnexoPreviewModal()) return;
            if (refs.anexoPreviewClose) {
                refs.anexoPreviewClose.addEventListener('click', function () {
                    closeAnexoPreviewModal();
                });
            }
            if (refs.anexoPreviewBackdrop) {
                refs.anexoPreviewBackdrop.addEventListener('click', function () {
                    closeAnexoPreviewModal();
                });
            }
            if (refs.anexoPreviewModal && refs.anexoPreviewDialog) {
                refs.anexoPreviewModal.addEventListener('click', function (event) {
                    if (!state.previewState.isOpen) return;
                    if (refs.anexoPreviewDialog.contains(event.target)) return;
                    closeAnexoPreviewModal();
                });
            }
            document.addEventListener('keydown', function (event) {
                if (event.key === 'Escape' && state.previewState.isOpen) {
                    closeAnexoPreviewModal();
                }
            });
        }

        function escapeAnexoHtml(s) {
            var d = document.createElement('div');
            d.textContent = s;
            return d.innerHTML;
        }

        function renderDrawerAnexoItem(anexo) {
            var el = document.createElement('div');
            el.className = 'task-item-drawer-anexo-item';
            el.setAttribute('data-anexo-id', anexo.id);

            var isImg = !!anexo.is_image;
            var preview = '';
            if (isImg) {
                preview = '<img class="task-item-drawer-anexo-thumb" src="' + escapeAnexoHtml(anexo.url) + '" alt="' + escapeAnexoHtml(anexo.filename) + '" loading="lazy">';
            } else {
                preview = '<span class="task-item-drawer-anexo-icon"><i class="fas fa-file" aria-hidden="true"></i></span>';
            }

            el.innerHTML =
                '<a class="task-item-drawer-anexo-link" href="' + escapeAnexoHtml(anexo.url) + '" target="_blank" rel="noopener" data-filename="' + escapeAnexoHtml(anexo.filename) + '" data-content-type="' + escapeAnexoHtml(anexo.content_type || '') + '" data-is-image="' + (isImg ? '1' : '0') + '">' +
                preview +
                '<span class="task-item-drawer-anexo-name">' + escapeAnexoHtml(anexo.filename) + '</span>' +
                '</a>' +
                '<button type="button" class="task-item-drawer-anexo-del" data-action="delete-anexo" data-anexo-id="' + anexo.id + '" title="Remover anexo">' +
                '<i class="fas fa-times" aria-hidden="true"></i>' +
                '</button>';
            return el;
        }

        function loadDrawerAnexos(itemId) {
            if (!refs.drawerAnexosList) return;
            refs.drawerAnexosList.innerHTML = '<span class="task-item-drawer-anexos-loading">Carregando...</span>';

            fetch('/tarefas/' + itemId + '/anexos', {
                headers: { 'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json' },
            })
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    if (!data.success) throw new Error(data.message || 'Erro ao carregar anexos.');
                    refs.drawerAnexosList.innerHTML = '';
                    if (!data.anexos.length) {
                        var empty = document.createElement('p');
                        empty.className = 'task-item-drawer-anexos-empty';
                        empty.textContent = 'Nenhum anexo nesta tarefa.';
                        refs.drawerAnexosList.appendChild(empty);
                    } else {
                        data.anexos.forEach(function (a) {
                            refs.drawerAnexosList.appendChild(renderDrawerAnexoItem(a));
                        });
                    }
                    var row = getTaskItemRowById(itemId);
                    if (row) setTaskItemAnexosCount(row, data.count);
                    if (refs.drawerAnexosCount) refs.drawerAnexosCount.textContent = String(data.count);
                })
                .catch(function (e) {
                    if (refs.drawerAnexosList) refs.drawerAnexosList.innerHTML = '<p class="task-item-drawer-anexos-error">' + (e && e.message || 'Erro') + '</p>';
                });
        }

        function uploadDrawerAnexo(itemId, file) {
            if (!file || !itemId) return;
            var formData = new FormData();
            formData.append('file', file);

            var uploadingEl = document.createElement('div');
            uploadingEl.className = 'task-item-drawer-anexo-uploading';
            uploadingEl.textContent = 'Enviando ' + file.name + '...';
            if (refs.drawerAnexosList) refs.drawerAnexosList.appendChild(uploadingEl);

            fetch('/tarefas/' + itemId + '/anexos/add', {
                method: 'POST',
                headers: { 'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json' },
                body: formData,
            })
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    if (!data.success) throw new Error(data.message || 'Erro ao enviar.');
                    if (uploadingEl.parentNode) uploadingEl.parentNode.removeChild(uploadingEl);
                    var emptyEl = refs.drawerAnexosList ? refs.drawerAnexosList.querySelector('.task-item-drawer-anexos-empty') : null;
                    if (emptyEl) emptyEl.parentNode.removeChild(emptyEl);
                    if (refs.drawerAnexosList) refs.drawerAnexosList.appendChild(renderDrawerAnexoItem(data.anexo));
                    var row = getTaskItemRowById(itemId);
                    if (row) setTaskItemAnexosCount(row, data.anexos_count);
                    if (refs.drawerAnexosCount) refs.drawerAnexosCount.textContent = String(data.anexos_count);
                    if (window.taskItemsKanban && typeof window.taskItemsKanban.syncItemFromRow === 'function') {
                        window.taskItemsKanban.syncItemFromRow(itemId);
                    }
                })
                .catch(function (e) {
                    if (uploadingEl.parentNode) uploadingEl.parentNode.removeChild(uploadingEl);
                    alert((e && e.message) || 'Erro ao enviar anexo.');
                });
        }

        function handleDrawerAnexoDelete(anexoId) {
            if (!anexoId || !state.drawerState.itemId) return;
            if (!confirm('Remover este anexo?')) return;

            fetch('/tarefas/anexos/' + anexoId + '/delete', {
                method: 'POST',
                headers: { 'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json' },
            })
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    if (!data.success) throw new Error(data.message || 'Erro ao excluir.');
                    var itemEl = refs.drawerAnexosList ? refs.drawerAnexosList.querySelector('[data-anexo-id="' + anexoId + '"]') : null;
                    if (itemEl) itemEl.parentNode.removeChild(itemEl);
                    var row = getTaskItemRowById(state.drawerState.itemId);
                    if (row) setTaskItemAnexosCount(row, data.anexos_count);
                    if (refs.drawerAnexosCount) refs.drawerAnexosCount.textContent = String(data.anexos_count);
                    if (refs.drawerAnexosList && !refs.drawerAnexosList.querySelector('.task-item-drawer-anexo-item')) {
                        var empty = document.createElement('p');
                        empty.className = 'task-item-drawer-anexos-empty';
                        empty.textContent = 'Nenhum anexo nesta tarefa.';
                        refs.drawerAnexosList.appendChild(empty);
                    }
                    if (window.taskItemsKanban && typeof window.taskItemsKanban.syncItemFromRow === 'function') {
                        window.taskItemsKanban.syncItemFromRow(state.drawerState.itemId);
                    }
                })
                .catch(function (e) {
                    alert((e && e.message) || 'Erro ao remover anexo.');
                });
        }

        ctx.openDrawerAnexos = openDrawerAnexos;
        ctx.performQuickAnexoUpload = performQuickAnexoUpload;
        ctx.requestQuickAnexoUpload = requestQuickAnexoUpload;
        ctx.openItemAnexoAction = openItemAnexoAction;
        ctx.hasAnexoPreviewModal = hasAnexoPreviewModal;
        ctx.clearAnexoPreviewContent = clearAnexoPreviewContent;
        ctx.closeAnexoPreviewModal = closeAnexoPreviewModal;
        ctx.openAnexoPreviewModal = openAnexoPreviewModal;
        ctx.bindAnexoPreviewModalEvents = bindAnexoPreviewModalEvents;
        ctx.escapeAnexoHtml = escapeAnexoHtml;
        ctx.renderDrawerAnexoItem = renderDrawerAnexoItem;
        ctx.loadDrawerAnexos = loadDrawerAnexos;
        ctx.uploadDrawerAnexo = uploadDrawerAnexo;
        ctx.handleDrawerAnexoDelete = handleDrawerAnexoDelete;
    };
})(window);
