<script lang="ts">
	/**
	 * Micro-interacao: pasta que ABRE no hover e revela ate 3 "papeis" em leque
	 * (inspirado no componente Folder da Aceternity UI). Totalmente isolado e
	 * reutilizavel — primeiro de uma colecao de micro-interacoes em `micro/`.
	 *
	 * Gatilho de abertura (qualquer um destes):
	 *   - hover/foco no proprio componente (`:hover` / `:focus-within`);
	 *   - hover/foco-visivel em um ancestral com a classe `group` (ex.: o cartao
	 *     de KPI inteiro) — assim a pasta abre ao passar o mouse no cartao todo.
	 *
	 * Decorativo: marcado `aria-hidden`. O rotulo acessivel deve ficar no
	 * container (ex.: o `aria-label` do link do KPI).
	 *
	 * Respeita `prefers-reduced-motion`: sem transicoes/transformacoes.
	 */
	interface Props {
		/** Largura da pasta em px (a altura e derivada). Default 40 (cabe no KPI). */
		size?: number;
		/**
		 * Ate 3 URLs de imagem (webp/png/…). Quando ausentes, cada papel e
		 * desenhado como um "documento" (folha branca com linhas) via CSS.
		 */
		images?: string[];
		/** Cor base da pasta (azul suave por padrao, harmoniza com a marca). */
		accent?: string;
		/** Tom mais escuro (base da pasta / fundo do gradiente). */
		accentDark?: string;
		/** Tom mais claro (topo da aba frontal). */
		accentLight?: string;
	}

	let {
		size = 40,
		images = [],
		accent = '#6aa6db',
		accentDark = '#3f7cb3',
		accentLight = '#9bc6ec'
	}: Props = $props();

	// Sempre 3 lugares; cada um recebe uma imagem (se houver) ou vira documento.
	const slots = [0, 1, 2];
</script>

<span
	class="fr-root"
	style="--fr-size: {size}px; --fr-accent: {accent}; --fr-accent-dark: {accentDark}; --fr-accent-light: {accentLight};"
	aria-hidden="true"
>
	<span class="fr-folder">
		<!-- Papeis revelados: ficam atras da aba frontal e sobem em leque no hover. -->
		<span class="fr-papers">
			{#each slots as i (i)}
				<span class="fr-paper fr-paper--{i}">
					{#if images[i]}
						<img src={images[i]} alt="" loading="lazy" decoding="async" class="fr-paper-img" />
					{:else}
						<!-- Documento ilustrativo (folha + linhas), espelha os cards do video. -->
						<span class="fr-doc-lines"></span>
					{/if}
				</span>
			{/each}
		</span>

		<!-- Corpo (atras) + aba superior. -->
		<span class="fr-back"></span>
		<!-- Aba frontal: dobra para frente no hover (rotateX) revelando os papeis. -->
		<span class="fr-front"></span>
	</span>
</span>

<style>
	.fr-root {
		display: inline-flex;
		position: relative;
		width: var(--fr-size);
		height: calc(var(--fr-size) * 0.78);
		flex-shrink: 0;
	}

	/* Anti hover-flicker: nenhum elemento interno transformado captura o cursor.
	   Assim o `:hover` so e avaliado na caixa estavel `.fr-root` (que nao se move),
	   nunca num papel/aba que voou para fora de baixo do mouse — o que dispararia
	   mouseleave->reverte->mouseenter em LOOP. Ref: dev.to/annlin/css-flicker-on-hover. */
	.fr-folder,
	.fr-folder * {
		pointer-events: none;
	}

	/* perspectiva habilita o rotateX 3D da aba frontal. */
	.fr-folder {
		position: relative;
		width: 100%;
		height: 100%;
		perspective: 160px;
	}

	/* Corpo da pasta (atras de tudo) + aba/lingueta no topo-esquerdo. */
	.fr-back {
		position: absolute;
		inset: auto 0 0 0;
		height: 86%;
		border-radius: calc(var(--fr-size) * 0.11);
		background: linear-gradient(180deg, var(--fr-accent) 0%, var(--fr-accent-dark) 100%);
		z-index: 1;
	}
	.fr-back::before {
		content: '';
		position: absolute;
		top: calc(var(--fr-size) * -0.1);
		left: 0;
		width: 46%;
		height: calc(var(--fr-size) * 0.16);
		border-radius: calc(var(--fr-size) * 0.07) calc(var(--fr-size) * 0.07) 0 0;
		background: var(--fr-accent);
	}

	/* Aba frontal — fecha (vertical) por padrao, cobrindo os papeis.
	   Base = leave RAPIDO (0.22s, sem delay): ao tirar o mouse a pose volta na
	   hora, sem esperar a cascata. O enter (lento + delay) fica no estado :hover.
	   transition no base => interrompivel/reversivel em qualquer ponto. */
	.fr-front {
		position: absolute;
		inset: auto 0 0 0;
		height: 64%;
		border-radius: calc(var(--fr-size) * 0.1);
		background: linear-gradient(180deg, var(--fr-accent-light) 0%, var(--fr-accent) 100%);
		box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.45);
		transform-origin: bottom center;
		transform: rotateX(0deg);
		transition: transform 0.22s ease;
		will-change: transform;
		backface-visibility: hidden;
		z-index: 4;
	}

	/* Camada dos papeis: cada um centralizado embaixo, escondido atras da aba. */
	.fr-papers {
		position: absolute;
		inset: 0;
		z-index: 2;
	}
	.fr-paper {
		position: absolute;
		left: 50%;
		bottom: 18%;
		width: 92%;
		height: 74%;
		border-radius: calc(var(--fr-size) * 0.07);
		background: var(--color-surface-elevated);
		border: 1px solid var(--color-border);
		box-shadow: 0 6px 14px rgba(15, 42, 71, 0.18);
		overflow: hidden;
		transform-origin: bottom center;
		/* Base = leave RAPIDO e SEM delay (cascata reversa proibida): ao sair, os 3
		   papeis voltam juntos e na hora. O leque lento + delay escalonado fica no
		   :hover. So animamos transform/opacity => GPU, zero reflow no hover. */
		transition:
			transform 0.2s ease,
			opacity 0.16s ease;
		transition-delay: 0s;
		will-change: transform, opacity;
		backface-visibility: hidden;
	}
	/* Estado de REPOUSO: maco visivel espreitando para fora do topo da pasta
	   (atras da aba frontal, que cobre a parte de baixo). Leve leque empilhado. */
	.fr-paper--0 {
		transform: translate(-54%, 0) rotate(-6deg) scale(0.9);
	}
	.fr-paper--1 {
		transform: translate(-50%, -4%) rotate(0deg) scale(0.95);
	}
	.fr-paper--2 {
		transform: translate(-46%, 0) rotate(6deg) scale(0.9);
	}
	.fr-paper-img {
		width: 100%;
		height: 100%;
		object-fit: cover;
		object-position: top center;
		display: block;
	}
	/* "Documento": linhas de texto falsas no topo da folha. */
	.fr-doc-lines {
		position: absolute;
		inset: 14% 14% auto 14%;
		height: 56%;
		background-image: repeating-linear-gradient(
			180deg,
			rgba(100, 116, 139, 0.55) 0,
			rgba(100, 116, 139, 0.55) calc(var(--fr-size) * 0.025),
			transparent calc(var(--fr-size) * 0.025),
			transparent calc(var(--fr-size) * 0.11)
		);
	}

	/* ----- Estado ABERTO (hover/foco proprio OU do cartao `.group` ancestral) -----
	   O enter (lento + curva de "assentar" + delay escalonado) vive AQUI, no estado
	   ativo. Assim a cascata so atua na ABERTURA; o fechamento usa a transition base
	   (rapida, sem delay) e nunca reproduz a cascata ao contrario (anti-flicker). */
	.fr-root:is(:hover, :focus-within) .fr-front,
	:global(.group:hover) .fr-front,
	:global(.group:focus-within) .fr-front {
		transform: rotateX(-42deg);
		transition: transform 0.4s cubic-bezier(0.34, 1.2, 0.64, 1);
	}

	/* Papeis sobem para a FRENTE da pasta e abrem em leque (esq / centro / dir). */
	.fr-root:is(:hover, :focus-within) .fr-paper,
	:global(.group:hover) .fr-paper,
	:global(.group:focus-within) .fr-paper {
		opacity: 1;
		z-index: 5;
		transition:
			transform 0.42s cubic-bezier(0.34, 1.25, 0.64, 1),
			opacity 0.28s ease;
	}
	/* Escalonamento do leque APENAS na abertura (delay no estado ativo). Nada de
	   delay no base => o fechamento e imediato e simultaneo (sem cascata reversa). */
	.fr-root:is(:hover, :focus-within) .fr-paper--0,
	:global(.group:hover) .fr-paper--0,
	:global(.group:focus-within) .fr-paper--0 {
		transform: translate(-92%, -58%) rotate(-22deg) scale(1);
		transition-delay: 0.04s;
	}
	.fr-root:is(:hover, :focus-within) .fr-paper--1,
	:global(.group:hover) .fr-paper--1,
	:global(.group:focus-within) .fr-paper--1 {
		transform: translate(-50%, -74%) rotate(-3deg) scale(1.05);
	}
	.fr-root:is(:hover, :focus-within) .fr-paper--2,
	:global(.group:hover) .fr-paper--2,
	:global(.group:focus-within) .fr-paper--2 {
		transform: translate(-8%, -58%) rotate(17deg) scale(1);
		transition-delay: 0.08s;
	}

	:global([data-theme='dark']) .fr-paper {
		box-shadow: 0 6px 14px rgba(0, 0, 0, 0.55);
	}

	@media (prefers-reduced-motion: reduce) {
		.fr-front,
		.fr-paper {
			transition: none;
		}
	}
</style>
