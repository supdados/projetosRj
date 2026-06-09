<script lang="ts">
	/**
	 * Alternância Lista ⇄ Kanban — porte FIEL do toggle "refinado" do v4.5
	 * (templates/tasks/hub.html + static/css/tasks/detail/view-toggle.css +
	 * static/js/modules/kanban/view-toggle.js). A pílula é desenhada em SVG: dois
	 * preenchimentos (ativo em gradiente azul-escuro, inativo azul-claro) separados
	 * por um divisor em curva-S. Ao trocar de modo, o divisor MORFA de um lado para
	 * o outro via requestAnimationFrame (500ms, ease-in-out-cubic), enquanto as
	 * cores/realces/rótulos trocam para o lado ativo. Respeita prefers-reduced-motion.
	 *
	 * A página continua dona do estado `view`; este componente só reflete o valor
	 * recebido e chama `onSelect` no clique (mesma assinatura do `selectView`).
	 */
	import { onMount } from 'svelte';

	type ViewMode = 'list' | 'kanban';

	interface Props {
		/** Modo atual (dono = página). 'list' default. */
		view: ViewMode;
		/** Disparado ao clicar num dos lados (a página decide o resto). */
		onSelect: (mode: ViewMode) => void;
	}

	let { view, onSelect }: Props = $props();

	// Refs dos elementos SVG animados (preenchidos via bind:this).
	let pathLeft = $state<SVGPathElement | null>(null);
	let pathRight = $state<SVGPathElement | null>(null);
	let divider = $state<SVGPathElement | null>(null);
	let fillLeft = $state<SVGRectElement | null>(null);
	let fillRight = $state<SVGRectElement | null>(null);
	let highlightLeft = $state<SVGRectElement | null>(null);
	let highlightRight = $state<SVGRectElement | null>(null);
	let borderLeft = $state<SVGRectElement | null>(null);

	// Direção visual corrente do divisor: 1 = curva p/ a Lista, -1 = p/ Kanban.
	// É o valor INTERPOLADO durante a animação (não só o alvo).
	let visualDir = 1;
	let frame = 0;
	let mounted = false;

	function prefersReducedMotion(): boolean {
		return (
			typeof window !== 'undefined' &&
			window.matchMedia('(prefers-reduced-motion: reduce)').matches
		);
	}

	/** Curva-S do divisor em x≈136, deslocada conforme `direction` (±). */
	function buildToggleCurvePath(direction: number): string {
		const d = direction;
		const x = 136;
		return [
			`M ${x} 0`,
			`C ${x + 7 * 0.3 * d} ${50 * 0.15},`,
			`  ${x + 7 * d} ${50 * 0.28},`,
			`  ${x + 7 * 0.5 * d} ${50 * 0.5}`,
			`C ${x} ${50 * 0.72},`,
			`  ${x - 7 * 0.7 * d} ${50 * 0.85},`,
			`  ${x} 50`
		].join(' ');
	}

	function buildToggleLeftPath(direction: number): string {
		return `${buildToggleCurvePath(direction)} L 0 50 L 0 0 Z`;
	}

	function buildToggleRightPath(direction: number): string {
		return `${buildToggleCurvePath(direction)} L 272 50 L 272 0 Z`;
	}

	function syncTogglePaths(direction: number): void {
		if (!pathLeft || !pathRight || !divider) return;
		pathLeft.setAttribute('d', buildToggleLeftPath(direction));
		pathRight.setAttribute('d', buildToggleRightPath(direction));
		divider.setAttribute('d', buildToggleCurvePath(direction));
	}

	function syncToggleColors(mode: ViewMode): void {
		const isList = mode !== 'kanban';
		fillLeft?.setAttribute('fill', isList ? 'url(#taskHubViewToggleActive)' : 'url(#taskHubViewToggleInactive)');
		fillRight?.setAttribute('fill', isList ? 'url(#taskHubViewToggleInactive)' : 'url(#taskHubViewToggleActive)');
		highlightLeft?.setAttribute('opacity', isList ? '1' : '0');
		highlightRight?.setAttribute('opacity', isList ? '0' : '1');
		borderLeft?.setAttribute('opacity', isList ? '1' : '0');
	}

	function easeInOutCubic(t: number): number {
		return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
	}

	function animateToggleVisual(targetDir: number): void {
		const fromDir = visualDir;
		const duration = 500;
		// performance.now() é o relógio local da animação (não Date.now()): ok no SPA.
		const start = performance.now();

		if (frame) {
			cancelAnimationFrame(frame);
			frame = 0;
		}

		function step(now: number): void {
			const progress = Math.min((now - start) / duration, 1);
			visualDir = fromDir + (targetDir - fromDir) * easeInOutCubic(progress);
			syncTogglePaths(visualDir);
			if (progress < 1) {
				frame = requestAnimationFrame(step);
				return;
			}
			visualDir = targetDir;
			frame = 0;
		}

		frame = requestAnimationFrame(step);
	}

	/** Reflete `view`: cor troca instantânea; divisor morfa (anima) p/ o lado novo. */
	$effect(() => {
		const targetDir = view === 'kanban' ? -1 : 1;
		syncToggleColors(view);

		// Primeira sincronização (mount) e prefers-reduced-motion: sem animação.
		if (!mounted || prefersReducedMotion() || visualDir === targetDir) {
			if (frame) {
				cancelAnimationFrame(frame);
				frame = 0;
			}
			syncTogglePaths(targetDir);
			visualDir = targetDir;
			return;
		}
		animateToggleVisual(targetDir);
	});

	onMount(() => {
		mounted = true;
		return () => {
			if (frame) cancelAnimationFrame(frame);
		};
	});
</script>

<div
	class="task-items-view-toggle"
	data-active-view={view}
	role="group"
	aria-label="Alternar visualização de tarefas"
>
	<svg
		class="task-items-view-toggle-art"
		viewBox="0 0 272 50"
		preserveAspectRatio="none"
		xmlns="http://www.w3.org/2000/svg"
		aria-hidden="true"
		focusable="false"
	>
		<defs>
			<clipPath id="taskHubViewTogglePill">
				<rect width="272" height="50" rx="10" />
			</clipPath>
			<clipPath id="taskHubViewToggleLeft">
				<path
					bind:this={pathLeft}
					d="M 136 0 C 138.1 7.5, 143 14, 139.5 25 C 136 36, 131.1 42.5, 136 50 L 0 50 L 0 0 Z"
				/>
			</clipPath>
			<clipPath id="taskHubViewToggleRight">
				<path
					bind:this={pathRight}
					d="M 136 0 C 138.1 7.5, 143 14, 139.5 25 C 136 36, 131.1 42.5, 136 50 L 272 50 L 272 0 Z"
				/>
			</clipPath>
			<linearGradient id="taskHubViewToggleActive" x1="0" y1="0" x2="0" y2="1">
				<stop offset="0%" style="stop-color: var(--td-toggle-active-start);" />
				<stop offset="100%" style="stop-color: var(--td-toggle-active-end);" />
			</linearGradient>
			<linearGradient id="taskHubViewToggleInactive" x1="0" y1="0" x2="0" y2="1">
				<stop offset="0%" style="stop-color: var(--td-toggle-inactive-start);" />
				<stop offset="100%" style="stop-color: var(--td-toggle-inactive-end);" />
			</linearGradient>
			<linearGradient id="taskHubViewToggleShine" x1="0" y1="0" x2="0" y2="1">
				<stop offset="0%" stop-color="#ffffff" stop-opacity="0.04" />
				<stop offset="100%" stop-color="#ffffff" stop-opacity="0" />
			</linearGradient>
		</defs>

		<g clip-path="url(#taskHubViewTogglePill)">
			<rect width="272" height="50" style="fill: var(--td-toggle-base-fill);" />

			<g clip-path="url(#taskHubViewToggleLeft)">
				<rect bind:this={fillLeft} width="272" height="50" fill="url(#taskHubViewToggleActive)" />
				<rect bind:this={highlightLeft} width="272" height="50" fill="url(#taskHubViewToggleShine)" opacity="1" />
			</g>

			<g clip-path="url(#taskHubViewToggleRight)">
				<rect bind:this={fillRight} width="272" height="50" fill="url(#taskHubViewToggleInactive)" />
				<rect bind:this={highlightRight} width="272" height="50" fill="url(#taskHubViewToggleShine)" opacity="0" />
			</g>

			<path
				bind:this={divider}
				d="M 136 0 C 138.1 7.5, 143 14, 139.5 25 C 136 36, 131.1 42.5, 136 50"
				style="stroke: var(--td-toggle-divider-stroke);"
				stroke-width="1"
				fill="none"
			/>

			<rect x="0.5" y="0.5" width="271" height="49" rx="9.5" style="stroke: var(--td-toggle-outer-border);" fill="none" />

			<g clip-path="url(#taskHubViewToggleLeft)">
				<rect bind:this={borderLeft} x="1" y="1" width="270" height="48" rx="9" style="stroke: var(--td-toggle-inner-border);" fill="none" opacity="1" />
			</g>
		</g>
	</svg>

	<div class="task-items-view-toggle-labels">
		<button
			type="button"
			class="task-items-view-btn"
			class:is-active={view === 'list'}
			data-view="list"
			aria-pressed={view === 'list'}
			onclick={() => onSelect('list')}
		>
			<span class="task-items-view-label" class:is-active={view === 'list'}>Lista</span>
		</button>
		<button
			type="button"
			class="task-items-view-btn"
			class:is-active={view === 'kanban'}
			data-view="kanban"
			aria-pressed={view === 'kanban'}
			onclick={() => onSelect('kanban')}
		>
			<span class="task-items-view-label" class:is-active={view === 'kanban'}>Kanban</span>
		</button>
	</div>
</div>

<style>
	/* Tons portados 1:1 do v4.5 (view-toggle.css). Dark mode via [data-theme]. */
	.task-items-view-toggle {
		--td-view-toggle-width: 160px;
		--td-view-toggle-height: 32px;
		--td-toggle-base-fill: #ccdff2;
		--td-toggle-active-start: #0e6aa8;
		--td-toggle-active-end: #084f7e;
		--td-toggle-inactive-start: #e0edf8;
		--td-toggle-inactive-end: #d2e4f4;
		--td-toggle-divider-stroke: rgba(10, 74, 130, 0.16);
		--td-toggle-outer-border: rgba(10, 74, 130, 0.22);
		--td-toggle-inner-border: rgba(255, 255, 255, 0.32);
		position: relative;
		display: inline-flex;
		flex: 0 0 auto;
		align-items: stretch;
		/* Largura DEFINIDA (não `min(100%, …)`): dentro do grupo de ações do header
		   (flex `shrink-0` = container de largura INDEFINIDA), o `100%` dentro de um
		   `min()` é indefinido e o cap era descartado — o SVG esticava e "vazava"
		   para a direita (a metade inativa virava um retângulo vazio) e os rótulos
		   ficavam encostados à esquerda da caixa esticada. Largura fixa + max-width
		   evita depender de porcentagem indefinida. */
		width: var(--td-view-toggle-width);
		max-width: 100%;
		height: var(--td-view-toggle-height);
		padding: 0;
		border: none;
		background: transparent;
		isolation: isolate;
		overflow: visible;
		user-select: none;
		-webkit-tap-highlight-color: transparent;
	}

	:global([data-theme='dark']) .task-items-view-toggle {
		--td-toggle-base-fill: #253545;
		--td-toggle-active-start: #0f6fae;
		--td-toggle-active-end: #09507e;
		--td-toggle-inactive-start: #1f2936;
		--td-toggle-inactive-end: #1c2634;
		--td-toggle-divider-stroke: rgba(30, 120, 190, 0.18);
		--td-toggle-outer-border: rgba(30, 120, 190, 0.24);
		--td-toggle-inner-border: rgba(255, 255, 255, 0.06);
	}

	.task-items-view-toggle-art {
		width: 100%;
		height: 100%;
		display: block;
		overflow: visible;
		pointer-events: none;
	}

	.task-items-view-toggle-labels {
		position: absolute;
		inset: 0;
		display: flex;
		align-items: stretch;
		justify-content: stretch;
		gap: 0;
	}

	.task-items-view-btn {
		flex: 1 1 50%;
		width: 50%;
		height: 100%;
		padding: 0;
		border: none;
		background: transparent;
		color: inherit;
		position: relative;
		z-index: 1;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		border-radius: 10px;
		cursor: pointer;
		transition: transform 0.1s ease;
	}

	.task-items-view-btn:focus {
		outline: none;
	}

	.task-items-view-btn:active {
		transform: scale(0.985);
	}

	.task-items-view-btn:focus-visible {
		outline: none;
		box-shadow: inset 0 0 0 2px rgba(130, 175, 230, 0.32);
	}

	.task-items-view-label {
		width: 100%;
		height: 100%;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		padding: 0 0.5rem;
		color: #5a7fa0;
		font-size: 0.75rem;
		font-weight: 600;
		letter-spacing: 0;
		text-shadow: none;
		transition:
			color 0.55s cubic-bezier(0.25, 0.8, 0.25, 1),
			text-shadow 0.55s ease;
		white-space: nowrap;
	}

	.task-items-view-label.is-active {
		color: #ffffff;
		text-shadow: 0 1px 1px rgba(5, 45, 90, 0.22);
	}

	.task-items-view-btn:hover .task-items-view-label:not(.is-active),
	.task-items-view-btn:focus-visible .task-items-view-label:not(.is-active) {
		color: #3d6282;
	}

	:global([data-theme='dark']) .task-items-view-label {
		color: rgba(214, 220, 226, 0.72);
	}

	:global([data-theme='dark']) .task-items-view-label.is-active {
		color: #f3f6f8;
		text-shadow: 0 1px 2px rgba(3, 25, 50, 0.4);
	}

	:global([data-theme='dark']) .task-items-view-btn:hover .task-items-view-label:not(.is-active),
	:global([data-theme='dark']) .task-items-view-btn:focus-visible .task-items-view-label:not(.is-active) {
		color: #eef2f5;
	}
</style>
