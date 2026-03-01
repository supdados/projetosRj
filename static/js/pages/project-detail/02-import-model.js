    document.addEventListener('DOMContentLoaded', function () {
        const importModal = document.getElementById('importModelModal');
        if (!importModal) return;

        const templateSelect = document.getElementById('template_id_import');
        const previewContainer = document.getElementById('model-preview-container');
        const previewList = document.getElementById('model-preview-list');

        function setPreviewVisible(visible) {
            if (!previewContainer) {
                return;
            }

            if (visible) {
                previewContainer.classList.remove('ds-hidden');
                previewContainer.style.display = 'block';
            } else {
                previewContainer.classList.add('ds-hidden');
                previewContainer.style.display = 'none';
            }
        }

        // Carregar templates quando o modal abre
        importModal.addEventListener('show.bs.modal', function () {
            loadTemplatesForImport();
            if (previewList) {
                previewList.innerHTML = '';
            }
            setPreviewVisible(false);
        });

        // Mostrar preview quando selecionar template
        if (templateSelect) {
            templateSelect.addEventListener('change', function () {
                if (this.value) {
                    loadTemplatePreview(this.value);
                } else {
                    if (previewList) {
                        previewList.innerHTML = '';
                    }
                    setPreviewVisible(false);
                }
            });
        }

        async function loadTemplatesForImport() {
            try {
                const response = await fetch('/api/templates');
                const templates = await response.json();

                templateSelect.innerHTML = '<option value="">Selecione um modelo...</option>';

                if (templates && templates.length > 0) {
                    templates.forEach(template => {
                        const option = document.createElement('option');
                        option.value = template.id;
                        option.textContent = template.name;
                        templateSelect.appendChild(option);
                    });
                } else {
                    templateSelect.innerHTML = '<option value="">Nenhum modelo disponível</option>';
                }
            } catch (error) {
                console.error('Erro ao carregar templates:', error);
                templateSelect.innerHTML = '<option value="">Erro ao carregar modelos</option>';
            }
        }

        async function loadTemplatePreview(templateId) {
            try {
                const response = await fetch(`/api/templates/${templateId}`);
                const stages = await response.json();

                if (stages && stages.length > 0) {
                    let html = '';
                    stages.forEach((stage, index) => {
                        const duration = stage.duration || 1;
                        const plural = duration > 1 ? 's' : '';
                        html += `
                        <div class="preview-item-import">
                            <div class="preview-item-main">
                                <div class="preview-item-number">${index + 1}</div>
                                <div class="preview-item-name">${stage.name}</div>
                            </div>
                            <div class="preview-item-duration">${duration} dia${plural}</div>
                        </div>
                    `;
                    });

                    const totalDays = stages.reduce((sum, stage) => sum + (stage.duration || 1), 0);
                    html += `
                    <div class="preview-summary-import">
                        <i class="fas fa-info-circle"></i>
                        <strong>Total:</strong> ${stages.length} etapa${stages.length > 1 ? 's' : ''} • ${totalDays} dia${totalDays > 1 ? 's' : ''}
                    </div>
                `;

                    previewList.innerHTML = html;
                    setPreviewVisible(true);
                } else {
                    previewList.innerHTML = `
                    <div class="preview-summary-import">
                        <i class="fas fa-info-circle"></i>
                        <strong>Modelo sem etapas cadastradas.</strong>
                    </div>
                `;
                    setPreviewVisible(true);
                }
            } catch (error) {
                console.error('Erro ao carregar preview:', error);
                if (previewList) {
                    previewList.innerHTML = '';
                }
                setPreviewVisible(false);
            }
        }
    });

    // ============================================
    // COMENTÁRIOS DAS ETAPAS - Edição Inline
    // ============================================
