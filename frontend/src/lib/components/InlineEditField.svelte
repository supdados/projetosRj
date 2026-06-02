<script lang="ts">
	/**
	 * Edição inline genérica (texto/textarea/select/data), CONTROLADA por callback.
	 *
	 * Espelha o padrão de 09-project-inline-editor.js: o usuário vê o valor; ao
	 * acionar "editar" entra em modo de edição com salvar/cancelar e estados
	 * `pending`/`erro`. O componente NÃO chama API — emite `onSave(value)` e a
	 * página orquestra a chamada e re-renderiza. O resultado (sucesso/erro) volta
	 * pelos props `pending`/`error` controlados pela página.
	 *
	 * Acessibilidade: o gatilho de edição é um <button>; o editor recebe foco ao
	 * abrir; Enter salva (exceto em textarea, onde Ctrl+Enter salva) e Escape
	 * cancela; erros anunciados via role="alert" e aria-describedby.
	 */
	import { tick } from 'svelte';

	type FieldKind = 'text' | 'textarea' | 'select' | 'date';
	interface SelectOption {
		value: string;
		label: string;
	}

	interface Props {
		/** Rótulo acessível do campo (ex.: "Descrição"). */
		label: string;
		/** Valor atual exibido (string vazia = vazio). */
		value: string | null;
		/** Tipo de editor. */
		kind?: FieldKind;
		/** Opções quando `kind === 'select'`. */
		options?: SelectOption[];
		/** Texto exibido quando o valor está vazio (modo leitura). */
		emptyLabel?: string;
		/** Bloqueia a edição (ex.: sem permissão ou etapa concluída). */
		readonly?: boolean;
		/** Em andamento (controlado pela página durante o save). */
		pending?: boolean;
		/** Mensagem de erro do último save (controlada pela página). */
		error?: string | null;
		/** id estável para vincular o label/erro. */
		fieldId: string;
		/** Snippet opcional para renderizar o valor de leitura (ex.: badge/data). */
		display?: import('svelte').Snippet<[string | null]>;
		/** Chamado ao salvar; recebe o novo valor (string; '' = vazio). */
		onSave: (value: string) => void;
		/** Chamado ao cancelar a edição. */
		onCancel?: () => void;
	}

	let {
		label,
		value,
		kind = 'text',
		options = [],
		emptyLabel = '—',
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

	async function enterEdit(): Promise<void> {
		if (readonly || pending) return;
		draft = value ?? '';
		editing = true;
		await tick();
		editorEl?.focus();
		if (editorEl && 'select' in editorEl && kind !== 'select') {
			(editorEl as HTMLInputElement | HTMLTextAreaElement).select();
		}
	}

	function commit(): void {
		const trimmed = kind === 'date' || kind === 'select' ? draft : draft.trim();
		onSave(trimmed);
		// A página fecha o modo edição re-renderizando o `value`; otimisticamente
		// fechamos o editor — se houver erro, a página mantém `error` e o usuário
		// reabre. (Sem otimismo de valor; só de UI.)
		editing = false;
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
			if (kind === 'textarea' && !event.ctrlKey && !event.metaKey) return;
			event.preventDefault();
			commit();
		}
	}
</script>

<div class="flex flex-col gap-1">
	<span id={`${fieldId}-label`} class="text-xs font-semibold uppercase tracking-wide text-text-muted">
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
		<!--
			Modo leitura. Fidelidade a .editable-field do original: a área de valor
			tem hover sutil (background-color shift, transição 0.16s ease) quando
			editável, sinalizando affordance de clique-para-editar.
		-->
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
