<script lang="ts">
	/**
	 * Pilha de toasts (FLASH) da SPA — equivalente visual ao `app-flash-alert` do
	 * Jinja (`base.html` + `static/js/app-shell/flash.js`): toasts fixos no topo,
	 * com ícone por categoria, auto-dismiss (no store) e fechamento manual.
	 *
	 * Montado UMA vez por tela. O anúncio para leitor de tela sai de UMA região
	 * `aria-live` persistente (fora da lista), escrita só no NASCIMENTO do toast:
	 * repetição coalescida (contador `×N`) não gera anúncio novo.
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

	/** Classes de cor por categoria (tokens de tema da SPA). */
	const TONE: Record<FlashCategory, string> = {
		success: 'border-success text-success',
		info: 'border-brand text-brand',
		warning: 'border-warning text-warning',
		danger: 'border-danger text-danger'
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
</script>

<div
	class="pointer-events-none fixed inset-x-0 top-4 z-toast flex flex-col items-center gap-2 px-4"
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
			class="pointer-events-auto flex w-full max-w-md items-start gap-2 rounded-lg border bg-surface px-4 py-3 shadow-lg {TONE[
				item.category
			]}"
		>
			<span class="sr-only">{item.message}</span>
			<div class="flex min-w-0 flex-1 items-start gap-2" aria-hidden="true">
				<i class="fas {ICON[item.category]} mt-0.5"></i>
				<span class="min-w-0 flex-1 text-sm text-text-primary">{item.message}</span>
			</div>
			<button
				type="button"
				onclick={() => flash.dismiss(item.id)}
				aria-label="Fechar aviso"
				class="shrink-0 text-text-muted hover:text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
			>
				✕
			</button>
		</div>
	{/each}
</div>
