<script lang="ts">
	/**
	 * Card fantasma "Nova coleção", último item do grid do índice (design
	 * "Coleções 2b"): borda tracejada, marca d'água de camadas e o "+" num
	 * círculo tracejado. No hover/foco a borda e o "+" ganham a cor da marca e
	 * a marca d'água gira de leve. É um `<button>` de verdade (a11y), não div.
	 */
	import ColecaoIconeSvg from '$lib/components/ColecaoIconeSvg.svelte';

	interface Props {
		onCriar: () => void;
	}

	let { onCriar }: Props = $props();
</script>

<button
	type="button"
	onclick={onCriar}
	class="group relative flex h-full min-h-[186px] flex-col items-center justify-center gap-2.5 overflow-hidden rounded-xl border-2 border-dashed border-border-strong p-5 text-center transition-ui duration-200 hover:border-brand hover:bg-surface focus:outline-none focus-visible:border-brand focus-visible:bg-surface focus-visible:ring-2 focus-visible:ring-brand"
>
	<ColecaoIconeSvg
		icone="camadas"
		size={140}
		class="pointer-events-none absolute -bottom-[30px] -right-4 text-text-secondary opacity-10 transition-transform duration-300 group-hover:-rotate-[10deg] group-hover:scale-[1.08] group-hover:text-brand group-focus-visible:text-brand"
	/>
	<span
		class="relative grid h-[52px] w-[52px] place-items-center rounded-full border-2 border-dashed border-border-strong text-text-muted transition-ui duration-200 group-hover:scale-[1.12] group-hover:border-brand group-hover:bg-wash-brand group-hover:text-brand group-focus-visible:border-brand group-focus-visible:text-brand"
		aria-hidden="true"
	>
		<i class="fas fa-plus text-xl"></i>
	</span>
	<span
		class="relative text-md font-bold text-text-secondary transition-colors duration-200 group-hover:text-brand group-focus-visible:text-brand"
	>
		Nova coleção
	</span>
</button>
