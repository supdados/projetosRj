// === task-item-operations.js — Funções de operações AJAX (updateItemStatus, updateItemPrioridade, etc.) ===
    var TASK_FINALIZADA_STATUS = 'finalizada';
    var TASK_FINALIZE_CONFETTI_COLORS = ['#f4d35e', '#ee964b', '#f95738', '#0d8b8b', '#4f7cac', '#9c6ade', '#52b788'];

    var taskFinalizeCelebration = (function () {
        var canvas = null;
        var ctx = null;
        var particles = [];
        var rafId = 0;
        var lastTs = 0;
        var resizeBound = false;
        var hideTimer = null;

        function prefersReducedMotion() {
            return !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
        }

        function randomBetween(min, max) {
            return min + (Math.random() * (max - min));
        }

        function randomColor() {
            return TASK_FINALIZE_CONFETTI_COLORS[Math.floor(Math.random() * TASK_FINALIZE_CONFETTI_COLORS.length)];
        }

        function ensureCanvas() {
            if (canvas) return;
            canvas = document.createElement('canvas');
            canvas.className = 'task-finalize-confetti-canvas';
            canvas.setAttribute('aria-hidden', 'true');
            document.body.appendChild(canvas);
            ctx = canvas.getContext('2d', { alpha: true });
            resizeCanvas();
            if (!resizeBound) {
                resizeBound = true;
                window.addEventListener('resize', resizeCanvas);
                window.addEventListener('orientationchange', resizeCanvas);
            }
        }

        function resizeCanvas() {
            if (!canvas) return;
            var viewportWidth = Math.max(window.innerWidth || 0, document.documentElement.clientWidth || 0, 1);
            var viewportHeight = Math.max(window.innerHeight || 0, document.documentElement.clientHeight || 0, 1);
            var dpr = Math.min(window.devicePixelRatio || 1, 2);
            canvas.width = Math.round(viewportWidth * dpr);
            canvas.height = Math.round(viewportHeight * dpr);
            canvas.style.width = viewportWidth + 'px';
            canvas.style.height = viewportHeight + 'px';
            if (ctx) {
                ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
            }
        }

        function originFromRect(rect) {
            if (!rect) return null;
            if (!Number.isFinite(rect.left) || !Number.isFinite(rect.right) || !Number.isFinite(rect.top) || !Number.isFinite(rect.bottom)) {
                return null;
            }
            return {
                x: rect.left + ((rect.right - rect.left) / 2),
                y: rect.top + ((rect.bottom - rect.top) * 0.36),
            };
        }

        function resolveOrigin(originLike) {
            var viewportWidth = window.innerWidth || document.documentElement.clientWidth || 1280;
            var viewportHeight = window.innerHeight || document.documentElement.clientHeight || 720;
            var fallback = {
                x: Math.max(24, viewportWidth * 0.72),
                y: Math.max(84, viewportHeight * 0.24),
            };

            if (!originLike) return fallback;
            if (Number.isFinite(originLike.x) && Number.isFinite(originLike.y)) {
                return { x: originLike.x, y: originLike.y };
            }

            if (typeof originLike.getBoundingClientRect === 'function') {
                var fromElement = originFromRect(originLike.getBoundingClientRect());
                if (fromElement) return fromElement;
            }

            var fromRectLike = originFromRect(originLike);
            if (fromRectLike) return fromRectLike;

            return fallback;
        }

        function spawnBurst(origin, count, spread, speedMin, speedMax, gravityMin, gravityMax) {
            for (var i = 0; i < count; i += 1) {
                var angle = (-Math.PI / 2) + randomBetween(-spread, spread);
                var speed = randomBetween(speedMin, speedMax);
                var life = randomBetween(44, 92);
                particles.push({
                    x: origin.x + randomBetween(-8, 8),
                    y: origin.y + randomBetween(-6, 6),
                    vx: Math.cos(angle) * speed,
                    vy: Math.sin(angle) * speed,
                    gravity: randomBetween(gravityMin, gravityMax),
                    drag: randomBetween(0.97, 0.992),
                    angle: randomBetween(0, Math.PI * 2),
                    spin: randomBetween(-0.24, 0.24),
                    tilt: randomBetween(0, Math.PI * 2),
                    tiltSpeed: randomBetween(0.08, 0.22),
                    width: randomBetween(4, 9),
                    height: randomBetween(6, 12),
                    shape: Math.random() < 0.2 ? 'circle' : 'rect',
                    color: randomColor(),
                    life: life,
                    maxLife: life,
                });
            }
        }

        function spawnCascade(origin, count) {
            for (var i = 0; i < count; i += 1) {
                var life = randomBetween(56, 112);
                particles.push({
                    x: origin.x + randomBetween(-220, 220),
                    y: origin.y - randomBetween(120, 300),
                    vx: randomBetween(-1.4, 1.4),
                    vy: randomBetween(2.4, 5.1),
                    gravity: randomBetween(0.1, 0.22),
                    drag: randomBetween(0.976, 0.994),
                    angle: randomBetween(0, Math.PI * 2),
                    spin: randomBetween(-0.16, 0.16),
                    tilt: randomBetween(0, Math.PI * 2),
                    tiltSpeed: randomBetween(0.06, 0.18),
                    width: randomBetween(3, 7),
                    height: randomBetween(5, 10),
                    shape: Math.random() < 0.18 ? 'circle' : 'rect',
                    color: randomColor(),
                    life: life,
                    maxLife: life,
                });
            }
        }

        function drawParticle(particle, alpha) {
            if (!ctx) return;
            ctx.save();
            ctx.translate(
                particle.x + (Math.cos(particle.tilt) * 2.4),
                particle.y + (Math.sin(particle.tilt * 0.72) * 0.8)
            );
            ctx.rotate(particle.angle);
            ctx.globalAlpha = alpha;
            ctx.fillStyle = particle.color;

            if (particle.shape === 'circle') {
                ctx.beginPath();
                ctx.arc(0, 0, Math.max(2, particle.width * 0.48), 0, Math.PI * 2);
                ctx.fill();
            } else {
                var flip = 0.35 + ((Math.sin(particle.tilt) + 1) * 0.45);
                ctx.scale(1, flip);
                ctx.fillRect(-particle.width / 2, -particle.height / 2, particle.width, particle.height);
            }
            ctx.restore();
        }

        function tick(timestamp) {
            if (!canvas || !ctx) {
                rafId = 0;
                lastTs = 0;
                particles.length = 0;
                return;
            }

            var dt = lastTs ? Math.min((timestamp - lastTs) / 16.6667, 2.4) : 1;
            lastTs = timestamp;
            var viewportWidth = window.innerWidth || document.documentElement.clientWidth || 0;
            var viewportHeight = window.innerHeight || document.documentElement.clientHeight || 0;
            ctx.clearRect(0, 0, viewportWidth, viewportHeight);

            for (var i = particles.length - 1; i >= 0; i -= 1) {
                var particle = particles[i];
                particle.life -= dt;
                if (particle.life <= 0) {
                    particles.splice(i, 1);
                    continue;
                }

                particle.vx *= particle.drag;
                particle.vy = (particle.vy * particle.drag) + (particle.gravity * dt);
                particle.x += particle.vx * dt;
                particle.y += particle.vy * dt;
                particle.angle += particle.spin * dt;
                particle.tilt += particle.tiltSpeed * dt;

                if (
                    particle.y > (viewportHeight + 56) ||
                    particle.x < -72 ||
                    particle.x > (viewportWidth + 72)
                ) {
                    particles.splice(i, 1);
                    continue;
                }

                var alpha = Math.min(1, Math.max(0, particle.life / (particle.maxLife * 0.66)));
                drawParticle(particle, alpha);
            }

            if (particles.length > 0) {
                rafId = window.requestAnimationFrame(tick);
                return;
            }

            rafId = 0;
            lastTs = 0;
            ctx.clearRect(0, 0, viewportWidth, viewportHeight);
            canvas.classList.remove('is-active');
            if (hideTimer) clearTimeout(hideTimer);
            hideTimer = setTimeout(function () {
                if (!canvas || rafId || particles.length) return;
                if (canvas.parentNode) {
                    canvas.parentNode.removeChild(canvas);
                }
                canvas = null;
                ctx = null;
                hideTimer = null;
            }, 320);
        }

        function trigger(originLike) {
            if (prefersReducedMotion()) return;
            ensureCanvas();
            if (!canvas || !ctx) return;

            var origin = resolveOrigin(originLike);
            if (hideTimer) {
                clearTimeout(hideTimer);
                hideTimer = null;
            }

            canvas.classList.add('is-active');
            spawnBurst(origin, 84, 1.02, 5.4, 11.4, 0.16, 0.34);
            spawnBurst(
                { x: origin.x + randomBetween(-18, 18), y: origin.y - randomBetween(14, 36) },
                44,
                1.14,
                4.4,
                10.2,
                0.18,
                0.36
            );
            spawnCascade(origin, 38);

            if (particles.length > 420) {
                particles.splice(0, particles.length - 420);
            }

            if (!rafId) {
                rafId = window.requestAnimationFrame(tick);
            }
        }

        return {
            trigger: trigger,
        };
    })();

    function normalizeTaskStatusValue(status) {
        var normalized = String(status == null ? '' : status).trim();
        return normalized || 'nao_iniciada';
    }

    function shouldCelebrateFinalize(previousStatus, nextStatus) {
        return (
            normalizeTaskStatusValue(previousStatus) !== TASK_FINALIZADA_STATUS &&
            normalizeTaskStatusValue(nextStatus) === TASK_FINALIZADA_STATUS
        );
    }

    function resolveFinalizeCelebrationOrigin(itemId, opts, row) {
        var options = opts || {};
        if (options.celebrationOrigin) return options.celebrationOrigin;
        var sourceRow = row || getTaskItemRowById(itemId);
        if (!sourceRow) return null;
        var statusSelect = sourceRow.querySelector('.task-item-status');
        if (statusSelect) return statusSelect;
        return sourceRow;
    }

    // Atualizar status da tarefa via AJAX (sem recarregar a página)
    function updateItemStatus(itemId, status, options) {
        var opts = options || {};
        var showAlert = opts.showAlert !== false;
        var nextStatus = normalizeTaskStatusValue(status);
        var rowBeforeUpdate = getTaskItemRowById(itemId);
        var previousStatus = normalizeTaskStatusValue(rowBeforeUpdate ? getTaskItemStatus(rowBeforeUpdate) : '');

        return fetch('/tarefas/' + itemId + '/update_status', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ status: nextStatus })
        })
            .then(function (response) { return response.json(); })
            .then(function (data) {
                if (!data.success) {
                    throw new Error(data.message || 'Erro ao atualizar status.');
                }

                var row = getTaskItemRowById(itemId);
                if (row) {
                    setTaskItemRowStatus(row, nextStatus);
                    syncTaskItemRowMetadata(row);
                }

                if (!opts.skipKanbanSync && window.taskItemsKanban && typeof window.taskItemsKanban.syncItemFromRow === 'function') {
                    window.taskItemsKanban.syncItemFromRow(String(itemId));
                }

                if (opts.celebrateOnFinalize !== false && shouldCelebrateFinalize(previousStatus, nextStatus)) {
                    taskFinalizeCelebration.trigger(
                        resolveFinalizeCelebrationOrigin(itemId, opts, rowBeforeUpdate || row)
                    );
                }

                return data;
            })
            .catch(function (error) {
                console.error('Erro:', error);
                if (showAlert) {
                    alert(error && error.message ? error.message : 'Erro ao atualizar status');
                }
                throw error;
            });
    }

    function updateItemPrioridade(itemId, prioridade, selectEl) {
        var prev = selectEl ? selectEl.getAttribute('data-prev-value') || '' : '';
        if (selectEl) selectEl.setAttribute('data-prev-value', prioridade);

        return fetch('/tarefas/' + itemId + '/update_prioridade', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ prioridade: prioridade || null })
        })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (!data.success) throw new Error(data.message || 'Erro ao atualizar prioridade.');
                var row = getTaskItemRowById(itemId);
                if (row) {
                    row.setAttribute('data-item-prioridade', prioridade || '');
                    if (selectEl) _applyPrioridadeClass(selectEl, prioridade);
                    syncTaskItemRowMetadata(row);
                }
                if (window.taskItemsKanban && typeof window.taskItemsKanban.syncItemFromRow === 'function') {
                    window.taskItemsKanban.syncItemFromRow(String(itemId));
                }
                return data;
            })
            .catch(function (error) {
                console.error('Erro:', error);
                if (selectEl) {
                    selectEl.value = prev;
                    _applyPrioridadeClass(selectEl, prev);
                }
                alert(error && error.message ? error.message : 'Erro ao atualizar prioridade');
            });
    }

    function updateItemTipo(itemId, tipo) {
        return fetch('/tarefas/' + itemId + '/update_tipo', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ tipo_pedido: tipo || null })
        })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (!data.success) throw new Error(data.message || 'Erro ao atualizar tipo.');
                var row = getTaskItemRowById(itemId);
                if (row) {
                    row.setAttribute('data-item-tipo', tipo || '');
                    syncTaskItemRowMetadata(row);
                }
                if (window.taskItemsKanban && typeof window.taskItemsKanban.syncItemFromRow === 'function') {
                    window.taskItemsKanban.syncItemFromRow(String(itemId));
                }
                return data;
            })
            .catch(function (error) {
                console.error('Erro:', error);
                alert(error && error.message ? error.message : 'Erro ao atualizar tipo');
            });
    }
