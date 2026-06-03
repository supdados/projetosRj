<script lang="ts">
	/**
	 * Micro-interacao "Projetos concluidos": uma prancheta com uma FOTO de projeto
	 * presa por um clipe. No hover a prancheta se levanta/inclina e uma imagem de
	 * carimbo "OK" (verde, desenhada a mao) e estampada por cima com fade + leve
	 * assentamento de escala.
	 *
	 * Gatilho: hover/foco proprio OU de um ancestral `.group` (o cartao de KPI).
	 * Decorativo (`aria-hidden`); respeita `prefers-reduced-motion`.
	 */
	interface Props {
		/** Altura da prancheta em px (largura segue a proporcao). */
		size?: number;
		/** Screenshot do projeto preso na prancheta (webp/png servido pelo Flask). */
		image?: string;
		/** Imagem do carimbo "OK" (PNG/webp com transparencia). */
		stamp?: string;
	}
	let {
		size = 46,
		image = '/static/img/dashboard/folder/1.webp',
		stamp = '/static/img/dashboard/ok.webp'
	}: Props = $props();
</script>

<span class="cs-root" style="--cs-size: {size}px" aria-hidden="true">
	<span class="cs-board">
		<img class="cs-photo" src={image} alt="" loading="lazy" decoding="async" />
		<!-- Carimbo "OK" (imagem desenhada a mao, fundo transparente). -->
		<img class="cs-stamp" src={stamp} alt="" loading="lazy" decoding="async" />
		<span class="cs-clip"></span>
	</span>
</span>

<style>
	.cs-root {
		display: inline-flex;
		width: calc(var(--cs-size) * 0.86);
		height: var(--cs-size);
		flex-shrink: 0;
		/* perspectiva para a leve inclinacao 3D ao levantar. */
		perspective: 240px;
	}

	/* Anti hover-flicker: a prancheta e o carimbo se movem no hover; nenhum deles
	   pode capturar o cursor, senao ao levantar saem de baixo do mouse e disparam
	   mouseleave->reverte->mouseenter em LOOP. O `:hover` fica na caixa estavel
	   `.cs-root` (que nao se move). Ref: dev.to/annlin/css-flicker-on-hover. */
	.cs-board,
	.cs-board * {
		pointer-events: none;
	}

	/* Prancheta (board + papel). Levanta e inclina de leve no hover. */
	.cs-board {
		position: relative;
		width: 100%;
		height: 100%;
		border-radius: calc(var(--cs-size) * 0.1);
		background: #fff;
		border: 1px solid rgba(148, 163, 184, 0.5);
		box-shadow: 0 3px 8px rgba(15, 42, 71, 0.16);
		padding: calc(var(--cs-size) * 0.085);
		transform-origin: bottom center;
		/* Base = leave RAPIDO (0.2s, sem delay): solta na hora ao sair. O enter lento
		   fica no estado ativo. transition no base => reversivel em qualquer ponto. */
		transition:
			transform 0.2s ease,
			box-shadow 0.2s ease;
		will-change: transform;
		backface-visibility: hidden;
	}

	.cs-photo {
		width: 100%;
		height: 100%;
		object-fit: cover;
		object-position: top center;
		border-radius: calc(var(--cs-size) * 0.055);
		display: block;
	}

	/* Clipe metalico no topo, sobreposto a borda da prancheta. */
	.cs-clip {
		position: absolute;
		top: calc(var(--cs-size) * -0.05);
		left: 50%;
		transform: translateX(-50%);
		width: 42%;
		height: calc(var(--cs-size) * 0.13);
		border-radius: calc(var(--cs-size) * 0.07);
		background: linear-gradient(180deg, #cdd6e0 0%, #9aa7b4 100%);
		box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.7);
	}

	/* Carimbo "OK" (imagem): mais para cima/direita. Escondido no repouso; entra
	   com fade + leve assentamento de escala. opacity e transform tem a MESMA
	   duracao/atraso para terminarem juntos (sem "termina e desce" no fim). */
	.cs-stamp {
		position: absolute;
		top: 32%;
		left: 66%;
		width: 58%;
		aspect-ratio: 1;
		object-fit: contain;
		display: block;
		opacity: 0;
		transform: translate(-50%, -50%) rotate(-8deg) scale(1.25);
		/* Base = leave RAPIDO e SEM delay: o carimbo some na hora ao sair, nunca fica
		   esperando o delay de entrada (que so existe no estado ativo). */
		transition:
			opacity 0.16s ease,
			transform 0.16s ease;
		transition-delay: 0s;
		will-change: transform, opacity;
		backface-visibility: hidden;
	}

	/* ----- Estado ATIVO (hover/foco proprio OU do cartao `.group`) ----- */
	.cs-root:is(:hover, :focus-within) .cs-board,
	:global(.group:hover) .cs-board,
	:global(.group:focus-within) .cs-board {
		transform: translateY(-3px) rotateX(8deg) rotate(-2deg);
		box-shadow: 0 10px 18px rgba(15, 42, 71, 0.24);
		/* enter mais lento/suave (so no estado ativo). */
		transition:
			transform 0.38s cubic-bezier(0.22, 1, 0.36, 1),
			box-shadow 0.38s ease;
	}
	.cs-root:is(:hover, :focus-within) .cs-stamp,
	:global(.group:hover) .cs-stamp,
	:global(.group:focus-within) .cs-stamp {
		opacity: 1;
		transform: translate(-50%, -50%) rotate(-8deg) scale(1);
		/* enter lento + mesmo atraso p/ opacity e transform: entram e assentam juntos.
		   Delay so aqui (ativo) => leave nao espera (sem flicker). */
		transition:
			opacity 0.3s ease-out,
			transform 0.3s cubic-bezier(0.2, 0.8, 0.3, 1);
		transition-delay: 0.1s;
	}

	@media (prefers-reduced-motion: reduce) {
		.cs-board,
		.cs-stamp {
			transition: none;
		}
		.cs-stamp {
			transform: translate(-50%, -50%) rotate(-8deg) scale(1);
		}
	}
</style>
