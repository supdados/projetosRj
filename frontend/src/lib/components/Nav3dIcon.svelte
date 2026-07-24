<script lang="ts">
	/**
	 * Ícone de item do topnav: Font Awesome por baixo, 3D por cima.
	 *
	 * REGRA DE OURO DO LAYOUT: o `<i class="fas">` nunca sai do DOM — é ele que
	 * dá largura ao `<a>`, e a pílula branca da nav mede essa largura. O canvas
	 * é `position:absolute` (fora de fluxo), então o item tem exatamente a
	 * mesma caixa de antes, sem nenhum px chumbado. Quando o 3D sobe, o glifo
	 * só fica transparente por baixo.
	 *
	 * Sem WebGL, com o kill switch ligado ou se o `three` não carregar, o
	 * canvas nunca acende e o item segue idêntico ao que era.
	 */
	import { onDestroy } from 'svelte';
	import { attachNavIcon, ICON_Y_NUDGE, type NavIconHandle } from '$lib/nav3d/navIconStage';
	import type { NavIconKind } from '$lib/nav3d/palettes';

	interface Props {
		/** Classe Font Awesome do ícone equivalente (estado inicial e de erro). */
		faIcon: string;
		kind: NavIconKind;
		active: boolean;
		pressed: boolean;
	}

	let { faIcon, kind, active, pressed }: Props = $props();

	let canvasEl = $state<HTMLCanvasElement | null>(null);
	let handle = $state<NavIconHandle | null>(null);
	let live = $state(false);

	$effect(() => {
		const canvas = canvasEl;
		if (!canvas || handle) return;
		let dropped = false;
		// O stage avisa quando o tile some (contexto perdido, stage derrubado):
		// aí o glifo Font Awesome precisa reaparecer no mesmo frame.
		const onLive = (next: boolean) => {
			if (!dropped) live = next;
		};
		void attachNavIcon(canvas, kind, active, onLive).then((next) => {
			// O attach é assíncrono (idle + import): pode resolver depois do destroy.
			if (dropped || !next) {
				next?.detach();
				return;
			}
			handle = next;
		});
		return () => {
			dropped = true;
		};
	});

	$effect(() => {
		handle?.setActive(active);
	});

	$effect(() => {
		if (pressed) handle?.press();
		else handle?.release();
	});

	onDestroy(() => {
		handle?.detach();
		handle = null;
	});
</script>

<span class="nav3d" class:nav3d--live={live}>
	<i class="fas {faIcon} shrink-0" aria-hidden="true"></i>
	<canvas
		bind:this={canvasEl}
		class="nav3d__canvas"
		style="--nav3d-y: {ICON_Y_NUDGE}px;"
		aria-hidden="true"
	></canvas>
</span>

<style>
	.nav3d {
		position: relative;
		display: inline-flex;
		align-items: center;
		justify-content: center;
	}

	/* Fora de fluxo e maior que o glifo: o transbordo cabe no gap/padding do
	   item e não altera a largura medida pela pílula. */
	.nav3d__canvas {
		position: absolute;
		left: 50%;
		top: 50%;
		width: 20px;
		height: 20px;
		transform: translate(-50%, calc(-50% + var(--nav3d-y, 0px)));
		pointer-events: none;
		opacity: 0;
		transition: opacity 120ms linear;
	}

	.nav3d--live .nav3d__canvas {
		opacity: 1;
	}

	/* O glifo some só quando o 3D já está pintado. Sem transição própria: no
	   modo Font Awesome ele precisa continuar herdando a cor interpolada pelo
	   `transition-colors` do <a>, em lockstep com o rótulo. */
	.nav3d--live i {
		color: transparent;
	}

	@media (prefers-reduced-motion: reduce) {
		.nav3d__canvas {
			transition: none;
		}
	}
</style>
