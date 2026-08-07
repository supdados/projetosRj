<script lang="ts" module>
	/** Opção de um chip-toggle: `id` é o valor emitido, `label` o rótulo visível. */
	export interface FilterChipOption {
		id: string;
		label: string;
	}
</script>

<script lang="ts">
	/**
	 * Grupo de chips-toggle de filtro (seleção única), no lugar de um `<select>`
	 * quando as opções são poucas e vale mostrar todas — ex.: "Minhas coleções /
	 * Das minhas áreas" no índice de Coleções.
	 *
	 * A11y: `role="group"` rotulado + `aria-pressed` por chip (o ativo não é só
	 * cor). Cor sozinha nunca carrega o estado: o ativo também ganha peso medium.
	 *
	 * Exemplo:
	 *   <FilterChipGroup label="Escopo" options={escopos} value={escopo}
	 *     onchange={(id) => (escopo = id)} />
	 */
	interface Props {
		/** Rótulo acessível do grupo (não renderizado). */
		label: string;
		options: FilterChipOption[];
		value: string;
		onchange: (id: string) => void;
	}

	let { label, options, value, onchange }: Props = $props();

	const base =
		'inline-flex h-[var(--control-h-md)] items-center rounded-sm border px-2.5 text-xs transition-ui duration-fast focus:outline-none focus-visible:ring-2 focus-visible:ring-brand';
	const active = 'border-brand-soft bg-wash-brand font-medium text-brand';
	const idle =
		'border-border-subtle bg-surface text-text-secondary hover:border-brand hover:text-brand';
</script>

<div role="group" aria-label={label} class="flex items-center gap-2">
	{#each options as option (option.id)}
		<button
			type="button"
			aria-pressed={option.id === value}
			onclick={() => onchange(option.id)}
			class="{base} {option.id === value ? active : idle}"
		>
			{option.label}
		</button>
	{/each}
</div>
