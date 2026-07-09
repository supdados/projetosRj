<script lang="ts">
	/**
	 * Chrome ÚNICO de modais do app: backdrop escurecido + painel centralizado
	 * (rounded-xl, bg-surface, shadow-lg, animate-modal-slide-in). O conteúdo
	 * interno fica por conta do chamador via `children`.
	 *
	 * Uso:
	 *   <Modal labelId="meu-titulo" onBackdrop={fechar}>
	 *     <h2 id="meu-titulo">…</h2>
	 *   </Modal>
	 */
	import type { Snippet } from 'svelte';

	interface Props {
		labelId: string;
		maxWidth?: string;
		onBackdrop?: () => void;
		children: Snippet;
	}

	let { labelId, maxWidth = 'max-w-md', onBackdrop, children }: Props = $props();

	function handleBackdropClick(event: MouseEvent) {
		if (event.target === event.currentTarget) onBackdrop?.();
	}
</script>

<div
	class="fixed inset-0 z-[1050] flex items-center justify-center bg-overlay p-4"
	role="presentation"
	onclick={handleBackdropClick}
>
	<div
		class="w-full {maxWidth} animate-modal-slide-in rounded-xl border border-border-subtle bg-surface p-6 shadow-lg"
		role="dialog"
		aria-modal="true"
		aria-labelledby={labelId}
	>
		{@render children()}
	</div>
</div>
