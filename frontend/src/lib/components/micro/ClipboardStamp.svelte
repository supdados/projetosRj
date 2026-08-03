<script lang="ts">
	/**
	 * Micro-interacao do KPI "Concluidos": prancheta com um termo de encerramento.
	 * No hover (proprio OU do cartao `.group` ancestral) a prancheta se levanta, um
	 * carimbo de madeira desce de cima, bate no papel (que da uma leve squash) e
	 * deixa um LACRE DE CERA verde; o carimbo recua e sai, o lacre permanece
	 * enquanto o hover durar. Ao sair, tudo volta ao repouso.
	 *
	 * Decorativa (`aria-hidden`); rotulo acessivel fica no link do StatCard.
	 *
	 * Estagios (timers): 0 repouso · 1 prancheta sobe + carimbo em posicao ·
	 * 2 impacto (cera aparece) · 3 recuo · 4 carimbo sai (lacre fica).
	 */
	import { onMount } from 'svelte';

	interface Props {
		/** Altura da prancheta em px (largura segue a proporcao). */
		size?: number;
	}

	let { size = 52 }: Props = $props();
	const uid = $props.id();

	/** Contornos irregulares de cera derretida; um e sorteado a cada hover. */
	const WAX_BLOBS: readonly string[] = [
		'M133.0 83.7C133.3 93.0 137.9 102.4 134.0 109.9C130.1 117.5 116.7 128.7 107.1 134.1C97.5 139.6 80.3 148.0 69.8 146.0C59.3 144.0 44.6 129.0 36.9 120.9C29.2 112.8 20.0 100.1 18.8 92.1C17.6 84.0 24.9 74.8 28.8 67.5C32.8 60.1 38.4 50.1 45.3 43.3C52.1 36.6 66.9 24.4 74.8 22.7C82.6 20.9 89.0 27.8 97.5 31.7C106.0 35.5 126.1 40.6 131.5 48.4C136.8 56.2 132.6 74.5 133.0 83.7Z',
		'M146.1 75.6C145.6 84.6 130.7 96.6 125.3 105.1C120.0 113.7 118.8 126.9 110.5 132.5C102.2 138.1 80.4 144.2 70.3 142.5C60.3 140.7 50.0 127.8 43.5 120.7C37.0 113.7 29.8 105.2 26.9 95.6C23.9 86.0 21.9 65.4 23.7 56.8C25.5 48.1 31.2 43.0 38.8 37.7C46.3 32.4 64.0 23.1 74.3 21.5C84.7 19.8 99.5 23.0 107.7 26.6C115.9 30.1 123.0 37.7 128.8 45.1C134.6 52.4 146.6 66.6 146.1 75.6Z',
		'M140.8 83.8C140.6 92.2 131.4 100.9 125.9 107.7C120.4 114.5 112.5 125.4 104.2 129.1C95.9 132.9 79.3 134.4 70.6 132.8C61.9 131.3 53.2 124.8 46.1 118.9C39.0 112.9 25.3 101.4 23.2 93.1C21.1 84.8 29.7 71.6 32.0 63.5C34.3 55.4 31.9 45.7 38.3 39.2C44.7 32.7 64.3 21.3 74.8 20.1C85.4 18.9 100.6 26.7 108.5 31.4C116.3 36.1 122.2 43.6 127.0 51.5C131.9 59.3 141.0 75.4 140.8 83.8Z',
		'M141.3 76.5C143.0 84.9 142.5 101.4 137.2 108.7C131.9 116.0 116.2 121.0 106.0 125.2C95.8 129.5 79.9 136.8 69.3 136.9C58.6 137.0 41.2 131.8 35.0 125.9C28.9 120.1 29.7 107.7 28.1 97.6C26.5 87.6 23.3 68.4 24.4 58.9C25.5 49.3 27.6 39.5 35.5 34.0C43.4 28.5 67.2 24.6 77.0 22.2C86.9 19.9 93.8 13.8 101.2 18.3C108.5 22.8 120.0 43.8 126.0 52.5C132.0 61.2 139.6 68.1 141.3 76.5Z'
	];

	let stage = $state(0);
	let waxIndex = $state(0);
	let root: HTMLSpanElement;

	const waxBlob = $derived(WAX_BLOBS[waxIndex]);
	const dropX = $derived(118 + (waxIndex % 3) * 9);
	const dropY = $derived(126 + (waxIndex % 4) * 5);
	const dropR = $derived(3.4 + (waxIndex % 3) * 0.9);

	let timers: ReturnType<typeof setTimeout>[] = [];

	function clearTimers(): void {
		timers.forEach(clearTimeout);
		timers = [];
	}

	function prefersReducedMotion(): boolean {
		return typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches;
	}

	function enter(): void {
		clearTimers();
		waxIndex = Math.floor(Math.random() * WAX_BLOBS.length);
		// Sem movimento: pula direto ao estado final (lacre posto, carimbo fora).
		if (prefersReducedMotion()) {
			stage = 4;
			return;
		}
		stage = 1;
		const seq: [number, number][] = [
			[265, 2],
			[390, 3],
			[700, 4]
		];
		for (const [at, next] of seq) timers.push(setTimeout(() => (stage = next), at));
	}

	function leave(): void {
		clearTimers();
		stage = 0;
	}

	// Hover e foco coexistem no mesmo alvo: so transicionar nas bordas
	// inativo<->ativo, senao um focusin em pleno hover reinicia a sequencia.
	let hovered = false;
	let focused = false;

	function syncActive(): void {
		const active = hovered || focused;
		if (active && stage === 0) enter();
		if (!active && stage !== 0) leave();
	}

	onMount(() => {
		// UM unico alvo: escutar root E .group faria a borda interna disparar
		// enter/leave extras (pingue-pongue).
		const target: Element = root.closest('.group') ?? root;
		const hoverOn = (): void => {
			hovered = true;
			syncActive();
		};
		const hoverOff = (): void => {
			hovered = false;
			syncActive();
		};
		const focusOn = (): void => {
			focused = true;
			syncActive();
		};
		const focusOff = (event: Event): void => {
			const next = (event as FocusEvent).relatedTarget;
			if (next instanceof Node && target.contains(next)) return;
			focused = false;
			syncActive();
		};
		target.addEventListener('mouseenter', hoverOn);
		target.addEventListener('mouseleave', hoverOff);
		target.addEventListener('focusin', focusOn);
		target.addEventListener('focusout', focusOff);
		return () => {
			target.removeEventListener('mouseenter', hoverOn);
			target.removeEventListener('mouseleave', hoverOff);
			target.removeEventListener('focusin', focusOn);
			target.removeEventListener('focusout', focusOff);
			clearTimers();
		};
	});
</script>

<span class="cs-root" bind:this={root} style="--cs-size: {size}px" aria-hidden="true">
	<span class="cs-stage" data-stage={stage}>
		<span class="cs-board">
			<span class="cs-sheet cs-sheet--a"></span>
			<span class="cs-sheet cs-sheet--b"></span>

			<span class="cs-paper">
				<span class="cs-doc">
					<span class="cs-doc-line cs-doc-line--title"></span>
					<span class="cs-doc-line"></span>
					<span class="cs-doc-line"></span>
					<span class="cs-doc-line cs-doc-line--short"></span>
					<span class="cs-doc-line cs-doc-line--tiny"></span>
				</span>

				<span class="cs-wax">
					<span class="cs-wax-pulse">
						<svg viewBox="0 0 160 160" fill="none">
							<defs>
								<radialGradient id="cst-wax-body-{uid}" cx="34%" cy="28%" r="82%">
									<stop class="cs-stop-wax-lit" offset="0%" />
									<stop class="cs-stop-wax-mid" offset="52%" />
									<stop class="cs-stop-wax-deep" offset="100%" />
								</radialGradient>
								<radialGradient id="cst-wax-dish-{uid}" cx="42%" cy="34%" r="78%">
									<stop class="cs-stop-dish-lit" offset="0%" />
									<stop class="cs-stop-dish-deep" offset="100%" />
								</radialGradient>
							</defs>
							<path d={waxBlob} fill="url(#cst-wax-body-{uid})" />
							<circle cx={dropX} cy={dropY} r={dropR} fill="url(#cst-wax-body-{uid})" />
							<circle cx="80" cy="80" r="47" fill="url(#cst-wax-dish-{uid})" />
							<circle class="cs-wax-ink" cx="80" cy="80" r="47" fill="none" stroke-opacity=".42" stroke-width="3" />
							<!-- Relevo escuro por baixo + traco claro por cima: legivel sobre a cera. -->
							<g class="cs-wax-ink" stroke-opacity=".5" stroke-width="13" fill="none" transform="translate(0,3)">
								<ellipse cx="56" cy="80" rx="16" ry="20" />
								<path d="M90 58v44M90 80l23-19M90 80l24 21" stroke-linecap="square" />
							</g>
							<g class="cs-wax-glyph" stroke-width="13" fill="none">
								<ellipse cx="56" cy="80" rx="16" ry="20" />
								<path d="M90 58v44M90 80l23-19M90 80l24 21" stroke-linecap="square" />
							</g>
							<path d="M44 46q14-18 34-20-22 10-30 24z" fill="rgba(255,255,255,.20)" />
						</svg>
					</span>
				</span>
			</span>

			<span class="cs-clip"></span>
			<span class="cs-clip-ring"></span>
		</span>

		<!-- Carimbo de madeira: desce de fora do box, bate e sai. -->
		<span class="cs-stamp">
			<svg viewBox="0 0 120 220" fill="none">
				<defs>
					<linearGradient id="cst-wood-{uid}" x1="0" y1="0" x2="1" y2="0">
						<stop offset="0%" stop-color="#3a1f0d" />
						<stop offset="18%" stop-color="#7d4520" />
						<stop offset="40%" stop-color="#b8743f" />
						<stop offset="58%" stop-color="#94512a" />
						<stop offset="82%" stop-color="#563014" />
						<stop offset="100%" stop-color="#2e1a08" />
					</linearGradient>
					<linearGradient id="cst-brass-{uid}" x1="0" y1="0" x2="1" y2="0">
						<stop offset="0%" stop-color="#6b5622" />
						<stop offset="22%" stop-color="#c2a44b" />
						<stop offset="42%" stop-color="#ecdca4" />
						<stop offset="64%" stop-color="#b2913c" />
						<stop offset="88%" stop-color="#7d6528" />
						<stop offset="100%" stop-color="#57451a" />
					</linearGradient>
				</defs>
				<path
					d="M60 8C74 8 84 24 84 46C84 70 74 86 71 108C69 126 66 140 68 152C70 166 82 172 83 180L37 180C38 172 50 166 52 152C54 140 51 126 49 108C46 86 36 70 36 46C36 24 46 8 60 8Z"
					fill="url(#cst-wood-{uid})"
				/>
				<path
					d="M56 20C50 34 50 58 54 78C58 98 60 120 58 140"
					stroke="rgba(255,226,180,.16)"
					stroke-width="3"
					stroke-linecap="round"
				/>
				<rect x="36" y="178" width="48" height="12" rx="3" fill="url(#cst-brass-{uid})" />
				<path d="M34 190h52l6 12H28z" fill="url(#cst-brass-{uid})" />
				<rect x="16" y="200" width="88" height="14" rx="4" fill="url(#cst-brass-{uid})" />
				<ellipse cx="60" cy="213" rx="44" ry="5" fill="rgba(40,30,8,.35)" />
			</svg>
		</span>
	</span>
</span>

<style>
	.cs-root {
		display: inline-flex;
		position: relative;
		width: calc(var(--cs-size) * 0.86);
		height: var(--cs-size);
		flex-shrink: 0;
	}

	/* Anti hover-flicker: a raiz avalia o hover e NAO se move; nada que anima pode
	   capturar o cursor. Ref: dev.to/annlin/css-flicker-on-hover. */
	.cs-stage,
	.cs-stage * {
		pointer-events: none;
	}

	.cs-stage {
		position: relative;
		width: 100%;
		height: 100%;
		perspective: calc(var(--cs-size) * 3);
	}

	.cs-board {
		position: absolute;
		inset: 0;
		border-radius: calc(var(--cs-size) * 0.1);
		background: linear-gradient(160deg, var(--ds-color-neutral-100) 0%, var(--ds-color-neutral-300) 100%);
		border: 1px solid var(--ds-color-border-base);
		box-shadow: 0 3px 8px rgba(15, 42, 71, 0.16);
		transform-origin: bottom center;
		/* Base = leave RAPIDO e sem delay: reversivel em qualquer ponto. */
		transition:
			transform 0.2s ease,
			box-shadow 0.2s ease;
		will-change: transform;
		backface-visibility: hidden;
	}

	/* Folhas de tras: dao espessura ao maco preso na prancheta. */
	.cs-sheet,
	.cs-paper {
		position: absolute;
		left: 5.4%;
		right: 5.4%;
		bottom: 4.1%;
		border-radius: calc(var(--cs-size) * 0.055);
	}
	.cs-sheet--a {
		top: 7.2%;
		background: var(--ds-color-neutral-100);
		transform: rotate(-1.1deg);
	}
	.cs-sheet--b {
		top: 6.7%;
		background: var(--ds-color-neutral-50);
		transform: rotate(0.6deg);
	}

	.cs-paper {
		top: 6.2%;
		background: var(--ds-color-surface-raised);
		box-shadow: 0 2px 6px rgba(35, 50, 45, 0.12);
		overflow: hidden;
		transform: scale(1);
		transition: transform 0.22s cubic-bezier(0.3, 1.6, 0.5, 1);
		will-change: transform;
		backface-visibility: hidden;
	}

	/* Texto falso: a 52px qualquer glifo seria ilegivel, entao so linhas. */
	.cs-doc {
		position: absolute;
		inset: 13% 12% auto 12%;
		display: flex;
		flex-direction: column;
		gap: calc(var(--cs-size) * 0.055);
	}
	.cs-doc-line {
		height: calc(var(--cs-size) * 0.032);
		border-radius: 99px;
		background: var(--ds-color-neutral-200);
	}
	.cs-doc-line--title {
		width: 66%;
		background: var(--ds-color-success-600);
	}
	.cs-doc-line--short {
		width: 74%;
	}
	.cs-doc-line--tiny {
		width: 46%;
	}

	/* Clipe metalico + argola, sobrepostos a borda superior da prancheta. */
	.cs-clip {
		position: absolute;
		top: calc(var(--cs-size) * -0.036);
		left: 50%;
		width: 33%;
		height: calc(var(--cs-size) * 0.088);
		margin-left: -16.5%;
		border-radius: calc(var(--cs-size) * 0.03) calc(var(--cs-size) * 0.03) calc(var(--cs-size) * 0.02)
			calc(var(--cs-size) * 0.02);
		background: linear-gradient(150deg, var(--ds-color-neutral-200), var(--ds-color-neutral-400));
		box-shadow: 0 2px 5px rgba(35, 50, 45, 0.22);
	}
	.cs-clip-ring {
		position: absolute;
		top: calc(var(--cs-size) * -0.057);
		left: 50%;
		width: 15.5%;
		height: calc(var(--cs-size) * 0.031);
		margin-left: -7.75%;
		border: calc(var(--cs-size) * 0.016) solid var(--ds-color-neutral-300);
		border-bottom: none;
		border-radius: calc(var(--cs-size) * 0.02) calc(var(--cs-size) * 0.02) 0 0;
	}

	/* Lacre de cera: entra no impacto e SEGURA a pose ate o fim do hover. */
	.cs-wax {
		position: absolute;
		left: 66%;
		top: 32%;
		width: calc(var(--cs-size) * 0.5);
		height: calc(var(--cs-size) * 0.5);
		margin-left: calc(var(--cs-size) * -0.25);
		margin-top: calc(var(--cs-size) * -0.25);
		opacity: 0;
		transition: opacity 0.16s ease;
	}
	.cs-wax-pulse,
	.cs-wax svg {
		display: block;
		width: 100%;
		height: 100%;
	}
	.cs-wax-pulse {
		will-change: transform, opacity;
		backface-visibility: hidden;
	}
	.cs-wax svg {
		filter: drop-shadow(0 1px 2px color-mix(in srgb, var(--ds-color-success-900) 34%, transparent));
	}
	.cs-wax-ink {
		stroke: var(--ds-color-success-900);
	}
	.cs-wax-glyph {
		stroke: var(--ds-color-success-100);
	}
	.cs-stop-wax-lit {
		stop-color: var(--ds-color-success-400);
	}
	.cs-stop-wax-mid {
		stop-color: var(--ds-color-success-600);
	}
	.cs-stop-wax-deep {
		stop-color: var(--ds-color-success-800);
	}
	.cs-stop-dish-lit {
		stop-color: var(--ds-color-success-500);
	}
	.cs-stop-dish-deep {
		stop-color: var(--ds-color-success-700);
	}

	/* Excecao ao "so transition": o squash-and-settle da cera e uma timeline que
	   roda UMA vez e cujo estado final permanece (doc, secao 4). */
	@keyframes cs-wax-settle {
		0% {
			transform: scale(0.62);
			opacity: 0;
		}
		30% {
			opacity: 1;
		}
		46% {
			transform: scale(1.13, 0.9);
		}
		72% {
			transform: scale(0.985, 1.035);
		}
		100% {
			transform: scale(1);
			opacity: 1;
		}
	}

	.cs-stamp {
		position: absolute;
		/* Mesmo eixo do lacre: 5.4% + 0.892 x 66% do papel. */
		left: 64.3%;
		top: 0;
		width: calc(var(--cs-size) * 0.38);
		z-index: 10;
		opacity: 0;
		transform: translate(-50%, calc(var(--cs-size) * -1.02)) rotate(-6deg) scale(0.94);
		transition:
			transform 0.24s ease-in,
			opacity 0.2s ease;
		will-change: transform, opacity;
		backface-visibility: hidden;
	}
	.cs-stamp svg {
		display: block;
		width: 100%;
		height: auto;
		filter: drop-shadow(0 2px 4px rgba(16, 28, 22, 0.3));
	}

	/* ----- Estagios ----- */
	.cs-stage:not([data-stage='0']) .cs-board {
		transform: translateY(calc(var(--cs-size) * -0.05)) rotateX(3deg);
		box-shadow: 0 10px 18px rgba(15, 42, 71, 0.24);
		transition:
			transform 0.43s cubic-bezier(0.22, 1, 0.36, 1),
			box-shadow 0.43s ease;
	}

	.cs-stage[data-stage='2'] .cs-paper {
		transform: scale(0.96) translateY(2%);
	}

	.cs-stage[data-stage='2'] .cs-wax,
	.cs-stage[data-stage='3'] .cs-wax,
	.cs-stage[data-stage='4'] .cs-wax {
		opacity: 1;
	}
	/* Tambem em 3/4: a timeline (0.5s) atravessa a troca de estagio em 500ms;
	   valor computado identico nao reinicia, so deixa completar e o both segura. */
	.cs-stage[data-stage='2'] .cs-wax-pulse,
	.cs-stage[data-stage='3'] .cs-wax-pulse,
	.cs-stage[data-stage='4'] .cs-wax-pulse {
		animation: cs-wax-settle 0.4s cubic-bezier(0.25, 0.9, 0.3, 1) both;
	}

	.cs-stage[data-stage='1'] .cs-stamp {
		opacity: 1;
		transform: translate(-50%, calc(var(--cs-size) * -0.42)) rotate(-2deg) scale(0.98);
		transition:
			transform 0.26s cubic-bezier(0.3, 0.7, 0.4, 1),
			opacity 0.16s ease;
	}
	.cs-stage[data-stage='2'] .cs-stamp {
		opacity: 1;
		transform: translate(-50%, calc(var(--cs-size) * -0.27)) rotate(0deg) scale(1);
		transition:
			transform 0.1s cubic-bezier(0.6, 0, 0.9, 0.5),
			opacity 0.16s ease;
	}
	.cs-stage[data-stage='3'] .cs-stamp {
		opacity: 1;
		transform: translate(-50%, calc(var(--cs-size) * -0.58)) rotate(2deg) scale(0.97);
		transition:
			transform 0.3s cubic-bezier(0.2, 0.9, 0.3, 1),
			opacity 0.24s ease;
	}
	.cs-stage[data-stage='4'] .cs-stamp {
		transition:
			transform 0.32s ease-in,
			opacity 0.28s ease;
	}

	:global([data-theme='dark']) .cs-board {
		box-shadow: 0 3px 8px rgba(0, 0, 0, 0.45);
	}
	:global([data-theme='dark']) .cs-stage:not([data-stage='0']) .cs-board {
		box-shadow: 0 10px 22px rgba(0, 0, 0, 0.6);
	}
	:global([data-theme='dark']) .cs-paper {
		box-shadow: 0 2px 6px rgba(0, 0, 0, 0.5);
	}

	/* Movimento reduzido: sem sequencia — o hover so revela o lacre (estagio 4). */
	@media (prefers-reduced-motion: reduce) {
		.cs-board,
		.cs-paper,
		.cs-stamp {
			transition: none;
		}
		.cs-stage:not([data-stage='0']) .cs-board {
			transform: none;
		}
		/* Mesma especificidade das regras de estagio; vence por vir depois. */
		.cs-stage[data-stage] .cs-wax-pulse {
			animation: none;
		}
	}
</style>
