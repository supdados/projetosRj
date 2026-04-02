(function (global) {
    var registry = global.TaskItemsKanbanModules = global.TaskItemsKanbanModules || {};

    registry.drawerCore = function registerDrawerCore(ctx) {
        var refs = ctx.refs;
        var state = ctx.state;

        function setDrawerDeleteConfirmVisible(visible) {
            if (!ctx.hasDrawer() || !refs.drawerDeleteConfirm) return;
            if (visible) {
                refs.drawerDeleteConfirm.removeAttribute('hidden');
            } else {
                refs.drawerDeleteConfirm.setAttribute('hidden', '');
            }
            refs.drawer.classList.toggle('is-delete-confirming', !!visible);
            refs.drawerDeleteIcon.classList.toggle('is-active', !!visible);
        }

        function setDrawerAutosaveStatus(stateName, message) {
            if (!ctx.hasDrawer() || !refs.drawerAutosaveStatus) return;
            var normalizedState = stateName || 'idle';
            refs.drawerAutosaveStatus.classList.remove('is-saving', 'is-saved', 'is-error', 'is-invalid');

            if (message) {
                if (normalizedState !== 'idle') {
                    refs.drawerAutosaveStatus.classList.add('is-' + normalizedState);
                }
                refs.drawerAutosaveStatus.textContent = message;
                return;
            }

            if (normalizedState === 'idle') {
                refs.drawerAutosaveStatus.textContent = '';
            } else if (normalizedState === 'saving') {
                refs.drawerAutosaveStatus.classList.add('is-saving');
                refs.drawerAutosaveStatus.textContent = 'Salvando...';
            } else if (normalizedState === 'error') {
                refs.drawerAutosaveStatus.classList.add('is-error');
                refs.drawerAutosaveStatus.textContent = 'Não foi possível salvar.';
            } else if (normalizedState === 'invalid') {
                refs.drawerAutosaveStatus.classList.add('is-invalid');
                refs.drawerAutosaveStatus.textContent = 'Descrição é obrigatória.';
            } else {
                refs.drawerAutosaveStatus.classList.add('is-saved');
                refs.drawerAutosaveStatus.textContent = 'Salvo';
            }
        }

        function resizeDrawerDescTextarea() {
            if (!ctx.hasDrawer() || !refs.drawerDesc) return;
            refs.drawerDesc.style.height = '0px';
            var computed = window.getComputedStyle(refs.drawerDesc);
            var lineHeight = parseFloat(computed.lineHeight || '20');
            if (!Number.isFinite(lineHeight) || lineHeight <= 0) lineHeight = 20;
            var minHeight = Math.round((lineHeight * 2) + 24);
            var nextHeight = Math.max(minHeight, refs.drawerDesc.scrollHeight + 2);
            refs.drawerDesc.style.height = nextHeight + 'px';
        }

        function setDrawerSaving(isSaving) {
            state.drawerState.isSaving = !!isSaving;
            if (!ctx.hasDrawer()) return;
            refs.drawer.classList.toggle('is-saving', state.drawerState.isSaving);
            ctx.refreshDrawerActionControls();
        }

        function setDrawerStatus(status) {
            if (!ctx.hasDrawer()) return;
            var normalized = ctx.normalizeStatus(status);
            refs.drawerStatusBadge.classList.remove('status-nao_iniciada', 'status-em_andamento', 'status-para_validacao', 'status-para_ajustes', 'status-finalizada');
            refs.drawerStatusBadge.classList.add('status-' + normalized);
            refs.drawerStatusBadge.textContent = ctx.getStatusLabel(normalized);
        }

        function setDrawerResponsavel(names) {
            state.drawerState.responsavelNames = (names || []).slice();
            if (!ctx.hasDrawer()) return;
            renderResponsavelPickerTrigger(refs.drawerResponsavelTrigger, state.drawerState.responsavelNames, 'Responsável');
        }

        function buildDrawerPayload(itemId) {
            if (!ctx.hasDrawer() || !itemId) return null;
            var row = getTaskItemRowById(itemId);
            if (!row) return null;
            return {
                descricao: (refs.drawerDesc.value || '').trim(),
                status: getTaskItemStatus(row),
                responsavel: state.drawerState.responsavelNames.join(', '),
                prioridade: refs.drawerPrioridade ? refs.drawerPrioridade.value : '',
                tipo_pedido: refs.drawerTipoPedido ? refs.drawerTipoPedido.value : '',
            };
        }

        function scheduleDrawerAutosave(options) {
            if (!ctx.hasDrawer() || !state.drawerState.itemId || state.isDeleting) return;
            var opts = options || {};
            ctx.clearDrawerAutosaveTimer();

            var payload = buildDrawerPayload(state.drawerState.itemId);
            if (!payload) return;
            if (!payload.descricao) {
                state.drawerState.hasUnsavedChanges = true;
                setDrawerAutosaveStatus('invalid');
                return;
            }

            var snapshot = ctx.payloadSnapshot(payload);
            if (snapshot !== state.drawerState.lastSavedSnapshot) {
                state.drawerState.hasUnsavedChanges = true;
                setDrawerAutosaveStatus();
            } else if (!state.drawerState.isSaving && !state.drawerState.hasPendingSave) {
                state.drawerState.hasUnsavedChanges = false;
                setDrawerAutosaveStatus();
            }

            if (opts.immediate) {
                flushDrawerAutosave('immediate');
                return;
            }

            state.drawerState.autosaveTimer = setTimeout(function () {
                flushDrawerAutosave('debounce');
            }, state.drawerState.autosaveDebounceMs);
        }

        function flushDrawerAutosave(source) {
            ctx.clearDrawerAutosaveTimer();
            if (!ctx.hasDrawer() || !state.drawerState.itemId || state.isDeleting) return Promise.resolve(false);

            var itemId = String(state.drawerState.itemId);
            var payload = buildDrawerPayload(itemId);
            if (!payload) return Promise.resolve(false);

            if (!payload.descricao) {
                state.drawerState.hasUnsavedChanges = true;
                setDrawerAutosaveStatus('invalid');
                return Promise.resolve(false);
            }

            var snapshot = ctx.payloadSnapshot(payload);
            if (snapshot === state.drawerState.lastSavedSnapshot) {
                state.drawerState.hasUnsavedChanges = false;
                setDrawerAutosaveStatus();
                return Promise.resolve(true);
            }

            if (state.drawerState.isSaving) {
                state.drawerState.hasPendingSave = true;
                return Promise.resolve(false);
            }

            var token = ++state.drawerState.saveToken;
            var saveReason = source || 'unknown';
            setDrawerSaving(true);
            setDrawerAutosaveStatus('saving');

            return persistTaskItemDetails(itemId, payload)
                .then(function (data) {
                    if (token !== state.drawerState.saveToken) return false;
                    if (!data || !data.item) {
                        throw new Error('Erro ao salvar tarefa.');
                    }

                    updateTaskItemRowFromPayload(data.item);
                    ctx.syncCardFromRow(itemId);
                    state.drawerState.lastSavedSnapshot = ctx.payloadSnapshot({
                        descricao: data.item.descricao || payload.descricao,
                        status: data.item.status || payload.status,
                        responsavel: typeof data.item.responsavel === 'string' ? data.item.responsavel : payload.responsavel,
                        prioridade: typeof data.item.prioridade === 'string' ? data.item.prioridade : payload.prioridade,
                        tipo_pedido: typeof data.item.tipo_pedido === 'string' ? data.item.tipo_pedido : payload.tipo_pedido,
                    });
                    state.drawerState.hasUnsavedChanges = false;
                    setDrawerAutosaveStatus('saved', saveReason === 'blur' ? 'Salvo' : '');
                    syncDrawerFromCurrentRow();
                    return true;
                })
                .catch(function (error) {
                    if (token !== state.drawerState.saveToken) return false;
                    state.drawerState.hasUnsavedChanges = true;
                    var message = (error && error.message) || '';
                    if (/descri[cç][aã]o.*obrigat[óo]ria/i.test(message)) {
                        setDrawerAutosaveStatus('invalid');
                    } else {
                        setDrawerAutosaveStatus('error', message || 'Não foi possível salvar.');
                    }
                    return false;
                })
                .finally(function () {
                    if (token !== state.drawerState.saveToken) return;
                    setDrawerSaving(false);
                    if (state.drawerState.hasPendingSave) {
                        state.drawerState.hasPendingSave = false;
                        flushDrawerAutosave('queued');
                    }
                });
        }

        function syncDrawerFromCurrentRow() {
            if (!ctx.hasDrawer() || !state.drawerState.itemId) return;
            var row = getTaskItemRowById(state.drawerState.itemId);
            if (!row) {
                closeDrawer();
                return;
            }
            var canEditRestricted = !!(typeof getTaskItemCanDelete === 'function' && getTaskItemCanDelete(row));
            ctx.setDrawerRestrictedFieldLocks(canEditRestricted);

            var descricao = getTaskItemDescricao(row);
            var responsavel = getTaskItemResponsavel(row);
            var status = getTaskItemStatus(row);
            var prioridade = getTaskItemPrioridade(row);
            var tipoPedido = getTaskItemTipoPedido(row);
            var anexosCount = getTaskItemAnexosCount(row);

            if (!state.drawerState.isSaving && !state.drawerState.hasUnsavedChanges) {
                refs.drawerDesc.value = descricao;
                resizeDrawerDescTextarea();
                setDrawerResponsavel(splitResponsavelNames(responsavel));
                if (refs.drawerPrioridade) refs.drawerPrioridade.value = prioridade || '';
                if (refs.drawerTipoPedido) refs.drawerTipoPedido.value = tipoPedido || '';
                state.drawerState.lastSavedSnapshot = ctx.payloadSnapshot({
                    descricao: descricao,
                    status: status,
                    responsavel: responsavel,
                    prioridade: prioridade,
                    tipo_pedido: tipoPedido,
                });
            }
            setDrawerStatus(status);
            if (refs.drawerAnexosCount) refs.drawerAnexosCount.textContent = String(anexosCount);
            refs.drawerTitle.textContent = (refs.drawerDesc.value || '').trim() || descricao || 'Item sem descrição';
            ctx.renderDrawerCommentsFromRow(row, { forceBottom: state.drawerState.forceCommentsBottom });
            state.drawerState.forceCommentsBottom = false;
            ctx.refreshDrawerActionControls();
        }

        function openDrawer(itemId) {
            if (!ctx.hasDrawer()) return;
            var row = getTaskItemRowById(itemId);
            if (!row) return;
            state.drawerState.itemId = String(itemId);
            state.drawerState.hasPendingSave = false;
            state.drawerState.hasUnsavedChanges = false;
            state.drawerState.forceCommentsBottom = true;
            ctx.clearDrawerAutosaveTimer();
            ctx.hideDrawerPermissionBanner();
            ctx.clearDrawerCommentsStatusTimer();
            syncDrawerFromCurrentRow();
            setDrawerSaving(false);
            ctx.setDrawerCommentsBusy(false);
            setDrawerDeleteConfirmVisible(false);
            setDrawerAutosaveStatus();
            refs.drawerCommentForm.reset();
            ctx.resizeDrawerCommentTextarea();
            resizeDrawerDescTextarea();
            ctx.refreshDrawerCommentComposer();
            ctx.setDrawerCommentsStatus();
            ctx.setDrawerCommentsExpanded(false, { instant: true });

            if (refs.drawerAnexosToggle) {
                refs.drawerAnexosToggle.setAttribute('aria-expanded', 'false');
                refs.drawerAnexosToggle.classList.remove('is-expanded');
            }
            if (refs.drawerAnexosBody) refs.drawerAnexosBody.setAttribute('hidden', '');
            if (refs.drawerAnexosList) refs.drawerAnexosList.innerHTML = '';
            if (refs.drawerAnexosCount) refs.drawerAnexosCount.textContent = '0';

            refs.drawer.removeAttribute('hidden');
            refs.drawerBackdrop.removeAttribute('hidden');
            refs.drawer.setAttribute('aria-hidden', 'false');
            document.body.classList.add('task-item-drawer-open');
            requestAnimationFrame(function () {
                refs.drawer.classList.add('is-open');
                refs.drawerBackdrop.classList.add('is-open');
                resizeDrawerDescTextarea();
                setTimeout(function () {
                    resizeDrawerDescTextarea();
                }, 180);
            });
        }

        function performDrawerClose() {
            if (!ctx.hasDrawer()) return;
            ctx.clearDrawerAutosaveTimer();
            ctx.clearDrawerCommentsStatusTimer();
            state.drawerState.isClosing = false;
            state.drawerState.hasPendingSave = false;
            state.drawerState.hasUnsavedChanges = false;
            state.drawerState.forceCommentsBottom = false;
            state.drawerState.isCommentsExpanded = false;
            state.drawerState.itemId = null;
            ctx.setDrawerRestrictedFieldLocks(true);
            ctx.hideDrawerPermissionBanner();
            refs.drawer.classList.remove('is-open');
            refs.drawerBackdrop.classList.remove('is-open');
            refs.drawer.setAttribute('aria-hidden', 'true');
            setDrawerDeleteConfirmVisible(false);
            ctx.setDrawerCommentsExpanded(false, { instant: true });
            ctx.clearDrawerCommentsTransitionTimer();
            document.body.classList.remove('task-item-drawer-open');
            setTimeout(function () {
                if (state.drawerState.itemId) return;
                refs.drawer.setAttribute('hidden', '');
                refs.drawerBackdrop.setAttribute('hidden', '');
                refs.drawerCommentsList.innerHTML = '';
                if (refs.drawerAnexosList) refs.drawerAnexosList.innerHTML = '';
                if (refs.drawerAnexosCount) refs.drawerAnexosCount.textContent = '0';
                refs.drawerTitle.textContent = 'Item';
                setDrawerAutosaveStatus();
                ctx.setDrawerCommentsStatus();
                refs.drawerCommentForm.reset();
                ctx.resizeDrawerCommentTextarea();
                resizeDrawerDescTextarea();
                ctx.refreshDrawerCommentComposer();
            }, 160);
        }

        function closeDrawer(options) {
            if (!ctx.hasDrawer()) return;
            var opts = options || {};
            var force = opts.force === true;
            var currentItemId = state.drawerState.itemId ? String(state.drawerState.itemId) : '';

            if (!currentItemId) {
                performDrawerClose();
                return;
            }

            if (!force && !state.isDeleting) {
                if (state.drawerState.isClosing) return;
                state.drawerState.isClosing = true;
                flushDrawerAutosave('close')
                    .catch(function () {})
                    .finally(function () {
                        if (state.drawerState.itemId && String(state.drawerState.itemId) !== currentItemId) {
                            state.drawerState.isClosing = false;
                            return;
                        }
                        performDrawerClose();
                    });
                return;
            }

            performDrawerClose();
        }

        function openDrawerComments(itemId) {
            openDrawer(itemId);
            setTimeout(function () {
                if (refs.drawerCommentsToggle && refs.drawerCommentsToggle.getAttribute('aria-expanded') !== 'true') {
                    ctx.setDrawerCommentsExpanded(true);
                }
            }, 80);
        }

        function bindDrawerEvents() {
            if (!ctx.hasDrawer()) return;

            refs.drawerClose.addEventListener('click', closeDrawer);
            refs.drawerBackdrop.addEventListener('click', closeDrawer);
            refs.drawerDeleteIcon.addEventListener('click', function () {
                if (!state.drawerState.itemId || state.drawerState.isSaving || state.isDeleting) return;
                setDrawerDeleteConfirmVisible(true);
            });
            refs.drawerDeleteCancel.addEventListener('click', function () {
                setDrawerDeleteConfirmVisible(false);
            });
            refs.drawerDeleteConfirmBtn.addEventListener('click', function () {
                if (!state.drawerState.itemId || state.isDeleting || state.drawerState.isSaving) return;
                ctx.deleteKanbanItem(String(state.drawerState.itemId));
            });

            refs.drawerCommentsToggle.addEventListener('click', function () {
                if (!state.drawerState.itemId || state.isDeleting) return;
                ctx.setDrawerCommentsExpanded(!state.drawerState.isCommentsExpanded);
            });
            refs.drawerCommentsToggle.addEventListener('keydown', function (event) {
                if (event.key !== 'Enter' && event.key !== ' ') return;
                event.preventDefault();
                refs.drawerCommentsToggle.click();
            });

            refs.drawerResponsavelTrigger.addEventListener('click', function (event) {
                event.preventDefault();
                event.stopPropagation();
                if (!state.drawerState.itemId || state.isDeleting) return;
                if (ctx.handleDrawerRestrictedInteraction(event)) return;
                var drawerProjectValue = getTaskItemProjectValue(state.drawerState.itemId);
                if (!drawerProjectValue) {
                    alert('Projeto não encontrado para esta tarefa.');
                    return;
                }

                responsavelPickerManager.open({
                    anchorEl: refs.drawerResponsavelTrigger,
                    taskId: ctx.taskId,
                    sugestoesUrl: refs.listEl.getAttribute('data-sugestoes-url') || '',
                    projectValue: drawerProjectValue,
                    initialRawValue: state.drawerState.responsavelNames.join(', '),
                    onApply: function (payload) {
                        setDrawerResponsavel(payload.names.slice());
                        if (payload && payload.dirty) {
                            scheduleDrawerAutosave({ immediate: true });
                        }
                        return true;
                    },
                });
            });

            refs.drawerDesc.addEventListener('click', function (event) {
                if (!state.drawerState.itemId || state.isDeleting) return;
                if (!state.drawerState.canEditRestricted) {
                    ctx.handleDrawerRestrictedInteraction(event);
                }
            });
            refs.drawerDesc.addEventListener('keydown', function (event) {
                if (!state.drawerState.itemId || state.isDeleting) return;
                if (!state.drawerState.canEditRestricted) {
                    ctx.handleDrawerRestrictedInteraction(event);
                }
            });
            refs.drawerDesc.addEventListener('input', function () {
                if (!state.drawerState.itemId || state.isDeleting) return;
                if (!state.drawerState.canEditRestricted) return;
                refs.drawerTitle.textContent = (refs.drawerDesc.value || '').trim() || 'Item sem descrição';
                resizeDrawerDescTextarea();
                scheduleDrawerAutosave();
            });
            refs.drawerDesc.addEventListener('change', function () {
                if (!state.drawerState.itemId || state.isDeleting) return;
                if (!state.drawerState.canEditRestricted) return;
                resizeDrawerDescTextarea();
            });
            refs.drawerDesc.addEventListener('keyup', function () {
                if (!state.drawerState.itemId || state.isDeleting) return;
                if (!state.drawerState.canEditRestricted) return;
                resizeDrawerDescTextarea();
            });
            refs.drawerDesc.addEventListener('blur', function () {
                if (!state.drawerState.itemId || state.isDeleting) return;
                if (!state.drawerState.canEditRestricted) return;
                flushDrawerAutosave('blur');
            });

            if (refs.drawerPrioridade) {
                refs.drawerPrioridade.addEventListener('pointerdown', function (event) {
                    if (!state.drawerState.itemId || state.isDeleting) return;
                    if (!state.drawerState.canEditRestricted) {
                        ctx.handleDrawerRestrictedInteraction(event);
                    }
                });
                refs.drawerPrioridade.addEventListener('mousedown', function (event) {
                    if (!state.drawerState.itemId || state.isDeleting) return;
                    if (!state.drawerState.canEditRestricted) {
                        ctx.handleDrawerRestrictedInteraction(event);
                    }
                });
                refs.drawerPrioridade.addEventListener('keydown', function (event) {
                    if (!state.drawerState.itemId || state.isDeleting) return;
                    if (state.drawerState.canEditRestricted) return;
                    if (event.key === 'ArrowDown' || event.key === 'ArrowUp' || event.key === 'Enter' || event.key === ' ') {
                        ctx.handleDrawerRestrictedInteraction(event);
                    }
                });
                refs.drawerPrioridade.addEventListener('change', function () {
                    if (!state.drawerState.itemId || state.isDeleting) return;
                    if (!state.drawerState.canEditRestricted) {
                        var row = getTaskItemRowById(state.drawerState.itemId);
                        if (row) {
                            refs.drawerPrioridade.value = getTaskItemPrioridade(row) || '';
                        }
                        ctx.showDrawerPermissionBanner(ctx.drawerRestrictedEditMessage);
                        return;
                    }
                    scheduleDrawerAutosave({ immediate: true });
                });
            }
            if (refs.drawerTipoPedido) {
                refs.drawerTipoPedido.addEventListener('change', function () {
                    if (!state.drawerState.itemId || state.isDeleting) return;
                    scheduleDrawerAutosave({ immediate: true });
                });
            }

            if (refs.drawerAnexosToggle) {
                refs.drawerAnexosToggle.addEventListener('click', function () {
                    if (!state.drawerState.itemId) return;
                    var expanded = refs.drawerAnexosToggle.getAttribute('aria-expanded') === 'true';
                    refs.drawerAnexosToggle.setAttribute('aria-expanded', expanded ? 'false' : 'true');
                    refs.drawerAnexosToggle.classList.toggle('is-expanded', !expanded);
                    if (refs.drawerAnexosBody) {
                        if (expanded) {
                            refs.drawerAnexosBody.setAttribute('hidden', '');
                        } else {
                            refs.drawerAnexosBody.removeAttribute('hidden');
                            ctx.loadDrawerAnexos(state.drawerState.itemId);
                        }
                    }
                });
            }

            if (refs.drawerAnexoInput) {
                refs.drawerAnexoInput.addEventListener('change', function () {
                    if (!state.drawerState.itemId || !refs.drawerAnexoInput.files || !refs.drawerAnexoInput.files.length) return;
                    var file = refs.drawerAnexoInput.files[0];
                    ctx.uploadDrawerAnexo(state.drawerState.itemId, file);
                    refs.drawerAnexoInput.value = '';
                });
            }

            if (refs.quickAnexoInput) {
                refs.quickAnexoInput.addEventListener('change', function () {
                    if (!refs.quickAnexoInput.files || !refs.quickAnexoInput.files.length) {
                        state.quickUploadState.itemId = null;
                        return;
                    }
                    var itemId = state.quickUploadState.itemId;
                    var file = refs.quickAnexoInput.files[0];
                    refs.quickAnexoInput.value = '';
                    state.quickUploadState.itemId = null;
                    if (!itemId || !file) return;
                    ctx.performQuickAnexoUpload(itemId, file).catch(function (error) {
                        alert((error && error.message) || 'Erro ao enviar anexo.');
                    });
                });
            }

            var commentTextarea = ctx.getDrawerCommentTextarea();
            if (commentTextarea) {
                commentTextarea.addEventListener('input', function () {
                    ctx.resizeDrawerCommentTextarea();
                    ctx.refreshDrawerCommentComposer();
                    if (!state.drawerState.isCommentBusy) {
                        ctx.setDrawerCommentsStatus();
                    }
                });
            }

            refs.drawerCommentForm.addEventListener('submit', ctx.handleDrawerAddComment);
            refs.drawerCommentForm.addEventListener('keydown', function (event) {
                if (!(event.target && event.target.matches('textarea[name="content"]'))) return;
                if (event.key === 'Enter' && !event.shiftKey) {
                    event.preventDefault();
                    if (refs.drawerCommentForm.requestSubmit) refs.drawerCommentForm.requestSubmit();
                    else refs.drawerCommentForm.dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }));
                }
            });

            refs.drawerCommentsList.addEventListener('click', function (event) {
                var editBtn = event.target.closest('[data-action="edit-comment"][data-comment-id]');
                if (editBtn) {
                    event.preventDefault();
                    ctx.startDrawerCommentEdit(editBtn.getAttribute('data-comment-id'));
                    return;
                }

                var delBtn = event.target.closest('[data-action="delete-comment"][data-comment-id]');
                if (delBtn) {
                    event.preventDefault();
                    ctx.handleDrawerDeleteComment(delBtn.getAttribute('data-comment-id'));
                }
            });

            if (refs.drawerAnexosList) {
                refs.drawerAnexosList.addEventListener('click', function (event) {
                    var delBtn = event.target.closest('[data-action="delete-anexo"][data-anexo-id]');
                    if (delBtn) {
                        event.preventDefault();
                        ctx.handleDrawerAnexoDelete(delBtn.getAttribute('data-anexo-id'));
                        return;
                    }
                    var anexoLink = event.target.closest('.task-item-drawer-anexo-link');
                    if (anexoLink) {
                        event.preventDefault();
                        ctx.openAnexoPreviewModal({
                            url: anexoLink.getAttribute('href') || '',
                            filename: anexoLink.getAttribute('data-filename') || 'Anexo',
                            contentType: anexoLink.getAttribute('data-content-type') || '',
                            isImage: anexoLink.getAttribute('data-is-image') === '1',
                        });
                    }
                });
            }

            document.addEventListener('keydown', function (event) {
                if (event.key === 'Escape' && state.drawerState.itemId) {
                    if (state.previewState.isOpen) return;
                    if (!refs.drawerDeleteConfirm.hasAttribute('hidden')) {
                        setDrawerDeleteConfirmVisible(false);
                        return;
                    }
                    closeDrawer();
                }
            });

            ctx.resizeDrawerCommentTextarea();
            resizeDrawerDescTextarea();
            ctx.refreshDrawerCommentComposer();
        }

        ctx.setDrawerDeleteConfirmVisible = setDrawerDeleteConfirmVisible;
        ctx.setDrawerAutosaveStatus = setDrawerAutosaveStatus;
        ctx.resizeDrawerDescTextarea = resizeDrawerDescTextarea;
        ctx.setDrawerSaving = setDrawerSaving;
        ctx.setDrawerStatus = setDrawerStatus;
        ctx.setDrawerResponsavel = setDrawerResponsavel;
        ctx.buildDrawerPayload = buildDrawerPayload;
        ctx.scheduleDrawerAutosave = scheduleDrawerAutosave;
        ctx.flushDrawerAutosave = flushDrawerAutosave;
        ctx.syncDrawerFromCurrentRow = syncDrawerFromCurrentRow;
        ctx.openDrawer = openDrawer;
        ctx.performDrawerClose = performDrawerClose;
        ctx.closeDrawer = closeDrawer;
        ctx.openDrawerComments = openDrawerComments;
        ctx.bindDrawerEvents = bindDrawerEvents;
    };
})(window);
