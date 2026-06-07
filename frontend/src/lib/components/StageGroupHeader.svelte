<script lang="ts">
	/**
	 * Header de ETAPA (variation-d): barra azul que usa a MESMA `.task-hub-grid`
	 * das linhas, de modo que os rótulos de coluna (Prioridade/Tipo/Status/
	 * Responsável/Ações) fiquem embutidos no header e alinhados com os chips
	 * abaixo — substituindo o cabeçalho de colunas separado. A coluna 1 traz o
	 * chevron de colapso, a pill de código da etapa, o nome e o badge de contagem.
	 */
	interface Props {
		/** Código exibível da etapa (ex.: "42.1"); `null` para "Sem etapa". */
		stageCode: string | null;
		titulo: string | null;
		count: number;
		collapsed: boolean;
		onToggle: () => void;
		/** id do corpo colapsável, para `aria-controls`. */
		controlsId?: string;
	}

	let { stageCode, titulo, count, collapsed, onToggle, controlsId }: Props = $props();

	// Rótulos de coluna: token de texto neutro (contraste garantido em light E dark;
	// `primary-700/60` falhava no dark sobre o header translúcido).
	const LABEL = 'self-center text-center text-2xs font-bold uppercase tracking-[0.08em] text-text-secondary';
</script>

<button
	type="button"
	onclick={onToggle}
	aria-expanded={!collapsed}
	aria-controls={controlsId}
	class="task-hub-grid w-full bg-primary-100 px-3 py-2 text-left transition-colors duration-fast hover:bg-primary-100/70 focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary-500"
>
	<span class="flex min-w-0 items-center gap-2">
		<i
			class="fas fa-chevron-right shrink-0 text-2xs text-primary-700/70 transition-transform duration-fast motion-reduce:transition-none {collapsed
				? ''
				: 'rotate-90'}"
			aria-hidden="true"
		></i>
		{#if stageCode}
			<span
				class="shrink-0 rounded bg-surface/80 px-1.5 py-0.5 font-mono text-2xs font-semibold text-primary-700"
			>
				{stageCode}
			</span>
		{/if}
		<span class="truncate text-sm font-semibold text-primary-700">{titulo ?? 'Sem etapa'}</span>
		<span
			class="shrink-0 rounded-full bg-surface px-2 py-0.5 text-2xs font-semibold text-primary-700"
		>
			{count}
		</span>
	</span>

	{#if !collapsed}
		<span class={LABEL}>Prioridade</span>
		<span class={LABEL}>Tipo</span>
		<span class={LABEL}>Status</span>
		<span class={LABEL}>Responsável</span>
		<span class={LABEL}>Ações</span>
	{/if}
</button>
