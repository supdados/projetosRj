import type { Config } from 'tailwindcss';

/*
 * Derivado de static/css/design-system.css (tokens --ds-*).
 * Cores apontam para CSS vars SEMANTICAS (definidas em src/app.css :root e
 * [data-theme="dark"]) para que o dark mode troque sozinho, sem variantes dark:.
 * Escala numerica (primary 500/600/700) mapeia os tokens --ds-color-primary-*.
 */
export default {
	content: ['./src/**/*.{html,js,svelte,ts}'],
	// Dark mode dirigido pelo atributo data-theme="dark" (igual base.html anti-flash).
	darkMode: ['selector', '[data-theme="dark"]'],
	theme: {
		extend: {
			colors: {
				// Semanticas (trocam no dark via app.css)
				canvas: 'var(--color-canvas)',
				surface: 'var(--color-surface)',
				'surface-elevated': 'var(--color-surface-elevated)',
				'surface-muted': 'var(--color-surface-muted)',
				'border-subtle': 'var(--color-border)',
				'border-strong': 'var(--color-border-strong)',
				'text-primary': 'var(--color-text-primary)',
				'text-secondary': 'var(--color-text-secondary)',
				'text-muted': 'var(--color-text-muted)',
				primary: {
					100: 'var(--ds-color-primary-100)',
					500: 'var(--ds-color-primary-500)',
					600: 'var(--ds-color-primary-600)',
					700: 'var(--ds-color-primary-700)',
					DEFAULT: 'var(--ds-color-primary-600)',
					fg: 'var(--ds-color-primary-fg)'
				},
				secondary: 'var(--ds-color-secondary-600)',
				success: {
					DEFAULT: 'var(--ds-color-success-600)',
					fg: 'var(--ds-color-success-fg)'
				},
				warning: 'var(--ds-color-warning-600)',
				danger: {
					DEFAULT: 'var(--ds-color-danger-600)',
					fg: 'var(--ds-color-danger-fg)'
				},
				info: 'var(--ds-color-info-600)',
				violet: 'var(--ds-color-violet-600)',
				overlay: 'var(--color-overlay)',
				pending: 'var(--ds-color-pending)',
				// Cor da prioridade "alta" no original (#ea580c, laranja) — nao havia
				// token semantico equivalente; mapeada para CSS var (ajusta no dark).
				orange: 'var(--ds-color-orange-600)',
				// Cores de prioridade (badges) — valores 1:1 de 00-foundation.css:1650.
				priority: {
					baixa: 'var(--ds-color-priority-baixa)',
					media: 'var(--ds-color-priority-media)',
					alta: 'var(--ds-color-priority-alta)',
					urgente: 'var(--ds-color-priority-urgente)'
				}
			},
			backgroundImage: {
				// Gradiente do topbar/brand do original (#1769a8). Util reutilizavel.
				'topnav-gradient':
					'linear-gradient(135deg, var(--ds-color-topnav-from) 0%, var(--ds-color-topnav-to) 100%)',
				// Azul de marca dos botoes primarios: constante em light E dark.
				'brand-gradient':
					'linear-gradient(135deg, var(--ds-color-brand-from) 0%, var(--ds-color-brand-to) 100%)',
				// Skeleton shimmer (90deg) — 10-skeleton.css:52.
				'skeleton-shimmer':
					'linear-gradient(90deg, var(--ds-color-skeleton-base) 0%, var(--ds-color-skeleton-highlight) 50%, var(--ds-color-skeleton-base) 100%)',
				// Glass card (135deg) — 20-glass-forms-and-admin.css:162.
				'glass-card':
					'linear-gradient(135deg, var(--ds-glass-card-from) 0%, var(--ds-glass-card-to) 100%)',
				'glass-card-header':
					'linear-gradient(135deg, var(--ds-glass-header-from) 0%, var(--ds-glass-header-to) 100%)'
			},
			fontFamily: {
				body: [
					'InterVariable',
					'Inter',
					'-apple-system',
					'Segoe UI',
					'Roboto',
					'Arial',
					'sans-serif'
				],
				sans: [
					'InterVariable',
					'Inter',
					'-apple-system',
					'Segoe UI',
					'Roboto',
					'Arial',
					'sans-serif'
				],
				heading: [
					'ManropeVariable',
					'Manrope',
					'Inter',
					'-apple-system',
					'Segoe UI',
					'Roboto',
					'Arial',
					'sans-serif'
				],
				mono: ['SFMono-Regular', 'Consolas', 'Liberation Mono', 'Menlo', 'monospace']
			},
			fontSize: {
				// --ds-font-size-* (base = 0.95rem, NAO 1rem)
				'2xs': '0.6875rem',
				xs: '0.75rem',
				sm: '0.8125rem',
				// md (0.875rem) aposentado no contrato de estilo — usar sm ou base
				base: '0.95rem',
				lg: '1.05rem',
				xl: '1.2rem',
				'2xl': '1.4rem',
				'3xl': '1.6rem',
				'4xl': '2rem',
				'5xl': '2.5rem',
				'6xl': '3rem',
				'7xl': '3.5rem'
			},
			lineHeight: {
				tight: '1.15',
				snug: '1.25',
				normal: '1.4',
				relaxed: '1.5'
			},
			letterSpacing: {
				tight: '-0.01em',
				normal: '0',
				wide: '0.02em',
				caps: '0.04em'
			},
			fontWeight: {
				regular: '400',
				medium: '500',
				semibold: '600',
				bold: '700',
				extrabold: '800'
			},
			spacing: {
				// --ds-space-* PULA o 7 (vai 1,2,3,4,5,6,8); demais herdados do default Tailwind.
				1: '0.25rem',
				2: '0.5rem',
				3: '0.75rem',
				4: '1rem',
				5: '1.25rem',
				6: '1.5rem',
				8: '2rem'
			},
			borderRadius: {
				// --ds-radius-*
				sm: '6px',
				md: '8px',
				lg: '12px',
				xl: '16px'
			},
			boxShadow: {
				// --ds-shadow-* (vars em app.css; mesmos literais no light, re-temperadas no dark)
				sm: 'var(--ds-shadow-sm)',
				md: 'var(--ds-shadow-md)',
				lg: 'var(--ds-shadow-lg)'
			},
			transitionDuration: {
				// --ds-transition-*
				fast: '150ms',
				base: '250ms',
				slow: '350ms'
			},
			zIndex: {
				// --ds-z-*
				dropdown: '1000',
				sticky: '1020',
				fixed: '1030',
				'modal-backdrop': '1040',
				modal: '1050',
				toast: '1080'
			},
			// Keyframes globais reproduzidos 1:1 do legacy CSS (mesmos nomes/passos).
			keyframes: {
				// 00-foundation.css:579
				'app-dropdown-in': {
					from: { opacity: '0', transform: 'translateY(-6px) scale(0.985)' },
					to: { opacity: '1', transform: 'translateY(0) scale(1)' }
				},
				// 00-foundation.css:1402
				'search-focus-pulse': {
					'0%': {
						boxShadow: '0 0 0 0 rgba(0, 90, 146, 0.36)',
						backgroundColor: 'rgba(0, 90, 146, 0.12)'
					},
					'60%': {
						boxShadow: '0 0 0 10px rgba(0, 90, 146, 0)',
						backgroundColor: 'rgba(0, 90, 146, 0.08)'
					},
					'100%': {
						boxShadow: '0 0 0 0 rgba(0, 90, 146, 0)',
						backgroundColor: 'transparent'
					}
				},
				// 10-skeleton.css:1997
				'skeleton-loading': {
					'0%': { backgroundPosition: '200% 0' },
					'100%': { backgroundPosition: '-200% 0' }
				},
				// 20-glass-forms-and-admin.css:752
				'modal-slide-in': {
					from: { opacity: '0', transform: 'translateY(-50px) scale(0.9)' },
					to: { opacity: '1', transform: 'translateY(0) scale(1)' }
				},
				// 20-glass-forms-and-admin.css:763
				'glass-shimmer': {
					'0%': { transform: 'translateX(-100%)' },
					'100%': { transform: 'translateX(100%)' }
				},
				// style.css:96 (chatbot panel) — entrada de painel/dropdown rico.
				'panel-in': {
					from: { opacity: '0', transform: 'translateY(16px) scale(0.95)' },
					to: { opacity: '1', transform: 'translateY(0) scale(1)' }
				}
			},
			animation: {
				// Duracoes/easings 1:1 do original.
				'dropdown-in': 'app-dropdown-in 0.16s ease-out',
				'search-focus-pulse': 'search-focus-pulse 2.1s ease-out 1',
				'skeleton-loading': 'skeleton-loading 1.5s infinite',
				'modal-slide-in': 'modal-slide-in 0.3s cubic-bezier(0.34, 1.15, 0.64, 1) both',
				'glass-shimmer': 'glass-shimmer 1.5s ease-in-out infinite',
				'panel-in': 'panel-in 0.22s cubic-bezier(0.34, 1.15, 0.64, 1) both'
			}
		}
	},
	plugins: []
} satisfies Config;
