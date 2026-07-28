<script lang="ts">
	/**
	 * Overlay de celebração da conclusão de projeto — porte FIEL do
	 * `#projectConcludeCelebration` (templates/projects/detail.html) + CSS
	 * `.project-conclude-celebration*` (static/css/projects/detail/
	 * 03-stages-and-interactions.css). Backdrop, card com check + ring animado +
	 * título + mensagem + 6 partículas. A classe `is-active` liga as animações.
	 *
	 * CONTROLADO pela página: recebe `active`, `title`, `message`. O som (chime)
	 * e o confete (canvas épico) são disparados pela PÁGINA (lib/celebration/*),
	 * não aqui — este componente é só o aviso visual em tela. RESPEITA
	 * `prefers-reduced-motion` (via a media query do CSS portado).
	 */
	interface Props {
		active: boolean;
		title: string;
		message: string;
	}

	let { active, title, message }: Props = $props();
</script>

<div class="project-conclude-celebration" class:is-active={active} aria-hidden={!active}>
	<div class="project-conclude-celebration__backdrop"></div>
	<div class="project-conclude-celebration__card" role="status" aria-live="polite">
		<div class="project-conclude-celebration__check">
			<i class="fas fa-check"></i>
		</div>
		<div class="project-conclude-celebration__ring" aria-hidden="true"></div>
		<h3 class="project-conclude-celebration__title">{title}</h3>
		<p class="project-conclude-celebration__message">{message}</p>
		<div class="project-conclude-celebration__particles" aria-hidden="true">
			<span></span>
			<span></span>
			<span></span>
			<span></span>
			<span></span>
			<span></span>
		</div>
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
		backdrop-filter: blur(2px);
		-webkit-backdrop-filter: blur(2px);
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
		border-radius: 18px;
		border: 1px solid rgba(180, 218, 244, 0.95);
		background: linear-gradient(
			155deg,
			rgba(255, 255, 255, 0.96) 0%,
			rgba(231, 248, 239, 0.95) 100%
		);
		box-shadow:
			0 16px 34px rgba(10, 60, 99, 0.22),
			inset 0 1px 0 rgba(255, 255, 255, 0.8);
		text-align: center;
		padding: 2rem 1.25rem 1.5rem;
		transform: translateY(14px) scale(0.92);
		opacity: 0;
	}

	:global([data-theme='dark']) .project-conclude-celebration__card {
		border-color: var(--ds-color-border-strong);
		background: linear-gradient(155deg, var(--ds-color-surface-raised) 0%, var(--ds-color-surface-base) 100%);
		box-shadow:
			0 16px 34px rgba(0, 0, 0, 0.55),
			inset 0 1px 0 rgba(255, 255, 255, 0.06);
	}

	.project-conclude-celebration.is-active .project-conclude-celebration__card {
		animation: concludeCelebrationCardIn 0.34s cubic-bezier(0.2, 0.9, 0.2, 1) forwards;
	}

	.project-conclude-celebration__check {
		width: 66px;
		height: 66px;
		border-radius: 50%;
		margin: 0 auto;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		background: linear-gradient(135deg, #2cb67d 0%, #1f9d68 100%);
		color: #ffffff;
		box-shadow: 0 10px 24px rgba(44, 182, 125, 0.35);
		font-size: 1.55rem;
		position: relative;
		z-index: 2;
	}

	.project-conclude-celebration.is-active .project-conclude-celebration__check {
		animation: concludeCheckPop 0.46s ease-out 0.08s both;
	}

	.project-conclude-celebration__ring {
		width: 96px;
		height: 96px;
		border-radius: 50%;
		border: 2px solid rgba(44, 182, 125, 0.5);
		position: absolute;
		left: 50%;
		top: 1.25rem;
		transform: translateX(-50%) scale(0.6);
		opacity: 0;
		z-index: 1;
	}

	.project-conclude-celebration.is-active .project-conclude-celebration__ring {
		animation: concludeRingPulse 0.85s ease-out 0.02s forwards;
	}

	.project-conclude-celebration__title {
		margin: 1rem 0 0.35rem;
		color: var(--ds-color-text-primary);
		font-size: 1.25rem;
		font-weight: 700;
		line-height: 1.3;
	}

	.project-conclude-celebration__message {
		margin: 0;
		color: var(--ds-color-text-secondary);
		font-size: 1rem;
		line-height: 1.5;
	}

	.project-conclude-celebration__particles {
		position: absolute;
		inset: 0;
		pointer-events: none;
	}

	.project-conclude-celebration__particles span {
		position: absolute;
		width: 8px;
		height: 8px;
		border-radius: 50%;
		opacity: 0;
		transform: scale(0.4);
	}

	.project-conclude-celebration__particles span:nth-child(1) {
		top: 26%;
		left: 18%;
		background: #ffd166;
	}

	.project-conclude-celebration__particles span:nth-child(2) {
		top: 20%;
		right: 20%;
		background: #ef476f;
	}

	.project-conclude-celebration__particles span:nth-child(3) {
		top: 46%;
		left: 12%;
		background: #118ab2;
	}

	.project-conclude-celebration__particles span:nth-child(4) {
		top: 52%;
		right: 14%;
		background: #06d6a0;
	}

	.project-conclude-celebration__particles span:nth-child(5) {
		bottom: 26%;
		left: 28%;
		background: #f77f00;
	}

	.project-conclude-celebration__particles span:nth-child(6) {
		bottom: 20%;
		right: 28%;
		background: #2a9d8f;
	}

	.project-conclude-celebration.is-active .project-conclude-celebration__particles span {
		animation: concludeParticleBurst 0.8s ease-out 0.14s forwards;
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

	@keyframes concludeCheckPop {
		0% {
			transform: scale(0.6);
		}
		70% {
			transform: scale(1.08);
		}
		100% {
			transform: scale(1);
		}
	}

	@keyframes concludeRingPulse {
		0% {
			transform: translateX(-50%) scale(0.6);
			opacity: 0.5;
		}
		100% {
			transform: translateX(-50%) scale(1.2);
			opacity: 0;
		}
	}

	@keyframes concludeParticleBurst {
		0% {
			opacity: 0;
			transform: scale(0.45) translateY(0);
		}
		20% {
			opacity: 1;
		}
		100% {
			opacity: 0;
			transform: scale(1.4) translateY(-10px);
		}
	}

	@media (prefers-reduced-motion: reduce) {
		.project-conclude-celebration,
		.project-conclude-celebration__card {
			transition-duration: 0.08s;
		}

		.project-conclude-celebration.is-active .project-conclude-celebration__card,
		.project-conclude-celebration.is-active .project-conclude-celebration__check,
		.project-conclude-celebration.is-active .project-conclude-celebration__ring,
		.project-conclude-celebration.is-active .project-conclude-celebration__particles span {
			animation: none !important;
		}

		.project-conclude-celebration__card {
			transform: translateY(0) scale(1);
			opacity: 1;
		}
	}
</style>
