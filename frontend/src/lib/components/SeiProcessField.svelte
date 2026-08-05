<script lang="ts">
	/**
	 * Campo de MÚLTIPLOS processos SEI, compartilhado pelo card "Detalhes do
	 * Projeto" e pelo CriarProjetoModal.
	 *
	 * Linha fechada (visual de campo): primeiro número + botão copiar (SEM
	 * precisar abrir) + chip "+N" quando há mais + chevron que abre o popover.
	 * Popover: todos os números (copiar/remover por item) e rodapé de adição
	 * com prefixo "SEI-" fixo — o usuário digita só os dígitos; colar o número
	 * já com "SEI-" é normalizado pela máscara.
	 *
	 * SEM nenhum número o popover não existe: clicar na linha abre o campo de
	 * adição ali mesmo. Dropdown só a partir do segundo número, quando há de
	 * fato uma lista para listar.
	 *
	 * CONTROLADO por callback (não chama API): `onSave(lista)` envia a lista
	 * completa (substituição). No detalhe a página persiste via /inline e
	 * devolve `pending`/`error`; no modal a lista é estado local até o submit.
	 */
	import { tick } from 'svelte';
	import { seiDigitsOnly, formatSeiDigits, hasMinimumSeiDigits } from '$lib/utils/seiFormat';
	import { flash } from '$lib/stores/flash';

	interface Props {
		fieldId: string;
		/** Opcional: backend do release anterior não emite a chave (rolling deploy). */
		processes?: string[];
		readonly?: boolean;
		pending?: boolean;
		error?: string | null;
		/** Sem moldura própria: para uso dentro de um bloco que já tem a sua. */
		bare?: boolean;
		onSave: (list: string[]) => void;
	}

	let {
		fieldId,
		processes = [],
		readonly = false,
		pending = false,
		error = null,
		bare = false,
		onSave
	}: Props = $props();

	let open = $state(false);
	let inlineAdding = $state(false);
	let draftDigits = $state('');
	let copiedIndex = $state<number | null>(null);
	let copyResetTimer: ReturnType<typeof setTimeout> | null = null;
	let draftInputEl = $state<HTMLInputElement | null>(null);
	let triggerEl = $state<HTMLButtonElement | null>(null);
	// Lista otimista: mostrada até o prop `processes` alcançar (mecânica do
	// InlineEditField) — sem ela o campo pisca de volta enquanto a API responde.
	let optimisticList = $state<string[] | null>(null);
	let sawPending = $state(false);

	const errorId = $derived(`${fieldId}-error`);
	const popoverId = $derived(`${fieldId}-popover`);
	const shownList = $derived(optimisticList ?? processes);
	const firstNumber = $derived(shownList[0] ?? null);
	const extraCount = $derived(Math.max(0, shownList.length - 1));
	const draftFormatted = $derived(formatSeiDigits(draftDigits));
	const canAddDraft = $derived(hasMinimumSeiDigits(draftDigits) && !pending);
	// Popover só existe quando há número para listar; com a lista vazia a adição
	// acontece na própria linha.
	const canOpen = $derived(shownList.length > 0);
	const canInlineAdd = $derived(!readonly && shownList.length === 0);

	$effect(() => {
		if (optimisticList === null) {
			sawPending = false;
			return;
		}
		if (pending) {
			sawPending = true;
			return;
		}
		if (JSON.stringify(processes) === JSON.stringify(optimisticList) || error || sawPending) {
			optimisticList = null;
			sawPending = false;
		}
	});

	function saveList(next: string[]): void {
		optimisticList = next;
		onSave(next);
	}

	async function copyNumber(numero: string, index: number): Promise<void> {
		try {
			await navigator.clipboard.writeText(numero);
			copiedIndex = index;
			if (copyResetTimer) clearTimeout(copyResetTimer);
			copyResetTimer = setTimeout(() => {
				copiedIndex = null;
			}, 1700);
		} catch {
			flash.danger('Não foi possível copiar o número do processo SEI.', {
				key: 'sei-copy-number'
			});
		}
	}

	function onTriggerClick(): void {
		if (open) {
			closePopover();
			return;
		}
		if (canInlineAdd) {
			startInlineAdd();
			return;
		}
		togglePopover();
	}

	function startInlineAdd(): void {
		inlineAdding = true;
		draftDigits = '';
		void tick().then(() => draftInputEl?.focus());
	}

	function cancelInlineAdd(): void {
		if (!inlineAdding) return;
		inlineAdding = false;
		draftDigits = '';
	}

	function togglePopover(): void {
		if (!canOpen) return;
		open = !open;
		if (!open) {
			draftDigits = '';
			return;
		}
		// Foco programático ao abrir: Safari/Firefox NÃO focam <button> no clique,
		// e sem foco dentro do wrapper o fechamento por focusout nunca dispara.
		void tick().then(() => {
			(draftInputEl ?? triggerEl)?.focus();
		});
	}

	function closePopover(): void {
		if (!open) return;
		open = false;
		draftDigits = '';
	}

	function closeAndRefocus(): void {
		closePopover();
		cancelInlineAdd();
		void tick().then(() => triggerEl?.focus());
	}

	function onWrapperFocusOut(event: FocusEvent): void {
		const wrapper = event.currentTarget as HTMLElement;
		// Blur para fora do wrapper fecha (timeout no padrão do InlineCombobox:
		// deixa o clique em botões internos resolver antes).
		setTimeout(() => {
			if (wrapper.contains(document.activeElement)) return;
			closePopover();
			cancelInlineAdd();
		}, 120);
	}

	function onDraftInput(event: Event): void {
		const input = event.currentTarget as HTMLInputElement;
		draftDigits = seiDigitsOnly(input.value);
		input.value = draftFormatted;
	}

	function addDraft(): void {
		if (!canAddDraft) return;
		const candidate = `SEI-${draftFormatted}`;
		// Duplicata vira no-op local: o backend deduplicaria de qualquer forma e a
		// lista otimista não pode ter chave repetida no {#each}.
		if (!shownList.some((n) => n.toLowerCase() === candidate.toLowerCase())) {
			saveList([...shownList, candidate]);
		}
		draftDigits = '';
		// Adição na linha é de um número só: com a lista preenchida o próximo
		// entra pelo popover.
		if (inlineAdding) {
			inlineAdding = false;
			void tick().then(() => triggerEl?.focus());
			return;
		}
		draftInputEl?.focus();
	}

	function removeAt(index: number): void {
		saveList(shownList.filter((_, i) => i !== index));
		// Ancora o foco no input: o botão × fica disabled no pending e um botão
		// focado que desabilita derruba o foco para o body (fecharia o popover).
		draftInputEl?.focus();
	}

	function onDraftKeydown(event: KeyboardEvent): void {
		if (event.key === 'Enter') {
			event.preventDefault();
			addDraft();
		}
	}

	// Escape fecha o popover onde quer que o foco esteja (input ou botões).
	// stopPropagation no wrapper: sem ele o mesmo Esc borbulha até o modal
	// hospedeiro e dispara a ação de fase (voltar/fechar) junto.
	function onWrapperKeydown(event: KeyboardEvent): void {
		if ((open || inlineAdding) && event.key === 'Escape') {
			event.preventDefault();
			event.stopPropagation();
			closeAndRefocus();
		}
	}

	function onWindowKeydown(event: KeyboardEvent): void {
		if ((open || inlineAdding) && event.key === 'Escape') {
			event.preventDefault();
			closeAndRefocus();
		}
	}
</script>

{#snippet copyIcon()}
	<svg
		viewBox="0 0 24 24"
		class="h-3.5 w-3.5"
		fill="none"
		stroke="currentColor"
		stroke-width="2"
		stroke-linecap="round"
		stroke-linejoin="round"
		aria-hidden="true"
	>
		<rect x="9" y="9" width="13" height="13" rx="2" />
		<path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
	</svg>
{/snippet}

{#snippet checkIcon()}
	<svg
		viewBox="0 0 24 24"
		class="h-3.5 w-3.5"
		fill="none"
		stroke="currentColor"
		stroke-width="2"
		stroke-linecap="round"
		stroke-linejoin="round"
		aria-hidden="true"
	>
		<path d="M5 13l4.5 4.5L19 7" />
	</svg>
{/snippet}

{#snippet draftControls()}
	<span aria-hidden="true" class="shrink-0 text-sm font-semibold text-text-muted">SEI-</span>
	<!-- NÃO desabilitar no pending: o input segura o foco do popover e
	     disabled derruba o foco para o body, fechando via focusout no
	     meio de remoções consecutivas (adicionar já é barrado por
	     canAddDraft). -->
	<input
		bind:this={draftInputEl}
		id={`${fieldId}-input`}
		type="text"
		inputmode="numeric"
		autocomplete="off"
		placeholder="000000/000000/0000"
		aria-label="Novo número de processo SEI (somente números)"
		value={draftFormatted}
		oninput={onDraftInput}
		onkeydown={onDraftKeydown}
		class="h-7 min-w-0 flex-1 rounded-md border border-border-subtle bg-surface px-2 text-sm text-text-primary placeholder:text-text-muted focus:border-brand focus:outline-none"
	/>
	<button
		type="button"
		disabled={!canAddDraft}
		onmousedown={(e) => e.preventDefault()}
		onclick={addDraft}
		aria-label="Adicionar processo SEI"
		title="Adicionar"
		class="grid h-7 w-7 flex-none place-items-center rounded-md text-text-muted transition-colors duration-fast hover:bg-surface hover:text-brand active:scale-95 disabled:cursor-not-allowed disabled:opacity-60 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
	>
		<svg
			viewBox="0 0 24 24"
			class="h-3.5 w-3.5"
			fill="none"
			stroke="currentColor"
			stroke-width="2"
			stroke-linecap="round"
			aria-hidden="true"
		>
			<path d="M12 5v14M5 12h14" />
		</svg>
	</button>
{/snippet}

<svelte:window onkeydown={onWindowKeydown} />

<!-- svelte-ignore a11y_no_static_element_interactions -->
<div class="relative" onfocusout={onWrapperFocusOut} onkeydown={onWrapperKeydown}>
	<!-- Linha fechada: visual de campo com o 1º número + copiar + chip +N + chevron. -->
	<!-- Token de altura padrão de campo — linha de Detalhes alinhada. -->
	<div
		class="flex items-center gap-1.5 {bare
			? 'min-h-6'
			: 'h-[var(--control-h-md)] rounded-lg border border-border-subtle bg-surface pl-3 pr-1.5'}"
	>
		{#if inlineAdding}
			{@render draftControls()}
		{:else}
			<button
				bind:this={triggerEl}
				type="button"
				id={fieldId}
				disabled={!canOpen && !canInlineAdd}
				aria-expanded={open}
				aria-haspopup={canOpen ? 'true' : undefined}
				aria-controls={canOpen ? popoverId : undefined}
				aria-label={shownList.length
					? `Processos SEI: ${shownList.length}. Abrir lista`
					: 'Processos SEI: nenhum. Adicionar número'}
				onclick={onTriggerClick}
				class="flex min-w-0 flex-1 items-center text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-default {bare &&
				!firstNumber
					? 'sei-vazio'
					: 'h-full cursor-pointer'}"
			>
				<span
					class="truncate {bare ? 'text-md' : 'text-sm'} {firstNumber
						? 'text-text-primary'
						: 'italic text-text-muted'}"
				>
					{firstNumber ?? 'Não informado'}
				</span>
			</button>
		{/if}

		{#if firstNumber && !inlineAdding}
			<button
				type="button"
				title={copiedIndex === -1 ? 'Número copiado!' : 'Copiar número'}
				aria-label={copiedIndex === -1 ? 'Número copiado' : `Copiar ${firstNumber}`}
				onmousedown={(e) => e.preventDefault()}
				onclick={() => void copyNumber(firstNumber, -1)}
				class="grid h-7 w-7 flex-none place-items-center rounded-md transition-colors duration-fast hover:bg-surface-muted hover:text-brand active:scale-95 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand {copiedIndex ===
				-1
					? 'text-brand'
					: 'text-text-muted'}"
			>
				{#if copiedIndex === -1}
					{@render checkIcon()}
				{:else}
					{@render copyIcon()}
				{/if}
			</button>
		{/if}

		{#if extraCount > 0}
			<span
				class="inline-flex h-5 shrink-0 items-center rounded-full bg-wash-neutral px-2 text-xs font-semibold text-brand"
			>
				+{extraCount}
			</span>
		{/if}

		{#if canOpen && !inlineAdding}
			<button
				type="button"
				tabindex="-1"
				aria-hidden="true"
				disabled={pending}
				onmousedown={(e) => e.preventDefault()}
				onclick={togglePopover}
				class="grid h-7 w-7 flex-none place-items-center rounded-md text-text-muted transition-colors duration-fast hover:bg-surface-muted hover:text-brand active:scale-95 disabled:opacity-60 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
			>
				{#if pending}
					<svg class="h-3.5 w-3.5 animate-spin" viewBox="0 0 24 24" fill="none" aria-hidden="true">
						<circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="3" class="opacity-25" />
						<path d="M22 12a10 10 0 0 0-10-10" stroke="currentColor" stroke-width="3" stroke-linecap="round" />
					</svg>
				{:else}
					<svg
						viewBox="0 0 24 24"
						class="h-3.5 w-3.5 transition-transform duration-fast {open ? 'rotate-180' : ''}"
						fill="none"
						stroke="currentColor"
						stroke-width="2"
						stroke-linecap="round"
						stroke-linejoin="round"
						aria-hidden="true"
					>
						<path d="M6 9l6 6 6-6" />
					</svg>
				{/if}
			</button>
		{/if}
	</div>

	{#if open}
		<div
			id={popoverId}
			role="group"
			aria-label="Processos SEI do projeto"
			class="app-dropdown-in absolute left-0 right-0 top-full z-20 mt-1 max-h-64 overflow-auto rounded-md border border-border-subtle bg-surface py-1 shadow-md"
		>
			{#if shownList.length}
				<ul class="flex flex-col">
					{#each shownList as numero, index (numero)}
						<li class="flex items-center gap-1.5 px-3 py-1.5 hover:bg-surface-muted">
							<span class="min-w-0 flex-1 truncate text-sm text-text-primary">{numero}</span>
							<button
								type="button"
								title={copiedIndex === index ? 'Número copiado!' : 'Copiar número'}
								aria-label={copiedIndex === index ? 'Número copiado' : `Copiar ${numero}`}
								onmousedown={(e) => e.preventDefault()}
								onclick={() => void copyNumber(numero, index)}
								class="grid h-7 w-7 flex-none place-items-center rounded-md transition-colors duration-fast hover:bg-surface hover:text-brand active:scale-95 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand {copiedIndex ===
								index
									? 'text-brand'
									: 'text-text-muted'}"
							>
								{#if copiedIndex === index}
									{@render checkIcon()}
								{:else}
									{@render copyIcon()}
								{/if}
							</button>
							{#if !readonly}
								<button
									type="button"
									title="Remover número"
									aria-label={`Remover ${numero}`}
									disabled={pending}
									onmousedown={(e) => e.preventDefault()}
									onclick={() => removeAt(index)}
									class="grid h-7 w-7 flex-none place-items-center rounded-md text-text-muted transition-colors duration-fast hover:bg-surface hover:text-danger active:scale-95 disabled:opacity-60 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
								>
									<svg
										viewBox="0 0 24 24"
										class="h-3.5 w-3.5"
										fill="none"
										stroke="currentColor"
										stroke-width="2"
										stroke-linecap="round"
										aria-hidden="true"
									>
										<path d="M6 6l12 12M18 6L6 18" />
									</svg>
								</button>
							{/if}
						</li>
					{/each}
				</ul>
			{/if}

			{#if !readonly}
				<div
					class="flex items-center gap-1.5 px-3 pb-1.5 {shownList.length
						? 'mt-1 border-t border-border-subtle pt-2'
						: 'pt-1.5'}"
				>
					{@render draftControls()}
				</div>
			{/if}
		</div>
	{/if}

	<span aria-live="polite" class="sr-only">
		{copiedIndex !== null ? 'Número copiado para a área de transferência' : ''}
	</span>

	{#if error}
		<span id={errorId} role="alert" class="sei-error">{error}</span>
	{/if}
</div>

<style>
	/* Animação do painel (paridade `app-dropdown-in` do InlineCombobox). */
	.app-dropdown-in {
		transform-origin: top center;
		animation: sei-dropdown-in 0.16s ease-out;
	}
	@keyframes sei-dropdown-in {
		from {
			opacity: 0;
			transform: scale(0.95);
		}
		to {
			opacity: 1;
			transform: scale(1);
		}
	}

	/* Vazio: mesma moldura tracejada do .editable-field vazio (InlineEditField) —
	   na ficha o campo tem de convidar o clique igual ao Órgão ao lado. */
	.sei-vazio {
		/* Cursor de texto: vazio o clique abre o input ali mesmo (escrita), não um
		   menu. A mãozinha volta a partir do 1º número, quando o clique abre o
		   popover. */
		min-height: 1.75rem;
		padding: 0.18rem 0.4rem;
		border: 1px dashed var(--ds-color-border-base);
		border-radius: 8px;
		transition:
			background-color 0.16s ease,
			border-color 0.16s ease;
	}
	.sei-vazio:not(:disabled) {
		/* Cursor de texto: vazio o clique abre o input ali mesmo (escrita), não um
		   menu. A mãozinha volta a partir do 1º número, quando o clique abre o
		   popover. */
		cursor: text;
	}
	.sei-vazio:hover:not(:disabled) {
		background: var(--ds-color-surface-muted);
		border-color: var(--ds-color-border-strong);
	}

	.sei-error {
		display: block;
		margin-top: 0.2rem;
		font-size: 0.75rem;
		color: var(--ds-color-text-danger);
	}

	@media (prefers-reduced-motion: reduce) {
		.app-dropdown-in {
			animation-duration: 1ms;
		}
	}
</style>
