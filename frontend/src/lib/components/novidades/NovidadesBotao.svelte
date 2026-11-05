<script lang="ts">
	/**
	 * Botão "Novidades" do topnav: reabre a novidade mais recente e mostra um
	 * ponto laranja enquanto houver alguma não vista. Some quando não há
	 * novidade ativa com conteúdo. Rótulo por extenso só a partir de `xl` — em
	 * telas menores fica só o ícone (com `aria-label`), como o sino ao lado.
	 */
	import { temConteudoNovidade } from '$lib/novidades/conteudo';
	import { novidadeDoBotao, temNovidadeNaoVista } from '$lib/novidades/selecao';
	import { novidades } from '$lib/stores/novidades';

	const slug = $derived(novidadeDoBotao($novidades.itens, temConteudoNovidade));
	const naoVista = $derived(temNovidadeNaoVista($novidades.itens, temConteudoNovidade));
	const rotulo = $derived(naoVista ? 'Novidades (há novidade não vista)' : 'Novidades');
	const aberta = $derived($novidades.aberta !== null);
</script>

{#if slug}
	<button
		type="button"
		onclick={() => slug && novidades.abrir(slug)}
		title={rotulo}
		aria-label={rotulo}
		class="relative inline-flex h-[1.95rem] min-w-[1.95rem] items-center justify-center gap-1.5 rounded-md border px-1.5 text-sm font-bold transition-ui duration-[180ms] focus:outline-none focus-visible:ring-2 focus-visible:ring-on-brand xl:px-2.5 {aberta
			? 'border-surface-elevated bg-surface-elevated text-brand'
			: 'border-transparent bg-transparent text-on-brand-muted hover:bg-on-brand-hover hover:text-on-topnav'}"
	>
		<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M5.6 18.4l2.1-2.1M16.3 7.7l2.1-2.1" /></svg>
		<span class="hidden xl:inline">Novidades</span>
		{#if naoVista}
			<span
				class="absolute right-0.5 top-0.5 h-2 w-2 rounded-full bg-attention-400 ring-2 ring-[var(--ds-color-surface-topnav)] xl:static xl:ring-0"
				aria-hidden="true"
			></span>
		{/if}
	</button>
{/if}
