<script lang="ts">
	/**
	 * Modal "Novidades" em passos (design aprovado "lançamento em passos"):
	 * ilustração à esquerda sobre o fundo do passo, texto à direita, barra de
	 * progresso e "Agora não / Voltar" + "Próximo". No último passo o botão
	 * principal vira a ação final (ex.: "Abrir Coleções").
	 *
	 * Só desenha e navega: quem decide marcar como vista, mostrar o toast e
	 * navegar é o `NovidadesHost` (`onFechar`/`onAcaoFinal`). Esc e o X
	 * dispensam; clicar fora NÃO fecha (ninguém perde o tour por um clique
	 * acidental). Setas ← → trocam de passo.
	 */
	import { fade } from 'svelte/transition';
	import { prefersReducedMotion } from 'svelte/motion';
	import Modal from '$lib/components/Modal.svelte';
	import type { ConteudoNovidade } from '$lib/novidades/conteudo';

	interface Props {
		conteudo: ConteudoNovidade;
		/** Fechou antes do fim (X, Esc, "Agora não") — `concluida=false`. */
		onFechar: (concluida: boolean) => void;
		/** Botão do último passo: conclui e leva à função apresentada. */
		onAcaoFinal: () => void;
	}

	let { conteudo, onFechar, onAcaoFinal }: Props = $props();

	const TITULO_ID = 'novidades-titulo';
	const BOTAO =
		'inline-flex h-11 shrink-0 items-center justify-center gap-2 whitespace-nowrap rounded-control text-md font-bold transition-ui duration-fast focus:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-1';

	let indice = $state(0);
	const total = $derived(conteudo.passos.length);
	const passo = $derived(conteudo.passos[indice]);
	const ultimo = $derived(indice === total - 1);
	const Visual = $derived(passo.visual);
	const duracao = $derived(prefersReducedMotion.current ? 0 : 180);

	function avancar(): void {
		if (ultimo) {
			onAcaoFinal();
			return;
		}
		indice += 1;
	}

	function voltarOuDispensar(): void {
		if (indice === 0) {
			onFechar(false);
			return;
		}
		indice -= 1;
	}

	function teclas(event: KeyboardEvent): void {
		if (event.key === 'ArrowRight' && !ultimo) {
			event.preventDefault();
			indice += 1;
		} else if (event.key === 'ArrowLeft' && indice > 0) {
			event.preventDefault();
			indice -= 1;
		}
	}

	function corDaBarra(k: number): string {
		if (k === indice) return 'bg-primary-600';
		return k < indice ? 'bg-primary-300' : 'bg-neutral-200';
	}
</script>

<Modal labelId={TITULO_ID} flush maxWidth="max-w-[920px]" onEscape={() => onFechar(false)}>
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div class="grid md:h-[560px] md:grid-cols-[440px_minmax(0,1fr)]" onkeydown={teclas}>
		<div
			class="relative flex h-[280px] items-center justify-center overflow-hidden transition-colors duration-base md:h-auto {passo.fundo}"
		>
			{#key indice}
				<div class="scale-[0.78] md:scale-100" in:fade={{ duration: duracao }}>
					<Visual />
				</div>
			{/key}
		</div>

		<div class="flex min-w-0 flex-col px-6 py-6 md:py-8 md:pl-11 md:pr-10">
			<div class="flex items-center justify-between">
				<span class="font-mono text-2xs font-semibold uppercase tracking-[0.12em] text-primary-600">
					Novidades · {conteudo.rotulo}
				</span>
				<button
					type="button"
					aria-label="Fechar novidades"
					onclick={() => onFechar(false)}
					class="-mr-2.5 grid h-9 w-9 place-items-center rounded-lg text-text-muted transition-colors duration-fast hover:bg-surface-muted hover:text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
				>
					<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>
				</button>
			</div>

			{#key indice}
				<div in:fade={{ duration: duracao }}>
					<h2
						id={TITULO_ID}
						class="m-0 mt-6 font-heading text-[1.75rem] font-extrabold leading-[1.15] tracking-[-0.02em] text-text-primary md:mt-7 md:text-[1.875rem]"
					>
						{passo.titulo}
					</h2>
					<p class="m-0 mt-3.5 text-base leading-relaxed text-text-secondary">{passo.texto}</p>
					<ul class="m-0 mt-6 flex list-none flex-col gap-3 p-0">
						{#each passo.detalhes as detalhe (detalhe)}
							<li class="flex gap-2.5 text-md leading-snug text-text-primary">
								<span
									class="mt-px grid h-5 w-5 shrink-0 place-items-center rounded-full bg-primary-50 text-primary-600"
									aria-hidden="true"
								>
									<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round"><path d="M5 12l5 5 9-10" /></svg>
								</span>
								{detalhe}
							</li>
						{/each}
					</ul>
				</div>
			{/key}

			<div class="min-h-6 flex-1"></div>

			<!-- Botões de 44px (alvo de toque) — por isso não o `Button` (lg = 48px e
			     largo demais para caber barra + dois botões na coluna de texto). -->
			<div class="flex items-center gap-3">
				<p class="sr-only" aria-live="polite">Passo {indice + 1} de {total}</p>
				<div class="flex min-w-0 flex-1 gap-1.5" aria-hidden="true">
					{#each conteudo.passos as _, k (k)}
						<span class="h-1 w-6 rounded-sm transition-colors duration-base {corDaBarra(k)}"></span>
					{/each}
				</div>
				<button type="button" onclick={voltarOuDispensar} class="{BOTAO} px-4 text-text-secondary hover:bg-surface-muted hover:text-text-primary">
					{indice === 0 ? 'Agora não' : 'Voltar'}
				</button>
				<button type="button" onclick={avancar} class="{BOTAO} bg-brand px-5 text-on-brand shadow-sm hover:bg-brand-hover hover:shadow-md">
					{ultimo ? conteudo.acaoFinal.rotulo : 'Próximo'}
					<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6" /></svg>
				</button>
			</div>
		</div>
	</div>
</Modal>
