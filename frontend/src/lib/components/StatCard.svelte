<script lang="ts">
	/**
	 * Cartao de metrica (contador) do Dashboard, fiel aos KPI cards "glass" do
	 * original (templates/index.html + static/css/index.css):
	 *   icone em wrapper arredondado (44x44, radius 12px) + numero grande colorido
	 *   por tom + rotulo + subtitulo opcional.
	 *
	 * APIs retrocompativeis: `label`/`value`/`tone` continuam funcionando como
	 * antes. As novas props (`icon`, `subtitle`) sao OPCIONAIS — call-sites
	 * existentes (dashboard) nao quebram. O slot `icon` permite passar um SVG.
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
	}

	let { label, value, tone = 'neutral', subtitle, icon }: Props = $props();

	const accent: Record<NonNullable<Props['tone']>, string> = {
		neutral: 'text-text-primary',
		primary: 'text-primary-700',
		success: 'text-success',
		warning: 'text-warning',
		danger: 'text-danger'
	};

	// Wrapper do icone: fundo suave + cor do tom (espelha .dash-kpi-*-bg/.dash-kpi-*
	// e .dashboard-brand-icon-wrap do index.css; tons via vars semanticas no dark).
	const iconWrap: Record<NonNullable<Props['tone']>, string> = {
		neutral: 'bg-surface-muted text-text-secondary',
		primary: 'bg-primary-100 text-primary-700',
		success: 'bg-surface-muted text-success',
		warning: 'bg-surface-muted text-warning',
		danger: 'bg-surface-muted text-danger'
	};
</script>

<div
	role="group"
	class="flex items-center gap-3 rounded-lg border border-border-subtle bg-surface px-5 py-4 shadow-sm transition-shadow duration-slow hover:shadow-md"
>
	{#if icon}
		<span
			aria-hidden="true"
			class="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg shadow-sm {iconWrap[
				tone
			]}"
		>
			{@render icon()}
		</span>
	{/if}
	<div class="flex min-w-0 flex-col gap-1">
		<span class="order-1 font-heading text-3xl font-bold leading-tight {accent[tone]}">{value}</span>
		<span class="order-2 text-sm font-medium text-text-secondary">{label}</span>
		{#if subtitle}
			<span class="order-3 text-xs {accent[tone]}">{subtitle}</span>
		{/if}
	</div>
</div>
