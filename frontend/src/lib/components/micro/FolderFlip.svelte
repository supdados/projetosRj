<script lang="ts">
	/**
	 * Micro-interacao do KPI "Vigentes": pilha de 3 pastas AMARELAS (FolderShape),
	 * vista levemente de cima. No hover (proprio OU de um ancestral `.group`, ex.:
	 * o cartao de KPI), cada PASTA INTEIRA inclina para frente (rotateX, dobradica
	 * na base) — o MESMO movimento de inclinacao do flap da pasta de "Todos os
	 * projetos" — em sequencia (frente -> tras) e MANTENDO a pose. Retorno suave ao
	 * tirar o mouse. Decorativo (`aria-hidden`).
	 *
	 * Por que CSS `transition` (e nao `@keyframes`): transition vai do estado atual
	 * ao alvo e SEGURA a pose enquanto o hover durar; ao sair, volta suave sozinha.
	 * Keyframes tem timeline fixa que reverte/reinicia -> e o "cai-e-volta" antigo.
	 * Respeita `prefers-reduced-motion`.
	 */
	import FolderShape from './FolderShape.svelte';

	interface Props {
		/** Largura de cada pasta em px (altura derivada em FolderShape). */
		size?: number;
	}

	let { size = 46 }: Props = $props();

	// 0 = frente (vem primeiro), 2 = fundo (por ultimo). Tons de amarelo bem
	// distintos: frente = MEIO TERMO, meio = MAIS CLARO, fundo = MAIS ESCURO.
	const layers = [
		{ accent: '#f3bf42', accentDark: '#d9a226', accentLight: '#ffd86b' }, // frente: medio
		{ accent: '#ffe08a', accentDark: '#f0c44e', accentLight: '#fff2c4' }, // meio: claro
		{ accent: '#c98a1a', accentDark: '#a66f10', accentLight: '#e0a838' } // fundo: escuro
	];
</script>

<span class="ff-root" style="--ff-size: {size}px;" aria-hidden="true">
	<span class="ff-stage">
		{#each layers as layer, i (i)}
			<!-- Wrapper carrega o rotateX (vista de cima) + o afastar; a FolderShape
			     so desenha. O rotateX base e IGUAL em repouso e hover = "nao caiu". -->
			<span class="ff-folder ff-folder--{i}" style="--i: {i};">
				<FolderShape
					{size}
					accent={layer.accent}
					accentDark={layer.accentDark}
					accentLight={layer.accentLight}
				/>
			</span>
		{/each}
	</span>
</span>

<style>
	.ff-root {
		display: inline-flex;
		position: relative;
		/* A pilha ocupa um pouco mais que uma pasta por causa do empilhamento/afastar. */
		width: var(--ff-size);
		height: calc(var(--ff-size) * 1.05);
		flex-shrink: 0;
	}

	/* perspective + preserve-3d no CONTAINER => cena 3D coerente, mesmo ponto de
	   fuga para as 3 pastas. perspective-origin alto = camera "de cima". */
	.ff-stage {
		position: relative;
		width: 100%;
		height: 100%;
		perspective: 720px;
		perspective-origin: 50% 18%;
		transform-style: preserve-3d;
	}

	/* Anti hover-flicker: as pastas inclinam para frente no hover; se uma delas
	   capturasse o cursor poderia sair de baixo do mouse ao inclinar e disparar
	   mouseleave->reverte->mouseenter em LOOP. O hover vem da caixa estavel `.ff-root`
	   (que nao se move) e do `.group` ancestral. Ref: dev.to/annlin/css-flicker-on-hover. */
	.ff-stage,
	.ff-stage * {
		pointer-events: none;
	}

	.ff-folder {
		position: absolute;
		left: 0;
		bottom: 0;
		width: 100%;
		/* Dobradica na BASE: reclina/afasta a partir do pe, base plantada. */
		transform-origin: 50% 100%;
		/* Base = leave RAPIDO (0.22s) e SEM delay: ao tirar o mouse as 3 pastas voltam
		   juntas e na hora — nunca reproduzem a cascata ao contrario (anti-flicker). O
		   enter lento + a curva de "assentar" + os delays escalonados ficam no :hover.
		   transition no base => interrompivel; so transform => 60fps, sem reflow. */
		transition: transform 0.22s ease;
		will-change: transform;
		backface-visibility: hidden;
	}

	/* REPOUSO = pilha COLAPSADA com a pasta NA MESMA POSICAO da de "Todos os
	   projetos" (de frente, sem inclinacao: rotateX 0). As de tras ficam um pouco
	   mais altas/ao fundo (espreitando). A inclinacao "de cima" e so na animacao. */
	.ff-folder--0 {
		transform: rotateX(0deg) translateZ(0px) translateY(0px);
		z-index: 3;
	}
	.ff-folder--1 {
		transform: rotateX(0deg) translateZ(-20px) translateY(-7px);
		z-index: 2;
	}
	.ff-folder--2 {
		transform: rotateX(0deg) translateZ(-40px) translateY(-14px);
		z-index: 1;
	}

	/* HOVER (proprio OU cartao `.group` ancestral): cada PASTA INTEIRA VEM PARA
	   FRENTE — inclina para frente (rotateX negativo) e avanca em direcao a camera
	   (translateZ/Y) — separando-se da pilha, uma de cada vez, como se estivessem
	   sendo folheadas. A da frente vem mais; as de tras, progressivamente menos.
	   Sequencial por transition-delay; mantem a pose ate o mouse sair. */
	.ff-root:is(:hover, :focus-within) .ff-folder--0,
	:global(.group:hover) .ff-folder--0,
	:global(.group:focus-within) .ff-folder--0 {
		transform: rotateX(-34deg) translateZ(20px) translateY(0px);
		/* enter lento + curva de "assentar" (so no estado ativo). */
		transition: transform 0.42s cubic-bezier(0.34, 1.2, 0.64, 1);
	}
	.ff-root:is(:hover, :focus-within) .ff-folder--1,
	:global(.group:hover) .ff-folder--1,
	:global(.group:focus-within) .ff-folder--1 {
		transform: rotateX(-28deg) translateZ(8px) translateY(-8px);
		transition: transform 0.42s cubic-bezier(0.34, 1.2, 0.64, 1);
		transition-delay: 120ms;
	}
	.ff-root:is(:hover, :focus-within) .ff-folder--2,
	:global(.group:hover) .ff-folder--2,
	:global(.group:focus-within) .ff-folder--2 {
		transform: rotateX(-22deg) translateZ(-4px) translateY(-16px);
		transition: transform 0.42s cubic-bezier(0.34, 1.2, 0.64, 1);
		transition-delay: 240ms;
	}

	@media (prefers-reduced-motion: reduce) {
		.ff-folder {
			transition: none;
		}
	}
</style>
