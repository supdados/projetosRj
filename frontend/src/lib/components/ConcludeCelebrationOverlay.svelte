<script lang="ts">
	/**
	 * Overlay de conclusão de projeto. Duas fases via `state`: 'loading' mostra
	 * spinner discreto ("Concluindo projeto..."); 'success' mostra a arte do
	 * popper (mesma da tela de sucesso do CriarProjetoModal) com pop-shake e
	 * dispara o confete com origem medida na própria imagem. Backdrop, título e
	 * mensagem vêm da página; o chime segue disparado pela página. RESPEITA
	 * `prefers-reduced-motion` (animações none; o confete já é no-op).
	 */
	import { triggerTaskFinalizeConfetti } from '$lib/celebration/confettiEpic';

	interface Props {
		active: boolean;
		state: 'loading' | 'success';
		title: string;
		message: string;
	}

	let { active, state: phase, title, message }: Props = $props();

	let popperEl = $state<HTMLElement | null>(null);

	$effect(() => {
		if (!active || phase !== 'success') return;
		// Rajadas escalonadas a partir do pop-shake, com origem na arte do popper.
		const timers = [420, 780, 1140].map((delay) =>
			window.setTimeout(() => {
				if (!popperEl) return;
				const rect = popperEl.getBoundingClientRect();
				triggerTaskFinalizeConfetti({
					x: rect.left + rect.width / 2,
					y: rect.top + rect.height / 2
				});
			}, delay)
		);
		return () => timers.forEach((timer) => window.clearTimeout(timer));
	});
</script>

<div class="project-conclude-celebration" class:is-active={active} aria-hidden={!active}>
	<div class="project-conclude-celebration__backdrop"></div>
	<div
		class="project-conclude-celebration__card rounded-xl border border-border-subtle bg-surface px-5 pb-6 pt-8 shadow-modal"
		role="status"
		aria-live="polite"
	>
		{#if phase === 'success'}
			<!-- Wrapper sem transform: rect estável para a origem do confete. -->
			<span bind:this={popperEl} class="mx-auto block h-28 w-28">
				<img
					src="/static/img/confete-popper.png"
					alt=""
					class="project-conclude-celebration__popper h-28 w-28"
					aria-hidden="true"
				/>
			</span>
		{:else if active}
			<span
				class="mx-auto block h-10 w-10 animate-spin rounded-full border-[3px] border-border-subtle border-t-primary-600 motion-reduce:animate-none"
				aria-hidden="true"
			></span>
		{/if}
		<h3 class="project-conclude-celebration__title">{title}</h3>
		<p class="project-conclude-celebration__message">{message}</p>
	</div>
</div>

<style>
	.project-conclude-celebration {
		position: fixed;
		inset: 0;
		z-index: 1085;
		display: flex;
		align-items: center;
		justify-content: center;
		opacity: 0;
		pointer-events: none;
		transition: opacity 150ms ease;
	}

	.project-conclude-celebration.is-active {
		opacity: 1;
		pointer-events: auto;
	}

	.project-conclude-celebration__backdrop {
		position: absolute;
		inset: 0;
		background: radial-gradient(
			circle at center,
			rgba(6, 56, 96, 0.14) 0%,
			rgba(6, 56, 96, 0.36) 100%
		);
		backdrop-filter: blur(14px);
		-webkit-backdrop-filter: blur(14px);
	}

	:global([data-theme='dark']) .project-conclude-celebration__backdrop {
		background: radial-gradient(
			circle at center,
			rgba(0, 0, 0, 0.14) 0%,
			rgba(0, 0, 0, 0.55) 100%
		);
	}

	.project-conclude-celebration__card {
		position: relative;
		width: min(360px, calc(100vw - 2rem));
		text-align: center;
		transform: translateY(14px) scale(0.92);
		opacity: 0;
	}

	.project-conclude-celebration.is-active .project-conclude-celebration__card {
		animation: concludeCelebrationCardIn 0.34s cubic-bezier(0.2, 0.9, 0.2, 1) forwards;
	}

	.project-conclude-celebration__popper {
		transform-origin: 35% 75%;
	}

	.project-conclude-celebration.is-active .project-conclude-celebration__popper {
		animation: concludePopperPopShake 0.9s cubic-bezier(0.34, 1.4, 0.64, 1) both;
	}

	.project-conclude-celebration__title {
		margin: 1rem 0 0.35rem;
		color: var(--ds-color-text-primary);
		font-size: 1.25rem;
		font-weight: 700;
		line-height: 1.25;
	}

	.project-conclude-celebration__message {
		margin: 0;
		color: var(--ds-color-text-secondary);
		font-size: 1rem;
		line-height: 1.5;
	}

	@keyframes concludeCelebrationCardIn {
		0% {
			transform: translateY(14px) scale(0.92);
			opacity: 0;
		}
		70% {
			transform: translateY(-2px) scale(1.01);
			opacity: 1;
		}
		100% {
			transform: translateY(0) scale(1);
			opacity: 1;
		}
	}

	@keyframes concludePopperPopShake {
		0% {
			opacity: 0;
			transform: scale(0.5) rotate(0deg);
		}
		35% {
			opacity: 1;
			transform: scale(1.06) rotate(-9deg);
		}
		55% {
			transform: scale(1) rotate(7deg);
		}
		75% {
			transform: rotate(-4deg);
		}
		100% {
			opacity: 1;
			transform: scale(1) rotate(0deg);
		}
	}

	@media (prefers-reduced-motion: reduce) {
		.project-conclude-celebration,
		.project-conclude-celebration__card {
			transition-duration: 0.08s;
		}

		.project-conclude-celebration.is-active .project-conclude-celebration__card,
		.project-conclude-celebration__popper {
			animation: none !important;
		}

		.project-conclude-celebration__card {
			transform: translateY(0) scale(1);
			opacity: 1;
		}
	}
</style>
