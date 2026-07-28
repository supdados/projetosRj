<script lang="ts">
	/**
	 * Painel de calendário reutilizável (visual 1:1 do date picker do modal de
	 * evento do Calendário — cdp-calendar), ancorado a um elemento e promovido ao
	 * top layer via Popover API (imune a overflow/transform de ancestrais).
	 * Controlado: emite onPick/onClear/onClose; quem abre gerencia o estado.
	 */
	interface Props {
		/** Elemento âncora (trigger) para o posicionamento. */
		anchor: HTMLElement;
		/** Data selecionada (ISO yyyy-mm-dd) ou null. */
		value: string | null;
		/** Data mínima selecionável (ISO), opcional. */
		min?: string | null;
		/** Data máxima selecionável (ISO), opcional. */
		max?: string | null;
		/** Exibe "Limpar" no rodapé (para campos que aceitam ficar sem data). */
		allowClear?: boolean;
		ariaLabel?: string;
		onPick: (iso: string) => void;
		onClear?: () => void;
		/** Escape / clique fora. */
		onClose: () => void;
	}

	let {
		anchor,
		value,
		min = null,
		max = null,
		allowClear = false,
		ariaLabel = 'Selecionar data',
		onPick,
		onClear,
		onClose
	}: Props = $props();

	const MONTHS_PT = [
		'janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho',
		'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro'
	];
	const WEEKDAYS_PT = ['Dom', 'Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb'];

	const pad = (n: number): string => String(n).padStart(2, '0');
	function todayStr(): string {
		const d = new Date();
		return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
	}

	let panelEl = $state<HTMLDivElement | null>(null);

	// Mês exibido: parte do valor selecionado, senão de hoje. Captura só o valor
	// inicial DE PROPÓSITO — o painel remonta a cada abertura ({#if} no caller).
	// svelte-ignore state_referenced_locally
	const initial = (value || todayStr()).split('-').map(Number);
	let year = $state(initial[0]);
	let month = $state(initial[1] - 1);

	function prevMonth(): void {
		if (--month < 0) {
			month = 11;
			year--;
		}
	}
	function nextMonth(): void {
		if (++month > 11) {
			month = 0;
			year++;
		}
	}

	interface DayCell {
		day: number;
		dateStr: string;
		outside: boolean;
	}
	const cells = $derived.by<DayCell[]>(() => {
		const firstDay = new Date(year, month, 1).getDay();
		const startOffset = firstDay; // semana começa no domingo
		const daysInMonth = new Date(year, month + 1, 0).getDate();
		const daysInPrev = new Date(year, month, 0).getDate();
		const out: DayCell[] = [];
		for (let p = startOffset - 1; p >= 0; p--) {
			const d = daysInPrev - p;
			let pm = month - 1;
			let py = year;
			if (pm < 0) {
				pm = 11;
				py--;
			}
			out.push({ day: d, dateStr: `${py}-${pad(pm + 1)}-${pad(d)}`, outside: true });
		}
		for (let d = 1; d <= daysInMonth; d++) {
			out.push({ day: d, dateStr: `${year}-${pad(month + 1)}-${pad(d)}`, outside: false });
		}
		const remaining = 7 - (out.length % 7);
		if (remaining < 7) {
			for (let n = 1; n <= remaining; n++) {
				let nm = month + 1;
				let ny = year;
				if (nm > 11) {
					nm = 0;
					ny++;
				}
				out.push({ day: n, dateStr: `${ny}-${pad(nm + 1)}-${pad(n)}`, outside: true });
			}
		}
		return out;
	});
	const monthLabel = $derived(`${MONTHS_PT[month]} de ${year}`);

	// Top layer + coordenadas do anchor (padrão SelectMenu): flip vertical quando
	// falta espaço abaixo, clamp horizontal à viewport.
	function activatePopover(node: HTMLElement): void {
		if (typeof node.showPopover === 'function') node.showPopover();
	}

	interface Pos {
		top: number | null;
		bottom: number | null;
		left: number;
	}
	const PANEL_W = 272; // 17rem
	const PANEL_H = 320;
	let pos = $state<Pos>({ top: 0, bottom: null, left: 0 });

	function computePosition(): void {
		const r = anchor.getBoundingClientRect();
		const gap = 6;
		const margin = 8;
		const spaceBelow = window.innerHeight - r.bottom - gap - margin;
		const spaceAbove = r.top - gap - margin;
		const flip = spaceBelow < PANEL_H && spaceAbove > spaceBelow;
		pos = {
			top: flip ? null : r.bottom + gap,
			bottom: flip ? window.innerHeight - r.top + gap : null,
			left: Math.min(Math.max(margin, r.left), window.innerWidth - PANEL_W - margin)
		};
	}
	computePosition();

	// Fecha em Escape/clique fora; scroll/resize reposicionam para seguir o anchor.
	$effect(() => {
		const onPointerDown = (e: PointerEvent): void => {
			const target = e.target as Node;
			if (panelEl?.contains(target) || anchor.contains(target)) return;
			onClose();
		};
		const onKeydown = (e: KeyboardEvent): void => {
			if (e.key === 'Escape') {
				e.preventDefault();
				// Escape fecha SÓ o calendário — não vaza para composer/modal pai.
				e.stopPropagation();
				onClose();
			}
		};
		const onScroll = (e: Event): void => {
			if (panelEl && e.target instanceof Node && panelEl.contains(e.target)) return;
			computePosition();
		};
		const onResize = (): void => computePosition();
		window.addEventListener('pointerdown', onPointerDown, true);
		window.addEventListener('keydown', onKeydown, true);
		window.addEventListener('scroll', onScroll, true);
		window.addEventListener('resize', onResize);
		return () => {
			window.removeEventListener('pointerdown', onPointerDown, true);
			window.removeEventListener('keydown', onKeydown, true);
			window.removeEventListener('scroll', onScroll, true);
			window.removeEventListener('resize', onResize);
		};
	});

	const tdy = todayStr();
</script>

<div
	bind:this={panelEl}
	popover="manual"
	use:activatePopover
	role="dialog"
	aria-label={ariaLabel}
	class="dfp-panel"
	style:top={pos.top != null ? `${pos.top}px` : undefined}
	style:bottom={pos.bottom != null ? `${pos.bottom}px` : undefined}
	style:left="{pos.left}px"
>
	<div class="dfp-header">
		<button type="button" class="dfp-nav-btn" aria-label="Mês anterior" onclick={prevMonth}>
			<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6" /></svg>
		</button>
		<span class="dfp-month-label">{monthLabel}</span>
		<button type="button" class="dfp-nav-btn" aria-label="Próximo mês" onclick={nextMonth}>
			<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 6 15 12 9 18" /></svg>
		</button>
	</div>
	<div class="dfp-weekdays">
		{#each WEEKDAYS_PT as wd (wd)}<span>{wd}</span>{/each}
	</div>
	<div class="dfp-days">
		{#each cells as c (c.dateStr)}
			{@const disabled = (!!min && c.dateStr < min) || (!!max && c.dateStr > max)}
			<button
				type="button"
				class="dfp-day"
				class:dfp-day--outside={c.outside}
				class:dfp-day--today={c.dateStr === tdy}
				class:dfp-day--selected={c.dateStr === value}
				class:dfp-day--disabled={disabled}
				{disabled}
				onclick={() => onPick(c.dateStr)}
			>
				{c.day}
			</button>
		{/each}
	</div>
	<div class="dfp-footer">
		<button type="button" class="dfp-footer-btn" onclick={() => onPick(todayStr())}>Hoje</button>
		{#if allowClear && value}
			<button type="button" class="dfp-footer-btn dfp-footer-btn--clear" onclick={() => onClear?.()}>
				Limpar
			</button>
		{/if}
	</div>
</div>

<style>
	/* Visual 1:1 do .cdp-calendar do CalendarEventModal, tokens idênticos.
	   margin/inset neutralizam a UA stylesheet de [popover]. */
	.dfp-panel {
		position: fixed;
		margin: 0;
		inset: auto;
		z-index: 1110;
		width: 17rem;
		background: var(--ds-color-surface-base);
		border: 1px solid var(--ds-color-border-base);
		border-radius: 12px;
		box-shadow: 0 12px 32px rgba(0, 0, 0, 0.12), 0 2px 8px rgba(0, 0, 0, 0.06);
		overflow: hidden;
		animation: dfp-in 0.14s ease both;
	}
	:global([data-theme='dark']) .dfp-panel {
		box-shadow: 0 12px 32px rgba(0, 0, 0, 0.5), 0 2px 8px rgba(0, 0, 0, 0.35);
	}
	@keyframes dfp-in {
		from {
			opacity: 0;
			transform: translateY(-4px);
		}
		to {
			opacity: 1;
			transform: translateY(0);
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.dfp-panel {
			animation-duration: 1ms;
		}
	}
	.dfp-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 0.55rem 0.55rem 0.35rem;
	}
	.dfp-month-label {
		font-size: 0.8125rem;
		font-weight: 600;
		color: var(--ds-color-text-primary);
		user-select: none;
	}
	.dfp-nav-btn {
		width: 1.6rem;
		height: 1.6rem;
		border-radius: 50%;
		border: none;
		background: none;
		color: var(--ds-color-text-muted);
		cursor: pointer;
		display: flex;
		align-items: center;
		justify-content: center;
		transition: background 0.12s, color 0.12s;
	}
	.dfp-nav-btn:hover {
		background: var(--ds-color-surface-muted);
		color: var(--ds-color-text-primary);
	}
	.dfp-weekdays {
		display: grid;
		grid-template-columns: repeat(7, 1fr);
		padding: 0 0.4rem;
	}
	.dfp-weekdays span {
		text-align: center;
		font-size: 0.6875rem;
		color: var(--ds-color-text-muted);
		font-weight: 500;
		padding: 0.18rem 0;
		text-transform: uppercase;
		letter-spacing: 0.02em;
	}
	.dfp-days {
		display: grid;
		grid-template-columns: repeat(7, 1fr);
		padding: 0.1rem 0.4rem 0.4rem;
		gap: 0.08rem;
	}
	.dfp-day {
		width: 2rem;
		height: 2rem;
		margin: auto;
		display: flex;
		align-items: center;
		justify-content: center;
		font-size: 0.75rem;
		border-radius: 50%;
		cursor: pointer;
		border: none;
		background: none;
		color: var(--ds-color-text-primary);
		transition: background 0.1s, color 0.1s, box-shadow 0.1s;
		font-family: inherit;
		padding: 0;
		line-height: 1;
	}
	.dfp-day:hover:not(.dfp-day--selected):not(.dfp-day--disabled):not(.dfp-day--outside) {
		background: var(--ds-color-surface-muted);
	}
	.dfp-day--today:not(.dfp-day--selected) {
		font-weight: 600;
		color: var(--ds-color-text-brand);
		box-shadow: inset 0 0 0 1.5px var(--ds-color-fill-brand);
	}
	.dfp-day--selected {
		background: var(--ds-color-fill-brand);
		color: var(--ds-color-fill-brand-fg);
		font-weight: 600;
	}
	.dfp-day--selected:hover {
		background: var(--ds-color-fill-brand-hover);
	}
	.dfp-day--outside {
		color: var(--ds-color-text-muted);
		opacity: 0.35;
	}
	.dfp-day--disabled {
		opacity: 0.25;
		cursor: default;
		pointer-events: none;
	}
	.dfp-footer {
		padding: 0.25rem 0.55rem 0.45rem;
		border-top: 1px solid var(--ds-color-border-base);
		display: flex;
		justify-content: center;
		gap: 0.5rem;
	}
	.dfp-footer-btn {
		font-size: 0.75rem;
		font-weight: 500;
		color: var(--ds-color-text-brand);
		background: none;
		border: none;
		cursor: pointer;
		padding: 0.22rem 0.65rem;
		border-radius: 6px;
		transition: background 0.12s;
		font-family: inherit;
	}
	.dfp-footer-btn:hover {
		background: var(--ds-color-wash-neutral);
	}
	.dfp-footer-btn--clear {
		color: var(--ds-color-text-danger);
	}
	.dfp-footer-btn--clear:hover {
		background: var(--ds-color-wash-danger);
	}
</style>
