/**
 * Geometria dos ícones 3D do topnav — porte tipado de
 * `micro/docs/protos/icons-models.js` (protótipo aprovado).
 *
 * Só malha e material: nenhuma cena, câmera ou renderer. Tudo procedural —
 * zero loaders de `three/examples/jsm`, que instanciam Worker/WASM via `blob:`
 * e obrigariam a afrouxar a CSP.
 *
 * `THREE` entra por parâmetro (injeção de dependência) para o módulo não
 * carregar three estaticamente: quem decide quando baixar é o `navIconStage`.
 *
 * Exemplo:
 *     const THREE = await import('three');
 *     const mats = makeMats(THREE, IDLE_PALETTE);
 *     scene.add(buildIcon(THREE, 'inicio', mats));
 */
import type {
	Group,
	Mesh,
	MeshStandardMaterial,
	Shape as ThreeShape,
	BufferGeometry
} from 'three';
import { PALETTE_CHANNELS, type IconPalette, type NavIconKind, type PaletteChannel } from './palettes';

type ThreeNS = typeof import('three');

export type IconMaterials = Record<PaletteChannel, MeshStandardMaterial>;

/** Um MeshStandardMaterial por canal da paleta, com o mesmo acabamento do protótipo. */
export function makeMats(THREE: ThreeNS, palette: IconPalette): IconMaterials {
	return {
		main: new THREE.MeshStandardMaterial({ color: palette.main, roughness: 0.4, metalness: 0.1 }),
		deep: new THREE.MeshStandardMaterial({ color: palette.deep, roughness: 0.45, metalness: 0.1 }),
		light: new THREE.MeshStandardMaterial({ color: palette.light, roughness: 0.35, metalness: 0.06 }),
		accent: new THREE.MeshStandardMaterial({ color: palette.accent, roughness: 0.38, metalness: 0.14 })
	};
}

/** Libera materiais e todas as geometrias do grupo (chamado no destroy do stage). */
export function disposeIcon(icon: Group, mats: IconMaterials): void {
	icon.traverse((node) => {
		const geometry = (node as Mesh).geometry as BufferGeometry | undefined;
		geometry?.dispose();
	});
	for (const channel of PALETTE_CHANNELS) mats[channel].dispose();
}

/**
 * Monta o ícone de `kind` centrado na origem e normalizado para caber num
 * cubo unitário. O chamador só precisa posicionar a câmera.
 */
export function buildIcon(THREE: ThreeNS, kind: NavIconKind, M: IconMaterials): Group {
	function roundedRect(w: number, h: number, r: number): ThreeShape {
		const s = new THREE.Shape();
		const x = -w / 2;
		const y = -h / 2;
		s.moveTo(x + r, y);
		s.lineTo(x + w - r, y);
		s.quadraticCurveTo(x + w, y, x + w, y + r);
		s.lineTo(x + w, y + h - r);
		s.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
		s.lineTo(x + r, y + h);
		s.quadraticCurveTo(x, y + h, x, y + h - r);
		s.lineTo(x, y + r);
		s.quadraticCurveTo(x, y, x + r, y);
		return s;
	}

	function roundedPoly(pts: [number, number][], r: number): ThreeShape {
		const s = new THREE.Shape();
		const n = pts.length;
		for (let i = 0; i < n; i += 1) {
			const p0 = pts[(i - 1 + n) % n];
			const p1 = pts[i];
			const p2 = pts[(i + 1) % n];
			const v1 = new THREE.Vector2(p0[0] - p1[0], p0[1] - p1[1]).normalize();
			const v2 = new THREE.Vector2(p2[0] - p1[0], p2[1] - p1[1]).normalize();
			const a: [number, number] = [p1[0] + v1.x * r, p1[1] + v1.y * r];
			const b: [number, number] = [p1[0] + v2.x * r, p1[1] + v2.y * r];
			if (i === 0) s.moveTo(a[0], a[1]);
			else s.lineTo(a[0], a[1]);
			s.quadraticCurveTo(p1[0], p1[1], b[0], b[1]);
		}
		s.closePath();
		return s;
	}

	const ex = (shape: ThreeShape, depth: number, bevel = 0.018) =>
		new THREE.ExtrudeGeometry(shape, {
			depth,
			bevelEnabled: bevel > 0,
			bevelThickness: bevel,
			bevelSize: bevel,
			bevelOffset: 0,
			bevelSegments: 3,
			curveSegments: 16,
			steps: 1
		});

	function slab(
		name: string,
		mat: MeshStandardMaterial,
		w: number,
		h: number,
		d: number,
		r: number,
		x: number,
		y: number,
		z: number,
		bevel = 0.016
	): Mesh {
		const m = new THREE.Mesh(ex(roundedRect(w, h, r), d, bevel), mat);
		m.name = name;
		m.position.set(x, y, z - d / 2);
		return m;
	}

	const mesh = (name: string, geo: BufferGeometry, mat: MeshStandardMaterial): Mesh => {
		const m = new THREE.Mesh(geo, mat);
		m.name = name;
		return m;
	};

	function check(name: string, z: number): Group {
		const g = new THREE.Group();
		g.name = name;
		const a = slab(`${name}_a`, M.main, 0.13, 0.038, 0.024, 0.018, 0, 0, 0);
		a.rotation.z = -0.675;
		a.position.set(-0.05, 0.01, z);
		const b = slab(`${name}_b`, M.main, 0.2, 0.038, 0.024, 0.018, 0, 0, 0);
		b.rotation.z = 0.856;
		b.position.set(0.065, 0.045, z);
		g.add(a, b);
		return g;
	}

	const g = new THREE.Group();
	g.name = kind;

	if (kind === 'inicio') {
		g.add(slab('parede', M.main, 0.72, 0.56, 0.62, 0.05, 0, 0.28, 0));
		const roof = mesh(
			'telhado',
			ex(roundedPoly([[-0.47, 0], [0.47, 0], [0, 0.34]], 0.07), 0.68, 0.02),
			M.deep
		);
		roof.position.set(0, 0.55, -0.34);
		g.add(roof);
		g.add(slab('chamine', M.deep, 0.11, 0.26, 0.11, 0.03, 0.26, 0.72, 0));
		g.add(slab('porta', M.light, 0.2, 0.3, 0.055, 0.045, 0, 0.15, 0.335));
	}

	if (kind === 'projetos') {
		g.add(slab('costas', M.deep, 0.9, 0.64, 0.08, 0.07, 0, 0.32, 0));
		g.add(slab('aba', M.deep, 0.38, 0.16, 0.08, 0.05, -0.25, 0.7, 0));
		g.add(slab('folha_1', M.light, 0.78, 0.52, 0.022, 0.03, 0.02, 0.34, 0.075));
		g.add(slab('folha_2', M.light, 0.72, 0.48, 0.022, 0.03, -0.02, 0.31, 0.115));
		const hinge = new THREE.Group();
		hinge.name = 'frente_pivot';
		hinge.position.set(0, 0.03, 0.1);
		hinge.add(slab('frente', M.main, 0.9, 0.46, 0.07, 0.07, 0, 0.23, 0.035));
		hinge.rotation.x = 0.2;
		g.add(hinge);
	}

	if (kind === 'pendentes') {
		const body = mesh(
			'triangulo',
			ex(roundedPoly([[-0.56, -0.34], [0.56, -0.34], [0, 0.63]], 0.11), 0.16, 0.022),
			M.main
		);
		body.position.set(0, 0.36, -0.08);
		g.add(body);
		// light sobre main quase sumia sob a luz da cena; deep (azul mais escuro) lê.
		g.add(slab('exclamacao', M.deep, 0.095, 0.26, 0.05, 0.045, 0, 0.44, 0.085));
		const dot = mesh('ponto', new THREE.SphereGeometry(0.07, 24, 16), M.deep);
		dot.position.set(0, 0.23, 0.08);
		dot.scale.set(1, 1, 0.55);
		g.add(dot);
	}

	if (kind === 'tarefas') {
		g.add(slab('prancheta', M.main, 0.74, 0.96, 0.08, 0.07, 0, 0.48, 0));
		g.add(slab('papel', M.light, 0.64, 0.82, 0.03, 0.04, 0, 0.46, 0.055));
		g.add(slab('clipe_placa', M.deep, 0.26, 0.12, 0.1, 0.045, 0, 0.95, 0));
		const ring = mesh('clipe_arco', new THREE.TorusGeometry(0.055, 0.018, 12, 24, Math.PI), M.deep);
		ring.position.set(0, 1.0, 0);
		g.add(ring);
		[0.68, 0.46, 0.24].forEach((y, i) => {
			if (i < 2) {
				const c = check(`check_${i + 1}`, 0.075);
				c.position.set(-0.19, y, 0);
				g.add(c);
			} else {
				g.add(slab('caixa_vazia', M.deep, 0.11, 0.11, 0.026, 0.03, -0.19, y, 0.075));
			}
			g.add(slab(`linha_${i + 1}`, M.deep, 0.3, 0.055, 0.026, 0.025, 0.1, y, 0.075));
		});
	}

	if (kind === 'calendario') {
		g.add(slab('corpo', M.main, 0.92, 0.86, 0.1, 0.08, 0, 0.43, 0));
		g.add(slab('folha', M.light, 0.8, 0.6, 0.03, 0.05, 0, 0.34, 0.065));
		for (let r = 0; r < 3; r += 1) {
			for (let c = 0; c < 5; c += 1) {
				const today = r === 1 && c === 2;
				g.add(
					slab(
						`dia_${r * 5 + c + 1}`,
						today ? M.accent : M.deep,
						0.1,
						0.085,
						0.024,
						0.022,
						-0.28 + c * 0.14,
						0.53 - r * 0.16,
						0.09
					)
				);
			}
		}
		[-0.26, 0.26].forEach((x, i) => {
			const ring = mesh(`anel_${i + 1}`, new THREE.TorusGeometry(0.065, 0.022, 14, 28), M.deep);
			ring.position.set(x, 0.84, 0);
			ring.rotation.y = Math.PI / 2;
			g.add(ring);
		});
	}

	// Centraliza na origem e normaliza a escala para caber no ícone.
	const box = new THREE.Box3().setFromObject(g);
	const center = box.getCenter(new THREE.Vector3());
	const size = box.getSize(new THREE.Vector3());
	g.position.set(-center.x, -center.y, -center.z);
	const wrap = new THREE.Group();
	wrap.name = `${kind}_icone`;
	wrap.add(g);
	wrap.scale.setScalar(1 / Math.max(size.x, size.y));
	return wrap;
}
