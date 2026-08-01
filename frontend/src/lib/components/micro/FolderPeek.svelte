<script lang="ts">
	/**
	 * Micro-interacao do KPI "Vigentes": pasta-arquivo amarela vertical (estilo
	 * "Mini Archive") desenhada em SVG — capa, corpo traseiro com lombada e
	 * indices. No hover (proprio OU do cartao `.group` ancestral) a CAPA ABRE em
	 * 3D (rotateY, dobradica na esquerda) e OITO folhas escapam de dentro, cada
	 * uma numa direcao/angulo/tempo diferente — pasta abarrotada. viewBox
	 * cropado nos limites da arte; proporcao ~0.87 (mesma do ClipboardStamp).
	 *
	 * Decorativa (`aria-hidden`); rotulo acessivel fica no link do StatCard.
	 *
	 * Por que CSS `transition` (e nao `@keyframes`): transition vai do estado
	 * atual ao alvo e SEGURA a pose enquanto o hover durar; ao sair, volta suave
	 * e imediata (sem cascata reversa). Respeita `prefers-reduced-motion`.
	 */
	interface Props {
		/** Altura da pasta em px (largura = size * 0.867; pasta preenche o palco). */
		size?: number;
		/**
		 * Ate 2 URLs de imagem (webp/png), intercaladas entre as folhas.
		 * Quando ausentes, cada folha vira "documento" (folha com linhas) via CSS.
		 */
		images?: string[];
	}

	let { size = 52, images = [] }: Props = $props();

	interface PaperPose {
		left: number;
		top: number;
		w: number;
		h: number;
		rest: string;
		hover: string;
		delay: number;
		img?: number;
	}

	// Ordem = profundidade (primeira = mais ao fundo). Poses tortas de proposito:
	// direcoes, angulos, distancias e delays todos diferentes ("desengoncado").
	// Fechada, varias pontinhas vazam da capa (topo, direita e baixo); no hover a
	// maioria escapa para a DIREITA/baixo-direita (lado livre do cartao).
	const papers: PaperPose[] = [
		{ left: 33, top: 10, w: 34, h: 58, rest: 'translate(6%, -18%) rotate(-6deg)', hover: 'translate(-30%, -24%) rotate(-12deg)', delay: 120 },
		{ left: 30, top: 8, w: 40, h: 64, rest: 'translate(2%, -12%) rotate(3deg)', hover: 'translate(34%, -40%) rotate(6deg)', delay: 90, img: 1 },
		{ left: 32, top: 12, w: 36, h: 60, rest: 'none', hover: 'translate(70%, -18%) rotate(13deg)', delay: 150 },
		{ left: 27, top: 10, w: 46, h: 66, rest: 'none', hover: 'translate(58%, 6%) rotate(-8deg)', delay: 60 },
		{ left: 28, top: 14, w: 42, h: 62, rest: 'none', hover: 'translate(84%, 14%) rotate(11deg)', delay: 110, img: 0 },
		{ left: 25, top: 11, w: 50, h: 70, rest: 'translate(4%, 26%) rotate(-3deg)', hover: 'translate(40%, 26%) rotate(-5deg)', delay: 30 },
		{ left: 23, top: 9, w: 52, h: 72, rest: 'translate(48%, 4%) rotate(-2deg)', hover: 'translate(74%, -6%) rotate(4deg)', delay: 70, img: 1 },
		{ left: 22, top: 14, w: 62, h: 68, rest: 'translate(28%, 0) rotate(2deg)', hover: 'translate(88%, 6%) rotate(9deg)', delay: 0, img: 0 }
	];
</script>

<span class="fp-root" style="--fp-size: {size}px;" aria-hidden="true">
	<span class="fp-stage">
		<!-- Corpo traseiro (quase do tamanho da capa => pasta tem "dentro"). -->
		<svg class="fp-body" viewBox="68 48 364 420">
			<defs>
				<linearGradient id="fpk-back" x1="0%" y1="0%" x2="0%" y2="100%">
					<stop offset="0%" stop-color="#F5C754" />
					<stop offset="100%" stop-color="#E4A62C" />
				</linearGradient>
				<linearGradient id="fpk-edge" x1="0%" y1="0%" x2="100%" y2="0%">
					<stop offset="0%" stop-color="#D99819" />
					<stop offset="100%" stop-color="#C78612" />
				</linearGradient>
			</defs>
			<path
				d="M115 62h270q34 0 34 34v320q0 34-34 34h-270q-34 0-34-34v-320q0-34 34-34z"
				fill="url(#fpk-back)"
			/>
			<g transform="translate(55 0)">
				<rect x="332" y="88" width="18" height="300" rx="9" fill="url(#fpk-edge)" opacity=".55" />
				<g fill="#F8F5ED">
					<path d="M344 152c12 0 12 18 0 18h-12v-18z" />
					<path d="M344 188c12 0 12 18 0 18h-12v-18z" />
					<path d="M344 224c12 0 12 18 0 18h-12v-18z" />
					<path d="M344 260c12 0 12 18 0 18h-12v-18z" />
				</g>
			</g>
		</svg>

		<!-- Folhas abarrotadas entre o corpo e a capa; escapam tortas no hover. -->
		{#each papers as p, i (i)}
			<span
				class="fp-paper"
				style="left: {p.left}%; top: {p.top}%; width: {p.w}%; height: {p.h}%; z-index: {i +
					2}; --fp-rest: {p.rest}; --fp-hover: {p.hover}; --fp-delay: {p.delay}ms;"
			>
				{#if p.img !== undefined && images[p.img]}
					<img src={images[p.img]} alt="" loading="lazy" decoding="async" class="fp-paper-img" />
				{:else}
					<span class="fp-doc-lines"></span>
				{/if}
			</span>
		{/each}

		<!-- Capa: abre em rotateY com dobradica na propria borda esquerda. -->
		<svg class="fp-cover" viewBox="68 48 364 420">
			<defs>
				<linearGradient id="fpk-cover" x1="0%" y1="0%" x2="100%" y2="100%">
					<stop offset="0%" stop-color="#FFD866" />
					<stop offset="100%" stop-color="#F1B63A" />
				</linearGradient>
				<filter id="fpk-shadow" x="-30%" y="-30%" width="160%" height="180%">
					<feDropShadow dx="10" dy="14" stdDeviation="12" flood-color="#000000" flood-opacity=".18" />
				</filter>
			</defs>
			<g filter="url(#fpk-shadow)">
				<path
					d="M109 56h282q34 0 34 34v332q0 34-34 34h-282q-34 0-34-34v-332q0-34 34-34z"
					fill="url(#fpk-cover)"
				/>
			</g>
			<path
				d="M134 78q-10 110 0 240q8 92 46 118"
				fill="none"
				stroke="#FFF8D8"
				stroke-width="12"
				stroke-linecap="round"
				opacity=".18"
			/>
			<rect x="408" y="84" width="8" height="300" rx="4" fill="#FFE8A7" opacity=".45" />
		</svg>
	</span>
</span>

<style>
	/* Palco com a proporcao da arte cropada (364x420): a pasta enche o box. */
	.fp-root {
		display: inline-flex;
		position: relative;
		width: calc(var(--fp-size) * 0.867);
		height: var(--fp-size);
		flex-shrink: 0;
	}

	/* Anti hover-flicker: nada que se transforma captura o cursor. O `:hover` e
	   avaliado so na caixa estavel `.fp-root` (que nao se move) e no `.group`
	   ancestral. Ref: dev.to/annlin/css-flicker-on-hover. */
	.fp-stage,
	.fp-stage * {
		pointer-events: none;
	}

	/* perspective habilita o rotateY 3D da capa; origem alta a esquerda = camera
	   levemente acima/frontal, mesmo ponto de fuga para capa e folhas. */
	.fp-stage {
		position: relative;
		width: 100%;
		height: 100%;
		perspective: calc(var(--fp-size) * 8);
		perspective-origin: 40% 40%;
	}

	.fp-body,
	.fp-cover {
		position: absolute;
		inset: 0;
		width: 100%;
		height: 100%;
	}
	.fp-body {
		z-index: 1;
	}

	/* Capa: dobradica na borda ESQUERDA do desenho (x=75 no viewBox que comeca
	   em 68 => 1.9%). Base = leave RAPIDO (0.22s, sem delay); o enter lento fica
	   no :hover. z acima das 8 folhas (2..9). */
	.fp-cover {
		z-index: 10;
		transform-origin: 1.9% 50%;
		transform: rotateY(0deg);
		transition: transform 0.22s ease;
		will-change: transform;
		backface-visibility: hidden;
	}

	/* Folhas: atras da capa em repouso (so a da frente espreita a pontinha).
	   Poses de repouso/hover/delay vem por custom props do markup.
	   So transform/box-shadow => GPU, zero reflow. */
	.fp-paper {
		position: absolute;
		border-radius: calc(var(--fp-size) * 0.045);
		background: var(--ds-color-surface-raised);
		border: 1px solid var(--ds-color-border-base);
		overflow: hidden;
		transform-origin: 50% 100%;
		transform: var(--fp-rest, none);
		box-shadow: 0 3px 8px rgba(15, 42, 71, 0.12);
		transition:
			transform 0.22s ease,
			box-shadow 0.22s ease;
		transition-delay: 0s;
		will-change: transform;
		backface-visibility: hidden;
	}
	.fp-paper-img {
		width: 100%;
		height: 100%;
		object-fit: cover;
		object-position: top center;
		display: block;
	}
	/* "Documento": linhas de texto falsas no topo da folha. */
	.fp-doc-lines {
		position: absolute;
		inset: 12% 14% auto 14%;
		height: 58%;
		background-image: repeating-linear-gradient(
			180deg,
			rgba(100, 116, 139, 0.5) 0,
			rgba(100, 116, 139, 0.5) calc(var(--fp-size) * 0.02),
			transparent calc(var(--fp-size) * 0.02),
			transparent calc(var(--fp-size) * 0.09)
		);
	}

	/* ----- HOVER (proprio OU cartao `.group` ancestral) -----
	   Enter lento + curva de "assentar" + stagger SO no estado ativo: a cascata
	   atua na abertura; o fechamento usa a base (rapida, sem delay). */
	.fp-root:is(:hover, :focus-within) .fp-cover,
	:global(.group:hover) .fp-cover,
	:global(.group:focus-within) .fp-cover {
		transform: rotateY(-26deg);
		transition: transform 0.45s cubic-bezier(0.34, 1.2, 0.64, 1);
	}
	.fp-root:is(:hover, :focus-within) .fp-paper,
	:global(.group:hover) .fp-paper,
	:global(.group:focus-within) .fp-paper {
		transform: var(--fp-hover);
		box-shadow: 0 7px 16px rgba(15, 42, 71, 0.2);
		transition:
			transform 0.45s cubic-bezier(0.34, 1.2, 0.64, 1),
			box-shadow 0.45s ease;
		transition-delay: var(--fp-delay, 0ms);
	}

	:global([data-theme='dark']) .fp-paper {
		box-shadow: 0 3px 8px rgba(0, 0, 0, 0.45);
	}
	:global([data-theme='dark']) .fp-root:is(:hover, :focus-within) .fp-paper,
	:global([data-theme='dark'] .group:hover) .fp-paper,
	:global([data-theme='dark'] .group:focus-within) .fp-paper {
		box-shadow: 0 7px 16px rgba(0, 0, 0, 0.55);
	}

	@media (prefers-reduced-motion: reduce) {
		.fp-cover,
		.fp-paper {
			transition: none;
		}
	}
</style>
