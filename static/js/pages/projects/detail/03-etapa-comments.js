    document.addEventListener('DOMContentLoaded', function () {
        const etapasTbody = document.getElementById('etapas-tbody');
        if (!etapasTbody) {
            return;
        }

        let comentarioAtualEditando = null;
        const canEditEtapas = etapasTbody.dataset.canEdit === 'true';

        function getCommentData(etapaId) {
            const btnData = etapasTbody.querySelector(`.btn-comment-data[data-etapa-id="${etapaId}"]`);
            return btnData ? (btnData.dataset.comentario || '') : '';
        }

        function updateCommentData(etapaId, comentario) {
            const btnData = etapasTbody.querySelector(`.btn-comment-data[data-etapa-id="${etapaId}"]`);
            if (btnData) {
                btnData.dataset.comentario = comentario || '';
            }
        }

        function escapeHtml(value) {
            return String(value || '')
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#39;');
        }

        function autoResizeTextarea(textarea) {
            textarea.style.height = 'auto';
            textarea.style.height = `${textarea.scrollHeight}px`;
        }

        function renderCommentState(etapaId, comentario) {
            const row = etapasTbody.querySelector(`tr[data-etapa-id="${etapaId}"]`);
            if (!row) {
                return;
            }
            const commentContainer = row.querySelector('.etapa-descricao-comment');
            if (!commentContainer) {
                return;
            }

            const trimmedComentario = (comentario || '').trim();
            updateCommentData(etapaId, trimmedComentario);
            commentContainer.innerHTML = '';

            if (trimmedComentario) {
                const display = document.createElement('div');
                display.className = 'small text-muted etapa-comentario-display ds-cursor-pointer';
                display.dataset.etapaId = etapaId;
                display.title = 'Clique para editar';
                display.textContent = trimmedComentario;
                commentContainer.appendChild(display);
                return;
            }

            if (!canEditEtapas) {
                return;
            }

            const placeholder = document.createElement('div');
            placeholder.className = 'small text-muted etapa-comentario-placeholder ds-cursor-pointer';
            placeholder.dataset.etapaId = etapaId;
            placeholder.dataset.comentario = '';
            placeholder.innerHTML = '<i class="fas fa-comment-medical me-1"></i> adicionar comentário';
            commentContainer.appendChild(placeholder);
        }

        function abrirEdicaoInline(elemento, etapaId, comentarioAtual) {
            // Cancelar qualquer edição anterior
            if (comentarioAtualEditando) {
                cancelarEdicao();
            }

            // Criar textarea
            const textarea = document.createElement('textarea');
            textarea.className = 'comentario-textarea-inline';
            textarea.value = comentarioAtual;
            textarea.placeholder = 'Digite e pressione Enter para salvar';
            textarea.rows = 1;

            // Substituir elemento original pelo textarea
            elemento.style.display = 'none';
            elemento.after(textarea);
            autoResizeTextarea(textarea);

            // Focar no textarea
            textarea.focus();
            textarea.setSelectionRange(textarea.value.length, textarea.value.length);

            comentarioAtualEditando = { textarea, elemento, etapaId, comentarioAtual };

            textarea.addEventListener('input', function () {
                autoResizeTextarea(textarea);
            });

            // Salvar com Enter
            textarea.addEventListener('keydown', function (e) {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    const novoComentario = textarea.value.trim();
                    salvarComentarioInline(etapaId, novoComentario, textarea);
                } else if (e.key === 'Escape') {
                    cancelarEdicao();
                }
            });

            // Cancelar ao clicar fora (blur)
            textarea.addEventListener('blur', function () {
                setTimeout(() => {
                    if (comentarioAtualEditando && comentarioAtualEditando.textarea === textarea) {
                        cancelarEdicao();
                    }
                }, 140);
            });
        }

        function cancelarEdicao() {
            if (comentarioAtualEditando && comentarioAtualEditando.textarea && comentarioAtualEditando.elemento) {
                comentarioAtualEditando.textarea.remove();
                comentarioAtualEditando.elemento.style.display = '';
            }
            comentarioAtualEditando = null;
        }

        async function salvarComentarioInline(etapaId, comentario, textarea) {
            // Desabilitar textarea durante salvamento
            textarea.disabled = true;
            textarea.style.opacity = '0.7';
            textarea.placeholder = 'Salvando...';

            try {
                const response = await fetch(`/etapa/${etapaId}/comentario`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-Requested-With': 'XMLHttpRequest'
                    },
                    body: JSON.stringify({ comentario: comentario })
                });

                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }

                const data = await response.json();

                if (data.success) {
                    // Remover textarea
                    textarea.remove();
                    comentarioAtualEditando = null;

                    // Atualizar inline
                    renderCommentState(etapaId, comentario);

                    if (typeof showAjaxFlashMessage === 'function') {
                        showAjaxFlashMessage(comentario ? 'Comentário salvo!' : 'Comentário removido!', 'success');
                    }
                } else {
                    throw new Error(data.message || 'Erro ao salvar comentário.');
                }
            } catch (error) {
                console.error('Erro:', error);
                if (typeof showAjaxFlashMessage === 'function') {
                    showAjaxFlashMessage('Erro: ' + error.message, 'danger');
                } else {
                    alert('Erro: ' + error.message);
                }
                // Reabilitar textarea em caso de erro
                textarea.disabled = false;
                textarea.style.opacity = '1';
                textarea.placeholder = 'Digite e pressione Enter para salvar';
                textarea.focus();
            }
        }

        etapasTbody.addEventListener('click', function (event) {
            const target = event.target.closest('.etapa-comentario-display, .etapa-comentario-placeholder');
            if (!target || !etapasTbody.contains(target)) {
                return;
            }

            if (target.closest('tr.etapa-done')) {
                showAjaxFlashMessage('Não é possível editar comentários de uma etapa concluída.', 'warning');
                return;
            }

            event.preventDefault();
            event.stopPropagation();
            const etapaId = target.dataset.etapaId;
            const comentarioAtual = getCommentData(etapaId);
            abrirEdicaoInline(target, etapaId, comentarioAtual);
        });
    });

