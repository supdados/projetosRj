<script lang="ts">
	/**
	 * Chrome ÚNICO de modais do app: backdrop escurecido + painel centralizado
	 * (rounded-xl, bg-surface, shadow-lg, animate-modal-slide-in). O conteúdo
	 * interno fica por conta do chamador via `children`.
	 *
	 * Agora também: fecha no Esc (via `onEscape`, com fallback para `onBackdrop`;
	 * sem os dois, Esc não faz nada) e gerencia foco — move para o painel ao
	 * montar, prende Tab/Shift+Tab dentro dele, restaura ao desmontar.
	 *
	 * Uso:
	 *   <Modal labelId="meu-titulo" onBackdrop={fechar}>
	 *     <h2 id="meu-titulo">…</h2>
	 *   </Modal>
	 */
	import type { Snippet } from 'svelte';
	import { focusTrap } from '$lib/actions/focusTrap';

	interface Props {
		labelId: string;
		maxWidth?: string;
		onBackdrop?: () => void;
		onEscape?: () => void;
		children: Snippet;
	}

	let { labelId, maxWidth = 'max-w-md', onBackdrop, onEscape, children }: Props = $props();

	let panelEl: HTMLDivElement | undefined = $state();

	function handleBackdropClick(event: MouseEvent) {
		if (event.target === event.currentTarget) onBackdrop?.();
	}

	// Dialogo "mais externo" = o último [role=dialog]/[role=alertdialog] no DOM;
	// evita que um Esc feche um modal por baixo de outro empilhado sobre ele.
	function isOutermostDialog(): boolean {
		if (!panelEl) return false;
		const dialogs = document.querySelectorAll('[role="dialog"], [role="alertdialog"]');
		return dialogs[dialogs.length - 1] === panelEl;
	}

	function handleWindowKeydown(event: KeyboardEvent) {
		if (event.key !== 'Escape' || event.defaultPrevented) return;
		if (!isOutermostDialog()) return;
		(onEscape ?? onBackdrop)?.();
	}

	$effect(() => {
		window.addEventListener('keydown', handleWindowKeydown);
		return () => window.removeEventListener('keydown', handleWindowKeydown);
	});
</script>

<div
	class="fixed inset-0 z-modal flex items-center justify-center bg-overlay p-4"
	role="presentation"
	onclick={handleBackdropClick}
>
	<div
		bind:this={panelEl}
		class="w-full {maxWidth} animate-modal-slide-in rounded-xl border border-border-subtle bg-surface p-6 shadow-lg"
		role="dialog"
		aria-modal="true"
		aria-labelledby={labelId}
		tabindex="-1"
		use:focusTrap
	>
		{@render children()}
	</div>
</div>
