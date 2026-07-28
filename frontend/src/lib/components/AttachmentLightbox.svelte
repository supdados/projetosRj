<script lang="ts">
	/**
	 * Visualizador de anexos da tarefa, aberto pelo ícone de anexo da lista quando
	 * já há anexos. Mostra um por vez na ORDEM; navega para os lados (footer / ←→).
	 * Reusa o dimensionamento do preview do AttachmentsPanel (h-fit + max-h, imagem
	 * max-h-[68vh] object-contain) — sem altura fixa (evita espaço vazio rolável).
	 * Trava o scroll do `<main>` (único scroller do app) enquanto aberto — sem
	 * scroll duplo. Esc fecha.
	 */
	import type { TaskAttachment } from '$lib/types/taskDrawer';

	interface Props {
		anexos: TaskAttachment[];
		onClose: () => void;
		/** Abre o seletor de arquivo para anexar mais (opcional). */
		onAdd?: () => void;
	}

	let { anexos, onClose, onAdd }: Props = $props();

	// Abre no primeiro anexo (ordem de anexo).
	let index = $state(0);

	$effect(() => {
		if (index > anexos.length - 1) index = Math.max(0, anexos.length - 1);
	});

	// Scroll-lock no scroller REAL do app (`.app-shell > main`), não no body
	// (que não rola neste layout viewport-fit) — elimina o scroll duplo.
	$effect(() => {
		const scroller = document.querySelector<HTMLElement>('.app-shell > main');
		if (!scroller) return;
		const prev = scroller.style.overflow;
		scroller.style.overflow = 'hidden';
		return () => {
			scroller.style.overflow = prev;
		};
	});

	const current = $derived(anexos[index] ?? null);
	const total = $derived(anexos.length);
	const isPdf = $derived(
		current
			? current.content_type.toLowerCase().includes('pdf') || /\.pdf($|\?)/i.test(current.url ?? '')
			: false
	);

	function prev(): void {
		index = (index - 1 + total) % total;
	}
	function next(): void {
		index = (index + 1) % total;
	}
	function onKeydown(event: KeyboardEvent): void {
		if (event.key === 'Escape') onClose();
		else if (event.key === 'ArrowLeft' && total > 1) prev();
		else if (event.key === 'ArrowRight' && total > 1) next();
	}
</script>

<svelte:window onkeydown={onKeydown} />

{#if current}
	<div class="fixed inset-0 z-[1000] bg-overlay" onclick={onClose} role="presentation"></div>
	<!-- svelte-ignore a11y_no_noninteractive_element_to_interactive_role -->
	<section
		role="dialog"
		aria-modal="true"
		aria-label={`Anexos — ${current.filename}`}
		tabindex="-1"
		class="fixed inset-0 z-[1001] m-auto flex h-fit max-h-[88vh] w-[min(92vw,52rem)] flex-col overflow-hidden rounded-xl border border-border-subtle bg-surface shadow-lg"
	>
		<header class="flex items-center justify-between gap-2 border-b border-border-subtle px-4 py-2.5">
			<div class="flex min-w-0 items-center gap-2">
				<h6 class="m-0 truncate text-sm font-semibold text-text-primary">{current.filename}</h6>
				{#if total > 1}
					<span class="shrink-0 rounded-full bg-surface-muted px-2 py-0.5 text-2xs font-semibold text-text-secondary">
						{index + 1} / {total}
					</span>
				{/if}
			</div>
			<button
				type="button"
				onclick={onClose}
				aria-label="Fechar"
				class="flex h-7 w-7 items-center justify-center rounded-md text-lg leading-none text-text-muted transition-colors duration-fast hover:bg-surface-muted hover:text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
			>
				&times;
			</button>
		</header>

		<!-- Conteúdo encolhe ATÉ a imagem (sem flex-1/overflow-auto → sem barra
		     interna nem espaço vazio rolável). A imagem se limita a max-h-[68vh]. -->
		<div class="flex items-center justify-center bg-surface-muted p-3">
			{#if current.is_image}
				<img
					src={current.url}
					alt={current.filename}
					class="max-h-[68vh] max-w-full rounded-md object-contain"
				/>
			{:else if isPdf}
				<iframe
					src={current.url}
					title={current.filename}
					class="h-[68vh] w-full rounded-md border-none bg-surface"
				></iframe>
			{:else}
				<div class="flex flex-col items-center gap-2 py-12 text-center text-text-secondary">
					<i class="fas fa-file text-5xl text-text-muted" aria-hidden="true"></i>
					<p class="m-0 text-sm">Preview não disponível para este tipo de arquivo.</p>
					<span class="text-xs text-text-muted">{current.filename}</span>
				</div>
			{/if}
		</div>

		<footer class="flex items-center justify-between gap-2 border-t border-border-subtle px-4 py-2.5">
			<!-- Navegação discreta (retangular, igual ao botão fechar) -->
			<div class="flex items-center gap-1">
				{#if total > 1}
					<button
						type="button"
						onclick={prev}
						aria-label="Anexo anterior"
						class="flex h-7 w-7 items-center justify-center rounded-md text-text-secondary transition-colors duration-fast hover:bg-surface-muted hover:text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
					>
						<i class="fas fa-chevron-left text-xs" aria-hidden="true"></i>
					</button>
					<button
						type="button"
						onclick={next}
						aria-label="Próximo anexo"
						class="flex h-7 w-7 items-center justify-center rounded-md text-text-secondary transition-colors duration-fast hover:bg-surface-muted hover:text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
					>
						<i class="fas fa-chevron-right text-xs" aria-hidden="true"></i>
					</button>
				{/if}
			</div>
			<div class="flex shrink-0 items-center gap-2">
				{#if onAdd}
					<button
						type="button"
						onclick={onAdd}
						class="inline-flex items-center gap-1.5 rounded-md border border-border-subtle bg-surface px-3 py-1.5 text-xs font-semibold text-text-secondary transition-colors duration-fast hover:bg-surface-muted hover:text-brand focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
					>
						<i class="fas fa-plus" aria-hidden="true"></i>Anexar
					</button>
				{/if}
				<a
					href={current.url}
					target="_blank"
					rel="noopener"
					download={current.filename}
					class="rounded-md bg-brand-gradient px-3 py-1.5 text-xs font-semibold text-on-brand no-underline shadow-sm transition-colors duration-fast hover:opacity-90 hover:shadow-md focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
				>
					Baixar
				</a>
			</div>
		</footer>
	</section>
{/if}
