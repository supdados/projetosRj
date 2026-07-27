/**
 * Paletas dos ícones 3D do topnav — derivadas do protótipo aprovado
 * (`micro/docs/protos/navbar-3d.html`).
 *
 * São 4 shades correlacionados (corpo / sombra / superfície clara / destaque)
 * que não mapeiam em nenhum token semântico do design system, por isso vivem
 * aqui como constantes e não em `app.css`.
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

/** Estado de repouso: cinza dessaturado, igual para os 5 ícones. */
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

export const PALETTE_CHANNELS = ['main', 'deep', 'light', 'accent'] as const;
export type PaletteChannel = (typeof PALETTE_CHANNELS)[number];
