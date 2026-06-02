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
					DEFAULT: 'var(--ds-color-primary-600)'
				},
				secondary: 'var(--ds-color-secondary-600)',
				success: 'var(--ds-color-success-600)',
				warning: 'var(--ds-color-warning-600)',
				danger: 'var(--ds-color-danger-600)',
				info: 'var(--ds-color-info-600)'
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
				md: '0.875rem',
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
				// --ds-shadow-*
				sm: '0 2px 8px rgba(15, 23, 42, 0.06)',
				md: '0 4px 12px rgba(15, 23, 42, 0.08)',
				lg: '0 8px 24px rgba(15, 23, 42, 0.12)'
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
			}
		}
	},
	plugins: []
} satisfies Config;
