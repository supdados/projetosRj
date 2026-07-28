<script lang="ts">
	/**
	 * Seletor de órgão em ÁRVORE expansível (design 1a), substituto dos `<select>`
	 * alfabéticos. Recebe a lista PLANA de `serialize_orgao_option` e monta a
	 * hierarquia client-side por `pai_id` (órfãos viram raízes; a ordem de chegada
	 * entre irmãos é preservada, sem reordenação alfabética).
	 *
	 * Controlado por callback: emite `onSelect(value)` e mantém o estado de
	 * expansão da sessão (reabrir preserva o que o usuário expandiu/recolheu).
	 */
	import { tick } from 'svelte';
	import type { OrgaoSelectOption } from '$lib/types/orgaoTreeSelect';
	import {
		normalizeSearchText,
		buildOrgaoTree,
		computeDefaultExpanded,
		buildOrgaoTreeRows,
		type OrgaoTreeNode,
		type OrgaoTreeRow
	} from '$lib/utils/orgaoTree';

	interface Props {
		options: OrgaoSelectOption[];
		value: number | null;
		onSelect: (value: number | null) => void;
		placeholder?: string;
		allowTodos?: boolean;
		todosLabel?: string;
		disabled?: boolean;
		id?: string;
		ariaLabel?: string;
		/** Rótulo exibido quando `value` não está em `options` (ex.: órgão fora do escopo). */
		fallbackLabel?: string | null;
	}

	let {
		options,
		value,
		onSelect,
		placeholder = 'Selecionar unidade...',
		allowTodos = false,
		todosLabel = 'Todos os órgãos',
		disabled = false,
		id,
		ariaLabel,
		fallbackLabel = null
	}: Props = $props();

	let open = $state(false);
	let term = $state('');
	let inputEl = $state<HTMLInputElement | null>(null);
	let containerEl = $state<HTMLDivElement | null>(null);
	let triggerEl = $state<HTMLButtonElement | null>(null);
	// Override manual de expansão por nó — prevalece sobre o default da spec.
	let overrides = $state<Map<number, boolean>>(new Map());

	const listboxId = $derived(id ? `${id}-listbox` : 'orgao-tree-listbox');

	const norm = normalizeSearchText;

	const tree = $derived.by<OrgaoTreeNode<OrgaoSelectOption>[]>(() => buildOrgaoTree(options));

	const defaultExpanded = $derived.by<Set<number>>(() => computeDefaultExpanded(tree));

	const isExpanded = (v: number): boolean =>
		overrides.has(v) ? overrides.get(v)! : defaultExpanded.has(v);

	function toggle(v: number): void {
		const next = new Map(overrides);
		next.set(v, !isExpanded(v));
		overrides = next;
	}

	const rows = $derived.by<OrgaoTreeRow<OrgaoSelectOption>[]>(() =>
		buildOrgaoTreeRows(tree, isExpanded, term)
	);

	const selected = $derived(
		value == null ? null : (options.find((o) => Number(o.value) === Number(value)) ?? null)
	);

	const triggerLabel = $derived.by<string>(() => {
		if (selected) return selected.sigla || selected.nome || String(selected.value);
		if (value != null && fallbackLabel) return fallbackLabel;
		if (allowTodos) return todosLabel;
		return placeholder;
	});

	const isPlaceholder = $derived(!selected && !(value != null && fallbackLabel) && !allowTodos);

	async function openPanel(): Promise<void> {
		if (disabled) return;
		open = true;
		term = '';
		await tick();
		inputEl?.focus();
	}

	function closePanel(): void {
		open = false;
	}

	function chooseNode(v: number): void {
		onSelect(v);
		closePanel();
	}

	function chooseTodos(): void {
		onSelect(null);
		closePanel();
	}

	function onTriggerKeydown(event: KeyboardEvent): void {
		if (event.key === 'Escape' && open) {
			event.preventDefault();
			closePanel();
			return;
		}
		if (event.key === 'ArrowDown' || event.key === 'Enter' || event.key === ' ') {
			event.preventDefault();
			void openPanel();
		}
	}

	function onPanelKeydown(event: KeyboardEvent): void {
		if (event.key === 'Escape') {
			event.preventDefault();
			closePanel();
			triggerEl?.focus();
			return;
		}
		// O campo de busca é o único input do painel: sem isto, Enter dispara o
		// submit implícito do <form> que envolve o seletor.
		if (event.key === 'Enter' && event.target === inputEl) event.preventDefault();
	}

	// Fecha ao clicar fora do componente.
	$effect(() => {
		if (!open) return;
		const onPointerDown = (event: PointerEvent): void => {
			if (containerEl && !containerEl.contains(event.target as Node)) closePanel();
		};
		window.addEventListener('pointerdown', onPointerDown, true);
		return () => window.removeEventListener('pointerdown', onPointerDown, true);
	});
</script>

<div bind:this={containerEl} class="ots relative w-full">
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
		class="flex h-[var(--control-h-md)] w-full items-center justify-between gap-2 rounded-lg border border-border-subtle bg-surface px-3 text-left text-sm transition-colors duration-fast hover:border-brand focus:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-50"
	>
		<span class="truncate {isPlaceholder ? 'text-text-muted' : 'text-text-primary'}">
			{triggerLabel}
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
	</button>

	{#if open}
		<div
			role="listbox"
			id={listboxId}
			aria-label="Selecionar unidade"
			tabindex="-1"
			onkeydown={onPanelKeydown}
			class="ots-panel thin-scroll absolute left-0 top-full z-30 mt-1.5 max-h-[360px] w-max min-w-full max-w-[420px] overflow-auto rounded-xl border border-border-subtle bg-surface p-1.5 shadow-lg"
		>
			<div class="sticky top-0 z-[1] bg-surface pb-1.5 pt-0.5">
				<input
					bind:this={inputEl}
					bind:value={term}
					type="text"
					autocomplete="off"
					placeholder="Buscar sigla ou nome..."
					aria-label="Buscar órgão"
					class="w-full rounded-md border border-border-subtle bg-surface px-2.5 py-1.5 text-[12.5px] text-text-primary placeholder:text-text-muted focus:border-brand focus:outline-none"
				/>
			</div>

			{#if allowTodos && !term.trim()}
				<button
					type="button"
					role="option"
					aria-selected={value == null}
					onclick={chooseTodos}
					class="flex w-full items-center justify-between rounded-md px-2.5 py-1.5 text-left text-[12.5px] font-medium transition-colors duration-fast hover:bg-surface-muted {value ==
					null
						? 'bg-wash-brand text-brand'
						: 'text-text-primary'}"
				>
					<span>{todosLabel}</span>
					{#if value == null}
						{@render checkIcon()}
					{/if}
				</button>
				<div class="mx-1.5 my-1 h-px bg-border-subtle"></div>
			{/if}

			{#if rows.length === 0}
				<div class="px-2.5 py-6 text-center text-[12.5px] text-text-muted">
					Nenhuma unidade encontrada
				</div>
			{:else}
				{#each rows as row (row.value)}
					{@const isSelected = value != null && row.value === Number(value)}
					<div
						role="option"
						aria-selected={isSelected}
						tabindex="-1"
						onclick={() => chooseNode(row.value)}
						onkeydown={(e) => {
							if (e.key === 'Enter' || e.key === ' ') {
								e.preventDefault();
								chooseNode(row.value);
							}
						}}
						class="flex min-h-[30px] cursor-pointer items-center rounded-md pr-2 transition-colors duration-fast hover:bg-surface-muted {isSelected
							? 'bg-wash-brand'
							: ''}"
					>
						{#if !row.isSearch}
							<div class="shrink-0" style:width="{row.depth * 14}px"></div>
						{/if}
						<div class="flex h-[22px] w-[22px] shrink-0 items-center justify-center">
							{#if row.hasChildren}
								<button
									type="button"
									tabindex="-1"
									aria-label={row.expanded ? 'Recolher' : 'Expandir'}
									onclick={(e) => {
										e.stopPropagation();
										toggle(row.value);
									}}
									class="flex h-[22px] w-[22px] items-center justify-center rounded text-text-muted transition-colors duration-fast hover:bg-border-subtle"
								>
									<svg
										width="10"
										height="10"
										viewBox="0 0 10 10"
										class="transition-transform duration-fast"
										style:transform={row.expanded ? 'rotate(90deg)' : 'none'}
										aria-hidden="true"
									>
										<path
											d="M3 1.5 L7 5 L3 8.5"
											fill="none"
											stroke="currentColor"
											stroke-width="1.6"
											stroke-linecap="round"
											stroke-linejoin="round"
										/>
									</svg>
								</button>
							{:else}
								<span class="h-[5px] w-[5px] rounded-full bg-brand" aria-hidden="true"></span>
							{/if}
						</div>
						<span class="min-w-0 flex-1 truncate" title={row.option.nome ?? undefined}>
							{#if row.path}<span class="font-mono text-[11px] text-text-muted">{row.path} › </span
								>{/if}<span class="font-mono text-[11.5px] font-medium text-text-primary"
								>{row.option.sigla ?? row.option.nome ?? ''}</span
							>
						</span>
						{#if isSelected}
							{@render checkIcon()}
						{/if}
					</div>
				{/each}
			{/if}
		</div>
	{/if}
</div>

{#snippet checkIcon()}
	<svg
		width="12"
		height="12"
		viewBox="0 0 12 12"
		class="ml-1.5 shrink-0 text-brand"
		aria-hidden="true"
	>
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
	.ots-panel {
		transform-origin: top center;
		animation: ots-in 0.16s ease-out;
	}
	@keyframes ots-in {
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
		.ots-panel {
			animation-duration: 1ms;
		}
	}
</style>
