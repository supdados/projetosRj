<script lang="ts">
	/**
	 * Forma da pasta (corpo + aba frontal + lingueta), SEM os papeis/hover. Mesma
	 * geometria da pasta de "Todos os projetos" (FolderReveal), extraida para ser
	 * reutilizada com proporcoes IDENTICAS — ex.: a pilha do KPI "Vigentes".
	 *
	 * Cor configuravel via props (default azul da marca, como em Projetos).
	 * Decorativa (`aria-hidden`).
	 */
	interface Props {
		/** Largura da pasta em px (altura = size * 0.78, igual a FolderReveal). */
		size?: number;
		accent?: string;
		accentDark?: string;
		accentLight?: string;
	}
	let {
		size = 46,
		accent = 'var(--ds-color-icon-base)',
		accentDark = 'var(--ds-color-icon-outline)',
		accentLight = 'var(--ds-color-icon-light)'
	}: Props = $props();
</script>

<span
	class="fs-root"
	style="--fs-size: {size}px; --fs-accent: {accent}; --fs-accent-dark: {accentDark}; --fs-accent-light: {accentLight};"
	aria-hidden="true"
>
	<span class="fs-back"></span>
	<span class="fs-front"></span>
</span>

<style>
	/* Geometria 1:1 com FolderReveal (.fr-root/.fr-back/.fr-front). */
	.fs-root {
		position: relative;
		display: inline-block;
		width: var(--fs-size);
		height: calc(var(--fs-size) * 0.78);
	}
	.fs-back {
		position: absolute;
		inset: auto 0 0 0;
		height: 86%;
		border-radius: calc(var(--fs-size) * 0.11);
		background: linear-gradient(180deg, var(--fs-accent) 0%, var(--fs-accent-dark) 100%);
	}
	.fs-back::before {
		content: '';
		position: absolute;
		top: calc(var(--fs-size) * -0.1);
		left: 0;
		width: 46%;
		height: calc(var(--fs-size) * 0.16);
		border-radius: calc(var(--fs-size) * 0.07) calc(var(--fs-size) * 0.07) 0 0;
		background: var(--fs-accent);
	}
	.fs-front {
		position: absolute;
		inset: auto 0 0 0;
		height: 64%;
		border-radius: calc(var(--fs-size) * 0.1);
		background: linear-gradient(180deg, var(--fs-accent-light) 0%, var(--fs-accent) 100%);
		box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.45);
	}
</style>
