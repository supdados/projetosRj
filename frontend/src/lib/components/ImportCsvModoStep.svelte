<script lang="ts">
	/**
	 * Passo inicial da importação: escolha do formato do CSV (somente projetos
	 * × projetos com etapas), cada card com download do modelo do modo.
	 */
	import { downloadImportTemplate } from '$lib/utils/importTemplates';
	import type { ImportModo } from '$lib/types/importExport';

	interface Props {
		modo: ImportModo;
		/** Classe do link discreto, herdada do modal para manter o visual. */
		classeLink: string;
		onSelect: (modo: ImportModo) => void;
	}

	let { modo, classeLink, onSelect }: Props = $props();

	const CARDS: { valor: ImportModo; titulo: string; descricao: string }[] = [
		{
			valor: 'simples',
			titulo: 'Somente projetos',
			descricao:
				'Uma linha por projeto. Sem etapas, cada projeto nasce com a etapa "Etapas a definir".'
		},
		{
			valor: 'com_etapas',
			titulo: 'Projetos com etapas',
			descricao:
				'Uma linha por etapa; linhas do mesmo projeto ficam juntas, identificadas pela coluna Ref do projeto.'
		}
	];
</script>

<fieldset class="flex flex-col gap-2">
	<legend class="sr-only">Formato do arquivo CSV</legend>
	{#each CARDS as card (card.valor)}
		{@const ativo = modo === card.valor}
		<label
			class="flex cursor-pointer items-start gap-3 rounded-lg border p-3 transition-ui focus-within:ring-2 focus-within:ring-brand {ativo
				? 'border-brand bg-wash-brand'
				: 'border-border-subtle bg-surface hover:border-border-strong'}"
		>
			<input
				type="radio"
				name="importar-projetos-modo"
				value={card.valor}
				checked={ativo}
				onchange={() => onSelect(card.valor)}
				class="sr-only"
			/>
			<span
				class="mt-0.5 grid h-3.5 w-3.5 shrink-0 place-items-center rounded-full border {ativo
					? 'border-brand'
					: 'border-border-strong'}"
				aria-hidden="true"
			>
				<span
					class="h-2 w-2 rounded-full bg-brand transition-transform duration-fast"
					style:transform={ativo ? 'scale(1)' : 'scale(0)'}
				></span>
			</span>
			<span class="flex min-w-0 flex-col gap-1">
				<span class="text-sm font-semibold text-text-primary">{card.titulo}</span>
				<span class="text-xs text-text-muted">{card.descricao}</span>
				<button
					type="button"
					onclick={() => downloadImportTemplate(card.valor)}
					class="self-start {classeLink}"
				>
					Baixar modelo (.csv)
				</button>
			</span>
		</label>
	{/each}
</fieldset>
