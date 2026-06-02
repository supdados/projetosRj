<script lang="ts">
	/**
	 * Edição inline genérica, CONTROLADA por callback. Dois modos:
	 *
	 *  - variant="block" (default): rótulo + valor + botão "Editar" (usado nos
	 *    campos da seção "Detalhes" do projeto). Salvar/Cancelar explícitos.
	 *  - variant="cell": CLIQUE-PARA-EDITAR direto no valor (paridade com
	 *    09-project-inline-editor.js / 07-stage-dnd.js inline editing das células
	 *    da tabela de etapas). Clica no texto -> vira input/textarea; BLUR salva;
	 *    Enter salva (textarea: Enter também salva, Shift+Enter quebra linha);
	 *    Escape cancela. Textarea com AUTO-RESIZE. Sem botões.
	 *
	 * O componente NÃO chama API — emite `onSave(value)`; a página orquestra e
	 * devolve `pending`/`error`.
	 */
	import { tick } from 'svelte';

	type FieldKind = 'text' | 'textarea' | 'select' | 'date';
	type Variant = 'block' | 'cell';
	interface SelectOption {
		value: string;
		label: string;
	}

	interface Props {
		label?: string;
		value: string | null;
		kind?: FieldKind;
		variant?: Variant;
		options?: SelectOption[];
		emptyLabel?: string;
		/** No modo cell, alinha o conteúdo ao centro (datas/responsável). */
		centered?: boolean;
		readonly?: boolean;
		pending?: boolean;
		error?: string | null;
		fieldId: string;
		display?: import('svelte').Snippet<[string | null]>;
		onSave: (value: string) => void;
		onCancel?: () => void;
	}

	let {
		label = '',
		value,
		kind = 'text',
		variant = 'block',
		options = [],
		emptyLabel = '—',
		centered = false,
		readonly = false,
		pending = false,
		error = null,
		fieldId,
		display,
		onSave,
		onCancel
	}: Props = $props();

	let editing = $state(false);
	let draft = $state('');
	let editorEl = $state<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement | null>(null);

	const errorId = $derived(`${fieldId}-error`);
	const hasValue = $derived(value !== null && value !== '');

	function autoResize(): void {
		if (editorEl && editorEl.tagName === 'TEXTAREA') {
			const ta = editorEl as HTMLTextAreaElement;
			ta.style.height = 'auto';
			ta.style.height = `${ta.scrollHeight}px`;
		}
	}

	async function enterEdit(): Promise<void> {
		if (readonly || pending) return;
		draft = value ?? '';
		editing = true;
		await tick();
		editorEl?.focus();
		if (editorEl && kind !== 'select' && 'select' in editorEl) {
			(editorEl as HTMLInputElement | HTMLTextAreaElement).select();
		}
		autoResize();
	}

	function commit(): void {
		const trimmed = kind === 'date' || kind === 'select' ? draft : draft.trim();
		editing = false;
		if (trimmed !== (value ?? '')) onSave(trimmed);
	}

	function cancel(): void {
		editing = false;
		draft = value ?? '';
		onCancel?.();
	}

	function onKeydown(event: KeyboardEvent): void {
		if (event.key === 'Escape') {
			event.preventDefault();
			cancel();
			return;
		}
		if (event.key === 'Enter') {
			if (kind === 'textarea' && event.shiftKey) return;
			if (kind === 'textarea' && variant === 'block' && !event.ctrlKey && !event.metaKey) return;
			event.preventDefault();
			commit();
		}
	}
</script>

{#if variant === 'cell'}
	<!-- ===== Modo CÉLULA: clique-para-editar, blur salva ===== -->
	{#if editing}
		{#if kind === 'textarea'}
			<textarea
				bind:this={editorEl}
				bind:value={draft}
				id={fieldId}
				rows="1"
				disabled={pending}
				aria-label={label}
				class="cell-editor cell-editor-textarea"
				class:centered
				oninput={autoResize}
				onblur={commit}
				onkeydown={onKeydown}
			></textarea>
		{:else}
			<input
				bind:this={editorEl}
				bind:value={draft}
				id={fieldId}
				type={kind === 'date' ? 'date' : 'text'}
				disabled={pending}
				aria-label={label}
				class="cell-editor cell-editor-input"
				class:centered
				onblur={commit}
				onkeydown={onKeydown}
			/>
		{/if}
	{:else}
		<button
			type="button"
			class="editable-field"
			class:centered
			class:editable-field-empty={!hasValue}
			disabled={readonly || pending}
			aria-label={label ? `Editar ${label}` : 'Editar campo'}
			onclick={enterEdit}
		>
			{#if display}{@render display(value)}{:else if hasValue}{value}{:else}{emptyLabel}{/if}
		</button>
	{/if}
	{#if error}
		<span id={errorId} role="alert" class="cell-error">{error}</span>
	{/if}
{:else}
	<!-- ===== Modo BLOCO: rótulo + valor + botão Editar ===== -->
	<div class="flex flex-col gap-1">
		<span
			id={`${fieldId}-label`}
			class="text-xs font-semibold uppercase tracking-wide text-text-muted"
		>
			{label}
		</span>

		{#if editing}
			<div class="flex flex-col gap-2">
				{#if kind === 'textarea'}
					<textarea
						bind:this={editorEl}
						bind:value={draft}
						id={fieldId}
						rows="3"
						disabled={pending}
						aria-labelledby={`${fieldId}-label`}
						aria-describedby={error ? errorId : undefined}
						aria-invalid={error ? 'true' : undefined}
						onkeydown={onKeydown}
						class="w-full rounded-md border border-border-subtle bg-surface px-3 py-2 text-sm text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
					></textarea>
				{:else if kind === 'select'}
					<select
						bind:this={editorEl}
						bind:value={draft}
						id={fieldId}
						disabled={pending}
						aria-labelledby={`${fieldId}-label`}
						aria-describedby={error ? errorId : undefined}
						aria-invalid={error ? 'true' : undefined}
						onkeydown={onKeydown}
						class="w-full rounded-md border border-border-subtle bg-surface px-3 py-2 text-sm text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
					>
						{#each options as opt (opt.value)}
							<option value={opt.value}>{opt.label}</option>
						{/each}
					</select>
				{:else}
					<input
						bind:this={editorEl}
						bind:value={draft}
						id={fieldId}
						type={kind === 'date' ? 'date' : 'text'}
						disabled={pending}
						aria-labelledby={`${fieldId}-label`}
						aria-describedby={error ? errorId : undefined}
						aria-invalid={error ? 'true' : undefined}
						onkeydown={onKeydown}
						class="w-full rounded-md border border-border-subtle bg-surface px-3 py-2 text-sm text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
					/>
				{/if}

				<div class="flex items-center gap-2">
					<button
						type="button"
						onclick={commit}
						disabled={pending}
						class="rounded-md border border-primary-500 bg-primary-100 px-3 py-1.5 text-sm font-medium text-primary-700 transition-colors duration-fast hover:bg-primary-500 hover:text-white disabled:opacity-60 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
					>
						{pending ? 'Salvando…' : 'Salvar'}
					</button>
					<button
						type="button"
						onclick={cancel}
						disabled={pending}
						class="rounded-md border border-border-subtle bg-surface px-3 py-1.5 text-sm font-medium text-text-primary transition-colors duration-fast hover:bg-surface-muted disabled:opacity-60 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
					>
						Cancelar
					</button>
				</div>

				{#if error}
					<p id={errorId} role="alert" class="text-sm text-danger">{error}</p>
				{/if}
			</div>
		{:else}
			<div class="flex items-start justify-between gap-2">
				<div
					class="min-w-0 rounded-md text-sm text-text-primary transition-colors duration-fast ease-out {!readonly
						? 'px-1 -mx-1 hover:bg-surface-muted'
						: ''}"
				>
					{#if display}
						{@render display(value)}
					{:else if hasValue}
						<span class="break-words">{value}</span>
					{:else}
						<span class="text-text-muted">{emptyLabel}</span>
					{/if}
				</div>
				{#if !readonly}
					<button
						type="button"
						onclick={enterEdit}
						disabled={pending}
						aria-label={`Editar ${label}`}
						class="shrink-0 rounded-md border border-border-subtle bg-surface px-2 py-1 text-xs font-medium text-text-secondary transition-colors duration-fast ease-out hover:bg-surface-muted hover:text-primary-700 disabled:opacity-60 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
					>
						Editar
					</button>
				{/if}
			</div>
		{/if}
	</div>
{/if}

<style>
	/* ----- Modo célula (paridade com .editable-field / .editable-field-input) ----- */
	.editable-field {
		display: inline-block;
		width: 100%;
		background: none;
		border: 1px solid transparent;
		border-radius: 8px;
		padding: 0.18rem 0.4rem;
		font: inherit;
		color: inherit;
		text-align: left;
		cursor: text;
		transition:
			background-color 0.16s ease,
			border-color 0.16s ease;
	}
	.editable-field.centered {
		text-align: center;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		min-height: 30px;
	}
	.editable-field:hover:not(:disabled) {
		background-color: #e2e8f0;
	}
	.editable-field:disabled {
		cursor: default;
		background: none;
	}
	.editable-field-empty {
		color: #6f859f;
		background: #f6f9fc;
		border: 1px dashed #d6e2ef;
	}
	.editable-field-empty:hover:not(:disabled) {
		background: #eef4fa;
		border-color: #bfd0e1;
		color: #536d89;
	}

	.cell-editor {
		width: 100%;
		padding: 0.38rem 0.58rem;
		border: 1px solid #c4d5e7;
		border-radius: 7px;
		font-size: 0.875rem;
		color: #3e556f;
		background: #fff;
		font-family: inherit;
		line-height: 1.45;
		box-sizing: border-box;
	}
	.cell-editor-textarea {
		resize: none;
		overflow: hidden;
		display: block;
	}
	.cell-editor.centered {
		text-align: center;
	}
	.cell-editor:focus {
		outline: none;
		border-color: #7ea6ce;
		box-shadow: 0 0 0 3px rgba(30, 84, 143, 0.12);
	}
	.cell-error {
		display: block;
		margin-top: 0.2rem;
		font-size: 0.72rem;
		color: var(--app-color-danger, #b42323);
	}

	:global(html[data-theme='dark']) .editable-field:hover:not(:disabled) {
		background-color: rgba(99, 166, 219, 0.18);
	}
</style>
