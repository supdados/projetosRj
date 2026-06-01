/* Modal reutilizável de exclusão de projeto em dois passos.
 *
 * Passo 1: aviso de que a exclusão é irreversível.
 * Passo 2: confirmação por digitação da frase exata "APAGAR PROJETO"
 *          (padrão "digite o nome para confirmar" do GitHub).
 *
 * Uso:
 *   DeleteProjectModal.open({
 *       deleteUrl: '/project/12/delete',
 *       projectName: 'Meu Projeto',
 *       onSuccess: function (data) { ... }   // pós-exclusão (remover linha, redirecionar…)
 *   });
 *
 * O CSRF é injetado automaticamente pelo wrapper de fetch em base.html, então
 * aqui basta marcar a requisição como XMLHttpRequest para a rota responder JSON.
 */
(function () {
    'use strict';

    var CONFIRM_PHRASE = 'APAGAR PROJETO';

    function flash(message, type) {
        if (typeof window.showFlash === 'function') {
            window.showFlash(message, type || 'info');
        }
    }

    function normalizePhrase(value) {
        // Tolerante a espaços nas pontas e maiúsculas/minúsculas, mas exige a
        // frase exata no miolo — coerente com o que o campo orienta a digitar.
        return String(value || '').trim().toUpperCase();
    }

    function DeleteProjectModalController(overlay) {
        this.overlay = overlay;
        this.stepWarn = overlay.querySelector('[data-delete-step="warn"]');
        this.stepConfirm = overlay.querySelector('[data-delete-step="confirm"]');
        this.projectNameEl = overlay.querySelector('[data-delete-project-name]');
        this.input = overlay.querySelector('[data-delete-confirm-input]');
        this.warnIcon = overlay.querySelector('[data-delete-warn-icon]');
        this.confirmIcon = overlay.querySelector('[data-delete-icon]');
        this.confirmBtn = overlay.querySelector('[data-delete-confirm]');
        this.advanceBtn = overlay.querySelector('[data-delete-advance]');
        this.backButtons = Array.prototype.slice.call(overlay.querySelectorAll('[data-delete-back]'));
        this.cancelButtons = Array.prototype.slice.call(overlay.querySelectorAll('[data-delete-cancel]'));
        this.pending = null;
        this.bind();
    }

    DeleteProjectModalController.prototype.bind = function () {
        var self = this;

        this.cancelButtons.forEach(function (btn) {
            btn.addEventListener('click', function () {
                self.close();
            });
        });

        if (this.advanceBtn) {
            this.advanceBtn.addEventListener('click', function () {
                self.goToConfirmStep();
            });
        }

        this.backButtons.forEach(function (btn) {
            btn.addEventListener('click', function () {
                self.resetToWarnStep();
            });
        });

        // Remove a classe assim que o balanço termina, para o svg não ficar com
        // transform residual (que desalinharia os ícones entre os passos).
        [this.warnIcon, this.confirmIcon].forEach(function (icon) {
            if (icon) {
                icon.addEventListener('animationend', function () {
                    icon.classList.remove('is-wobbling');
                });
            }
        });

        if (this.input) {
            this.input.addEventListener('input', function () {
                self.syncConfirmButtonState();
            });
            this.input.addEventListener('keydown', function (event) {
                if (event.key === 'Enter' && !self.confirmBtn.disabled) {
                    event.preventDefault();
                    self.submit();
                }
            });
        }

        if (this.confirmBtn) {
            this.confirmBtn.addEventListener('click', function () {
                self.submit();
            });
        }

        // Clicar fora do card ou apertar Esc cancela.
        this.overlay.addEventListener('mousedown', function (event) {
            if (event.target === self.overlay) {
                self.close();
            }
        });
        document.addEventListener('keydown', function (event) {
            if (event.key === 'Escape' && self.overlay.classList.contains('is-open')) {
                self.close();
            }
        });
    };

    DeleteProjectModalController.prototype.open = function (options) {
        var config = options || {};
        if (!config.deleteUrl) {
            return;
        }

        this.pending = {
            deleteUrl: config.deleteUrl,
            onSuccess: typeof config.onSuccess === 'function' ? config.onSuccess : null,
            onError: typeof config.onError === 'function' ? config.onError : null,
        };

        if (this.projectNameEl) {
            this.projectNameEl.textContent = config.projectName || 'este projeto';
        }

        this.resetToWarnStep();
        this.overlay.classList.add('is-open');
        this.overlay.setAttribute('aria-hidden', 'false');
        this.playWobble(this.warnIcon);
    };

    // Reinicia o balanço de um ícone. O remove + reflow + add garante que a
    // animação dispare de novo mesmo se a classe ainda estiver aplicada.
    DeleteProjectModalController.prototype.playWobble = function (icon) {
        if (!icon) {
            return;
        }
        icon.classList.remove('is-wobbling');
        void icon.offsetWidth;
        icon.classList.add('is-wobbling');
    };

    DeleteProjectModalController.prototype.close = function () {
        this.overlay.classList.remove('is-open');
        this.overlay.setAttribute('aria-hidden', 'true');
        this.pending = null;
        this.resetToWarnStep();
    };

    DeleteProjectModalController.prototype.resetToWarnStep = function () {
        if (this.input) {
            this.input.value = '';
            this.input.classList.remove('is-valid-phrase');
        }
        if (this.confirmIcon) {
            this.confirmIcon.classList.remove('delete-project-modal__icon--danger', 'is-wobbling');
        }
        this.confirmWasValid = false;
        // Garante que voltar ao passo 1 não redispare o balanço da lixeira.
        if (this.warnIcon) {
            this.warnIcon.classList.remove('is-wobbling');
        }
        if (this.confirmBtn) {
            this.confirmBtn.disabled = true;
            this.confirmBtn.textContent = 'Apagar projeto';
        }
        this.showStep('warn');
    };

    DeleteProjectModalController.prototype.showStep = function (name) {
        if (this.stepWarn) {
            this.stepWarn.classList.toggle('is-active', name === 'warn');
        }
        if (this.stepConfirm) {
            this.stepConfirm.classList.toggle('is-active', name === 'confirm');
        }
    };

    DeleteProjectModalController.prototype.goToConfirmStep = function () {
        var self = this;
        this.showStep('confirm');
        this.syncConfirmButtonState();
        // Foco no campo após a transição de passo.
        window.setTimeout(function () {
            if (self.input) {
                self.input.focus();
            }
        }, 50);
    };

    DeleteProjectModalController.prototype.isPhraseValid = function () {
        return this.input && normalizePhrase(this.input.value) === CONFIRM_PHRASE;
    };

    DeleteProjectModalController.prototype.syncConfirmButtonState = function () {
        var valid = this.isPhraseValid();
        if (this.confirmBtn) {
            this.confirmBtn.disabled = !valid;
        }
        if (this.input) {
            this.input.classList.toggle('is-valid-phrase', valid);
        }
        // A lixeira nasce preta e só fica vermelha quando a frase confere; no
        // momento em que passa a valer, ela também balança (só na transição,
        // para não retremer a cada tecla com a frase já completa).
        if (this.confirmIcon) {
            this.confirmIcon.classList.toggle('delete-project-modal__icon--danger', valid);
            if (valid && !this.confirmWasValid) {
                this.playWobble(this.confirmIcon);
            }
        }
        this.confirmWasValid = valid;
    };

    DeleteProjectModalController.prototype.submit = function () {
        var self = this;
        if (!this.pending || !this.isPhraseValid()) {
            return;
        }

        var pending = this.pending;
        this.confirmBtn.disabled = true;
        this.confirmBtn.textContent = 'Apagando…';

        fetch(pending.deleteUrl, {
            method: 'POST',
            headers: { 'X-Requested-With': 'XMLHttpRequest' },
        })
            .then(function (response) {
                return response.json().catch(function () {
                    return { ok: false };
                });
            })
            .then(function (data) {
                if (data && data.ok) {
                    self.close();
                    if (pending.onSuccess) {
                        pending.onSuccess(data);
                    } else {
                        flash(data.message || 'Projeto apagado.', 'success');
                    }
                    return;
                }
                self.handleFailure(pending, (data && data.message) || 'Erro ao apagar projeto.');
            })
            .catch(function () {
                self.handleFailure(pending, 'Erro de conexão. Tente novamente.');
            });
    };

    DeleteProjectModalController.prototype.handleFailure = function (pending, message) {
        this.confirmBtn.disabled = false;
        this.confirmBtn.textContent = 'Apagar projeto';
        this.syncConfirmButtonState();
        if (pending.onError) {
            pending.onError(message);
        } else {
            flash(message, 'danger');
        }
    };

    var controller = null;

    function getController() {
        if (controller) {
            return controller;
        }
        var overlay = document.getElementById('deleteProjectModal');
        if (!overlay) {
            return null;
        }
        controller = new DeleteProjectModalController(overlay);
        return controller;
    }

    window.DeleteProjectModal = {
        confirmPhrase: CONFIRM_PHRASE,
        open: function (options) {
            var instance = getController();
            if (!instance) {
                console.error('DeleteProjectModal: #deleteProjectModal não encontrado no DOM.');
                return;
            }
            instance.open(options);
        },
    };
})();
