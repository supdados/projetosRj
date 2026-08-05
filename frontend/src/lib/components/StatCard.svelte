<script lang="ts">
	/**
	 * Cartao de metrica (contador) do Dashboard, fiel aos KPI cards "glass" do
	 * original (templates/index.html + static/css/index.css):
	 *   icone + numero grande colorido por tom + rotulo + subtitulo opcional.
	 *
	 * Acessivel: o grupo numero+rotulo e exposto como uma unica figura; o icone
	 * decorativo fica fora do fluxo de leitura (aria-hidden no wrapper).
	 */
	import type { Snippet } from 'svelte';

	interface Props {
		label: string;
		value: number | string;
		tone?: 'neutral' | 'primary' | 'success' | 'warning' | 'danger';
		/** Subtitulo opcional (ex.: "Todos os projetos cadastrados"), na cor do tom. */
		subtitle?: string;
		/** Snippet de icone (SVG) opcional, renderizado no wrapper colorido. */
		icon?: Snippet;
		/**
		 * Destino do click-through (opcional). Quando presente, o cartao inteiro
		 * vira um link (espelha os KPI cards clicaveis do index.html original,
		 * que levavam a /projetos filtrado). Acessivel: label descreve o destino.
		 */
		href?: string;
		/** Rotulo acessivel do link (ex.: "Ver projetos finalizados"). */
		linkLabel?: string;
	}

	let { label, value, tone = 'neutral', subtitle, icon, href, linkLabel }: Props = $props();

	const accent: Record<NonNullable<Props['tone']>, string> = {
		neutral: 'text-text-primary',
		primary: 'text-brand',
		success: 'text-success',
		warning: 'text-warning',
		danger: 'text-danger'
	};

	// Cor do icone por tom. SEM fundo/caixa (glassmorphism removido a pedido):
	// renderizamos apenas o icone colorido, sem o wrapper preenchido atras.
	const iconColor: Record<NonNullable<Props['tone']>, string> = {
		neutral: 'text-text-secondary',
		primary: 'text-brand',
		success: 'text-success',
		warning: 'text-warning',
		danger: 'text-danger'
	};
</script>

{#snippet body()}
	{#if icon}
		<span
			aria-hidden="true"
			class="flex shrink-0 items-center justify-center {iconColor[tone]}"
		>
			{@render icon()}
		</span>
	{/if}
	<div class="flex min-w-0 flex-col gap-1.5">
		<span class="order-1 font-heading text-3xl font-bold leading-tight {accent[tone]}">{value}</span>
		<span class="order-2 text-base font-medium text-text-secondary">{label}</span>
		{#if subtitle}
			<span class="order-3 text-sm {accent[tone]}">{subtitle}</span>
		{/if}
	</div>
{/snippet}

{#if href}
	<!-- Click-through: cartao inteiro vira link para /projetos filtrado.
	     Hover/focus realcam a borda+sombra (espelha o estado :hover dos KPI
	     cards "glass" do index.css original). -->
	<a
		{href}
		aria-label={linkLabel ?? label}
		class="group flex h-full items-center gap-3 rounded-lg border border-border-subtle bg-surface px-5 py-4 no-underline shadow-sm transition-ui duration-slow hover:border-brand hover:shadow-md focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
	>
		{@render body()}
	</a>
{:else}
	<div
		role="group"
		class="group flex h-full items-center gap-3 rounded-lg border border-border-subtle bg-surface px-5 py-4 shadow-sm transition-shadow duration-slow hover:shadow-md"
	>
		{@render body()}
	</div>
{/if}
