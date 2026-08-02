<script lang="ts">
	/**
	 * Estado persistente dentro do container (spec Grupo 5). Não é modal nem
	 * toast: ocupa lugar RESERVADO — o consumidor deve reservar o espaço (ex.:
	 * altura mínima) para o banner não empurrar o layout ao aparecer/sumir.
	 */
	import FeedbackIcon from './FeedbackIcon.svelte';
	import type { FeedbackIconId } from '$lib/icons/feedbackIcons';

	type StateBannerTone = 'danger' | 'warning' | 'info';

	interface Props {
		tone: StateBannerTone;
		title: string;
		description?: string;
		icon?: FeedbackIconId;
		actionLabel?: string;
		onAction?: () => void;
		onDismiss?: () => void;
	}

	let { tone, title, description, icon, actionLabel, onAction, onDismiss }: Props = $props();

	const DEFAULT_ICON: Record<StateBannerTone, FeedbackIconId> = {
		danger: 'x',
		warning: 'alert',
		info: 'info'
	};

	const TONE_SURFACE: Record<StateBannerTone, string> = {
		danger: 'border-danger-soft bg-wash-danger',
		warning: 'border-warning-soft bg-wash-warning',
		info: 'border-brand-soft bg-wash-brand'
	};

	const TONE_INK: Record<StateBannerTone, string> = {
		danger: 'text-danger',
		warning: 'text-warning',
		info: 'text-brand'
	};

	const TONE_ACTION_HOVER: Record<StateBannerTone, string> = {
		danger: 'hover:bg-danger-soft',
		warning: 'hover:bg-warning-soft',
		info: 'hover:bg-brand-soft'
	};

	const iconId = $derived(icon ?? DEFAULT_ICON[tone]);
	const role = $derived(tone === 'danger' ? 'alert' : 'status');
</script>

<div {role} class="flex items-start gap-3 rounded-sm border px-4 py-3.5 {TONE_SURFACE[tone]}">
	<FeedbackIcon id={iconId} size={20} class="mt-px shrink-0 {TONE_INK[tone]}" />
	<div class="flex min-w-0 flex-1 flex-col gap-0.5">
		<span class="text-md font-semibold text-text-primary">{title}</span>
		{#if description}
			<span class="text-sm text-text-secondary">{description}</span>
		{/if}
	</div>
	{#if actionLabel && onAction}
		<button
			type="button"
			onclick={onAction}
			class="shrink-0 rounded-sm border border-current px-3 py-1.5 text-xs font-semibold transition-colors duration-fast focus:outline-none focus-visible:ring-2 focus-visible:ring-brand {TONE_INK[
				tone
			]} {TONE_ACTION_HOVER[tone]}"
		>
			{actionLabel}
		</button>
	{/if}
	{#if onDismiss}
		<button
			type="button"
			onclick={onDismiss}
			aria-label="Dispensar aviso"
			class="shrink-0 rounded-sm p-1 text-text-muted transition-colors duration-fast hover:bg-wash-neutral hover:text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
		>
			<FeedbackIcon id="close" size={16} />
		</button>
	{/if}
</div>
