(function () {
    const page = window.ProjectDetailPage;
    if (!page || typeof page.registerInit !== 'function') {
        return;
    }

    page.registerInit('projectStatus', function initProjectStatus(currentPage) {
        const refs = currentPage.refs;
        const shared = currentPage.shared;
        const config = currentPage.config;

        let concludeProjectForm = document.getElementById('concludeProjectForm');
        let concludeProjectButton = document.getElementById('btn-concluir-projeto');
        const concludeCelebrationEl = document.getElementById('projectConcludeCelebration');
        const concludeCelebrationTitleEl = concludeCelebrationEl
            ? concludeCelebrationEl.querySelector('[data-celebration-title]')
            : null;
        const concludeCelebrationMessageEl = concludeCelebrationEl
            ? concludeCelebrationEl.querySelector('[data-celebration-message]')
            : null;
        const reduceMotionQuery = window.matchMedia ? window.matchMedia('(prefers-reduced-motion: reduce)') : null;

        let concludeRequestInFlight = false;
        let concludeAudioContext = null;
        let concludeCelebrationTimeoutId = null;
        let concludeButtonDefaultHtml = concludeProjectButton
            ? concludeProjectButton.innerHTML
            : '<i class="fas fa-check-circle me-1"></i>Concluir Projeto';

        function ensureConcludeProjectButton() {
            if (document.getElementById('btn-concluir-projeto') || !refs.projectActionsFooter) {
                return;
            }

            const form = document.createElement('form');
            form.method = 'POST';
            form.action = config.concludeProjectUrl || `/project/${config.projectId}/concluir`;
            form.className = 'inline-form';
            form.id = 'concludeProjectForm';

            const totalEtapas = shared.getWorkflowStageRows().length;
            form.innerHTML = `
                <button type="submit" id="btn-concluir-projeto" class="btn btn-success btn-sm btn-conclude-project"
                    disabled
                    data-total-etapas="${totalEtapas}"
                    data-project-title="${shared.escapeHtml(config.projectTitle || '')}"
                    title="Todas as etapas devem estar iniciadas e concluídas">
                    <i class="fas fa-check-circle me-1"></i>Concluir Projeto
                </button>
            `;

            refs.projectActionsFooter.appendChild(form);
            bindConcludeProjectControls();
            if (typeof shared.verificarEAtualizarBotaoConcluir === 'function') {
                shared.verificarEAtualizarBotaoConcluir();
            }
        }

        function bindConcludeProjectControls() {
            concludeProjectForm = document.getElementById('concludeProjectForm');
            concludeProjectButton = document.getElementById('btn-concluir-projeto');

            if (!concludeProjectForm || !concludeProjectButton) {
                return;
            }

            concludeButtonDefaultHtml = concludeProjectButton.innerHTML || '<i class="fas fa-check-circle me-1"></i>Concluir Projeto';
            if (concludeProjectButton.dataset.boundConclude === 'true') {
                return;
            }

            concludeProjectButton.addEventListener('pointerdown', function () {
                primeConcludeAudioContext();
            }, { passive: true });

            concludeProjectForm.addEventListener('submit', function (event) {
                if (concludeRequestInFlight || concludeProjectButton.disabled) {
                    event.preventDefault();
                    return;
                }

                event.preventDefault();
                primeConcludeAudioContext();
                submitConcludeProjectWithCelebration();
            });

            concludeProjectButton.dataset.boundConclude = 'true';
        }

        function getConcludeAudioContext() {
            if (concludeAudioContext) {
                return concludeAudioContext;
            }
            const AudioContextClass = window.AudioContext || window.webkitAudioContext;
            if (!AudioContextClass) {
                return null;
            }
            concludeAudioContext = new AudioContextClass();
            return concludeAudioContext;
        }

        async function primeConcludeAudioContext() {
            try {
                const context = getConcludeAudioContext();
                if (!context) {
                    return;
                }
                if (context.state === 'suspended') {
                    await context.resume();
                }
            } catch (error) {
                console.warn('Não foi possível preparar o áudio de conclusão.', error);
            }
        }

        function playConcludeSuccessChime() {
            const context = getConcludeAudioContext();
            if (!context) {
                return;
            }
            if (context.state === 'suspended') {
                context.resume().catch(function () { });
            }

            try {
                const now = context.currentTime + 0.012;

                const masterGain = context.createGain();
                masterGain.gain.setValueAtTime(0.75, now);

                const toneFilter = context.createBiquadFilter();
                toneFilter.type = 'lowpass';
                toneFilter.frequency.setValueAtTime(2200, now);
                toneFilter.Q.value = 0.7;

                masterGain.connect(toneFilter);
                toneFilter.connect(context.destination);

                const sparkleGain = context.createGain();
                sparkleGain.gain.setValueAtTime(0.18, now);

                const sparkleHP = context.createBiquadFilter();
                sparkleHP.type = 'highpass';
                sparkleHP.frequency.setValueAtTime(1400, now);

                const sparkleShelf = context.createBiquadFilter();
                sparkleShelf.type = 'highshelf';
                sparkleShelf.frequency.setValueAtTime(2800, now);
                sparkleShelf.gain.setValueAtTime(3.5, now);

                sparkleGain.connect(sparkleHP);
                sparkleHP.connect(sparkleShelf);
                sparkleShelf.connect(context.destination);

                function playNote(freq, start, duration, gain, opts = {}) {
                    const startAt = now + start;
                    const endAt = startAt + duration;

                    const oscBody = context.createOscillator();
                    const oscTexture = context.createOscillator();
                    const gainBody = context.createGain();
                    const gainTexture = context.createGain();

                    oscBody.type = 'sine';
                    oscBody.frequency.setValueAtTime(freq, startAt);
                    oscTexture.type = 'triangle';
                    oscTexture.frequency.setValueAtTime(freq * 2, startAt);

                    gainBody.gain.setValueAtTime(0.0001, startAt);
                    gainBody.gain.exponentialRampToValueAtTime(gain, startAt + 0.010);
                    gainBody.gain.exponentialRampToValueAtTime(gain * 0.55, startAt + duration * 0.55);
                    gainBody.gain.exponentialRampToValueAtTime(0.0001, endAt + 0.03);

                    gainTexture.gain.setValueAtTime(0.0001, startAt);
                    gainTexture.gain.exponentialRampToValueAtTime(gain * 0.28, startAt + 0.008);
                    gainTexture.gain.exponentialRampToValueAtTime(0.0001, endAt + 0.02);

                    oscBody.connect(gainBody);
                    oscTexture.connect(gainTexture);
                    gainBody.connect(masterGain);
                    gainTexture.connect(masterGain);

                    if (opts.sparkle) {
                        const sparkleStart = startAt + duration * 0.55;
                        const sparkleEnd = endAt + 0.08;

                        const sp1 = context.createOscillator();
                        const sp2 = context.createOscillator();
                        const spGain = context.createGain();

                        sp1.type = 'sine';
                        sp2.type = 'triangle';

                        sp1.frequency.setValueAtTime(freq * 2, sparkleStart);
                        sp2.frequency.setValueAtTime(freq * 3, sparkleStart);

                        spGain.gain.setValueAtTime(0.0001, sparkleStart);
                        spGain.gain.exponentialRampToValueAtTime(gain * 0.075, sparkleStart + 0.012);
                        spGain.gain.exponentialRampToValueAtTime(0.0001, sparkleEnd);

                        sp1.connect(spGain);
                        sp2.connect(spGain);
                        spGain.connect(sparkleGain);

                        sp1.start(sparkleStart);
                        sp2.start(sparkleStart);
                        sp1.stop(sparkleEnd + 0.02);
                        sp2.stop(sparkleEnd + 0.02);
                    }

                    oscBody.start(startAt);
                    oscTexture.start(startAt);
                    oscBody.stop(endAt + 0.06);
                    oscTexture.stop(endAt + 0.06);
                }

                [
                    { freq: 196.0, start: 0.00, duration: 0.18, gain: 0.095, sparkle: false },
                    { freq: 246.94, start: 0.14, duration: 0.20, gain: 0.088, sparkle: false },
                    { freq: 329.63, start: 0.28, duration: 0.22, gain: 0.082, sparkle: true },
                ].forEach(note => playNote(note.freq, note.start, note.duration, note.gain, { sparkle: note.sparkle }));

                const subOsc = context.createOscillator();
                const subGain = context.createGain();
                subOsc.type = 'sine';
                subOsc.frequency.setValueAtTime(110, now);
                subOsc.frequency.exponentialRampToValueAtTime(65, now + 0.11);

                subGain.gain.setValueAtTime(0.0001, now);
                subGain.gain.exponentialRampToValueAtTime(0.040, now + 0.010);
                subGain.gain.exponentialRampToValueAtTime(0.0001, now + 0.11);

                subOsc.connect(subGain);
                subGain.connect(masterGain);
                subOsc.start(now);
                subOsc.stop(now + 0.13);

                setTimeout(function () {
                    masterGain.disconnect();
                    toneFilter.disconnect();
                    sparkleGain.disconnect();
                    sparkleHP.disconnect();
                    sparkleShelf.disconnect();
                }, 1100);
            } catch (error) {
                console.error('Sound error:', error);
            }
        }

        function showConcludeCelebration(title, message, autoHideMs = 0) {
            if (!concludeCelebrationEl) {
                return;
            }
            if (concludeCelebrationTimeoutId) {
                window.clearTimeout(concludeCelebrationTimeoutId);
                concludeCelebrationTimeoutId = null;
            }
            if (concludeCelebrationTitleEl && title) {
                concludeCelebrationTitleEl.textContent = title;
            }
            if (concludeCelebrationMessageEl && message) {
                concludeCelebrationMessageEl.textContent = message;
            }

            concludeCelebrationEl.classList.add('is-active');
            concludeCelebrationEl.setAttribute('aria-hidden', 'false');

            if (autoHideMs > 0) {
                concludeCelebrationTimeoutId = window.setTimeout(function () {
                    hideConcludeCelebration();
                }, autoHideMs);
            }
        }

        function hideConcludeCelebration() {
            if (!concludeCelebrationEl) {
                return;
            }
            if (concludeCelebrationTimeoutId) {
                window.clearTimeout(concludeCelebrationTimeoutId);
                concludeCelebrationTimeoutId = null;
            }
            concludeCelebrationEl.classList.remove('is-active');
            concludeCelebrationEl.setAttribute('aria-hidden', 'true');
        }

        function setConcludeLoadingState(isLoading) {
            if (!concludeProjectButton) {
                return;
            }
            if (isLoading) {
                concludeProjectButton.disabled = true;
                concludeProjectButton.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i>Concluindo...';
                return;
            }
            concludeProjectButton.innerHTML = concludeButtonDefaultHtml;
            if (typeof shared.verificarEAtualizarBotaoConcluir === 'function') {
                shared.verificarEAtualizarBotaoConcluir();
            }
        }

        function waitMs(duration) {
            return new Promise(resolve => window.setTimeout(resolve, duration));
        }

        async function submitConcludeProjectWithCelebration() {
            if (!concludeProjectForm || concludeRequestInFlight) {
                return;
            }

            concludeRequestInFlight = true;
            setConcludeLoadingState(true);
            showConcludeCelebration('Concluindo projeto...', 'Aguarde um instante.');

            try {
                const response = await fetch(concludeProjectForm.action, {
                    method: 'POST',
                    headers: {
                        'X-Requested-With': 'XMLHttpRequest',
                        'Accept': 'application/json',
                        'X-CSRFToken': config.csrfToken || '',
                    },
                });

                let data = null;
                try {
                    data = await response.json();
                } catch (error) {
                    data = null;
                }

                if (!response.ok || !data || !data.success) {
                    hideConcludeCelebration();
                    shared.showAjaxFlashMessage(
                        (data && data.message) || 'Não foi possível concluir o projeto.',
                        (data && data.category) || (response.status === 403 ? 'danger' : 'warning')
                    );
                    setConcludeLoadingState(false);
                    concludeRequestInFlight = false;
                    return;
                }

                showConcludeCelebration('Objetivo concluído', data.message || 'Projeto finalizado com sucesso.');
                playConcludeSuccessChime();
                if (window.finalizeCelebration && typeof window.finalizeCelebration.triggerEpic === 'function') {
                    window.finalizeCelebration.triggerEpic();
                }

                const celebrationDelay = reduceMotionQuery && reduceMotionQuery.matches ? 450 : 2400;
                await waitMs(celebrationDelay);
                window.location.href = data.redirect_url || concludeProjectForm.action;
            } catch (error) {
                console.error('Erro ao concluir projeto:', error);
                hideConcludeCelebration();
                shared.showAjaxFlashMessage('Erro de comunicação com o servidor.', 'danger');
                setConcludeLoadingState(false);
                concludeRequestInFlight = false;
            }
        }

        shared.ensureConcludeProjectButton = ensureConcludeProjectButton;
        bindConcludeProjectControls();
    });
})();
