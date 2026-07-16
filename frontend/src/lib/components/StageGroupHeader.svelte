<script lang="ts">
	/**
	 * Header estático de ETAPA: barra azul que usa a MESMA `.task-hub-grid`
	 * das linhas, de modo que os rótulos de coluna (Prioridade/Tipo/Status/
	 * Responsável/Ações) fiquem embutidos no header e alinhados com os chips
	 * abaixo — substituindo o cabeçalho de colunas separado. Etapas não
	 * colapsam (só o projeto expande/retrai).
	 */
	interface Props {
		/** Código exibível da etapa (ex.: "42.1"); `null` para "Sem etapa". */
		stageCode: string | null;
		titulo: string | null;
		count: number;
	}

	let { stageCode, titulo, count }: Props = $props();

	// Rótulos de coluna: token de texto neutro (contraste garantido em light E dark;
	// `primary-700/60` falhava no dark sobre o header translúcido).
	const LABEL = 'self-center text-center text-2xs font-bold uppercase tracking-[0.08em] text-text-secondary';
</script>

<div class="task-hub-grid w-full bg-primary-100 px-3 py-2 text-left">
	<span class="flex min-w-0 items-center gap-2">
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

	<span class={LABEL}>Prioridade</span>
	<span class={LABEL}>Tipo</span>
	<span class={LABEL}>Status</span>
	<span class={LABEL}>Responsável</span>
	<span class={LABEL}>Ações</span>
</div>
