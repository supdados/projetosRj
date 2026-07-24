/**
 * Paletas dos ícones 3D do topnav — cópia literal do protótipo aprovado
 * (`micro/docs/protos/navbar-3d.html`).
 *
 * São 4 shades correlacionados por ícone (corpo / sombra / superfície clara /
 * destaque) que não mapeiam em nenhum token semântico do design system, por
 * isso vivem aqui como constantes e não em `app.css`.
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

/** Estado ativo (item da rota atual), uma paleta por ícone. */
export const ACTIVE_PALETTES: Record<NavIconKind, IconPalette> = {
	inicio: { main: '#1c6ca3', deep: '#0f4a72', light: '#cfe3f1', accent: '#e9a63c' },
	projetos: { main: '#2a8f86', deep: '#14625c', light: '#d5ecea', accent: '#e9a63c' },
	pendentes: { main: '#e0a02f', deep: '#8a570f', light: '#f7e6c4', accent: '#8a570f' },
	tarefas: { main: '#5d63c9', deep: '#343a86', light: '#e0e2f8', accent: '#e9a63c' },
	calendario: { main: '#bd5878', deep: '#7c3350', light: '#f5dce4', accent: '#e9a63c' }
};

export const PALETTE_CHANNELS = ['main', 'deep', 'light', 'accent'] as const;
export type PaletteChannel = (typeof PALETTE_CHANNELS)[number];
