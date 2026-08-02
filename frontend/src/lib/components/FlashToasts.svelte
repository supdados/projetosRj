<script lang="ts">
	/**
	 * Pilha de toasts (FLASH) da SPA: cartões no canto superior direito, abaixo do
	 * topnav, com ícone na tinta da severidade sobre superfície NEUTRA, título e
	 * descrição opcional. Auto-dismiss vem do store (`danger` não expira), além de
	 * Esc e fechamento manual.
	 *
	 * Montado UMA vez por tela. O anúncio para leitor de tela sai de UMA região
	 * `aria-live` persistente (fora da lista), escrita só no NASCIMENTO do toast:
	 * repetição coalescida (`item.count` no store) não gera anúncio novo nem
	 * aparece na tela — só reinicia o timer.
	 */
	import { onDestroy, onMount, tick } from 'svelte';
	import { get } from 'svelte/store';
	import { flash, type FlashCategory, type FlashMessage } from '$lib/stores/flash';
	import FeedbackIcon from '$lib/components/FeedbackIcon.svelte';
	import type { FeedbackIconId } from '$lib/icons/feedbackIcons';
	import { fly, type TransitionConfig } from 'svelte/transition';

	const ICON: Record<FlashCategory, FeedbackIconId> = {
		success: 'check',
		info: 'info',
		warning: 'alert',
		danger: 'x'
	};

	/** A tinta da severidade fica só no ícone; o cartão é neutro. */
	const TINTA: Record<FlashCategory, string> = {
		success: 'text-success',
		info: 'text-brand',
		warning: 'text-warning',
		danger: 'text-danger'
	};

	/** Recuo por posição na pilha: o mais antigo (último) é o mais apagado. */
	const OPACIDADE = [1, 0.82, 0.62];

	// Mais recente no topo — é ele que recebe o Esc e a opacidade cheia.
	const pilha = $derived([...$flash].reverse());

	let reduceMotion = $state(false);

	/** Tempo que o texto fica no nó de anúncio antes de ser recolhido. */
	const ANNOUNCE_CLEAR_MS = 1000;

	let announcement = $state('');
	// `id` é monotônico no store: toast já vivo ao montar a tela não é nascimento.
	let lastAnnouncedId = get(flash).at(-1)?.id ?? 0;

	// Serializa as escritas: dois nascimentos em ticks vizinhos se atropelariam no
	// `await` e o primeiro texto sairia do nó antes de ser lido.
	let filaDeAnuncio: Promise<void> = Promise.resolve();
	let limparAnuncio: ReturnType<typeof setTimeout> | null = null;

	function textoCompleto(item: FlashMessage): string {
		return item.description ? `${item.message} ${item.description}` : item.message;
	}

	// Zera antes de escrever: reescrever o MESMO texto não muta o nó e não é anunciado.
	async function announceBirth(texto: string): Promise<void> {
		if (limparAnuncio) clearTimeout(limparAnuncio);
		announcement = '';
		await tick();
		announcement = texto;
		// Sem isto o texto fica residente e o cursor virtual o encontra muito depois
		// de o toast sumir.
		limparAnuncio = setTimeout(() => (announcement = ''), ANNOUNCE_CLEAR_MS);
	}

	$effect(() => {
		const nascidos = $flash.filter((item) => item.id > lastAnnouncedId);
		if (nascidos.length === 0) return;
		lastAnnouncedId = nascidos[nascidos.length - 1].id;
		const texto = nascidos.map(textoCompleto).join(' ');
		filaDeAnuncio = filaDeAnuncio.then(() => announceBirth(texto));
	});

	onDestroy(() => {
		if (limparAnuncio) clearTimeout(limparAnuncio);
	});

	onMount(() => {
		if (typeof window === 'undefined') return;
		const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
		reduceMotion = mq.matches;
		const onChange = (event: MediaQueryListEvent) => (reduceMotion = event.matches);
		mq.addEventListener('change', onChange);
		return () => mq.removeEventListener('change', onChange);
	});

	const toastTransition = (node: Element): TransitionConfig =>
		reduceMotion ? { duration: 0 } : fly(node, { x: 16, duration: 180 });

	// Esc dispensa o toast mais recente. Modais/dropdowns tratam Esc por conta
	// própria e o gesto deles vem primeiro: dentro de um diálogo (inclusive
	// `alertdialog`, que é o ConfirmDialog/InlineConfirm), não interceptar;
	// quem consumir o Esc no window (ex.: dropdowns do topnav, que mantêm o foco
	// no botão toggle) sinaliza via preventDefault e também não interceptamos.
	function dismissarComEsc(event: KeyboardEvent): void {
		if (event.key !== 'Escape' || event.defaultPrevented) return;
		const vivos = get(flash);
		if (vivos.length === 0) return;
		const alvo = event.target as Element | null;
		if (alvo?.closest?.('[role="dialog"], [role="alertdialog"], dialog')) return;
		flash.dismiss(vivos[vivos.length - 1].id);
	}
</script>

<svelte:window onkeydown={dismissarComEsc} />

<!-- z-toast (1080) > z-sticky (1020): sem ancorar abaixo da altura real do topnav
	 o toast nasce por cima da barra superior. -->
<div
	class="pointer-events-none fixed z-toast flex flex-col items-end gap-2.5"
	style="top: calc(var(--app-topnav-height) + 0.75rem); right: 1rem;"
>
	<div class="sr-only" aria-live="polite">{announcement}</div>
	{#each pilha as item, posicao (item.id)}
		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<div
			transition:toastTransition
			onmouseenter={() => flash.pause(item.id)}
			onmouseleave={() => flash.resume(item.id)}
			onfocusin={() => flash.pause(item.id)}
			onfocusout={() => flash.resume(item.id)}
			style="opacity: {OPACIDADE[posicao] ?? OPACIDADE[OPACIDADE.length - 1]};"
			class="pointer-events-auto flex w-96 max-w-[calc(100vw-2rem)] gap-3 rounded-md border border-border-subtle bg-surface px-4 py-3.5 shadow-popover {item.description
				? 'items-start'
				: 'items-center'}"
		>
			<span class="sr-only">{textoCompleto(item)}</span>
			<div class="flex min-w-0 flex-1 gap-3 {item.description ? 'items-start' : 'items-center'}">
				<span class="shrink-0 {TINTA[item.category]} {item.description ? 'mt-px' : ''}">
					<FeedbackIcon id={ICON[item.category]} size={21} />
				</span>
				<span class="flex min-w-0 flex-1 flex-col gap-0.5" aria-hidden="true">
					<span class="text-md font-semibold text-text-primary">{item.message}</span>
					{#if item.description}
						<span class="text-md text-text-secondary">{item.description}</span>
					{/if}
				</span>
			</div>
			<button
				type="button"
				onclick={() => flash.dismiss(item.id)}
				aria-label="Fechar aviso"
				class="grid h-[26px] w-[26px] shrink-0 place-items-center rounded-sm text-text-muted transition-colors duration-fast hover:bg-wash-neutral hover:text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
			>
				<FeedbackIcon id="close" size={17} />
			</button>
		</div>
	{/each}
</div>
