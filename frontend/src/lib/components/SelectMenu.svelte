<script lang="ts">
	/**
	 * Seletor base com painel custom (substitui `<select>` nativo). Controlado por
	 * callback (`value` + `onSelect`), mesma linguagem visual do OrgaoTreeSelect.
	 */
	import { tick, type Snippet } from 'svelte';
	import type { SelectMenuOption } from '$lib/types/selectMenu';
	import StateIcon from '$lib/components/StateIcon.svelte';
	import ProjectIcon from '$lib/components/ProjectIcon.svelte';
	import { isStateIconId } from '$lib/icons/stateIcons';

	interface Props {
		options: SelectMenuOption[];
		value: string | null;
		onSelect: (value: string | null) => void;
		placeholder?: string;
		allowAll?: boolean;
		allLabel?: string;
		disabled?: boolean;
		id?: string;
		ariaLabel?: string;
		size?: 'md' | 'sm';
		searchable?: boolean;
		align?: 'left' | 'right';
		unstyled?: boolean;
		/** Esconde o ✓ da opção selecionada (o realce de fundo/peso permanece). */
		hideCheck?: boolean;
		trigger?: Snippet<[{ open: boolean; label: string; selected: SelectMenuOption | null }]>;
		/**
		 * Ícone renderizado antes do rótulo de cada opção do painel — e também no
		 * gatilho padrão, para a opção selecionada (com `trigger` próprio, quem
		 * renderiza o gatilho decide).
		 */
		optionIcon?: Snippet<[SelectMenuOption]>;
	}

	let {
		options,
		value,
		onSelect,
		placeholder = 'Selecionar...',
		allowAll = false,
		allLabel = 'Todos',
		disabled = false,
		id,
		ariaLabel,
		size = 'md',
		searchable = false,
		align = 'left',
		unstyled = false,
		hideCheck = false,
		trigger,
		optionIcon
	}: Props = $props();

	interface NavItem {
		optValue: string | null;
		label: string;
		option: SelectMenuOption | null;
		isAll: boolean;
	}

	let open = $state(false);
	let term = $state('');
	let inputEl = $state<HTMLInputElement | null>(null);
	let containerEl = $state<HTMLDivElement | null>(null);
	let triggerEl = $state<HTMLButtonElement | null>(null);
	let panelEl = $state<HTMLDivElement | null>(null);
	let highlightedIndex = $state(-1);

	interface PanelPos {
		top: number | null;
		bottom: number | null;
		left: number | null;
		right: number | null;
		minWidth: number;
		maxWidth: number;
		maxHeight: number;
		flip: boolean;
	}
	let panelPos = $state<PanelPos | null>(null);

	const listboxId = $derived(id ? `${id}-listbox` : 'select-menu-listbox');

	const COMBINING_MARKS = /[̀-ͯ]/g;
	const norm = (s: string | null | undefined): string =>
		(s ?? '').normalize('NFD').replace(COMBINING_MARKS, '').toLowerCase();

	const showAllOption = $derived(allowAll && !term.trim());

	const filteredOptions = $derived.by<SelectMenuOption[]>(() => {
		const query = norm(term.trim());
		if (!searchable || !query) return options;
		return options.filter((o) => norm(o.label).includes(query));
	});

	const navItems = $derived.by<NavItem[]>(() => {
		const out: NavItem[] = [];
		if (showAllOption) out.push({ optValue: null, label: allLabel, option: null, isAll: true });
		for (const option of filteredOptions) {
			out.push({ optValue: option.value, label: option.label, option, isAll: false });
		}
		return out;
	});

	const selected = $derived(
		value == null ? null : (options.find((o) => o.value === value) ?? null)
	);

	const triggerLabel = $derived.by<string>(() => {
		if (selected) return selected.label;
		if (allowAll) return allLabel;
		return placeholder;
	});

	const isPlaceholder = $derived(!selected && !allowAll);

	function itemId(index: number): string {
		return `${listboxId}-item-${index}`;
	}

	function firstEnabledIndex(): number {
		return navItems.findIndex((item) => !item.option?.disabled);
	}

	function selectedNavIndex(): number {
		const idx = navItems.findIndex((item) =>
			item.isAll ? value == null : item.optValue === value
		);
		return idx >= 0 ? idx : firstEnabledIndex();
	}

	// Altura estimada de uma linha do painel (py-1.5 + texto sm).
	const ROW_H = 30;

	// Painel promovido ao top layer via Popover API: por spec, ignora containing
	// blocks de transform/filter/contain e overflow de QUALQUER ancestral (colunas
	// do Kanban com [contain:layout], modais com transition:fly). Sem showPopover
	// (browser antigo), degrada para o `fixed` posicionado abaixo.
	function activatePopover(node: HTMLElement): void {
		if (typeof node.showPopover === 'function') node.showPopover();
	}

	function computePanelPosition(): void {
		if (!triggerEl) return;
		const r = triggerEl.getBoundingClientRect();
		const gap = 6;
		const margin = 8;
		const spaceBelow = window.innerHeight - r.bottom - gap - margin;
		const spaceAbove = r.top - gap - margin;
		const estimatedContentHeight = (searchable ? 40 : 0) + navItems.length * ROW_H + 12;
		const flip = spaceBelow < Math.min(estimatedContentHeight, 180) && spaceAbove > spaceBelow;
		const maxWidth = Math.min(340, window.innerWidth - margin * 2);
		// Flip horizontal simétrico ao vertical: ancora à direita do trigger quando
		// falta espaço à direita, em vez de empurrar o painel pelo pior caso de largura.
		const spaceRight = window.innerWidth - r.left - margin;
		const spaceLeftOfTrigger = r.right - margin;
		const flipH = align === 'left' && spaceRight < Math.min(160, maxWidth) && spaceLeftOfTrigger > spaceRight;
		const resolvedAlign = flipH ? 'right' : align;
		panelPos = {
			top: flip ? null : r.bottom + gap,
			bottom: flip ? window.innerHeight - r.top + gap : null,
			left: resolvedAlign === 'left' ? Math.max(margin, r.left) : null,
			right: resolvedAlign === 'right' ? Math.max(margin, window.innerWidth - r.right) : null,
			minWidth: Math.min(r.width, maxWidth),
			maxWidth,
			maxHeight: Math.min(320, Math.max(ROW_H + 12, flip ? spaceAbove : spaceBelow)),
			flip
		};
	}

	async function openPanel(): Promise<void> {
		if (disabled) return;
		computePanelPosition();
		open = true;
		term = '';
		highlightedIndex = selectedNavIndex();
		await tick();
		if (searchable) inputEl?.focus();
	}

	function closePanel(): void {
		open = false;
		highlightedIndex = -1;
	}

	function chooseItem(item: NavItem): void {
		if (item.option?.disabled) return;
		onSelect(item.optValue);
		closePanel();
	}

	function moveHighlight(step: number): void {
		if (navItems.length === 0) return;
		let next = highlightedIndex;
		for (let i = 0; i < navItems.length; i++) {
			next = (next + step + navItems.length) % navItems.length;
			if (!navItems[next].option?.disabled) break;
		}
		highlightedIndex = next;
		tick().then(() => {
			document.getElementById(itemId(highlightedIndex))?.scrollIntoView({ block: 'nearest' });
		});
	}

	function onTriggerKeydown(event: KeyboardEvent): void {
		if (event.key === 'Escape' && open) {
			event.preventDefault();
			// Esc fecha só o painel — modal/drawer pai não deve fechar junto.
			event.stopPropagation();
			closePanel();
			return;
		}
		if (event.key === 'ArrowDown' || event.key === 'Enter' || event.key === ' ') {
			event.preventDefault();
			void openPanel();
		}
	}

	function onPanelKeydown(event: KeyboardEvent): void {
		if (event.key === 'Escape' || event.key === 'Tab') {
			if (event.key === 'Escape') {
				event.preventDefault();
				event.stopPropagation();
			}
			closePanel();
			triggerEl?.focus();
			return;
		}
		if (event.key === 'ArrowDown') {
			event.preventDefault();
			moveHighlight(1);
			return;
		}
		if (event.key === 'ArrowUp') {
			event.preventDefault();
			moveHighlight(-1);
			return;
		}
		if (event.key === 'Home') {
			event.preventDefault();
			highlightedIndex = firstEnabledIndex();
			return;
		}
		if (event.key === 'End') {
			event.preventDefault();
			for (let i = navItems.length - 1; i >= 0; i--) {
				if (!navItems[i].option?.disabled) {
					highlightedIndex = i;
					break;
				}
			}
			return;
		}
		if (event.key === 'Enter' || event.key === ' ') {
			if (document.activeElement === inputEl && event.key === ' ') return;
			event.preventDefault();
			const item = navItems[highlightedIndex];
			if (item) chooseItem(item);
		}
	}

	// Fecha ao clicar fora; scroll/resize REPOSICIONAM o painel (fixed) para seguir
	// o gatilho — fechar no scroll impediria até rolar a própria lista.
	$effect(() => {
		if (!open) return;
		const onPointerDown = (event: PointerEvent): void => {
			if (containerEl && !containerEl.contains(event.target as Node)) closePanel();
		};
		const onScroll = (event: Event): void => {
			if (panelEl && event.target instanceof Node && panelEl.contains(event.target)) return;
			computePanelPosition();
		};
		const onResize = (): void => computePanelPosition();
		// Reflow do container (campos condicionais aparecendo no form) também move
		// o trigger sem disparar scroll/resize.
		const resizeObserver = new ResizeObserver(() => computePanelPosition());
		if (containerEl) resizeObserver.observe(containerEl);
		window.addEventListener('pointerdown', onPointerDown, true);
		window.addEventListener('scroll', onScroll, true);
		window.addEventListener('resize', onResize);
		return () => {
			resizeObserver.disconnect();
			window.removeEventListener('pointerdown', onPointerDown, true);
			window.removeEventListener('scroll', onScroll, true);
			window.removeEventListener('resize', onResize);
		};
	});

	const triggerClass = $derived.by<string>(() => {
		if (unstyled) {
			return 'focus:outline-none focus-visible:ring-2 focus-visible:ring-context disabled:cursor-not-allowed disabled:opacity-50';
		}
		const base =
			'flex w-full items-center justify-between gap-2 rounded-lg border border-border-subtle bg-surface text-left transition-colors duration-fast hover:border-brand focus:outline-none focus-visible:ring-2 focus-visible:ring-context disabled:cursor-not-allowed disabled:opacity-50';
		const sizeClass =
			size === 'sm'
				? 'h-[var(--control-h-sm)] px-2.5 text-sm'
				: 'h-[var(--control-h-md)] px-3 text-md';
		return `${base} ${sizeClass}`;
	});

	// Gatilho `unstyled` vive dentro de chips densos: o painel dele acompanha o
	// degrau `sm`, não o de campo de formulário.
	const panelTextClass = $derived(size === 'sm' || unstyled ? 'text-sm' : 'text-md');
</script>

<div bind:this={containerEl} class="relative w-full">
	<button
		bind:this={triggerEl}
		type="button"
		{id}
		{disabled}
		aria-haspopup="listbox"
		aria-expanded={open}
		aria-controls={listboxId}
		aria-label={ariaLabel ? `${ariaLabel}: ${triggerLabel}` : undefined}
		onclick={() => (open ? closePanel() : openPanel())}
		onkeydown={onTriggerKeydown}
		class={triggerClass}
	>
		{#if trigger}
			{@render trigger({ open, label: triggerLabel, selected })}
		{:else}
			<span class="flex min-w-0 items-center gap-2">
				{#if selected?.icon}
					<span class="flex shrink-0" style:color={selected.dot ?? 'var(--ds-color-text-brand)'}>
						{#if isStateIconId(selected.icon)}
							<StateIcon id={selected.icon} />
						{:else}
							<ProjectIcon id={selected.icon} />
						{/if}
					</span>
				{:else if selected && optionIcon}
					{@render optionIcon(selected)}
				{:else if selected?.dot}
					<span class="h-2 w-2 shrink-0 rounded-full" style:background={selected.dot}></span>
				{/if}
				<span class="truncate {isPlaceholder ? 'text-text-muted' : 'text-text-primary'}">
					{triggerLabel}
				</span>
			</span>
			<svg
				width="10"
				height="6"
				viewBox="0 0 10 6"
				class="shrink-0 text-text-muted transition-transform duration-fast"
				style:transform={open ? 'rotate(180deg)' : 'none'}
				aria-hidden="true"
			>
				<path
					d="M1 1 L5 5 L9 1"
					fill="none"
					stroke="currentColor"
					stroke-width="1.6"
					stroke-linecap="round"
					stroke-linejoin="round"
				/>
			</svg>
		{/if}
	</button>

	{#if open && panelPos}
		<div
			bind:this={panelEl}
			popover="manual"
			use:activatePopover
			role="listbox"
			id={listboxId}
			aria-label={ariaLabel}
			aria-activedescendant={highlightedIndex >= 0 ? itemId(highlightedIndex) : undefined}
			tabindex="-1"
			onkeydown={onPanelKeydown}
			class="sm-panel thin-scroll fixed z-dropdown w-max overflow-auto rounded-xl border border-border-subtle bg-surface p-1.5 shadow-lg"
			style:top={panelPos.top != null ? `${panelPos.top}px` : undefined}
			style:bottom={panelPos.bottom != null ? `${panelPos.bottom}px` : undefined}
			style:left={panelPos.left != null ? `${panelPos.left}px` : undefined}
			style:right={panelPos.right != null ? `${panelPos.right}px` : undefined}
			style:min-width="{panelPos.minWidth}px"
			style:max-width="{panelPos.maxWidth}px"
			style:max-height="{panelPos.maxHeight}px"
			style:transform-origin={panelPos.flip ? 'bottom center' : 'top center'}
		>
			{#if searchable}
				<div class="sticky top-0 z-[1] bg-surface pb-1.5 pt-0.5">
					<input
						bind:this={inputEl}
						bind:value={term}
						type="text"
						autocomplete="off"
						placeholder="Buscar..."
						aria-label="Buscar opção"
						class="w-full rounded-md border border-border-subtle bg-surface px-2.5 py-1.5 {panelTextClass} text-text-primary placeholder:text-text-muted focus:border-brand focus:outline-none"
					/>
				</div>
			{/if}

			{#if navItems.length === 0}
				<div class="px-2.5 py-6 text-center {panelTextClass} text-text-muted">
					Nenhuma opção encontrada
				</div>
			{:else}
				{#each navItems as item, index (item.isAll ? '__all__' : item.optValue)}
					{@const isSelected = item.isAll ? value == null : item.optValue === value}
					{@const isHighlighted = index === highlightedIndex}
					<div
						id={itemId(index)}
						role="option"
						aria-selected={isSelected}
						aria-disabled={item.option?.disabled || undefined}
						tabindex="-1"
						onclick={() => chooseItem(item)}
						onmouseenter={() => (highlightedIndex = index)}
						onkeydown={(e) => {
							if (e.key === 'Enter' || e.key === ' ') {
								e.preventDefault();
								chooseItem(item);
							}
						}}
						class="flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left {panelTextClass} transition-colors duration-fast {item
							.option?.disabled
							? 'cursor-not-allowed opacity-50'
							: 'cursor-pointer'} {isSelected ? 'bg-wash-brand' : isHighlighted ? 'bg-surface-muted' : ''}"
					>
						{#if item.option?.icon}
							<!-- Sem `dot` semântico, o ícone cai no azul de marca (nunca no texto escuro). -->
							<span
								class="flex shrink-0"
								style:color={item.option.dot ?? 'var(--ds-color-text-brand)'}
							>
								{#if isStateIconId(item.option.icon)}
									<StateIcon id={item.option.icon} />
								{:else}
									<ProjectIcon id={item.option.icon} />
								{/if}
							</span>
						{:else if item.option?.dot}
							<span class="h-2 w-2 shrink-0 rounded-full" style:background={item.option.dot}
							></span>
						{/if}
						{#if item.option && optionIcon}
							{@render optionIcon(item.option)}
						{/if}
						<span
							class="min-w-0 flex-1 truncate {item.isAll
								? 'font-semibold'
								: ''} {isSelected ? 'font-semibold text-brand' : 'text-text-primary'}"
						>
							{item.label}
						</span>
						{#if isSelected && !hideCheck}
							{@render checkIcon()}
						{/if}
					</div>
					{#if item.isAll}
						<div class="mx-1.5 my-1 h-px bg-border-subtle"></div>
					{/if}
				{/each}
			{/if}
		</div>
	{/if}
</div>

{#snippet checkIcon()}
	<svg width="12" height="12" viewBox="0 0 12 12" class="ml-1.5 shrink-0 text-brand" aria-hidden="true">
		<path
			d="M2 6.5 L4.8 9.2 L10 3"
			fill="none"
			stroke="currentColor"
			stroke-width="1.8"
			stroke-linecap="round"
			stroke-linejoin="round"
		/>
	</svg>
{/snippet}

<style>
	.sm-panel {
		/* Neutraliza a UA stylesheet de [popover] (inset:0 + margin:auto), que
		   competiria com os top/left/right/bottom inline calculados em JS. */
		margin: 0;
		inset: auto;
		animation: sm-in 0.16s ease-out;
	}
	@keyframes sm-in {
		from {
			opacity: 0;
			transform: scale(0.97);
		}
		to {
			opacity: 1;
			transform: scale(1);
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.sm-panel {
			animation-duration: 1ms;
		}
	}
</style>
