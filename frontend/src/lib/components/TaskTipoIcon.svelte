<script lang="ts">
	/**
	 * Ícone de tipo de pedido — sistema "bloco chanfrado" (design Icones
	 * Complementares, bloco T-A): mesma silhueta 16×12,8 com chanfro a 45°,
	 * base de apoio em 48% e o tipo como estado da matéria (partido, degrau,
	 * incompleto ou intacto). Cores aprovadas junto com os desenhos — hex
	 * literal de propósito, fora da régua de tokens (exceção como o roxo de
	 * dúvida antigo). `outros` = bloco vazio cinza (igual sem_tipo);
	 * `implementacao` segue no FontAwesome (legado sem conceito aprovado).
	 *
	 * Ex.: `<TaskTipoIcon tipo={task.tipo_pedido} />` — `null`/desconhecido
	 * rende o bloco liso de "Sem tipo".
	 */
	interface Props {
		tipo: string | null;
		size?: number;
	}
	let { tipo, size = 16 }: Props = $props();

	const BLOCO: Record<string, { color: string; paths: { d: string; opacity?: string }[] }> = {
		bug: {
			color: '#9A4F42',
			paths: [
				{
					d: 'M4 5.6H16.4L20 9.2V18.4H4ZM11 5.6L12.3 9.4L10.3 12.6L12.1 15.6L10.5 18.4H11.9L13.5 15.6L11.7 12.6L13.7 9.4L12.4 5.6Z'
				},
				{ d: 'M2.6 19.8H21.4V21.2H2.6Z', opacity: '.48' }
			]
		},
		melhoria: {
			color: '#1E6B5C',
			paths: [
				{ d: 'M4 18.4V13.4H9.2V9.6H14.4V5.8H18.4L20 7.4V18.4Z' },
				{ d: 'M2.6 19.8H21.4V21.2H2.6Z', opacity: '.48' }
			]
		},
		duvida: {
			color: '#6A5490',
			paths: [
				{ d: 'M4 5.6H16.4L20 9.2V11.8H15.2V15.4H20V18.4H4Z' },
				{ d: 'M2.6 19.8H21.4V21.2H2.6Z', opacity: '.48' }
			]
		},
		sem_tipo: {
			color: '#7E888E',
			paths: [
				{ d: 'M4 5.6H16.4L20 9.2V18.4H4Z', opacity: '.48' },
				{ d: 'M2.6 19.8H21.4V21.2H2.6Z', opacity: '.48' }
			]
		}
	};
	// "Outros" = indefinido: mesmo bloco vazio cinza do sem_tipo (decisão 2026-08-02).
	BLOCO.outros = BLOCO.sem_tipo;

	const FA_LEGADO: Record<string, { icon: string; color: string }> = {
		implementacao: { icon: 'fa-code', color: 'var(--ds-color-text-brand)' }
	};

	const bloco = $derived(BLOCO[tipo ?? ''] ?? (FA_LEGADO[tipo ?? ''] ? null : BLOCO.sem_tipo));
	const legado = $derived(FA_LEGADO[tipo ?? ''] ?? null);
</script>

{#if bloco}
	<svg
		width={size}
		height={size}
		viewBox="0 0 24 24"
		fill="currentColor"
		style="color: {bloco.color};"
		aria-hidden="true"
	>
		{#each bloco.paths as p (p.d)}
			<path fill-rule="evenodd" d={p.d} opacity={p.opacity} />
		{/each}
	</svg>
{:else if legado}
	<i class="fas {legado.icon}" style="color: {legado.color};" aria-hidden="true"></i>
{/if}
