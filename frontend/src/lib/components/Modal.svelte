<script lang="ts">
	/**
	 * Chrome ÚNICO de modais do app: backdrop escurecido + painel centralizado
	 * (rounded-xl, bg-surface, shadow-lg), com entrada/saída animadas. O conteúdo
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
	import { fade, scale } from 'svelte/transition';
	import { cubicIn, cubicOut } from 'svelte/easing';
	import { prefersReducedMotion } from 'svelte/motion';
	import { focusTrap } from '$lib/actions/focusTrap';

	interface Props {
		labelId: string;
		/** Quando informado, o próprio Modal monta/desmonta — necessário para a saída animada. */
		open?: boolean;
		maxWidth?: string;
		onBackdrop?: () => void;
		onEscape?: () => void;
		children: Snippet;
	}

	let { labelId, open = true, maxWidth = 'max-w-md', onBackdrop, onEscape, children }: Props =
		$props();

	let panelEl: HTMLDivElement | undefined = $state();

	const duracao = (ms: number): number => (prefersReducedMotion.current ? 0 : ms);

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

{#if open}
	<div
		class="fixed inset-0 z-modal flex items-center justify-center bg-overlay p-4"
		role="presentation"
		onclick={handleBackdropClick}
		in:fade|global={{ duration: duracao(150) }}
		out:fade={{ duration: duracao(150) }}
	>
		<div
			bind:this={panelEl}
			class="w-full {maxWidth} rounded-xl border border-border-subtle bg-surface p-6 shadow-lg"
			role="dialog"
			aria-modal="true"
			aria-labelledby={labelId}
			tabindex="-1"
			use:focusTrap
			in:scale|global={{ start: 0.96, duration: duracao(220), easing: cubicOut }}
			out:scale={{ start: 0.98, duration: duracao(140), easing: cubicIn }}
		>
			{@render children()}
		</div>
	</div>
{/if}
