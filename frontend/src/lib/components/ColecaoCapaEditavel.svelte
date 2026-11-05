<script lang="ts">
	/**
	 * Topo dos modais Nova coleção e Editar coleção = a própria CAPA, editável
	 * (design "Coleções 3a"): nome e descrição são digitados direto nela, e
	 * cor, ícone e as áreas dos projetos atualizam o fundo, a marca d'água e a
	 * pílula na hora. O título do diálogo (`titulo`) fica `sr-only` — o nome
	 * visível é o campo.
	 */
	import ColecaoAreasPill from '$lib/components/ColecaoAreasPill.svelte';
	import ColecaoIconeSvg from '$lib/components/ColecaoIconeSvg.svelte';
	import { tomDaCapa } from '$lib/icons/collectionIdentity';
	import type { AreaColecao, CollectionColorId, CollectionIconId } from '$lib/types/collections';

	interface Props {
		titleId: string;
		/** Nome acessível do diálogo ("Nova coleção", "Editar coleção"). */
		titulo: string;
		icone: CollectionIconId;
		cor: CollectionColorId;
		nome: string;
		descricao: string;
		/** Áreas dos projetos já marcados (pílula); vazio esconde a pílula. */
		areas: readonly AreaColecao[];
		nomeInvalido: boolean;
		nomeMax: number;
		descricaoMax: number;
		/** Campo do nome, para o modal focar ao abrir e ao validar. */
		nomeInputEl: HTMLInputElement | null;
		fecharDesabilitado: boolean;
		onFechar: () => void;
	}

	let {
		titleId,
		titulo,
		icone,
		cor,
		nome = $bindable(),
		descricao = $bindable(),
		areas,
		nomeInvalido,
		nomeMax,
		descricaoMax,
		nomeInputEl = $bindable(),
		fecharDesabilitado,
		onFechar
	}: Props = $props();

	const tom = $derived(tomDaCapa(cor));
</script>

<div class="relative overflow-hidden px-5 pb-7 pt-6 transition-colors duration-slow sm:px-7 sm:pb-[30px] sm:pt-8 {tom.wash}">
	<h2 id={titleId} class="sr-only">{titulo}</h2>
	<ColecaoIconeSvg
		{icone}
		size={150}
		class="pointer-events-none absolute -bottom-11 right-6 opacity-[.13] transition-colors duration-slow sm:right-[100px] {tom.tinta}"
	/>

	<!-- Mobile: linha própria acima do nome; sm+: canto superior direito. -->
	<div class="relative z-[1] -mt-1 mb-2 flex items-center justify-end gap-2 sm:absolute sm:right-6 sm:top-[30px] sm:m-0">
		{#if areas.length > 0}
			<ColecaoAreasPill {areas} {cor} />
		{/if}
		<button
			type="button"
			onclick={onFechar}
			disabled={fecharDesabilitado}
			aria-label="Fechar"
			class="bg-capa-veu grid h-8 w-8 place-items-center rounded-full text-text-secondary transition-colors duration-fast hover:text-text-primary disabled:opacity-60 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
		>
			<svg viewBox="0 0 20 20" class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true">
				<path d="m5 5 10 10M15 5 5 15" stroke-linecap="round" />
			</svg>
		</button>
	</div>

	<div class="relative flex max-w-[640px] flex-col gap-2">
		<input
			id="{titleId}-nome"
			bind:this={nomeInputEl}
			bind:value={nome}
			type="text"
			maxlength={nomeMax}
			aria-label="Nome da coleção"
			aria-invalid={nomeInvalido}
			aria-describedby={nomeInvalido ? `${titleId}-nome-erro` : undefined}
			placeholder="Dê um nome à coleção"
			class="w-full border-0 border-b-2 border-dashed bg-transparent px-0 pb-1.5 pt-0.5 font-heading text-2xl font-bold text-text-primary outline-none transition-colors duration-fast placeholder:text-text-faint {nomeInvalido
				? 'border-danger'
				: 'border-border-strong focus:border-text-secondary'}"
		/>
		{#if nomeInvalido}
			<p id="{titleId}-nome-erro" class="m-0 text-xs font-medium text-danger">
				Informe o nome da coleção.
			</p>
		{/if}
		<input
			bind:value={descricao}
			type="text"
			maxlength={descricaoMax}
			aria-label="Descrição (opcional)"
			placeholder="Para que serve esta coleção (opcional)"
			class="w-full border-0 bg-transparent p-0 text-[0.9375rem] text-text-secondary outline-none placeholder:text-text-faint"
		/>
	</div>
</div>
