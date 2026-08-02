<script lang="ts">
	/**
	 * Chassi ÚNICO de confirmação (grupos 2 e 3 do spec de feedbacks): destrutiva
	 * e não-destrutiva no mesmo desenho de 440 px — só muda a tinta do `tone`.
	 *
	 * Uso direto é a exceção; o caminho normal é `confirmAction()` de
	 * `$lib/stores/confirm`, que monta este componente via `<ConfirmHost />`.
	 */
	import { onMount } from 'svelte';
	import FeedbackIcon from './FeedbackIcon.svelte';
	import StateBanner from './StateBanner.svelte';
	import type { FeedbackIconId } from '$lib/icons/feedbackIcons';
	import type { ConfirmTone } from '$lib/stores/confirm';

	interface Props {
		title: string;
		description?: string;
		tone?: ConfirmTone;
		icon?: FeedbackIconId;
		confirmLabel: string;
		cancelLabel?: string;
		busyLabel?: string;
		typeToConfirm?: string;
		busy?: boolean;
		error?: string;
		onConfirm: () => void | Promise<void>;
		onCancel: () => void;
	}

	let {
		title,
		description,
		tone = 'danger',
		icon,
		confirmLabel,
		cancelLabel = 'Cancelar',
		busyLabel,
		typeToConfirm,
		busy = false,
		error,
		onConfirm,
		onCancel
	}: Props = $props();

	const DEFAULT_ICON: Record<ConfirmTone, FeedbackIconId> = {
		danger: 'trash',
		brand: 'info',
		warning: 'draft'
	};

	const TONE_INK: Record<ConfirmTone, string> = {
		danger: 'text-danger',
		brand: 'text-brand',
		warning: 'text-warning'
	};

	const TONE_FILL: Record<ConfirmTone, string> = {
		danger: 'bg-fill-danger text-on-danger focus-visible:ring-danger',
		brand: 'bg-brand text-on-brand focus-visible:ring-brand',
		warning: 'bg-fill-warning text-on-warning focus-visible:ring-warning'
	};

	const FOCUSABLE =
		'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])';

	const titleId = `confirm-title-${Math.random().toString(36).slice(2, 9)}`;
	const descId = `${titleId}-desc`;
	const phraseId = `${titleId}-phrase`;

	let dialogEl = $state<HTMLDivElement | null>(null);
	let confirmEl = $state<HTMLButtonElement | null>(null);
	let cancelEl = $state<HTMLButtonElement | null>(null);
	let typed = $state('');

	const iconId = $derived(icon ?? DEFAULT_ICON[tone]);
	const phraseMatched = $derived(
		!typeToConfirm || typed.trim().toLowerCase() === typeToConfirm.trim().toLowerCase()
	);
	const confirmDisabled = $derived(busy || !phraseMatched);

	onMount(() => {
		const trigger = document.activeElement as HTMLElement | null;
		// Em ação destrutiva o foco entra no escape, não no gatilho do estrago.
		const initial = tone === 'danger' ? cancelEl : (confirmEl ?? cancelEl);
		initial?.focus();
		return () => trigger?.focus?.();
	});

	function focusableItems(): HTMLElement[] {
		if (!dialogEl) return [];
		return Array.from(dialogEl.querySelectorAll<HTMLElement>(FOCUSABLE));
	}

	function trapTab(event: KeyboardEvent): void {
		const items = focusableItems();
		if (items.length === 0) {
			event.preventDefault();
			return;
		}
		const first = items[0];
		const last = items[items.length - 1];
		const active = document.activeElement;
		const inside = dialogEl?.contains(active) ?? false;
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
			// Consome o Esc mesmo em `busy` para não vazar para o modal de baixo;
			// cancelar em voo é que não pode (mesma regra do backdrop e do Cancelar
			// desabilitado — fechar aqui abandonaria a ação e o banner de erro dela).
			event.preventDefault();
			event.stopPropagation();
			if (busy) return;
			onCancel();
			return;
		}
		if (event.key === 'Tab') trapTab(event);
	}

	// Enter nunca confirma: dentro do campo ele só seria "submit" acidental.
	function blockEnter(event: KeyboardEvent): void {
		if (event.key === 'Enter') event.preventDefault();
	}

	function handleBackdrop(event: MouseEvent): void {
		if (event.target !== event.currentTarget) return;
		if (busy) return;
		onCancel();
	}
</script>

<svelte:window onkeydown={handleKeydown} />

<div
	class="fixed inset-0 z-modal flex items-center justify-center bg-overlay p-4"
	role="presentation"
	onclick={handleBackdrop}
>
	<div
		bind:this={dialogEl}
		class="confirm-dialog flex w-full max-w-[27.5rem] animate-modal-slide-in flex-col gap-4 rounded-control border border-border-subtle bg-surface p-6 shadow-modal"
		role="alertdialog"
		aria-modal="true"
		aria-labelledby={titleId}
		aria-describedby={description ? descId : undefined}
	>
		<div class="flex items-start gap-3.5">
			<FeedbackIcon id={iconId} size={24} class="mt-0.5 {TONE_INK[tone]}" />
			<div class="flex flex-col gap-1.5">
				<h3 id={titleId} class="text-xl font-semibold tracking-tight text-text-primary">
					{title}
				</h3>
				{#if description}
					<p id={descId} class="text-md text-text-secondary">{description}</p>
				{/if}
			</div>
		</div>

		{#if error}
			<StateBanner tone="danger" title={error} />
		{/if}

		{#if typeToConfirm}
			<label class="flex flex-col gap-1.5">
				<span id={phraseId} class="text-sm text-text-secondary">
					Digite
					<strong class="font-mono text-sm font-medium text-text-primary">{typeToConfirm}</strong>
					para liberar o botão
				</span>
				<input
					type="text"
					bind:value={typed}
					disabled={busy}
					autocomplete="off"
					spellcheck="false"
					aria-labelledby={phraseId}
					onkeydown={blockEnter}
					class="w-full rounded-sm border border-border-strong bg-surface px-3 py-2.5 font-mono text-md text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:opacity-60"
				/>
			</label>
		{/if}

		<div class="mt-0.5 flex justify-end gap-2.5">
			<button
				bind:this={cancelEl}
				type="button"
				disabled={busy}
				onclick={onCancel}
				class="rounded-sm border border-border-strong bg-surface px-4 py-2.5 text-md font-semibold text-text-secondary transition-colors duration-fast hover:border-text-muted hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
			>
				{cancelLabel}
			</button>
			<button
				bind:this={confirmEl}
				type="button"
				disabled={confirmDisabled}
				onclick={() => void onConfirm()}
				class="rounded-sm px-4 py-2.5 text-md font-semibold transition-opacity duration-fast hover:opacity-90 focus:outline-none focus-visible:ring-2 disabled:cursor-not-allowed disabled:bg-surface-muted disabled:text-text-faint disabled:hover:opacity-100 {TONE_FILL[
					tone
				]}"
			>
				{busy ? (busyLabel ?? confirmLabel) : confirmLabel}
			</button>
		</div>
	</div>
</div>

<style>
	@media (prefers-reduced-motion: reduce) {
		.confirm-dialog {
			animation-duration: 0ms;
		}
	}
</style>
