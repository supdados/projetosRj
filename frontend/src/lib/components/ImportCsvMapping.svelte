<script lang="ts">
	/**
	 * Tabela de mapeamento coluna-do-CSV → campo do projeto (revisão da
	 * importação): uma linha por coluna com o campo sugerido pré-selecionado e
	 * unicidade resolvida por `applyFieldSelection` (campo roubado vira Ignorar).
	 */
	import { tick } from 'svelte';
	import { prefersReducedMotion } from 'svelte/motion';
	import type { CampoImportacao, ColunaDetectada } from '$lib/types/importExport';
	import type { SelectMenuOption } from '$lib/types/selectMenu';
	import SelectMenu from '$lib/components/SelectMenu.svelte';
	import { applyFieldSelection, type ImportFieldMapping } from '$lib/utils/importMappingState';

	interface Props {
		colunas: ColunaDetectada[];
		campos: CampoImportacao[];
		mapping: ImportFieldMapping;
		/** Trava os seletores enquanto a importação está em voo. */
		disabled?: boolean;
		onChange: (mapping: ImportFieldMapping) => void;
	}

	let { colunas, campos, mapping, disabled = false, onChange }: Props = $props();

	let containerEl = $state<HTMLDivElement | null>(null);

	const opcoesCampo = $derived<SelectMenuOption[]>(
		campos.map((campo) => ({ value: campo.campo, label: campo.rotulo }))
	);

	// A linha que perde o campo pode estar fora da viewport da lista — sem o
	// scroll, ela voltaria a "Ignorar" em silêncio.
	function aoEscolherCampo(indice: number, campo: string | null): void {
		const doadora =
			campo === null
				? undefined
				: Object.entries(mapping).find(([i, c]) => c === campo && Number(i) !== indice)?.[0];
		onChange(applyFieldSelection(mapping, indice, campo));
		if (doadora === undefined) return;
		void tick().then(() => {
			containerEl?.querySelector(`[data-indice="${doadora}"]`)?.scrollIntoView({
				block: 'nearest',
				behavior: prefersReducedMotion.current ? 'auto' : 'smooth'
			});
		});
	}
</script>

<div
	bind:this={containerEl}
	class="native-scroll max-h-[340px] overflow-auto rounded-lg border border-border-subtle"
>
	{#each colunas as coluna (coluna.indice)}
		{@const campoEscolhido = mapping[coluna.indice] ?? null}
		<div
			data-indice={coluna.indice}
			class="grid h-12 grid-cols-[1fr_auto_11rem] items-center gap-2 border-b border-border-hairline px-3 last:border-b-0"
		>
			<div class="flex min-w-0 flex-col">
				<span
					class="truncate text-sm font-medium transition-colors duration-fast {campoEscolhido ===
					null
						? 'text-text-muted'
						: 'text-text-primary'}"
				>
					{coluna.cabecalho}
				</span>
				{#if coluna.amostra}
					<span class="truncate text-xs text-text-muted">{coluna.amostra}</span>
				{/if}
			</div>
			<span class="text-text-faint" aria-hidden="true">→</span>
			<SelectMenu
				size="sm"
				{disabled}
				allowAll
				allLabel="Ignorar"
				options={opcoesCampo}
				value={campoEscolhido}
				onSelect={(campo) => aoEscolherCampo(coluna.indice, campo)}
				ariaLabel={`Campo para a coluna ${coluna.cabecalho}`}
			/>
		</div>
	{/each}
</div>
