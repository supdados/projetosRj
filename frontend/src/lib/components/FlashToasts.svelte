<script lang="ts">
	/**
	 * Pilha de toasts (FLASH) da SPA: cartões fixos abaixo do topnav, com ícone por
	 * categoria, auto-dismiss (no store), Esc e fechamento manual. O visual segue a
	 * receita de aviso do design system (wash + borda suave), não mais o
	 * `app-flash-alert` do Jinja legado.
	 *
	 * Montado UMA vez por tela. O anúncio para leitor de tela sai de UMA região
	 * `aria-live` persistente (fora da lista), escrita só no NASCIMENTO do toast:
	 * repetição coalescida (`item.count` no store) não gera anúncio novo nem
	 * aparece na tela — só reinicia o timer.
	 */
	import { onDestroy, onMount, tick } from 'svelte';
	import { get } from 'svelte/store';
	import { flash, type FlashCategory } from '$lib/stores/flash';
	import { fly, type TransitionConfig } from 'svelte/transition';

	/** Ícone FontAwesome por categoria (paridade com o flash legado). */
	const ICON: Record<FlashCategory, string> = {
		success: 'fa-check-circle',
		info: 'fa-info-circle',
		warning: 'fa-exclamation-triangle',
		danger: 'fa-exclamation-circle'
	};

	/**
	 * Cor por categoria: interior tingido (wash, degrau 100/800) + contorno suave
	 * (degrau 200/700) — mesma receita dos avisos do resto do app. A tinta forte
	 * fica só no ícone.
	 */
	const TONE: Record<FlashCategory, string> = {
		success: 'border-success-soft bg-wash-success text-success',
		info: 'border-brand-soft bg-wash-brand text-brand',
		warning: 'border-warning-soft bg-wash-warning text-warning',
		danger: 'border-danger-soft bg-wash-danger text-danger'
	};

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
		const texto = nascidos.map((item) => item.message).join(' ');
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
		reduceMotion ? { duration: 0 } : fly(node, { y: -16, duration: 180 });

	// Esc dispensa o toast mais recente. Modais/dropdowns tratam Esc por conta
	// própria e o gesto deles vem primeiro: dentro de um diálogo, não interceptar.
	function dismissarComEsc(event: KeyboardEvent): void {
		if (event.key !== 'Escape') return;
		const vivos = get(flash);
		if (vivos.length === 0) return;
		const alvo = event.target as Element | null;
		if (alvo?.closest?.('[role="dialog"], dialog')) return;
		flash.dismiss(vivos[vivos.length - 1].id);
	}
</script>

<svelte:window onkeydown={dismissarComEsc} />

<!-- z-toast (1080) > z-sticky (1020): sem ancorar abaixo da altura real do topnav
	 o toast nasce por cima da barra superior. -->
<div
	class="pointer-events-none fixed inset-x-0 z-toast flex flex-col items-center gap-2 px-4"
	style="top: calc(var(--app-topnav-height) + 0.75rem);"
>
	<div class="sr-only" aria-live="polite">{announcement}</div>
	{#each $flash as item (item.id)}
		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<div
			transition:toastTransition
			onmouseenter={() => flash.pause(item.id)}
			onmouseleave={() => flash.resume(item.id)}
			onfocusin={() => flash.pause(item.id)}
			onfocusout={() => flash.resume(item.id)}
			class="pointer-events-auto flex w-full max-w-md items-start gap-2.5 rounded-xl border px-3.5 py-2.5 shadow-popover {TONE[
				item.category
			]}"
		>
			<span class="sr-only">{item.message}</span>
			<div class="flex min-w-0 flex-1 items-start gap-2.5" aria-hidden="true">
				<i class="fas {ICON[item.category]} mt-px text-base leading-5"></i>
				<span class="min-w-0 flex-1 text-sm leading-5 text-text-primary">{item.message}</span>
			</div>
			<button
				type="button"
				onclick={() => flash.dismiss(item.id)}
				aria-label="Fechar aviso"
				class="grid h-7 w-7 shrink-0 place-items-center rounded-md text-text-muted transition-colors duration-fast hover:bg-surface-muted hover:text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
			>
				<svg
					viewBox="0 0 20 20"
					class="h-3.5 w-3.5"
					fill="none"
					stroke="currentColor"
					stroke-width="1.6"
					aria-hidden="true"
				>
					<path d="m5 5 10 10M15 5 5 15" stroke-linecap="round" />
				</svg>
			</button>
		</div>
	{/each}
</div>
