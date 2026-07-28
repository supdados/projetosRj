/**
 * Motor dos ícones 3D do topnav: UM contexto WebGL para os 5 ícones, com um
 * tile por ícone copiado para o `<canvas>` 2D de cada item. Um renderer por
 * ícone consumiria 5 dos ~8-16 contextos da aba, e ao estourar o limite o
 * navegador descarta o mais antigo — que seria o da navbar.
 *
 * Render sob demanda: a pose de repouso é estática, então o loop nasce na
 * interação e se auto-cancela quando as molas assentam. `three` entra por
 * `import()` em idle; até chegar, o `<i>` Font Awesome segue na tela.
 *
 * Exemplo:
 *     const handle = await attachNavIcon(canvasEl, 'projetos', true);
 *     handle?.press();  // pointerdown
 *     handle?.release(); // pointerup
 */
import { browser } from '$app/environment';
import { buildIcon, disposeIcon, makeMats, type IconMaterials } from './iconModels';
import {
	ACTIVE_PALETTES,
	IDLE_PALETTE,
	PALETTE_CHANNELS,
	resolveActiveTokens,
	type NavIconKind
} from './palettes';
import {
	NAV3D_SPRING,
	PRESS_SCALE,
	PRESS_YAW,
	RELEASE_KICK,
	snapSpring,
	springSettled,
	stepSpring,
	type SpringState
} from './spring';

type ThreeNS = typeof import('three');

/** Lado do tile em CSS px. Com a câmera do protótipo o ícone ocupa ~77% disso. */
const TILE_CSS = 20;
/** Dial de calibração óptica: massa visual do 3D contra o glifo Font Awesome. */
export const ICON_SCALE = 1;
/** Dial de alinhamento vertical (CSS px, positivo desce). */
export const ICON_Y_NUDGE = 0;
/** Pose de repouso do protótipo: o ícone "de lado" quando o item não é o atual. */
const IDLE_ROT = { x: -0.1, y: -0.34 };
const KILL_SWITCH_KEY = 'nav3d';
const PROBE_CACHE_KEY = 'nav3d:webgl';
/** Depois disso, contexto perdido de novo = desiste e fica no Font Awesome. */
const MAX_CONTEXT_RESTORES = 2;

export interface NavIconHandle {
	setActive(active: boolean): void;
	press(): void;
	release(): void;
	detach(): void;
}

interface ColorPair {
	material: IconMaterials[(typeof PALETTE_CHANNELS)[number]];
	/** Cores pré-criadas: o loop não pode alocar `Color` por frame. */
	from: import('three').Color;
	to: import('three').Color;
}

interface Slot {
	kind: NavIconKind;
	canvas: HTMLCanvasElement;
	ctx: CanvasRenderingContext2D;
	scene: import('three').Scene;
	icon: import('three').Group;
	mats: IconMaterials;
	pairs: ColorPair[];
	baseScale: number;
	/** 0 = repouso, 1 = ativo. Controla pose e cor. */
	route: SpringState;
	color: SpringState;
	/** Escala de acionamento (press/release). */
	punch: SpringState;
	activeTarget: number;
	pressed: boolean;
	dirty: boolean;
	detached: boolean;
	/** Avisa o componente para mostrar o 3D ou voltar ao Font Awesome. */
	onLive: (live: boolean) => void;
}

let THREE: ThreeNS | null = null;
let renderer: import('three').WebGLRenderer | null = null;
let glCanvas: HTMLCanvasElement | null = null;
let camera: import('three').PerspectiveCamera | null = null;
let slots: Slot[] = [];
let raf: number | null = null;
let lastFrame = 0;
let dpr = 1;
let reducedMotion = false;
let contextRestores = 0;
let dead = false;
let initPromise: Promise<boolean> | null = null;
let cleanups: (() => void)[] = [];

/** Kill switch de suporte: `localStorage.setItem('nav3d','off')`. */
function killSwitchOn(): boolean {
	try {
		return window.localStorage.getItem(KILL_SWITCH_KEY) === 'off';
	} catch {
		// Storage bloqueado por política do navegador não é motivo para desligar.
		return false;
	}
}

function readCache(key: string): string | null {
	try {
		return window.sessionStorage.getItem(key);
	} catch {
		return null;
	}
}

function writeCache(key: string, value: string): void {
	try {
		window.sessionStorage.setItem(key, value);
	} catch {
		/* storage indisponível: só perde o cache do probe */
	}
}

/**
 * O probe cria e descarta um contexto — custa dezenas de ms na primeira vez,
 * por isso roda em idle (nunca na hidratação) e o veredito fica em sessão.
 */
function probeWebgl(): boolean {
	const cached = readCache(PROBE_CACHE_KEY);
	if (cached === 'yes') return true;
	if (cached === 'no') return false;
	let ok = false;
	try {
		const probe = document.createElement('canvas');
		const gl = probe.getContext('webgl2', {
			failIfMajorPerformanceCaveat: true,
			powerPreference: 'low-power'
		}) as WebGL2RenderingContext | null;
		ok = gl !== null;
		gl?.getExtension('WEBGL_lose_context')?.loseContext();
	} catch {
		ok = false;
	}
	writeCache(PROBE_CACHE_KEY, ok ? 'yes' : 'no');
	return ok;
}

/** requestIdleCallback com fallback (Safari < 18) e teto de espera. */
function whenIdle(run: () => void): void {
	const rIC = window.requestIdleCallback?.bind(window);
	if (rIC) rIC(() => run(), { timeout: 3000 });
	else window.setTimeout(run, 300);
}

function tilePixels(): number {
	return Math.round(TILE_CSS * dpr);
}

function syncBufferSize(): void {
	if (!renderer || !glCanvas) return;
	const tile = tilePixels();
	renderer.setSize(tile * Math.max(slots.length, 1), tile, false);
	for (const slot of slots) {
		slot.canvas.width = tile;
		slot.canvas.height = tile;
		slot.dirty = true;
	}
	requestLoop();
}

/**
 * DPR não dispara `resize` ao arrastar a janela entre monitores diferentes —
 * o padrão canônico é re-armar uma media query de `resolution`.
 */
function watchDevicePixelRatio(): void {
	let current: MediaQueryList | null = null;
	const onChange = () => {
		dpr = Math.min(window.devicePixelRatio || 1, 2);
		renderer?.setPixelRatio(1);
		syncBufferSize();
		arm();
	};
	const arm = () => {
		current = window.matchMedia(`(resolution: ${window.devicePixelRatio}dppx)`);
		current.addEventListener('change', onChange, { once: true });
	};
	arm();
	cleanups.push(() => current?.removeEventListener('change', onChange));
}

function watchReducedMotion(): void {
	const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
	reducedMotion = mq.matches;
	const onChange = (event: MediaQueryListEvent) => {
		reducedMotion = event.matches;
		if (!reducedMotion) return;
		// Cancelar o loop com molas em voo congelaria os ícones a meio caminho.
		cancelLoop();
		for (const slot of slots) {
			snapAll(slot);
			paint(slot);
		}
	};
	mq.addEventListener('change', onChange);
	cleanups.push(() => mq.removeEventListener('change', onChange));
}

function watchVisibility(): void {
	const onVisible = () => {
		if (document.hidden) {
			cancelLoop();
			return;
		}
		for (const slot of slots) {
			snapAll(slot);
			paint(slot);
		}
	};
	document.addEventListener('visibilitychange', onVisible);
	cleanups.push(() => document.removeEventListener('visibilitychange', onVisible));
}

function watchContextLoss(): void {
	if (!glCanvas) return;
	const canvas = glCanvas;
	const onLost = (event: Event) => {
		event.preventDefault();
		cancelLoop();
		// Enquanto não restaura, os canvases ficam vazios: o Font Awesome volta.
		for (const slot of slots) hideSlot(slot);
	};
	const onRestored = () => {
		contextRestores += 1;
		if (contextRestores > MAX_CONTEXT_RESTORES) {
			destroyStage(true);
			return;
		}
		syncBufferSize();
		for (const slot of slots) showSlot(slot);
	};
	canvas.addEventListener('webglcontextlost', onLost);
	canvas.addEventListener('webglcontextrestored', onRestored);
	cleanups.push(() => {
		canvas.removeEventListener('webglcontextlost', onLost);
		canvas.removeEventListener('webglcontextrestored', onRestored);
	});
}

function hideSlot(slot: Slot): void {
	slot.ctx.clearRect(0, 0, slot.canvas.width, slot.canvas.height);
	slot.onLive(false);
}

function showSlot(slot: Slot): void {
	slot.dirty = true;
	requestLoop();
}

function buildStage(three: ThreeNS): boolean {
	glCanvas = document.createElement('canvas');
	try {
		renderer = new three.WebGLRenderer({
			canvas: glCanvas,
			alpha: true,
			antialias: true,
			preserveDrawingBuffer: true,
			powerPreference: 'low-power',
			failIfMajorPerformanceCaveat: true
		});
	} catch {
		renderer = null;
		glCanvas = null;
		return false;
	}
	renderer.setPixelRatio(1);
	renderer.setClearAlpha(0);
	renderer.autoClear = false;
	camera = new three.PerspectiveCamera(28, 1, 0.1, 10);
	camera.position.set(0, 0.06, 2.6);
	camera.lookAt(0, 0, 0);
	return true;
}

function buildScene(three: ThreeNS, kind: NavIconKind): {
	scene: import('three').Scene;
	icon: import('three').Group;
	mats: IconMaterials;
} {
	const scene = new three.Scene();
	scene.add(new three.HemisphereLight(0xffffff, 0x9db6c8, 0.85));
	const key = new three.DirectionalLight(0xffffff, 1.7);
	key.position.set(1.6, 2.2, 2.6);
	const fill = new three.DirectionalLight(0xffffff, 0.45);
	fill.position.set(-2.2, 0.4, 1.4);
	scene.add(key, fill);
	const mats = makeMats(three, IDLE_PALETTE);
	const icon = buildIcon(three, kind, mats);
	scene.add(icon);
	return { scene, icon, mats };
}

async function ensureStage(): Promise<boolean> {
	if (dead) return false;
	if (renderer) return true;
	if (initPromise) return initPromise;
	initPromise = new Promise<boolean>((resolve) => {
		whenIdle(async () => {
			if (dead) return resolve(false);
			if (!probeWebgl()) {
				dead = true;
				return resolve(false);
			}
			try {
				THREE = await import('three');
			} catch {
				dead = true;
				return resolve(false);
			}
			if (dead || !buildStage(THREE)) {
				dead = true;
				return resolve(false);
			}
			// Antes de qualquer material ser criado, para pegar o hex certo.
			resolveActiveTokens();
			dpr = Math.min(window.devicePixelRatio || 1, 2);
			watchDevicePixelRatio();
			watchReducedMotion();
			watchVisibility();
			watchContextLoss();
			resolve(true);
		});
	});
	return initPromise;
}

/** Cola todas as molas do slot no alvo (reduced-motion, aba oculta, restore). */
function snapAll(slot: Slot): void {
	snapSpring(slot.route, slot.activeTarget);
	snapSpring(slot.color, slot.activeTarget);
	snapSpring(slot.punch, slot.pressed ? PRESS_SCALE : 1);
	slot.dirty = true;
}

function applySprings(slot: Slot): void {
	const away = 1 - slot.route.x;
	const pressYaw = slot.pressed ? PRESS_YAW : 0;
	slot.icon.rotation.set(IDLE_ROT.x * away, IDLE_ROT.y * away + pressYaw, 0);
	slot.icon.scale.setScalar(slot.baseScale * ICON_SCALE * slot.punch.x);
	for (const pair of slot.pairs) {
		pair.material.color.copy(pair.from).lerp(pair.to, slot.color.x);
	}
}

/** Renderiza o tile do slot e copia para o canvas do item. */
function paint(slot: Slot): void {
	if (!renderer || !camera || !THREE || slot.detached) return;
	applySprings(slot);
	const tile = tilePixels();
	const index = slots.indexOf(slot);
	if (index < 0) return;
	renderer.setViewport(index * tile, 0, tile, tile);
	renderer.setScissor(index * tile, 0, tile, tile);
	renderer.setScissorTest(true);
	renderer.clear(true, true, false);
	renderer.render(slot.scene, camera);
	slot.ctx.globalCompositeOperation = 'copy';
	slot.ctx.drawImage(renderer.domElement, index * tile, 0, tile, tile, 0, 0, tile, tile);
	slot.onLive(true);
}

function frame(now: number): void {
	raf = null;
	if (!renderer) return;
	const dt = lastFrame ? (now - lastFrame) / 1000 : 1 / 60;
	lastFrame = now;
	let running = false;
	for (const slot of slots) {
		if (!slot.dirty) continue;
		const punchTarget = slot.pressed ? PRESS_SCALE : 1;
		stepSpring(slot.route, slot.activeTarget, NAV3D_SPRING.route, dt);
		stepSpring(slot.color, slot.activeTarget, NAV3D_SPRING.color, dt);
		stepSpring(slot.punch, punchTarget, slot.pressed ? NAV3D_SPRING.press : NAV3D_SPRING.release, dt);
		paint(slot);
		const settled =
			springSettled(slot.route, slot.activeTarget) &&
			springSettled(slot.color, slot.activeTarget) &&
			springSettled(slot.punch, punchTarget);
		slot.dirty = !settled;
		running ||= !settled;
	}
	if (running) requestLoop();
	else lastFrame = 0;
}

function requestLoop(): void {
	if (raf !== null || dead || !renderer) return;
	if (document.hidden) return;
	raf = window.requestAnimationFrame(frame);
}

function cancelLoop(): void {
	if (raf === null) return;
	window.cancelAnimationFrame(raf);
	raf = null;
	lastFrame = 0;
}

function invalidate(slot: Slot): void {
	if (dead || slot.detached || !renderer) return;
	if (reducedMotion) {
		snapAll(slot);
		paint(slot);
		slot.dirty = false;
		return;
	}
	slot.dirty = true;
	requestLoop();
}

/**
 * Derruba o stage. `permanent` distingue falha real (WebGL perdido demais) de
 * teardown por não haver mais item na tela — no segundo caso um remount do
 * topnav precisa poder subir o 3D de novo.
 */
function destroyStage(permanent: boolean): void {
	cancelLoop();
	for (const cleanup of cleanups) cleanup();
	cleanups = [];
	for (const slot of slots) {
		hideSlot(slot);
		disposeIcon(slot.icon, slot.mats);
		slot.detached = true;
	}
	slots = [];
	renderer?.dispose();
	renderer?.forceContextLoss();
	renderer = null;
	glCanvas = null;
	camera = null;
	THREE = null;
	dead = permanent;
	initPromise = null;
	if (!permanent) contextRestores = 0;
}

/**
 * Liga um `<canvas>` de item ao stage. Devolve `null` quando o 3D não é
 * possível (sem WebGL, kill switch, three não carregou, stage morto) — nesse
 * caso o item continua exibindo o ícone Font Awesome.
 */
export async function attachNavIcon(
	canvas: HTMLCanvasElement,
	kind: NavIconKind,
	active: boolean,
	onLive: (live: boolean) => void
): Promise<NavIconHandle | null> {
	if (!browser || killSwitchOn()) return null;
	if (!(await ensureStage()) || !THREE || !renderer) return null;
	const ctx = canvas.getContext('2d');
	if (!ctx) return null;

	const { scene, icon, mats } = buildScene(THREE, kind);
	const slot: Slot = {
		kind,
		canvas,
		ctx,
		scene,
		icon,
		mats,
		pairs: PALETTE_CHANNELS.map((channel) => ({
			material: mats[channel],
			from: new THREE!.Color(IDLE_PALETTE[channel]),
			to: new THREE!.Color(ACTIVE_PALETTES[kind][channel])
		})),
		baseScale: icon.scale.x,
		route: { x: active ? 1 : 0, v: 0 },
		color: { x: active ? 1 : 0, v: 0 },
		punch: { x: 1, v: 0 },
		activeTarget: active ? 1 : 0,
		pressed: false,
		dirty: true,
		detached: false,
		onLive
	};
	slots.push(slot);
	syncBufferSize();
	paint(slot);

	return {
		setActive(next: boolean): void {
			if (slot.detached) return;
			slot.activeTarget = next ? 1 : 0;
			invalidate(slot);
		},
		press(): void {
			if (slot.detached || slot.pressed) return;
			slot.pressed = true;
			invalidate(slot);
		},
		release(): void {
			if (slot.detached || !slot.pressed) return;
			slot.pressed = false;
			// Impulso: sem ele o retorno 0.9 -> 1 não teria "pop" perceptível.
			if (!reducedMotion) slot.punch.v = RELEASE_KICK;
			invalidate(slot);
		},
		detach(): void {
			if (slot.detached) return;
			slot.detached = true;
			const index = slots.indexOf(slot);
			if (index >= 0) slots.splice(index, 1);
			disposeIcon(slot.icon, slot.mats);
			slot.onLive(false);
			if (slots.length === 0) destroyStage(false);
			else syncBufferSize();
		}
	};
}
