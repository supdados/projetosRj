// === task-item-operations.js — Funções de operações AJAX (updateItemStatus, updateItemPrioridade, etc.) ===
    var TASK_FINALIZADA_STATUS = 'finalizada';
    // Múltiplas paletas — uma é sorteada a cada celebração para que projetos
    // diferentes tenham "vibes" visuais distintas (não pareçam copy/paste).
    var CONFETTI_PALETTES = [
        ['#f4d35e', '#ee964b', '#f95738', '#0d8b8b', '#4f7cac', '#9c6ade', '#52b788'],
        ['#ff6b9d', '#f06292', '#c4378b', '#7e57c2', '#5e35b1', '#3949ab', '#ffd54f'],
        ['#06d6a0', '#118ab2', '#073b4c', '#ffd166', '#ef476f', '#83c5be', '#e29578'],
        ['#fb8500', '#ffb703', '#fdf0d5', '#8ecae6', '#219ebc', '#023047', '#ff006e'],
        ['#ffba08', '#faa307', '#f48c06', '#dc2f02', '#9d0208', '#3a86ff', '#8338ec'],
        ['#caffbf', '#9bf6ff', '#a0c4ff', '#bdb2ff', '#ffc6ff', '#ffadad', '#ffd6a5'],
        ['#2ec4b6', '#cbf3f0', '#ff9f1c', '#ffbf69', '#e71d36', '#011627', '#fdfffc'],
    ];
    // Distribuição de formas por "vibe". Cada vibe sorteia formas diferentes
    // para variar o aspecto visual entre celebrações.
    var CONFETTI_SHAPE_MIXES = [
        // mix balanceado clássico
        { rect: 0.45, circle: 0.20, triangle: 0.15, streamer: 0.12, star: 0.08 },
        // dominado por estrelas e círculos (mais "festa")
        { rect: 0.18, circle: 0.30, triangle: 0.10, streamer: 0.12, star: 0.30 },
        // muitos streamers (efeito serpentina)
        { rect: 0.20, circle: 0.10, triangle: 0.15, streamer: 0.45, star: 0.10 },
        // geométrico (triângulos + retângulos)
        { rect: 0.40, circle: 0.10, triangle: 0.40, streamer: 0.05, star: 0.05 },
        // suave / orgânico (círculos + estrelas)
        { rect: 0.20, circle: 0.45, triangle: 0.05, streamer: 0.10, star: 0.20 },
    ];
    var activePalette = CONFETTI_PALETTES[0];
    var activeShapeMix = CONFETTI_SHAPE_MIXES[0];

    var taskFinalizeCelebration = (function () {
        var canvas = null;
        var ctx = null;
        var particles = [];
        var rafId = 0;
        var lastTs = 0;
        var resizeBound = false;
        var hideTimer = null;
        var lastPatternKey = '';

        function prefersReducedMotion() {
            return !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
        }

        function randomBetween(min, max) {
            return min + (Math.random() * (max - min));
        }

        function randomColor() {
            return activePalette[Math.floor(Math.random() * activePalette.length)];
        }

        function pickShape(circleChanceLegacy) {
            // Se o caller passou circleChance explicitamente (API antiga),
            // mantemos o comportamento binário rect/circle para não quebrar.
            if (Number.isFinite(circleChanceLegacy) && circleChanceLegacy >= 0 && circleChanceLegacy <= 1) {
                // Mistura binária + chance pequena de variar para fora.
                var roll = Math.random();
                if (roll < circleChanceLegacy * 0.78) return 'circle';
                if (roll < circleChanceLegacy * 0.78 + 0.10) return 'triangle';
                if (roll < circleChanceLegacy * 0.78 + 0.16) return 'star';
                if (roll < circleChanceLegacy * 0.78 + 0.22) return 'streamer';
                return 'rect';
            }
            var r = Math.random();
            var acc = 0;
            var keys = ['rect', 'circle', 'triangle', 'streamer', 'star'];
            for (var i = 0; i < keys.length; i += 1) {
                acc += activeShapeMix[keys[i]] || 0;
                if (r < acc) return keys[i];
            }
            return 'rect';
        }

        function randomizeVibe() {
            activePalette = CONFETTI_PALETTES[Math.floor(Math.random() * CONFETTI_PALETTES.length)];
            activeShapeMix = CONFETTI_SHAPE_MIXES[Math.floor(Math.random() * CONFETTI_SHAPE_MIXES.length)];
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

        function spawnBurst(origin, count, spread, speedMin, speedMax, gravityMin, gravityMax, options) {
            var opts = options || {};
            var angleCenter = Number.isFinite(opts.angleCenter) ? opts.angleCenter : (-Math.PI / 2);
            var xJitter = Number.isFinite(opts.xJitter) ? opts.xJitter : 8;
            var yJitter = Number.isFinite(opts.yJitter) ? opts.yJitter : 6;
            var circleChance = Number.isFinite(opts.circleChance) ? opts.circleChance : 0.2;
            for (var i = 0; i < count; i += 1) {
                var angle = angleCenter + randomBetween(-spread, spread);
                var speed = randomBetween(speedMin, speedMax);
                var life = randomBetween(44, 92);
                particles.push({
                    x: origin.x + randomBetween(-xJitter, xJitter),
                    y: origin.y + randomBetween(-yJitter, yJitter),
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
                    shape: pickShape(circleChance),
                    color: randomColor(),
                    life: life,
                    maxLife: life,
                });
            }
        }

        function spawnCascade(origin, count, options) {
            var opts = options || {};
            var xSpread = Number.isFinite(opts.xSpread) ? opts.xSpread : 220;
            var yMin = Number.isFinite(opts.yMin) ? opts.yMin : 120;
            var yMax = Number.isFinite(opts.yMax) ? opts.yMax : 300;
            var vxMin = Number.isFinite(opts.vxMin) ? opts.vxMin : -1.4;
            var vxMax = Number.isFinite(opts.vxMax) ? opts.vxMax : 1.4;
            var vyMin = Number.isFinite(opts.vyMin) ? opts.vyMin : 2.4;
            var vyMax = Number.isFinite(opts.vyMax) ? opts.vyMax : 5.1;
            var gravityMin = Number.isFinite(opts.gravityMin) ? opts.gravityMin : 0.1;
            var gravityMax = Number.isFinite(opts.gravityMax) ? opts.gravityMax : 0.22;
            var circleChance = Number.isFinite(opts.circleChance) ? opts.circleChance : 0.18;
            for (var i = 0; i < count; i += 1) {
                var life = randomBetween(56, 112);
                particles.push({
                    x: origin.x + randomBetween(-xSpread, xSpread),
                    y: origin.y - randomBetween(yMin, yMax),
                    vx: randomBetween(vxMin, vxMax),
                    vy: randomBetween(vyMin, vyMax),
                    gravity: randomBetween(gravityMin, gravityMax),
                    drag: randomBetween(0.976, 0.994),
                    angle: randomBetween(0, Math.PI * 2),
                    spin: randomBetween(-0.16, 0.16),
                    tilt: randomBetween(0, Math.PI * 2),
                    tiltSpeed: randomBetween(0.06, 0.18),
                    width: randomBetween(3, 7),
                    height: randomBetween(5, 10),
                    shape: pickShape(circleChance),
                    color: randomColor(),
                    life: life,
                    maxLife: life,
                });
            }
        }

        function pickConfettiPattern() {
            var patterns = ['classic', 'wide', 'fountain', 'double_side'];
            var index = Math.floor(Math.random() * patterns.length);
            var picked = patterns[index];

            if (patterns.length > 1 && picked === lastPatternKey) {
                picked = patterns[(index + 1 + Math.floor(Math.random() * (patterns.length - 1))) % patterns.length];
            }

            lastPatternKey = picked;
            return picked;
        }

        function runConfettiPattern(origin, patternKey) {
            if (patternKey === 'wide') {
                spawnBurst(origin, 112, 1.36, 4.8, 12.2, 0.16, 0.36, { xJitter: 16, yJitter: 9 });
                spawnCascade(origin, 58, {
                    xSpread: 320,
                    yMin: 130,
                    yMax: 350,
                    vxMin: -2.5,
                    vxMax: 2.5,
                    vyMin: 2.2,
                    vyMax: 5.4,
                    gravityMin: 0.12,
                    gravityMax: 0.24,
                });
                return;
            }

            if (patternKey === 'fountain') {
                spawnBurst(origin, 78, 0.54, 6.1, 12.9, 0.18, 0.34, { xJitter: 6, yJitter: 8 });
                spawnBurst(
                    { x: origin.x + randomBetween(-12, 12), y: origin.y - randomBetween(16, 32) },
                    54,
                    0.44,
                    6.7,
                    13.6,
                    0.18,
                    0.32,
                    { xJitter: 5, yJitter: 6 }
                );
                spawnCascade(origin, 30, {
                    xSpread: 160,
                    yMin: 170,
                    yMax: 400,
                    vxMin: -1.2,
                    vxMax: 1.2,
                    vyMin: 2.8,
                    vyMax: 6.1,
                    gravityMin: 0.1,
                    gravityMax: 0.2,
                });
                return;
            }

            if (patternKey === 'double_side') {
                var sideOffset = Math.min(Math.max((window.innerWidth || 1200) * 0.14, 120), 260);
                spawnBurst(
                    { x: origin.x - sideOffset, y: origin.y + 6 },
                    62,
                    0.5,
                    6.4,
                    12.8,
                    0.17,
                    0.33,
                    { angleCenter: -0.74, xJitter: 7, yJitter: 7 }
                );
                spawnBurst(
                    { x: origin.x + sideOffset, y: origin.y + 6 },
                    62,
                    0.5,
                    6.4,
                    12.8,
                    0.17,
                    0.33,
                    { angleCenter: -2.4, xJitter: 7, yJitter: 7 }
                );
                spawnCascade(
                    { x: origin.x + randomBetween(-18, 18), y: origin.y - 10 },
                    42,
                    {
                        xSpread: 280,
                        yMin: 110,
                        yMax: 290,
                        vxMin: -1.7,
                        vxMax: 1.7,
                        vyMin: 2.3,
                        vyMax: 4.9,
                        gravityMin: 0.12,
                        gravityMax: 0.24,
                    }
                );
                return;
            }

            // classic
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
            } else if (particle.shape === 'triangle') {
                var ts = Math.max(3, particle.width * 0.95);
                ctx.beginPath();
                ctx.moveTo(0, -ts);
                ctx.lineTo(ts * 0.92, ts * 0.78);
                ctx.lineTo(-ts * 0.92, ts * 0.78);
                ctx.closePath();
                ctx.fill();
            } else if (particle.shape === 'star') {
                var spikes = 5;
                var outer = Math.max(3, particle.width * 0.9);
                var inner = outer * 0.46;
                ctx.beginPath();
                for (var s = 0; s < spikes * 2; s += 1) {
                    var radius = (s % 2 === 0) ? outer : inner;
                    var angle = (Math.PI / spikes) * s - Math.PI / 2;
                    var px = Math.cos(angle) * radius;
                    var py = Math.sin(angle) * radius;
                    if (s === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
                }
                ctx.closePath();
                ctx.fill();
            } else if (particle.shape === 'streamer') {
                // Fita ondulada — retângulo longo com curvatura via flip vertical
                var len = particle.height * 1.8;
                var thick = Math.max(1.5, particle.width * 0.42);
                var wave = Math.sin(particle.tilt * 1.3) * 0.6 + 0.4;
                ctx.scale(1, wave);
                ctx.fillRect(-thick / 2, -len / 2, thick, len);
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

            randomizeVibe();
            var origin = resolveOrigin(originLike);
            var patternKey = pickConfettiPattern();
            if (hideTimer) {
                clearTimeout(hideTimer);
                hideTimer = null;
            }

            canvas.classList.add('is-active');
            runConfettiPattern(origin, patternKey);

            if (particles.length > 420) {
                particles.splice(0, particles.length - 420);
            }

            if (!rafId) {
                rafId = window.requestAnimationFrame(tick);
            }
        }

        // Estilos de explosão — cada um tem física distinta (spread, speed,
        // gravity, life). Usados pelo triggerEpic para variar o "ritmo" das
        // explosões e evitar o efeito de copy/paste entre elas.
        var BURST_STYLES = {
            // Estouro radial amplo e rápido, partículas curtas
            explosive: { spread: 1.55, speedMin: 8.6, speedMax: 16.4, gravityMin: 0.20, gravityMax: 0.40, xJitter: 14, yJitter: 10 },
            // Tiro estreito e potente para cima — efeito "fogos"
            firework:  { spread: 0.45, speedMin: 10.2, speedMax: 18.0, gravityMin: 0.17, gravityMax: 0.30, xJitter: 6, yJitter: 6 },
            // Estouro lateral suave (drift longo)
            drift:     { spread: 1.95, speedMin: 3.8, speedMax: 7.6, gravityMin: 0.06, gravityMax: 0.14, xJitter: 22, yJitter: 14 },
            // Pulso curto/concentrado
            pop:       { spread: 0.85, speedMin: 5.6, speedMax: 9.4, gravityMin: 0.22, gravityMax: 0.42, xJitter: 8, yJitter: 6 },
            // Chuveirão amplo cobrindo área — partículas pesadas
            shower:    { spread: 2.40, speedMin: 4.2, speedMax: 8.6, gravityMin: 0.26, gravityMax: 0.50, xJitter: 28, yJitter: 18 },
            // Fonte alta bem direcional
            geyser:    { spread: 0.32, speedMin: 11.4, speedMax: 17.6, gravityMin: 0.18, gravityMax: 0.32, xJitter: 4, yJitter: 8 },
        };
        var BURST_STYLE_KEYS = Object.keys(BURST_STYLES);

        function shuffledStyleKeys() {
            var keys = BURST_STYLE_KEYS.slice();
            for (var i = keys.length - 1; i > 0; i -= 1) {
                var j = Math.floor(Math.random() * (i + 1));
                var tmp = keys[i];
                keys[i] = keys[j];
                keys[j] = tmp;
            }
            return keys;
        }

        function styledBurst(origin, count, styleKey, angleCenter, extraOpts) {
            var s = BURST_STYLES[styleKey] || BURST_STYLES.explosive;
            // Pequena variação aleatória nos próprios parâmetros do estilo,
            // para que dois bursts do mesmo estilo não fiquem idênticos.
            var spread = s.spread * randomBetween(0.9, 1.12);
            var speedMin = s.speedMin * randomBetween(0.92, 1.08);
            var speedMax = s.speedMax * randomBetween(0.92, 1.10);
            var gravityMin = s.gravityMin * randomBetween(0.88, 1.14);
            var gravityMax = s.gravityMax * randomBetween(0.92, 1.12);
            var opts = {
                angleCenter: angleCenter,
                xJitter: s.xJitter,
                yJitter: s.yJitter,
            };
            if (extraOpts) {
                for (var k in extraOpts) {
                    if (Object.prototype.hasOwnProperty.call(extraOpts, k)) {
                        opts[k] = extraOpts[k];
                    }
                }
            }
            spawnBurst(origin, count, spread, speedMin, speedMax, gravityMin, gravityMax, opts);
        }

        function ensureRaf() {
            if (particles.length > 1500) {
                particles.splice(0, particles.length - 1500);
            }
            if (!rafId) {
                rafId = window.requestAnimationFrame(tick);
            }
        }

        function triggerEpic() {
            if (prefersReducedMotion()) return;
            ensureCanvas();
            if (!canvas || !ctx) return;
            if (hideTimer) {
                clearTimeout(hideTimer);
                hideTimer = null;
            }
            randomizeVibe();
            canvas.classList.add('is-active');

            var viewportWidth = window.innerWidth || document.documentElement.clientWidth || 1280;
            var viewportHeight = window.innerHeight || document.documentElement.clientHeight || 720;

            // Sorteia uma sequência única de estilos para esta celebração —
            // cada explosão na coreografia recebe um estilo distinto, e a
            // sequência muda a cada chamada.
            var styles = shuffledStyleKeys();
            var nextStyle = (function () {
                var i = 0;
                return function () {
                    var k = styles[i % styles.length];
                    i += 1;
                    return k;
                };
            })();

            // Sequência coreografada: cada disparo tem origem, ângulo, tamanho
            // e timing próprios. Os estilos ditam o "feel" de cada estouro.
            var schedule = [
                // Wave 1 — abertura: 3 fogos verticais em tempos próximos mas
                // não simultâneos (efeito de bateria de fogos).
                { delay: 0,    origin: { x: viewportWidth * 0.18, y: viewportHeight * 0.30 }, angle: -Math.PI / 2 + 0.05, count: 95, style: nextStyle() },
                { delay: 110,  origin: { x: viewportWidth * 0.82, y: viewportHeight * 0.32 }, angle: -Math.PI / 2 - 0.06, count: 95, style: nextStyle() },
                { delay: 220,  origin: { x: viewportWidth * 0.50, y: viewportHeight * 0.22 }, angle: -Math.PI / 2,        count: 130, style: nextStyle() },

                // Wave 2 — laterais grandes vindo "de fora" para o centro
                { delay: 480,  origin: { x: viewportWidth * 0.04, y: viewportHeight * 0.62 }, angle: -0.65, count: 110, style: nextStyle() },
                { delay: 540,  origin: { x: viewportWidth * 0.96, y: viewportHeight * 0.62 }, angle: -2.49, count: 110, style: nextStyle() },

                // Wave 3 — finale: fonte alta do centro + dois pops de fundo
                { delay: 880,  origin: { x: viewportWidth * 0.50, y: viewportHeight * 0.85 }, angle: -Math.PI / 2,        count: 170, style: nextStyle() },
                { delay: 1040, origin: { x: viewportWidth * 0.32, y: viewportHeight * 0.78 }, angle: -Math.PI / 2 + 0.20, count: 70,  style: nextStyle() },
                { delay: 1100, origin: { x: viewportWidth * 0.68, y: viewportHeight * 0.78 }, angle: -Math.PI / 2 - 0.20, count: 70,  style: nextStyle() },
            ];

            schedule.forEach(function (step) {
                if (step.delay === 0) {
                    styledBurst(step.origin, step.count, step.style, step.angle);
                } else {
                    window.setTimeout(function () {
                        if (!canvas || !ctx) return;
                        styledBurst(step.origin, step.count, step.style, step.angle);
                        ensureRaf();
                    }, step.delay);
                }
            });

            // Cascata contínua do topo, espalhando partículas durante toda a
            // celebração — usa estilo "shower" indireto via spawnCascade.
            spawnCascade(
                { x: viewportWidth / 2, y: viewportHeight * 0.05 },
                240,
                {
                    xSpread: viewportWidth * 0.55,
                    yMin: 20, yMax: 220,
                    vxMin: -2.6, vxMax: 2.6,
                    vyMin: 2.6, vyMax: 6.4,
                    gravityMin: 0.12, gravityMax: 0.26,
                }
            );
            window.setTimeout(function () {
                if (!canvas || !ctx) return;
                spawnCascade(
                    { x: viewportWidth / 2, y: viewportHeight * 0.06 },
                    180,
                    {
                        xSpread: viewportWidth * 0.48,
                        yMin: 30, yMax: 200,
                        vxMin: -2.2, vxMax: 2.2,
                        vyMin: 2.8, vyMax: 6.8,
                        gravityMin: 0.13, gravityMax: 0.26,
                    }
                );
                ensureRaf();
            }, 700);

            ensureRaf();
        }

        return {
            trigger: trigger,
            triggerEpic: triggerEpic,
        };
    })();

    if (typeof window !== 'undefined') {
        window.finalizeCelebration = taskFinalizeCelebration;
    }

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

    function isActiveTaskStatus(status) {
        return normalizeTaskStatusValue(status) !== TASK_FINALIZADA_STATUS;
    }

    function getStageIdFromTaskRow(row) {
        if (!row) return '';
        if (row.getAttribute('data-stage-legacy') === '1') return '';
        return String(row.getAttribute('data-stage-id') || '').trim();
    }

    function syncStageActiveTaskCount(row, previousStatus, nextStatus) {
        var stageId = getStageIdFromTaskRow(row);
        if (!stageId) return;

        var wasActive = isActiveTaskStatus(previousStatus);
        var isActive = isActiveTaskStatus(nextStatus);
        if (wasActive === isActive) return;

        // A mudança de status só afeta "concluídas" (done) na pílula da etapa;
        // o total permanece. Virou finalizada (inativa) → done+1;
        // voltou a ativa → done-1.
        var doneDelta = isActive ? -1 : 1;
        if (
            window.stageTaskQuickAddRows &&
            typeof window.stageTaskQuickAddRows.updateStageProgress === 'function'
        ) {
            window.stageTaskQuickAddRows.updateStageProgress(stageId, 0, doneDelta);
        }
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
        var isNewFinalizeAttempt = (
            nextStatus === TASK_FINALIZADA_STATUS &&
            previousStatus !== TASK_FINALIZADA_STATUS
        );

        if (
            isNewFinalizeAttempt &&
            rowBeforeUpdate &&
            typeof getTaskItemCanFinalize === 'function' &&
            !getTaskItemCanFinalize(rowBeforeUpdate)
        ) {
            var finalizePermissionError = new Error('Apenas o criador da tarefa pode movê-la para Finalizada.');
            if (showAlert) {
                alert(finalizePermissionError.message);
            }
            return Promise.reject(finalizePermissionError);
        }

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
                    syncStageActiveTaskCount(row, previousStatus, nextStatus);
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
