<script lang="ts">
	/**
	 * Faixa de confirmação que cobre o próprio elemento (spec Grupo 4) — não é
	 * um modal reduzido. Preenche 100% do espaço do contêiner (`h-full w-full`);
	 * cabe ao CONSUMIDOR posicioná-la por cima do elemento (ex.: wrapper com
	 * `position: relative` + esta faixa em `position: absolute; inset: 0`), o
	 * que garante que ela nunca aumente a altura do card.
	 */
	import { onMount } from 'svelte';
	import FeedbackIcon from './FeedbackIcon.svelte';
	import type { FeedbackIconId } from '$lib/icons/feedbackIcons';

	type InlineConfirmTone = 'danger' | 'warning';

	interface Props {
		question: string;
		tone: InlineConfirmTone;
		confirmLabel: string;
		cancelLabel?: string;
		icon?: FeedbackIconId;
		busy?: boolean;
		onConfirm: () => void | Promise<void>;
		onCancel: () => void;
	}

	let {
		question,
		tone,
		confirmLabel,
		cancelLabel = 'Cancelar',
		icon,
		busy = false,
		onConfirm,
		onCancel
	}: Props = $props();

	const DEFAULT_ICON: Record<InlineConfirmTone, FeedbackIconId> = {
		danger: 'trash',
		warning: 'draft'
	};

	const TONE_SURFACE: Record<InlineConfirmTone, string> = {
		danger: 'border-danger bg-wash-danger',
		warning: 'border-warning bg-wash-warning'
	};

	const TONE_INK: Record<InlineConfirmTone, string> = {
		danger: 'text-danger',
		warning: 'text-warning'
	};

	const TONE_FILL: Record<InlineConfirmTone, string> = {
		danger: 'bg-fill-danger text-on-danger focus-visible:ring-danger',
		warning: 'bg-fill-warning text-on-warning focus-visible:ring-warning'
	};

	const FOCUSABLE = 'button:not([disabled])';

	const iconId = $derived(icon ?? DEFAULT_ICON[tone]);

	let rootEl = $state<HTMLDivElement | null>(null);
	let cancelEl = $state<HTMLButtonElement | null>(null);
	let confirmEl = $state<HTMLButtonElement | null>(null);

	onMount(() => {
		const trigger = document.activeElement as HTMLElement | null;
		cancelEl?.focus();
		return () => trigger?.focus?.();
	});

	function focusableItems(): HTMLElement[] {
		if (!rootEl) return [];
		return Array.from(rootEl.querySelectorAll<HTMLElement>(FOCUSABLE));
	}

	function trapTab(event: KeyboardEvent): void {
		const items = focusableItems();
		if (items.length === 0) return;
		const first = items[0];
		const last = items[items.length - 1];
		const active = document.activeElement;
		const inside = rootEl?.contains(active) ?? false;
		if (event.shiftKey && (!inside || active === first)) {
			event.preventDefault();
			last.focus();
			return;
		}
		if (!event.shiftKey && (!inside || active === last)) {
			event.preventDefault();
			first.focus();
		}
	}

	function handleKeydown(event: KeyboardEvent): void {
		if (event.key === 'Escape') {
			event.preventDefault();
			event.stopPropagation();
			// Em voo, cancelar abandonaria a ação já disparada (mesma regra do
			// clique fora e dos botões desabilitados).
			if (busy) return;
			onCancel();
			return;
		}
		if (event.key === 'Tab') trapTab(event);
	}

	// Clique fora cancela, exceto em `busy` — mesmo bug de fechar-durante-o-voo
	// corrigido no ConfirmDialog (era o de TaskHubTaskRow.svelte:490).
	function closeOnClickOutside(node: HTMLElement) {
		function handle(event: PointerEvent): void {
			if (busy) return;
			if (node.contains(event.target as Node)) return;
			onCancel();
		}
		document.addEventListener('pointerdown', handle, true);
		return {
			destroy() {
				document.removeEventListener('pointerdown', handle, true);
			}
		};
	}
</script>

<div
	bind:this={rootEl}
	use:closeOnClickOutside
	onkeydown={handleKeydown}
	role="alertdialog"
	aria-label={question}
	aria-busy={busy}
	tabindex="-1"
	class="flex h-full w-full flex-col justify-center gap-3 rounded-md border p-3.5 {TONE_SURFACE[
		tone
	]}"
>
	<div class="flex items-start gap-[0.5625rem]">
		<FeedbackIcon id={iconId} size={18} class="mt-px shrink-0 {TONE_INK[tone]}" />
		<span class="text-md font-semibold text-text-primary">{question}</span>
	</div>
	<div class="flex gap-2">
		<button
			bind:this={confirmEl}
			type="button"
			disabled={busy}
			onclick={() => void onConfirm()}
			class="h-7 flex-1 rounded-sm text-xs font-semibold transition-opacity duration-fast hover:opacity-90 focus:outline-none focus-visible:ring-2 disabled:cursor-not-allowed disabled:opacity-50 {TONE_FILL[
				tone
			]}"
		>
			{confirmLabel}
		</button>
		<button
			bind:this={cancelEl}
			type="button"
			disabled={busy}
			onclick={onCancel}
			class="h-7 flex-1 rounded-sm border border-border-strong bg-transparent text-xs font-semibold text-text-secondary transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-50"
		>
			{cancelLabel}
		</button>
	</div>
</div>
