/**
 * Confete em CANVAS — porte FIEL de `static/js/modules/task-item-operations.js`
 * (objeto `taskFinalizeCelebration`), exposto no legado como
 * `window.finalizeCelebration`. Replica EXATAMENTE as paletas, mixes de forma,
 * padrões (classic/wide/fountain/double_side), estilos de explosão e a
 * coreografia de `triggerEpic` (8 rajadas em ondas + 2 cascatas contínuas).
 *
 * Usado pelo overlay de "Concluir Projeto" (chamando `triggerEpic`). NÃO usa
 * `canvas-confetti`: o legado tem um motor próprio, e a fidelidade exige
 * reproduzir a mesma física/timing — por isso o porte 1:1.
 *
 * RESPEITA `prefers-reduced-motion`: quando ativo, não dispara nada.
 *
 * O canvas usa a classe `.task-finalize-confetti-canvas` (mesmo CSS do legado,
 * portado em src/lib/celebration/confetti.css importado pelo componente).
 */

type ShapeMix = { rect: number; circle: number; triangle: number; streamer: number; star: number };

interface Particle {
	x: number;
	y: number;
	vx: number;
	vy: number;
	gravity: number;
	drag: number;
	angle: number;
	spin: number;
	tilt: number;
	tiltSpeed: number;
	width: number;
	height: number;
	shape: keyof ShapeMix;
	color: string;
	life: number;
	maxLife: number;
}

interface BurstOptions {
	angleCenter?: number;
	xJitter?: number;
	yJitter?: number;
	circleChance?: number;
}

interface CascadeOptions {
	xSpread?: number;
	yMin?: number;
	yMax?: number;
	vxMin?: number;
	vxMax?: number;
	vyMin?: number;
	vyMax?: number;
	gravityMin?: number;
	gravityMax?: number;
	circleChance?: number;
}

const CONFETTI_PALETTES: string[][] = [
	['#f4d35e', '#ee964b', '#f95738', '#0d8b8b', '#4f7cac', '#9c6ade', '#52b788'],
	['#ff6b9d', '#f06292', '#c4378b', '#7e57c2', '#5e35b1', '#3949ab', '#ffd54f'],
	['#06d6a0', '#118ab2', '#073b4c', '#ffd166', '#ef476f', '#83c5be', '#e29578'],
	['#fb8500', '#ffb703', '#fdf0d5', '#8ecae6', '#219ebc', '#023047', '#ff006e'],
	['#ffba08', '#faa307', '#f48c06', '#dc2f02', '#9d0208', '#3a86ff', '#8338ec'],
	['#caffbf', '#9bf6ff', '#a0c4ff', '#bdb2ff', '#ffc6ff', '#ffadad', '#ffd6a5'],
	['#2ec4b6', '#cbf3f0', '#ff9f1c', '#ffbf69', '#e71d36', '#011627', '#fdfffc']
];

const CONFETTI_SHAPE_MIXES: ShapeMix[] = [
	{ rect: 0.45, circle: 0.2, triangle: 0.15, streamer: 0.12, star: 0.08 },
	{ rect: 0.18, circle: 0.3, triangle: 0.1, streamer: 0.12, star: 0.3 },
	{ rect: 0.2, circle: 0.1, triangle: 0.15, streamer: 0.45, star: 0.1 },
	{ rect: 0.4, circle: 0.1, triangle: 0.4, streamer: 0.05, star: 0.05 },
	{ rect: 0.2, circle: 0.45, triangle: 0.05, streamer: 0.1, star: 0.2 }
];

type BurstStyle = {
	spread: number;
	speedMin: number;
	speedMax: number;
	gravityMin: number;
	gravityMax: number;
	xJitter: number;
	yJitter: number;
};

const BURST_STYLES: Record<string, BurstStyle> = {
	explosive: { spread: 1.55, speedMin: 8.6, speedMax: 16.4, gravityMin: 0.2, gravityMax: 0.4, xJitter: 14, yJitter: 10 },
	firework: { spread: 0.45, speedMin: 10.2, speedMax: 18.0, gravityMin: 0.17, gravityMax: 0.3, xJitter: 6, yJitter: 6 },
	drift: { spread: 1.95, speedMin: 3.8, speedMax: 7.6, gravityMin: 0.06, gravityMax: 0.14, xJitter: 22, yJitter: 14 },
	pop: { spread: 0.85, speedMin: 5.6, speedMax: 9.4, gravityMin: 0.22, gravityMax: 0.42, xJitter: 8, yJitter: 6 },
	shower: { spread: 2.4, speedMin: 4.2, speedMax: 8.6, gravityMin: 0.26, gravityMax: 0.5, xJitter: 28, yJitter: 18 },
	geyser: { spread: 0.32, speedMin: 11.4, speedMax: 17.6, gravityMin: 0.18, gravityMax: 0.32, xJitter: 4, yJitter: 8 }
};
const BURST_STYLE_KEYS = Object.keys(BURST_STYLES);

let canvas: HTMLCanvasElement | null = null;
let ctx: CanvasRenderingContext2D | null = null;
let particles: Particle[] = [];
let rafId = 0;
let lastTs = 0;
let resizeBound = false;
let hideTimer: ReturnType<typeof setTimeout> | null = null;
let activePalette = CONFETTI_PALETTES[0];
let activeShapeMix = CONFETTI_SHAPE_MIXES[0];

function prefersReducedMotion(): boolean {
	return !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
}

function randomBetween(min: number, max: number): number {
	return min + Math.random() * (max - min);
}

function randomColor(): string {
	return activePalette[Math.floor(Math.random() * activePalette.length)];
}

function pickShape(circleChance?: number): keyof ShapeMix {
	if (Number.isFinite(circleChance) && (circleChance as number) >= 0 && (circleChance as number) <= 1) {
		const cc = circleChance as number;
		const roll = Math.random();
		if (roll < cc * 0.78) return 'circle';
		if (roll < cc * 0.78 + 0.1) return 'triangle';
		if (roll < cc * 0.78 + 0.16) return 'star';
		if (roll < cc * 0.78 + 0.22) return 'streamer';
		return 'rect';
	}
	const r = Math.random();
	let acc = 0;
	const keys: (keyof ShapeMix)[] = ['rect', 'circle', 'triangle', 'streamer', 'star'];
	for (const key of keys) {
		acc += activeShapeMix[key] || 0;
		if (r < acc) return key;
	}
	return 'rect';
}

function randomizeVibe(): void {
	activePalette = CONFETTI_PALETTES[Math.floor(Math.random() * CONFETTI_PALETTES.length)];
	activeShapeMix = CONFETTI_SHAPE_MIXES[Math.floor(Math.random() * CONFETTI_SHAPE_MIXES.length)];
}

function resizeCanvas(): void {
	if (!canvas) return;
	const viewportWidth = Math.max(window.innerWidth || 0, document.documentElement.clientWidth || 0, 1);
	const viewportHeight = Math.max(window.innerHeight || 0, document.documentElement.clientHeight || 0, 1);
	const dpr = Math.min(window.devicePixelRatio || 1, 2);
	canvas.width = Math.round(viewportWidth * dpr);
	canvas.height = Math.round(viewportHeight * dpr);
	canvas.style.width = viewportWidth + 'px';
	canvas.style.height = viewportHeight + 'px';
	if (ctx) ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
}

function ensureCanvas(): void {
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

interface Origin {
	x: number;
	y: number;
}

function spawnBurst(
	origin: Origin,
	count: number,
	spread: number,
	speedMin: number,
	speedMax: number,
	gravityMin: number,
	gravityMax: number,
	options: BurstOptions = {}
): void {
	const angleCenter = Number.isFinite(options.angleCenter) ? (options.angleCenter as number) : -Math.PI / 2;
	const xJitter = Number.isFinite(options.xJitter) ? (options.xJitter as number) : 8;
	const yJitter = Number.isFinite(options.yJitter) ? (options.yJitter as number) : 6;
	const circleChance = Number.isFinite(options.circleChance) ? (options.circleChance as number) : 0.2;
	for (let i = 0; i < count; i += 1) {
		const angle = angleCenter + randomBetween(-spread, spread);
		const speed = randomBetween(speedMin, speedMax);
		const life = randomBetween(44, 92);
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
			life,
			maxLife: life
		});
	}
}

function spawnCascade(origin: Origin, count: number, options: CascadeOptions = {}): void {
	const xSpread = Number.isFinite(options.xSpread) ? (options.xSpread as number) : 220;
	const yMin = Number.isFinite(options.yMin) ? (options.yMin as number) : 120;
	const yMax = Number.isFinite(options.yMax) ? (options.yMax as number) : 300;
	const vxMin = Number.isFinite(options.vxMin) ? (options.vxMin as number) : -1.4;
	const vxMax = Number.isFinite(options.vxMax) ? (options.vxMax as number) : 1.4;
	const vyMin = Number.isFinite(options.vyMin) ? (options.vyMin as number) : 2.4;
	const vyMax = Number.isFinite(options.vyMax) ? (options.vyMax as number) : 5.1;
	const gravityMin = Number.isFinite(options.gravityMin) ? (options.gravityMin as number) : 0.1;
	const gravityMax = Number.isFinite(options.gravityMax) ? (options.gravityMax as number) : 0.22;
	const circleChance = Number.isFinite(options.circleChance) ? (options.circleChance as number) : 0.18;
	for (let i = 0; i < count; i += 1) {
		const life = randomBetween(56, 112);
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
			life,
			maxLife: life
		});
	}
}

function drawParticle(particle: Particle, alpha: number): void {
	if (!ctx) return;
	ctx.save();
	ctx.translate(
		particle.x + Math.cos(particle.tilt) * 2.4,
		particle.y + Math.sin(particle.tilt * 0.72) * 0.8
	);
	ctx.rotate(particle.angle);
	ctx.globalAlpha = alpha;
	ctx.fillStyle = particle.color;

	if (particle.shape === 'circle') {
		ctx.beginPath();
		ctx.arc(0, 0, Math.max(2, particle.width * 0.48), 0, Math.PI * 2);
		ctx.fill();
	} else if (particle.shape === 'triangle') {
		const ts = Math.max(3, particle.width * 0.95);
		ctx.beginPath();
		ctx.moveTo(0, -ts);
		ctx.lineTo(ts * 0.92, ts * 0.78);
		ctx.lineTo(-ts * 0.92, ts * 0.78);
		ctx.closePath();
		ctx.fill();
	} else if (particle.shape === 'star') {
		const spikes = 5;
		const outer = Math.max(3, particle.width * 0.9);
		const inner = outer * 0.46;
		ctx.beginPath();
		for (let s = 0; s < spikes * 2; s += 1) {
			const radius = s % 2 === 0 ? outer : inner;
			const angle = (Math.PI / spikes) * s - Math.PI / 2;
			const px = Math.cos(angle) * radius;
			const py = Math.sin(angle) * radius;
			if (s === 0) ctx.moveTo(px, py);
			else ctx.lineTo(px, py);
		}
		ctx.closePath();
		ctx.fill();
	} else if (particle.shape === 'streamer') {
		const len = particle.height * 1.8;
		const thick = Math.max(1.5, particle.width * 0.42);
		const wave = Math.sin(particle.tilt * 1.3) * 0.6 + 0.4;
		ctx.scale(1, wave);
		ctx.fillRect(-thick / 2, -len / 2, thick, len);
	} else {
		const flip = 0.35 + (Math.sin(particle.tilt) + 1) * 0.45;
		ctx.scale(1, flip);
		ctx.fillRect(-particle.width / 2, -particle.height / 2, particle.width, particle.height);
	}
	ctx.restore();
}

function tick(timestamp: number): void {
	if (!canvas || !ctx) {
		rafId = 0;
		lastTs = 0;
		particles.length = 0;
		return;
	}

	const dt = lastTs ? Math.min((timestamp - lastTs) / 16.6667, 2.4) : 1;
	lastTs = timestamp;
	const viewportWidth = window.innerWidth || document.documentElement.clientWidth || 0;
	const viewportHeight = window.innerHeight || document.documentElement.clientHeight || 0;
	ctx.clearRect(0, 0, viewportWidth, viewportHeight);

	for (let i = particles.length - 1; i >= 0; i -= 1) {
		const particle = particles[i];
		particle.life -= dt;
		if (particle.life <= 0) {
			particles.splice(i, 1);
			continue;
		}

		particle.vx *= particle.drag;
		particle.vy = particle.vy * particle.drag + particle.gravity * dt;
		particle.x += particle.vx * dt;
		particle.y += particle.vy * dt;
		particle.angle += particle.spin * dt;
		particle.tilt += particle.tiltSpeed * dt;

		if (particle.y > viewportHeight + 56 || particle.x < -72 || particle.x > viewportWidth + 72) {
			particles.splice(i, 1);
			continue;
		}

		const alpha = Math.min(1, Math.max(0, particle.life / (particle.maxLife * 0.66)));
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
	hideTimer = setTimeout(() => {
		if (!canvas || rafId || particles.length) return;
		if (canvas.parentNode) canvas.parentNode.removeChild(canvas);
		canvas = null;
		ctx = null;
		hideTimer = null;
	}, 320);
}

function shuffledStyleKeys(): string[] {
	const keys = BURST_STYLE_KEYS.slice();
	for (let i = keys.length - 1; i > 0; i -= 1) {
		const j = Math.floor(Math.random() * (i + 1));
		const tmp = keys[i];
		keys[i] = keys[j];
		keys[j] = tmp;
	}
	return keys;
}

function styledBurst(origin: Origin, count: number, styleKey: string, angleCenter: number): void {
	const s = BURST_STYLES[styleKey] || BURST_STYLES.explosive;
	const spread = s.spread * randomBetween(0.9, 1.12);
	const speedMin = s.speedMin * randomBetween(0.92, 1.08);
	const speedMax = s.speedMax * randomBetween(0.92, 1.1);
	const gravityMin = s.gravityMin * randomBetween(0.88, 1.14);
	const gravityMax = s.gravityMax * randomBetween(0.92, 1.12);
	spawnBurst(origin, count, spread, speedMin, speedMax, gravityMin, gravityMax, {
		angleCenter,
		xJitter: s.xJitter,
		yJitter: s.yJitter
	});
}

function ensureRaf(): void {
	if (particles.length > 1500) particles.splice(0, particles.length - 1500);
	if (!rafId) rafId = window.requestAnimationFrame(tick);
}

/**
 * Origem da celebração quando o caller passa um elemento/rect/ponto (paridade
 * com `resolveOrigin`/`originFromRect` do legado). Aceita:
 *   - `{ x, y }` (ponto absoluto, ex.: posição do ponteiro no drop);
 *   - um elemento DOM (usa `getBoundingClientRect` -> centro horizontal, 36% top);
 *   - um rect-like (`{ left, right, top, bottom }`);
 *   - `null`/indefinido -> fallback (canto superior direito).
 */
export type CelebrationOriginLike =
	| { x: number; y: number }
	| Element
	| { left: number; right: number; top: number; bottom: number }
	| null
	| undefined;

interface RectLike {
	left: number;
	right: number;
	top: number;
	bottom: number;
}

function originFromRect(rect: RectLike | null): Origin | null {
	if (!rect) return null;
	if (
		!Number.isFinite(rect.left) ||
		!Number.isFinite(rect.right) ||
		!Number.isFinite(rect.top) ||
		!Number.isFinite(rect.bottom)
	) {
		return null;
	}
	return {
		x: rect.left + (rect.right - rect.left) / 2,
		y: rect.top + (rect.bottom - rect.top) * 0.36
	};
}

function resolveOrigin(originLike: CelebrationOriginLike): Origin {
	const viewportWidth = window.innerWidth || document.documentElement.clientWidth || 1280;
	const viewportHeight = window.innerHeight || document.documentElement.clientHeight || 720;
	const fallback: Origin = {
		x: Math.max(24, viewportWidth * 0.72),
		y: Math.max(84, viewportHeight * 0.24)
	};

	if (!originLike) return fallback;

	const pointLike = originLike as { x?: number; y?: number };
	if (Number.isFinite(pointLike.x) && Number.isFinite(pointLike.y)) {
		return { x: pointLike.x as number, y: pointLike.y as number };
	}

	const maybeElement = originLike as { getBoundingClientRect?: () => DOMRect };
	if (typeof maybeElement.getBoundingClientRect === 'function') {
		const fromElement = originFromRect(maybeElement.getBoundingClientRect());
		if (fromElement) return fromElement;
	}

	const fromRectLike = originFromRect(originLike as RectLike);
	if (fromRectLike) return fromRectLike;

	return fallback;
}

let lastPatternKey = '';

function pickConfettiPattern(): string {
	const patterns = ['classic', 'wide', 'fountain', 'double_side'];
	const index = Math.floor(Math.random() * patterns.length);
	let picked = patterns[index];

	if (patterns.length > 1 && picked === lastPatternKey) {
		picked = patterns[(index + 1 + Math.floor(Math.random() * (patterns.length - 1))) % patterns.length];
	}

	lastPatternKey = picked;
	return picked;
}

function runConfettiPattern(origin: Origin, patternKey: string): void {
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
			gravityMax: 0.24
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
			gravityMax: 0.2
		});
		return;
	}

	if (patternKey === 'double_side') {
		const sideOffset = Math.min(Math.max((window.innerWidth || 1200) * 0.14, 120), 260);
		spawnBurst({ x: origin.x - sideOffset, y: origin.y + 6 }, 62, 0.5, 6.4, 12.8, 0.17, 0.33, {
			angleCenter: -0.74,
			xJitter: 7,
			yJitter: 7
		});
		spawnBurst({ x: origin.x + sideOffset, y: origin.y + 6 }, 62, 0.5, 6.4, 12.8, 0.17, 0.33, {
			angleCenter: -2.4,
			xJitter: 7,
			yJitter: 7
		});
		spawnCascade({ x: origin.x + randomBetween(-18, 18), y: origin.y - 10 }, 42, {
			xSpread: 280,
			yMin: 110,
			yMax: 290,
			vxMin: -1.7,
			vxMax: 1.7,
			vyMin: 2.3,
			vyMax: 4.9,
			gravityMin: 0.12,
			gravityMax: 0.24
		});
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

/**
 * Celebração de CONCLUSÃO DE TAREFA — porte 1:1 de
 * `taskFinalizeCelebration.trigger` (chamado por `updateItemStatus` no legado
 * quando uma tarefa transita para "finalizada"). Sorteia uma "vibe" (paleta +
 * mix de formas) e um padrão (classic/wide/fountain/double_side) a cada
 * disparo, originado na posição passada (card/ponteiro). No-op com
 * `prefers-reduced-motion`.
 */
export function triggerTaskFinalizeConfetti(originLike?: CelebrationOriginLike): void {
	if (typeof window === 'undefined') return;
	if (prefersReducedMotion()) return;
	ensureCanvas();
	if (!canvas || !ctx) return;

	randomizeVibe();
	const origin = resolveOrigin(originLike);
	const patternKey = pickConfettiPattern();
	if (hideTimer) {
		clearTimeout(hideTimer);
		hideTimer = null;
	}

	canvas.classList.add('is-active');
	runConfettiPattern(origin, patternKey);

	if (particles.length > 420) {
		particles.splice(0, particles.length - 420);
	}

	if (!rafId) rafId = window.requestAnimationFrame(tick);
}

/**
 * Coreografia "épica" da conclusão de projeto — porte 1:1 de
 * `taskFinalizeCelebration.triggerEpic`. No-op com `prefers-reduced-motion`.
 */
export function triggerEpicConfetti(): void {
	if (typeof window === 'undefined') return;
	if (prefersReducedMotion()) return;
	ensureCanvas();
	if (!canvas || !ctx) return;
	if (hideTimer) {
		clearTimeout(hideTimer);
		hideTimer = null;
	}
	randomizeVibe();
	canvas.classList.add('is-active');

	const viewportWidth = window.innerWidth || document.documentElement.clientWidth || 1280;
	const viewportHeight = window.innerHeight || document.documentElement.clientHeight || 720;

	const styles = shuffledStyleKeys();
	let styleIndex = 0;
	const nextStyle = (): string => {
		const k = styles[styleIndex % styles.length];
		styleIndex += 1;
		return k;
	};

	const schedule = [
		{ delay: 0, origin: { x: viewportWidth * 0.18, y: viewportHeight * 0.3 }, angle: -Math.PI / 2 + 0.05, count: 95, style: nextStyle() },
		{ delay: 110, origin: { x: viewportWidth * 0.82, y: viewportHeight * 0.32 }, angle: -Math.PI / 2 - 0.06, count: 95, style: nextStyle() },
		{ delay: 220, origin: { x: viewportWidth * 0.5, y: viewportHeight * 0.22 }, angle: -Math.PI / 2, count: 130, style: nextStyle() },
		{ delay: 480, origin: { x: viewportWidth * 0.04, y: viewportHeight * 0.62 }, angle: -0.65, count: 110, style: nextStyle() },
		{ delay: 540, origin: { x: viewportWidth * 0.96, y: viewportHeight * 0.62 }, angle: -2.49, count: 110, style: nextStyle() },
		{ delay: 880, origin: { x: viewportWidth * 0.5, y: viewportHeight * 0.85 }, angle: -Math.PI / 2, count: 170, style: nextStyle() },
		{ delay: 1040, origin: { x: viewportWidth * 0.32, y: viewportHeight * 0.78 }, angle: -Math.PI / 2 + 0.2, count: 70, style: nextStyle() },
		{ delay: 1100, origin: { x: viewportWidth * 0.68, y: viewportHeight * 0.78 }, angle: -Math.PI / 2 - 0.2, count: 70, style: nextStyle() }
	];

	schedule.forEach((step) => {
		if (step.delay === 0) {
			styledBurst(step.origin, step.count, step.style, step.angle);
		} else {
			window.setTimeout(() => {
				if (!canvas || !ctx) return;
				styledBurst(step.origin, step.count, step.style, step.angle);
				ensureRaf();
			}, step.delay);
		}
	});

	spawnCascade(
		{ x: viewportWidth / 2, y: viewportHeight * 0.05 },
		240,
		{
			xSpread: viewportWidth * 0.55,
			yMin: 20,
			yMax: 220,
			vxMin: -2.6,
			vxMax: 2.6,
			vyMin: 2.6,
			vyMax: 6.4,
			gravityMin: 0.12,
			gravityMax: 0.26
		}
	);
	window.setTimeout(() => {
		if (!canvas || !ctx) return;
		spawnCascade(
			{ x: viewportWidth / 2, y: viewportHeight * 0.06 },
			180,
			{
				xSpread: viewportWidth * 0.48,
				yMin: 30,
				yMax: 200,
				vxMin: -2.2,
				vxMax: 2.2,
				vyMin: 2.8,
				vyMax: 6.8,
				gravityMin: 0.13,
				gravityMax: 0.26
			}
		);
		ensureRaf();
	}, 700);

	ensureRaf();
}
