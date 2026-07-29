<script lang="ts">
	/**
	 * Linha do card "Links e observações" (CriarProjetoModal): dot de status,
	 * label flutuante, preview no estado fechado e editor inline expansível
	 * (grid-template-rows 0fr→1fr). Editor padrão controlado por `value`/
	 * `onCommit`; editor custom (ex.: SEI) via snippet `editor` + callbacks
	 * `onEditorOpen`/`onEditorConfirm`/`onEditorCancel`.
	 */
	import { tick, type Snippet } from 'svelte';

	interface Props {
		id: string;
		label: string;
		placeholder?: string;
		multiline?: boolean;
		first?: boolean;
		last?: boolean;
		/** Abre o editor já expandido ao montar (sem roubar o foco). */
		startOpen?: boolean;
		value?: string;
		onCommit?: (value: string) => void;
		/** Sobrescreve o estado "preenchido" quando o editor é custom. */
		filled?: boolean;
		/** Sobrescreve o texto do preview quando o editor é custom. */
		preview?: string;
		editor?: Snippet;
		onEditorOpen?: () => void;
		/** Confirmação do editor custom; retorna se houve mudança (celebra). */
		onEditorConfirm?: () => boolean;
		onEditorCancel?: () => void;
	}

	let {
		id,
		label,
		placeholder = '',
		multiline = false,
		first = false,
		last = false,
		startOpen = false,
		value = '',
		onCommit,
		filled,
		preview,
		editor,
		onEditorOpen,
		onEditorConfirm,
		onEditorCancel
	}: Props = $props();

	// startOpen: nasce expandido SÓ quando ainda vazio (sem animar/roubar foco);
	// se já houver valor (ex.: voltar à seção depois de salvar), nasce colapsado
	// mostrando o preview. O snapshot do editor custom (SEI) é feito uma vez via
	// onEditorOpen para que "cancelar" restaure. Init único a partir das props.
	// svelte-ignore state_referenced_locally
	const startExpanded = startOpen && !(filled ?? value.trim().length > 0);
	// svelte-ignore state_referenced_locally
	let open = $state(startExpanded);
	// Libera o overflow só após a expansão: o popover do SEI precisa vazar a área.
	let expandEnded = $state(startExpanded);
	// svelte-ignore state_referenced_locally
	let draft = $state(startExpanded ? value : '');
	// svelte-ignore state_referenced_locally
	if (startExpanded) onEditorOpen?.();
	let celebrating = $state(false);
	let celebrateTimer: ReturnType<typeof setTimeout> | null = null;
	let expandTimer: ReturnType<typeof setTimeout> | null = null;
	let inputEl = $state<HTMLInputElement | HTMLTextAreaElement | null>(null);
	let toggleEl = $state<HTMLButtonElement | null>(null);
	let editorAreaEl = $state<HTMLDivElement | null>(null);

	const isFilled = $derived(filled ?? value.trim().length > 0);
	const previewText = $derived(preview ?? value);
	const closedFilled = $derived(!open && isFilled);
	const editorId = $derived(`${id}-editor`);

	function celebrate(): void {
		if (celebrateTimer) clearTimeout(celebrateTimer);
		// Remove e recoloca as classes num tick para reiniciar em saves seguidos.
		celebrating = false;
		void tick().then(() => (celebrating = true));
		celebrateTimer = setTimeout(() => (celebrating = false), 1100);
	}

	function openEditor(): void {
		if (open) return;
		draft = value;
		open = true;
		onEditorOpen?.();
		// Fallback do transitionend (aba oculta etc.): sem ele o popover do SEI
		// ficaria clipado pelo overflow-hidden da área expansível.
		if (expandTimer) clearTimeout(expandTimer);
		expandTimer = setTimeout(() => {
			if (open) expandEnded = true;
		}, 420);
		// preventScroll: sem ele o focus scrolla o clip ainda colapsado (0fr) e a
		// caixa abre cortada no topo, "descendo" até o fim da expansão.
		void tick().then(() => {
			if (editor) {
				editorAreaEl
					?.querySelector<HTMLElement>('button:not([disabled]), input, textarea')
					?.focus({ preventScroll: true });
				return;
			}
			inputEl?.focus({ preventScroll: true });
		});
	}

	function closeEditor(refocus: boolean): void {
		open = false;
		expandEnded = false;
		if (expandTimer) clearTimeout(expandTimer);
		if (refocus) void tick().then(() => toggleEl?.focus());
	}

	function confirmRow(refocus: boolean): void {
		if (!open) return;
		if (editor) {
			const changed = onEditorConfirm?.() ?? false;
			// startOpen vazio: mantém aberto por padrão; caso contrário colapsa.
			if (!(startOpen && !isFilled)) closeEditor(refocus);
			if (changed) celebrate();
			return;
		}
		const next = draft.trim();
		const changed = next.length > 0 && next !== value.trim();
		// Sempre propaga (inclui limpar, para o status/preview não ficarem presos).
		onCommit?.(next);
		// startOpen vazio: não colapsa; com conteúdo, colapsa com a animação.
		if (!(startOpen && next.length === 0)) closeEditor(refocus);
		if (changed) celebrate();
	}

	function cancelRow(refocus: boolean): void {
		if (!open) return;
		if (editor) onEditorCancel?.();
		closeEditor(refocus);
	}

	function onInputKeydown(event: KeyboardEvent): void {
		if (event.key === 'Escape') {
			event.preventDefault();
			event.stopPropagation();
			cancelRow(true);
			return;
		}
		if (event.key === 'Enter' && (!multiline || event.ctrlKey || event.metaKey)) {
			event.preventDefault();
			event.stopPropagation();
			confirmRow(true);
		}
	}

	// Blur salva (paridade com o protótipo); os botões usam mousedown+preventDefault
	// justamente para agir antes do blur sem disparar commit duplo.
	function onInputBlur(): void {
		if (open) confirmRow(false);
	}

	// API para editores custom (snippet): confirmam/cancelam a LINHA, não só o
	// próprio estado — sem isso a linha com startOpen nunca colapsa.
	export function confirmFromEditor(): void {
		confirmRow(false);
	}

	export function cancelFromEditor(): void {
		cancelRow(true);
	}
</script>

<div
	class="{first ? 'rounded-t-lg' : 'border-t border-border-subtle'} {last ? 'rounded-b-lg' : ''}"
	class:cp-lrow-flash={celebrating}
>
	<div
		class="flex gap-3 px-4 py-3 transition-colors duration-fast {closedFilled && multiline
			? 'items-start'
			: 'items-center'} {open ? '' : 'hover:bg-surface-muted'} {first
			? 'rounded-t-lg'
			: ''} {last && !open ? 'rounded-b-lg' : ''}"
	>
		<span
			class="cp-lrow-dot grid h-[22px] w-[22px] flex-none place-items-center rounded-full border-[1.5px] {isFilled
				? 'border-brand bg-brand'
				: 'border-dashed border-border-strong bg-surface'}"
			class:cp-lrow-dot-pop={celebrating}
			aria-hidden="true"
		>
			<svg
				viewBox="0 0 24 24"
				class="h-3 w-3 text-on-brand transition-opacity duration-fast {isFilled
					? 'opacity-100'
					: 'opacity-0'}"
				fill="none"
				stroke="currentColor"
				stroke-width="3.5"
				stroke-linecap="round"
				stroke-linejoin="round"
			>
				<path d="M5 13l4.5 4.5L19 7" stroke-dasharray="24" class:cp-lrow-check-draw={celebrating} />
			</svg>
		</span>

		<span class="flex min-w-0 flex-1 flex-col gap-0.5">
			<span
				class="cp-lrow-label leading-snug {closedFilled
					? 'text-2xs font-semibold uppercase tracking-caps text-text-muted'
					: 'text-sm font-medium text-text-primary'}"
			>
				{label}
			</span>
			{#if closedFilled}
				<span
					class="text-sm text-text-primary {multiline
						? 'cp-lrow-preview-obs'
						: 'truncate font-medium'}"
					class:cp-lrow-fade-slide={celebrating}
				>
					{previewText}
				</span>
			{/if}
		</span>

		{#if !open}
			{#if isFilled}
				<button
					type="button"
					bind:this={toggleEl}
					title="Editar"
					aria-label={`Editar ${label}`}
					aria-expanded={open}
					aria-controls={editorId}
					onclick={openEditor}
					class="grid h-7 w-7 flex-none place-items-center rounded-md text-text-muted transition-colors duration-fast hover:bg-surface-muted hover:text-brand active:scale-95 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
				>
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
						<path d="M12 20h9" />
						<path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z" />
					</svg>
				</button>
			{:else}
				<button
					type="button"
					bind:this={toggleEl}
					aria-expanded={open}
					aria-controls={editorId}
					onclick={openEditor}
					class="flex h-8 flex-none items-center rounded-md border border-border-subtle bg-surface px-3.5 text-xs font-semibold text-brand transition-colors duration-fast hover:border-brand hover:bg-surface-muted active:scale-95 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
				>
					Adicionar
				</button>
			{/if}
		{:else if !startOpen}
			<!-- Par confirmar/cancelar: ✓ antes de ✕, ícones do FontAwesome e as MESMAS
			     classes usadas nos demais pares da SPA (ghost 28px, rounded-md). -->
			<span class="flex flex-none gap-1.5">
				<button
					type="button"
					title={multiline ? 'Salvar (Ctrl+Enter)' : 'Salvar (Enter)'}
					aria-label={`Salvar ${label}`}
					onmousedown={(e) => {
						e.preventDefault();
						confirmRow(true);
					}}
					onclick={() => confirmRow(true)}
					class="cp-lrow-btn-in grid h-7 w-7 flex-none place-items-center rounded-md text-text-muted transition-colors duration-fast hover:bg-surface-muted hover:text-brand active:scale-95 disabled:opacity-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
				>
					<i class="fas fa-check text-xs" aria-hidden="true"></i>
				</button>
				<button
					type="button"
					title="Cancelar (Esc)"
					aria-label={`Cancelar edição de ${label}`}
					onmousedown={(e) => {
						e.preventDefault();
						cancelRow(true);
					}}
					onclick={() => cancelRow(true)}
					class="cp-lrow-btn-in-delay grid h-7 w-7 flex-none place-items-center rounded-md text-text-muted transition-colors duration-fast hover:bg-surface-muted hover:text-danger active:scale-95 disabled:opacity-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
				>
					<i class="fas fa-xmark text-xs" aria-hidden="true"></i>
				</button>
			</span>
		{/if}
	</div>

	<div
		class="cp-lrow-expand grid"
		class:is-open={open}
		ontransitionend={(e) => {
			if (e.target === e.currentTarget && open) expandEnded = true;
		}}
	>
		<!-- clip (não hidden): clip não é scroll container, focus não desloca; hidden é fallback. -->
		<div class="min-h-0 {expandEnded ? '' : 'overflow-hidden overflow-clip'}">
			<div
				id={editorId}
				inert={!open}
				bind:this={editorAreaEl}
				class="cp-lrow-editor pb-4 pl-[50px] pr-4 pt-0.5"
			>
				{#if editor}
					{@render editor()}
				{:else if multiline}
					<textarea
						id={`${id}-input`}
						bind:this={inputEl}
						bind:value={draft}
						rows="3"
						{placeholder}
						aria-label={label}
						onkeydown={onInputKeydown}
						onblur={onInputBlur}
						class="w-full resize-y rounded-md border border-border-subtle bg-surface px-3 py-2 text-sm text-text-primary placeholder:text-text-muted transition-colors duration-fast focus:border-brand focus:outline-none"
					></textarea>
				{:else}
					<input
						id={`${id}-input`}
						bind:this={inputEl}
						bind:value={draft}
						type="text"
						{placeholder}
						aria-label={label}
						onkeydown={onInputKeydown}
						onblur={onInputBlur}
						class="h-10 w-full rounded-md border border-border-subtle bg-surface px-3 text-sm leading-tight text-text-primary placeholder:text-text-muted transition-colors duration-fast focus:border-brand focus:outline-none"
					/>
				{/if}
			</div>
		</div>
	</div>
</div>

<style>
	.cp-lrow-dot {
		transition:
			background-color 0.3s,
			border-color 0.3s;
	}
	.cp-lrow-label {
		transition:
			font-size 0.25s,
			color 0.25s,
			letter-spacing 0.25s;
	}
	.cp-lrow-preview-obs {
		display: -webkit-box;
		-webkit-box-orient: vertical;
		-webkit-line-clamp: 6;
		line-clamp: 6;
		overflow: hidden;
		white-space: pre-wrap;
		word-break: break-word;
	}
	.cp-lrow-expand {
		grid-template-rows: 0fr;
		transition: grid-template-rows 0.35s cubic-bezier(0.4, 0, 0.2, 1);
	}
	.cp-lrow-expand.is-open {
		grid-template-rows: 1fr;
	}
	.cp-lrow-editor {
		opacity: 0;
		transform: translateY(-6px);
		transition:
			opacity 0.25s 0.08s,
			transform 0.3s 0.05s;
	}
	.cp-lrow-expand.is-open .cp-lrow-editor {
		opacity: 1;
		transform: none;
	}
	.cp-lrow-flash {
		animation: cp-lrow-row-flash 1.1s ease-out;
	}
	.cp-lrow-dot-pop {
		animation:
			cp-lrow-dot-pop 0.55s cubic-bezier(0.34, 1.56, 0.64, 1),
			cp-lrow-ring-burst 0.8s 0.1s ease-out;
	}
	.cp-lrow-check-draw {
		animation: cp-lrow-check-draw 0.35s 0.2s cubic-bezier(0.4, 0, 0.2, 1) both;
	}
	.cp-lrow-fade-slide {
		animation: cp-lrow-fade-slide 0.4s 0.25s ease-out both;
	}
	.cp-lrow-btn-in {
		animation: cp-lrow-btn-in 0.18s ease-out both;
	}
	.cp-lrow-btn-in-delay {
		animation: cp-lrow-btn-in 0.18s 0.05s ease-out both;
	}
	@keyframes cp-lrow-row-flash {
		0% {
			background-color: var(--ds-color-wash-brand);
		}
		100% {
			background-color: transparent;
		}
	}
	@keyframes cp-lrow-dot-pop {
		0% {
			transform: scale(1);
		}
		35% {
			transform: scale(1.35);
		}
		65% {
			transform: scale(0.92);
		}
		100% {
			transform: scale(1);
		}
	}
	@keyframes cp-lrow-ring-burst {
		0% {
			box-shadow: 0 0 0 0 color-mix(in srgb, var(--ds-color-primary-600) 45%, transparent);
		}
		100% {
			box-shadow: 0 0 0 16px transparent;
		}
	}
	@keyframes cp-lrow-check-draw {
		from {
			stroke-dashoffset: 24;
		}
		to {
			stroke-dashoffset: 0;
		}
	}
	@keyframes cp-lrow-fade-slide {
		from {
			opacity: 0;
			transform: translateX(6px);
		}
		to {
			opacity: 1;
			transform: none;
		}
	}
	@keyframes cp-lrow-btn-in {
		from {
			opacity: 0;
			transform: scale(0.6);
		}
		to {
			opacity: 1;
			transform: scale(1);
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.cp-lrow-flash,
		.cp-lrow-dot-pop,
		.cp-lrow-check-draw,
		.cp-lrow-fade-slide,
		.cp-lrow-btn-in,
		.cp-lrow-btn-in-delay {
			animation: none;
		}
		/* 1ms (não none): o transitionend precisa disparar p/ liberar o overflow. */
		.cp-lrow-expand,
		.cp-lrow-editor,
		.cp-lrow-label,
		.cp-lrow-dot {
			transition-duration: 1ms;
		}
	}
</style>
