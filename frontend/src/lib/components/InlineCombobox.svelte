<script lang="ts">
	/**
	 * Combobox inline single-select pesquisável, CONTROLADO por callback.
	 *
	 * Estado fechado: mostra o valor como um "chip/valor clicável" (paridade
	 * visual com os cartões do detalhe do projeto), não um input nu — clicar
	 * (ou ArrowDown/Enter/Space) abre o input de filtro + listbox.
	 *
	 * Espelha o combobox ABEP de `CriarProjetoModal.svelte` (input `role=combobox`
	 * + `ul role=listbox`, setas/Enter/Esc, `aria-activedescendant`,
	 * `onmousedown preventDefault` nas opções, `onblur setTimeout(close,120)`) e a
	 * a11y de `OrgaoFormFields.svelte`.
	 *
	 * O componente NÃO chama API — emite `onSelect(value)` (só quando o valor
	 * muda); a página orquestra e devolve `pending`/`error` (UI otimista).
	 */
	import { tick } from 'svelte';

	interface InlineComboboxOption {
		value: string; // valor canônico enviado ao backend
		label: string; // texto exibido/filtrado
		sublabel?: string; // 2ª linha opcional (ex.: nome do órgão sob a sigla)
	}

	interface Props {
		fieldId: string; // base para ids (listbox/options/erro)
		label: string; // aria-label ("Área Responsável, editar")
		/** valor atual selecionado (value canônico) ou null. */
		value: string | null;
		/** texto a exibir no estado fechado quando há valor (ex.: sigla). */
		displayLabel?: string | null;
		options: InlineComboboxOption[];
		placeholder?: string; // estado vazio do input de filtro: "Selecionar…"
		emptyLabel?: string; // texto quando value === null (default "—")
		noResultsLabel?: string; // default "Nenhum resultado encontrado"
		readonly?: boolean;
		pending?: boolean; // "salvando" (esmaece + desabilita)
		error?: string | null;
		icon?: string; // classe FA opcional (ex.: "fas fa-sitemap")
		/** Textos longos (ex.: descrições EEGG) quebram linha em vez de truncar. */
		wrap?: boolean;
		/** Chamado ao escolher uma opção (Enter/clique). NÃO chamado se value não mudou. */
		onSelect: (value: string) => void;
		/** Opcional: fechar sem selecionar (Esc/blur sem escolha). */
		onCancel?: () => void;
	}

	let {
		fieldId,
		label,
		value,
		displayLabel = null,
		options,
		placeholder = 'Selecionar…',
		emptyLabel = '—',
		noResultsLabel = 'Nenhum resultado encontrado',
		readonly = false,
		pending = false,
		error = null,
		icon = '',
		wrap = false,
		onSelect,
		onCancel
	}: Props = $props();

	let open = $state(false);
	let term = $state('');
	let activeIndex = $state(-1);
	let inputEl = $state<HTMLInputElement | null>(null);

	const listboxId = $derived(`${fieldId}-listbox`);
	const errorId = $derived(`${fieldId}-error`);

	// Rótulo da opção atualmente casada com o `value` (para o estado fechado).
	const matchedLabel = $derived.by(() => {
		if (value === null) return null;
		return options.find((o) => o.value === value)?.label ?? null;
	});
	// O que o botão fechado exibe: displayLabel > label da opção casada > vazio.
	const closedLabel = $derived(displayLabel ?? matchedLabel);
	const hasValue = $derived(closedLabel !== null && closedLabel !== '');

	/** Subconjunto que casa com o texto digitado (label/value/sublabel). */
	const visible = $derived.by(() => {
		const q = term.trim().toLowerCase();
		if (!q) return options;
		return options.filter(
			(o) =>
				o.label.toLowerCase().includes(q) ||
				o.value.toLowerCase().includes(q) ||
				(o.sublabel?.toLowerCase().includes(q) ?? false)
		);
	});

	async function openList(): Promise<void> {
		if (readonly || pending) return;
		open = true;
		term = '';
		activeIndex = -1;
		await tick();
		inputEl?.focus();
	}

	function closeList(): void {
		open = false;
		activeIndex = -1;
		term = '';
	}

	function cancel(): void {
		closeList();
		onCancel?.();
	}

	function choose(option: InlineComboboxOption): void {
		closeList();
		// Só emite quando o valor canônico realmente muda (paridade com a spec).
		if (option.value !== value) onSelect(option.value);
	}

	function onKeydown(event: KeyboardEvent): void {
		const list = visible;
		if (event.key === 'Escape') {
			event.preventDefault();
			cancel();
			return;
		}
		if (event.key === 'Tab') {
			closeList();
			return;
		}
		if (event.key === 'ArrowDown') {
			event.preventDefault();
			if (!list.length) return;
			activeIndex = Math.min(activeIndex + 1, list.length - 1);
			return;
		}
		if (event.key === 'ArrowUp') {
			event.preventDefault();
			if (!list.length) return;
			activeIndex = Math.max(activeIndex - 1, 0);
			return;
		}
		if (event.key === 'Home') {
			event.preventDefault();
			if (list.length) activeIndex = 0;
			return;
		}
		if (event.key === 'End') {
			event.preventDefault();
			if (list.length) activeIndex = list.length - 1;
			return;
		}
		if (event.key === 'Enter') {
			if (activeIndex >= 0 && activeIndex < list.length) {
				event.preventDefault();
				choose(list[activeIndex]);
			}
		}
	}

	// Abre via teclado a partir do botão fechado (ArrowDown/Enter/Space).
	function onClosedKeydown(event: KeyboardEvent): void {
		if (event.key === 'ArrowDown' || event.key === 'Enter' || event.key === ' ') {
			event.preventDefault();
			void openList();
		}
	}
</script>

<div class="inline-combobox" class:is-pending={pending}>
	{#if open}
		<input
			bind:this={inputEl}
			bind:value={term}
			type="text"
			autocomplete="off"
			role="combobox"
			aria-label={label}
			aria-expanded="true"
			aria-haspopup="listbox"
			aria-controls={listboxId}
			aria-autocomplete="list"
			aria-activedescendant={activeIndex >= 0 ? `${fieldId}-option-${activeIndex}` : undefined}
			aria-invalid={error ? 'true' : undefined}
			aria-describedby={error ? errorId : undefined}
			{placeholder}
			disabled={pending}
			onkeydown={onKeydown}
			onblur={() => setTimeout(closeList, 120)}
			class="ic-input w-full rounded-md border border-border-subtle bg-surface px-2 text-sm leading-tight text-text-primary placeholder:text-text-muted focus:outline-none focus-visible:ring-1 focus-visible:ring-primary-500 {wrap
				? 'h-9'
				: 'h-7'}"
		/>
		<ul
			id={listboxId}
			role="listbox"
			aria-label={label}
			class="ic-listbox app-dropdown-in absolute left-0 right-0 top-full z-20 mt-1 max-h-64 overflow-auto rounded-md border border-border-subtle bg-surface py-1 shadow-md"
		>
			{#if visible.length === 0}
				<li class="px-3 py-2 text-sm text-text-muted">{noResultsLabel}</li>
			{:else}
				{#each visible as option, index (option.value)}
					<li class="contents">
						<button
							type="button"
							id={`${fieldId}-option-${index}`}
							role="option"
							aria-selected={option.value === value}
							onmousedown={(e) => e.preventDefault()}
							onclick={() => choose(option)}
							class="block w-full cursor-pointer px-3 py-2 text-left text-text-primary transition-colors duration-fast hover:bg-surface-muted active:scale-[.98] {index ===
							activeIndex
								? 'bg-surface-muted'
								: ''}"
						>
							<span class="block text-sm {wrap ? 'whitespace-normal break-words' : 'truncate'}"
								>{option.label}</span
							>
							{#if option.sublabel}
								<span class="block text-xs text-text-muted {wrap ? 'whitespace-normal break-words' : 'truncate'}"
									>{option.sublabel}</span
								>
							{/if}
						</button>
					</li>
				{/each}
			{/if}
		</ul>
	{:else}
		<button
			type="button"
			role="combobox"
			aria-label={label}
			aria-expanded="false"
			aria-haspopup="listbox"
			aria-controls={listboxId}
			aria-invalid={error ? 'true' : undefined}
			aria-describedby={error ? errorId : undefined}
			disabled={readonly || pending}
			onclick={openList}
			onkeydown={onClosedKeydown}
			class="ic-closed group flex w-full gap-2 rounded-md border border-transparent px-2 text-left text-sm transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 {wrap
				? 'min-h-9 items-start py-1.5'
				: 'h-7 items-center'}"
			class:is-empty={!hasValue}
		>
			{#if icon}
				<i class="{icon} shrink-0 text-primary-600 {wrap ? 'mt-0.5' : ''}" aria-hidden="true"></i>
			{/if}
			<span
				class="ic-value min-w-0 flex-1 {wrap ? 'whitespace-normal break-words' : 'truncate'} {hasValue
					? 'text-text-primary'
					: 'text-text-muted'}"
			>
				{hasValue ? closedLabel : emptyLabel}
			</span>
			{#if pending}
				<i class="fas fa-spinner fa-spin shrink-0 text-text-muted {wrap ? 'mt-0.5' : ''}" aria-hidden="true"></i>
			{:else}
				<i
					class="fas fa-chevron-down shrink-0 text-xs text-text-muted opacity-0 transition-opacity duration-fast group-hover:opacity-100 group-focus-visible:opacity-100 {wrap
						? 'mt-1'
						: ''}"
					aria-hidden="true"
				></i>
			{/if}
		</button>
	{/if}

	{#if error}
		<span id={errorId} role="alert" class="ic-error">{error}</span>
	{/if}
</div>

<style>
	.inline-combobox {
		position: relative;
		display: block;
		width: 100%;
	}
	.inline-combobox.is-pending {
		opacity: 0.6;
	}

	/* Afordância editável: sublinhado tracejado sob o valor no hover/focus. */
	.ic-closed .ic-value {
		border-bottom: 1px dashed transparent;
		transition: border-color 0.16s ease;
	}
	.ic-closed:hover:not(:disabled) .ic-value,
	.ic-closed:focus-visible .ic-value {
		border-bottom-color: var(--color-border, #c4d5e7);
	}
	.ic-closed.is-empty .ic-value {
		font-style: italic;
	}

	/* Animação do painel (paridade `app-dropdown-in` do AppTopnav). */
	.app-dropdown-in {
		transform-origin: top center;
		animation: ic-dropdown-in 0.16s ease-out;
	}
	@keyframes ic-dropdown-in {
		from {
			opacity: 0;
			transform: scale(0.95);
		}
		to {
			opacity: 1;
			transform: scale(1);
		}
	}

	.ic-error {
		display: block;
		margin-top: 0.2rem;
		font-size: 0.72rem;
		color: var(--app-color-danger, #b42323);
	}

	@media (prefers-reduced-motion: reduce) {
		.app-dropdown-in {
			animation-duration: 1ms;
		}
		.ic-closed .ic-value {
			transition-duration: 1ms;
		}
	}
</style>
