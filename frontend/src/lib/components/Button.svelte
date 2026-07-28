<script lang="ts">
	/**
	 * Botao do kit, fiel aos .btn-glass do original
	 * (legacy/20-glass-forms-and-admin.css) reinterpretado com tokens semanticos:
	 *   - primary: azul primary-600 solido + texto branco.
	 *   - secondary: superficie clara + borda/texto primary.
	 *   - danger: superficie + texto/borda danger.
	 *   - ghost: sem borda/fundo, so texto, hover suave.
	 * Transicao do original: all 0.3s cubic-bezier(0.4,0,0.2,1) (duration-slow).
	 *
	 * Renderiza <a> quando `href` e passado (preserva navegacao), senao <button>.
	 * Nao adiciona logica: handlers/atributos extras passam via `...rest`.
	 */
	import type { Snippet } from 'svelte';
	import type {
		HTMLButtonAttributes,
		HTMLAnchorAttributes
	} from 'svelte/elements';

	type Variant = 'primary' | 'secondary' | 'danger' | 'ghost';
	type Size = 'sm' | 'md' | 'lg';

	interface Props {
		variant?: Variant;
		size?: Size;
		/** Quando presente, renderiza um link <a> (navegacao) em vez de <button>. */
		href?: string;
		/** Tipo do <button> (ignorado quando href e usado). */
		type?: 'button' | 'submit' | 'reset';
		/** Ocupa 100% da largura do container. */
		block?: boolean;
		children: Snippet;
		/** Snippet de icone opcional, renderizado antes do texto. */
		icon?: Snippet;
	}

	let {
		variant = 'primary',
		size = 'md',
		href,
		type = 'button',
		block = false,
		children,
		icon,
		...rest
	}: Props & HTMLButtonAttributes & HTMLAnchorAttributes = $props();

	const base =
		'inline-flex items-center justify-center gap-2 rounded-md font-semibold transition-all duration-slow ease-[cubic-bezier(0.4,0,0.2,1)] focus:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-1 disabled:cursor-not-allowed disabled:opacity-60';

	const variantClass: Record<Variant, string> = {
		primary:
			'bg-brand text-on-brand shadow-sm hover:-translate-y-0.5 hover:bg-brand-hover hover:shadow-md active:translate-y-0',
		// Espelha .btn-glass-secondary: superficie clara, borda/texto primary.
		secondary:
			'border border-brand bg-surface text-brand shadow-sm hover:-translate-y-0.5 hover:bg-surface-muted hover:shadow-md active:translate-y-0',
		// Espelha .btn-glass-remove: superficie + danger.
		danger:
			'border border-danger bg-surface text-danger hover:-translate-y-0.5 hover:bg-surface-muted hover:shadow-md active:translate-y-0',
		ghost: 'bg-transparent text-text-primary hover:bg-surface-muted'
	};

	const sizeClass: Record<Size, string> = {
		sm: 'px-3 py-1.5 text-sm',
		md: 'px-5 py-2 text-sm',
		lg: 'px-6 py-3 text-base'
	};

	// $derived: classes reagem a mudancas de variant/size/block (props sao reativos).
	const cls = $derived(
		`${base} ${variantClass[variant]} ${sizeClass[size]}${block ? ' w-full' : ''}`
	);
</script>

{#if href}
	<a {href} class={cls} {...rest}>
		{#if icon}{@render icon()}{/if}
		{@render children()}
	</a>
{:else}
	<button {type} class={cls} {...rest}>
		{#if icon}{@render icon()}{/if}
		{@render children()}
	</button>
{/if}
