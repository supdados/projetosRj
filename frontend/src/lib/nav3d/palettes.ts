/**
 * Paletas dos ícones 3D do topnav — derivadas do protótipo aprovado
 * (`micro/docs/protos/navbar-3d.html`).
 *
 * São 4 shades correlacionados (corpo / sombra / superfície clara / destaque).
 * `IDLE_PALETTE` é cinza dessaturado sem equivalente na régua (fica literal).
 * `ACTIVE_PALETTE` mapeia para a "regra de marca" de `--ds-color-icon-*` em
 * `app.css` (600 contorno / 400 base / 300 luz) — ver `resolveActiveTokens`.
 *
 * 2026-07-27: o protótipo trazia uma paleta ativa por ícone (verde, âmbar,
 * roxo, rosa); por decisão do dono os 5 passaram a usar o azul do "inicio".
 */

export type NavIconKind = 'inicio' | 'projetos' | 'pendentes' | 'tarefas' | 'calendario';

export interface IconPalette {
	/** Volume principal (parede, capa da pasta, corpo do alerta). */
	main: string;
	/** Sombra/segundo plano (telhado, linhas, anéis). */
	deep: string;
	/** Superfície clara (porta, folha de papel). */
	light: string;
	/** Destaque pontual (dia marcado no calendário). */
	accent: string;
}

/** Estado de repouso: cinza dessaturado, igual para os 5 ícones. Sem token equivalente na régua — fica literal. */
export const IDLE_PALETTE: IconPalette = {
	main: '#dbe4ec',
	deep: '#a8b7c4',
	light: '#eef2f6',
	accent: '#c6d0d9'
};

/**
 * Estado ativo (item da rota atual): azul institucional, igual para os 5.
 * `accent` reusa `main` — o único uso visível é o dia marcado do calendário,
 * que fica azul claro sobre os demais dias em `deep`.
 *
 * Literais = fallback de SSR/pré-resolução. `resolveActiveTokens()` sobrescreve
 * estes campos em lugar (mesma referência de objeto, por isso `ACTIVE_PALETTES`
 * não precisa ser tocado) com o hex atual de `--ds-color-icon-*` na primeira
 * chamada no cliente — three.js aceita string CSS (hex/rgb) direto em `Color.set`.
 */
export const ACTIVE_PALETTE: IconPalette = {
	main: '#1c6ca3',
	deep: '#0f4a72',
	light: '#cfe3f1',
	accent: '#1c6ca3'
};

export const ACTIVE_PALETTES: Record<NavIconKind, IconPalette> = {
	inicio: ACTIVE_PALETTE,
	projetos: ACTIVE_PALETTE,
	pendentes: ACTIVE_PALETTE,
	tarefas: ACTIVE_PALETTE,
	calendario: ACTIVE_PALETTE
};

let activeTokensResolved = false;

/**
 * Lê `--ds-color-icon-outline/-base/-light` de `app.css` e substitui os
 * literais de `ACTIVE_PALETTE` em lugar. Roda uma vez, no primeiro attach de
 * ícone no cliente (chamada em `navIconStage.ensureStage`); memoizada porque
 * `getComputedStyle` custa um reflow. Se a leitura falhar (SSR, var ausente),
 * os literais acima seguem valendo.
 */
export function resolveActiveTokens(): void {
	if (activeTokensResolved || typeof document === 'undefined') return;
	const styles = getComputedStyle(document.documentElement);
	const outline = styles.getPropertyValue('--ds-color-icon-outline').trim();
	const base = styles.getPropertyValue('--ds-color-icon-base').trim();
	const light = styles.getPropertyValue('--ds-color-icon-light').trim();
	if (!outline || !base || !light) return;
	activeTokensResolved = true;
	ACTIVE_PALETTE.deep = outline;
	ACTIVE_PALETTE.main = base;
	ACTIVE_PALETTE.accent = base;
	ACTIVE_PALETTE.light = light;
}

export const PALETTE_CHANNELS = ['main', 'deep', 'light', 'accent'] as const;
export type PaletteChannel = (typeof PALETTE_CHANNELS)[number];
