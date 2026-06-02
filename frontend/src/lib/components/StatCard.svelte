<script lang="ts">
	/**
	 * Cartao de metrica (contador) do Dashboard. Numero grande + rotulo.
	 * Acessivel: o grupo numero+rotulo e exposto como uma unica figura.
	 */
	interface Props {
		label: string;
		value: number;
		tone?: 'neutral' | 'primary' | 'success' | 'warning' | 'danger';
	}

	let { label, value, tone = 'neutral' }: Props = $props();

	const accent: Record<NonNullable<Props['tone']>, string> = {
		neutral: 'text-text-primary',
		primary: 'text-primary-700',
		success: 'text-success',
		warning: 'text-warning',
		danger: 'text-danger'
	};
</script>

<figure
	class="flex flex-col gap-1 rounded-lg border border-border-subtle bg-surface px-5 py-4 shadow-sm"
>
	<figcaption class="order-2 text-sm text-text-secondary">{label}</figcaption>
	<span class="order-1 font-heading text-3xl font-bold {accent[tone]}">{value}</span>
</figure>
