<script lang="ts">
	/**
	 * Árvore de COMENTÁRIOS inline (variation-d) — drop-in do `CommentsPanel`
	 * (mesmas props `store`/`idPrefix`). Reaproveita a store do drawer
	 * (`addComment`/`editComment`/`deleteComment`) e troca apenas a apresentação:
	 *   - lista conectada em árvore (conectores em L via ::before/::after);
	 *   - avatar + nome + data por comentário, ações no hover (editar/excluir);
	 *   - menções `@nome` destacadas (cosmético) com AUTOCOMPLETE de usuários da
	 *     tarefa (reusa `GET /api/tarefas/<id>/sugestoes-responsavel`);
	 *   - composer de barra dupla (textarea acessível, não contentEditable);
	 *   - empty-state desenhado ("Faça o primeiro comentário").
	 * O delete usa mini-confirm inline (sem `window.confirm`, acessível).
	 */
	import { tick } from 'svelte';
	import type { TaskDrawerStore } from '$lib/stores/taskDrawer';
	import type { TaskAssignee } from '$lib/types/tasks';
	import { fetchTaskCandidates } from '$lib/api/tasks';
	import { formatCommentDate, splitMentions } from '$lib/utils/commentPresentation';
	import AssigneeAvatar from '$lib/components/AssigneeAvatar.svelte';

	interface Props {
		store: TaskDrawerStore;
		idPrefix?: string;
		/**
		 * "Sujo": há texto no composer ou uma edição em andamento. O pai usa para
		 * NÃO fechar o painel no clique-fora quando há conteúdo não salvo.
		 */
		dirty?: boolean;
		/** Esconde o cabeçalho próprio ("Comentários" + contagem) quando o
		 *  container já fornece um (ex.: a seção colapsável do drawer). */
		showHeader?: boolean;
	}

	let {
		store,
		idPrefix = 'task',
		dirty = $bindable(false),
		showHeader = true
	}: Props = $props();

	const comments = $derived($store.detail?.comentarios ?? []);
	const taskId = $derived($store.detail?.id ?? null);

	// ── Composer ──────────────────────────────────────────────────────────────
	let draft = $state('');
	let composing = $state(false); // empty-state -> abre o composer
	let busy = $state(false);
	let textareaEl = $state<HTMLTextAreaElement | null>(null);

	const showComposer = $derived(comments.length > 0 || composing);

	// ── Anexo no composer (réplica do botão de anexo da linha) ───────────────────
	let fileInput = $state<HTMLInputElement | null>(null);
	let uploading = $state(false);

	function pickAttachment(): void {
		fileInput?.click();
	}
	async function onAttachChange(event: Event): Promise<void> {
		const input = event.currentTarget as HTMLInputElement;
		const file = input.files?.[0];
		input.value = '';
		if (!file) return;
		uploading = true;
		await store.uploadAttachment(file);
		uploading = false;
	}

	// ── Edição inline ──────────────────────────────────────────────────────────
	let editingId = $state<number | null>(null);
	let editText = $state('');
	let editTextarea = $state<HTMLTextAreaElement | null>(null);

	// Reflete ao pai se há conteúdo não salvo (texto no composer ou edição aberta).
	$effect(() => {
		dirty = draft.trim() !== '' || editingId !== null;
	});

	// ── Mini-confirm de exclusão ────────────────────────────────────────────────
	let confirmingId = $state<number | null>(null);

	// ── Autocomplete de menções ──────────────────────────────────────────────────
	let candidates = $state<TaskAssignee[]>([]);
	let candidatesLoaded = false;
	let candidatesLoading = false;
	let mentionOpen = $state(false);
	let mentionQuery = $state('');
	let mentionStart = $state(-1);
	let mentionActiveIndex = $state(0);
	// Posição FIXED do dropdown de menção (escapa do overflow:hidden dos ancestrais
	// — o painel vive dentro de .task-collapse/scroller que clipariam um absolute).
	let mentionPos = $state<{ left: number; bottom: number; width: number }>({
		left: 0,
		bottom: 0,
		width: 256
	});

	const knownNames = $derived(candidates.map((c) => c.name));
	const mentionMatches = $derived.by(() => {
		if (!mentionOpen) return [] as TaskAssignee[];
		const q = mentionQuery.trim().toLowerCase();
		const list = q ? candidates.filter((c) => c.name.toLowerCase().includes(q)) : candidates;
		return list.slice(0, 6);
	});

	async function ensureCandidates(): Promise<void> {
		// `candidatesLoaded` só vira true APÓS sucesso — uma falha (rede/403) deixa
		// candidatesLoaded=false para permitir retry na próxima digitação de "@".
		// `candidatesLoading` evita requisições concorrentes durante o await.
		if (candidatesLoaded || candidatesLoading || taskId == null) return;
		candidatesLoading = true;
		try {
			const result = await fetchTaskCandidates(taskId);
			candidates = result.users;
			candidatesLoaded = true;
		} catch {
			candidates = [];
		} finally {
			candidatesLoading = false;
		}
	}

	function autoResize(el: HTMLTextAreaElement | null): void {
		if (!el) return;
		el.style.height = 'auto';
		el.style.height = `${el.scrollHeight}px`;
	}

	/** Ancora o dropdown (fixed) logo ACIMA da caixa de texto. */
	function computeMentionPos(): void {
		const el = textareaEl;
		if (!el) return;
		const rect = el.getBoundingClientRect();
		const width = Math.min(320, Math.max(220, rect.width));
		const left = Math.min(Math.max(8, rect.left), window.innerWidth - width - 8);
		mentionPos = { left, bottom: window.innerHeight - rect.top + 6, width };
	}

	function detectMention(): void {
		const el = textareaEl;
		if (!el) {
			mentionOpen = false;
			return;
		}
		const caret = el.selectionStart ?? draft.length;
		const before = draft.slice(0, caret);
		const match = before.match(/@(\S*)$/);
		if (match) {
			mentionStart = caret - match[0].length;
			mentionQuery = match[1];
			mentionActiveIndex = 0;
			computeMentionPos();
			mentionOpen = true;
			void ensureCandidates();
		} else {
			mentionOpen = false;
		}
	}

	// Dropdown é position:fixed — ao rolar/redimensionar, fecha (não acompanha).
	$effect(() => {
		if (!mentionOpen) return;
		const close = () => (mentionOpen = false);
		window.addEventListener('scroll', close, true);
		window.addEventListener('resize', close);
		return () => {
			window.removeEventListener('scroll', close, true);
			window.removeEventListener('resize', close);
		};
	});

	function onComposerInput(): void {
		autoResize(textareaEl);
		detectMention();
	}

	async function insertMention(candidate: TaskAssignee): Promise<void> {
		const el = textareaEl;
		const caret = el?.selectionStart ?? draft.length;
		const before = draft.slice(0, mentionStart);
		const after = draft.slice(caret);
		const insertion = `@${candidate.name} `;
		draft = before + insertion + after;
		mentionOpen = false;
		await tick();
		if (el) {
			const pos = (before + insertion).length;
			el.focus();
			el.setSelectionRange(pos, pos);
			autoResize(el);
		}
	}

	function onComposerKeydown(event: KeyboardEvent): void {
		if (mentionOpen && mentionMatches.length > 0) {
			if (event.key === 'ArrowDown') {
				event.preventDefault();
				mentionActiveIndex = Math.min(mentionActiveIndex + 1, mentionMatches.length - 1);
				return;
			}
			if (event.key === 'ArrowUp') {
				event.preventDefault();
				mentionActiveIndex = Math.max(mentionActiveIndex - 1, 0);
				return;
			}
			if (event.key === 'Enter' || event.key === 'Tab') {
				event.preventDefault();
				void insertMention(mentionMatches[mentionActiveIndex]);
				return;
			}
			if (event.key === 'Escape') {
				// stopPropagation: Esc fecha SÓ o dropdown — sem subir ao handler do
				// painel (TaskHubTaskRow), que recolheria toda a região de comentários.
				event.preventDefault();
				event.stopPropagation();
				mentionOpen = false;
				return;
			}
		}
		if (event.key === 'Enter' && !event.shiftKey) {
			event.preventDefault();
			void submit();
		} else if (event.key === 'Escape' && composing && comments.length === 0) {
			event.preventDefault();
			event.stopPropagation();
			discard();
		}
	}

	async function submit(): Promise<void> {
		const content = draft.trim();
		if (!content || busy) return;
		busy = true;
		const ok = await store.addComment(content);
		busy = false;
		if (ok) {
			draft = '';
			composing = false;
			mentionOpen = false;
			if (textareaEl) textareaEl.style.height = 'auto';
		}
	}

	function startComposing(): void {
		composing = true;
		void ensureCandidates();
		void tick().then(() => textareaEl?.focus());
	}

	function discard(): void {
		draft = '';
		composing = false;
		mentionOpen = false;
	}

	// ── Edição ───────────────────────────────────────────────────────────────────
	function startEdit(id: number, content: string): void {
		confirmingId = null;
		editingId = id;
		editText = content;
	}
	function cancelEdit(): void {
		editingId = null;
		editText = '';
	}
	async function saveEdit(id: number): Promise<void> {
		const content = editText.trim();
		if (!content || busy) return;
		busy = true;
		const ok = await store.editComment(id, content);
		busy = false;
		if (ok) cancelEdit();
	}
	function onEditKeydown(event: KeyboardEvent, id: number): void {
		if (event.key === 'Enter' && !event.shiftKey) {
			event.preventDefault();
			void saveEdit(id);
		} else if (event.key === 'Escape') {
			// stopPropagation: cancelar a edição não deve recolher o painel inteiro.
			event.preventDefault();
			event.stopPropagation();
			cancelEdit();
		}
	}
	$effect(() => {
		if (editingId !== null && editTextarea) {
			const el = editTextarea;
			autoResize(el);
			el.focus();
			el.setSelectionRange(el.value.length, el.value.length);
		}
	});

	// ── Exclusão ───────────────────────────────────────────────────────────────────
	async function confirmDelete(id: number): Promise<void> {
		if (busy) return;
		busy = true;
		await store.deleteComment(id);
		busy = false;
		confirmingId = null;
	}
</script>

<section aria-label="Comentários" class="ict">
	{#if comments.length > 0}
		{#if showHeader}
			<header class="mb-1 flex items-center gap-2 px-1">
				<h3 class="text-sm font-bold text-text-primary">Comentários</h3>
				<span
					class="inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-surface px-1.5 font-mono text-2xs font-semibold text-text-secondary"
				>
					{comments.length}
				</span>
			</header>
		{/if}

		<ol class="ict-list">
			{#each comments as comment (comment.id)}
				<li class="ict-cmt group/cmt">
					<span class="ict-avatar relative z-10">
						<AssigneeAvatar name={comment.author_name} size="sm" />
					</span>
					<div class="min-w-0 pt-0.5">
						<div class="flex items-center gap-1.5">
							<b class="text-xs font-semibold text-text-primary">{comment.author_name}</b>
							<span class="text-2xs text-text-muted">· {formatCommentDate(comment.updated_at ?? comment.created_at)}</span>
						</div>

						{#if editingId === comment.id}
							<!-- Edição compacta: textarea hugga o conteúdo (autoResize) e os
							     botões viram ícones AO LADO — sem linha extra embaixo. -->
							<div class="mt-1 flex items-start gap-1.5">
								<textarea
									bind:this={editTextarea}
									bind:value={editText}
									rows="1"
									aria-label="Editar comentário"
									oninput={() => autoResize(editTextarea)}
									onkeydown={(e) => onEditKeydown(e, comment.id)}
									class="min-h-[32px] w-full resize-none overflow-hidden rounded-md border border-border-subtle bg-surface px-2.5 py-1.5 text-sm leading-normal text-text-primary focus:border-brand focus:outline-none"
								></textarea>
								<button
									type="button"
									disabled={busy || editText.trim() === ''}
									onclick={() => saveEdit(comment.id)}
									title="Salvar"
									aria-label="Salvar"
									class="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-brand bg-wash-brand text-brand transition-colors duration-fast hover:bg-brand hover:text-white focus:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:opacity-50"
								>
									<i class="fas fa-check text-xs" aria-hidden="true"></i>
								</button>
								<button
									type="button"
									onclick={cancelEdit}
									title="Cancelar"
									aria-label="Cancelar"
									class="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-border-subtle text-text-secondary transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
								>
									<i class="fas fa-xmark text-xs" aria-hidden="true"></i>
								</button>
							</div>
						{:else}
							<!-- Ícones de editar/excluir junto ao FIM do texto (igual à tarefa),
							     revelados no hover da linha do comentário. -->
							<p class="m-0 whitespace-pre-wrap text-sm leading-relaxed text-text-secondary">{#each splitMentions(comment.content, knownNames) as seg}{#if seg.isMention}<span class="rounded bg-wash-neutral px-1 font-medium text-brand">{seg.text}</span>{:else}{seg.text}{/if}{/each}{#if (comment.can_edit || comment.can_delete) && confirmingId !== comment.id}<span class="ml-1.5 inline-flex translate-y-px items-center gap-0.5 align-middle opacity-0 transition-opacity duration-fast group-hover/cmt:opacity-100 group-focus-within/cmt:opacity-100">{#if comment.can_edit}<button
										type="button"
										onclick={() => startEdit(comment.id, comment.content)}
										aria-label="Editar comentário"
										title="Editar"
										class="inline-flex h-6 w-6 items-center justify-center rounded-md text-2xs text-text-muted transition-colors duration-fast hover:bg-surface-muted hover:text-brand focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
									><i class="fas fa-pen" aria-hidden="true"></i></button>{/if}{#if comment.can_delete}<button
										type="button"
										onclick={() => (confirmingId = comment.id)}
										aria-label="Excluir comentário"
										title="Excluir"
										class="inline-flex h-6 w-6 items-center justify-center rounded-md text-2xs text-text-muted transition-colors duration-fast hover:bg-danger/10 hover:text-danger focus:outline-none focus-visible:ring-2 focus-visible:ring-danger"
									><i class="fas fa-trash-can" aria-hidden="true"></i></button>{/if}</span>{/if}</p>
						{/if}

						{#if confirmingId === comment.id}
							<div class="mt-1.5 flex items-center gap-2 rounded-md border border-danger/40 bg-danger/5 px-2.5 py-1.5">
								<span class="mr-auto text-2xs text-text-primary">Excluir este comentário?</span>
								<button
									type="button"
									onclick={() => (confirmingId = null)}
									disabled={busy}
									class="rounded border border-border-subtle px-2 py-0.5 text-2xs font-medium text-text-secondary hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:opacity-50"
								>
									Cancelar
								</button>
								<button
									type="button"
									onclick={() => confirmDelete(comment.id)}
									disabled={busy}
									class="rounded bg-danger px-2 py-0.5 text-2xs font-medium text-white hover:opacity-90 focus:outline-none focus-visible:ring-2 focus-visible:ring-danger disabled:opacity-50"
								>
									Excluir
								</button>
							</div>
						{/if}
					</div>
				</li>
			{/each}
		</ol>
	{:else if !composing}
		<!-- Empty state desenhado -->
		<div class="flex flex-col items-center gap-2 px-4 py-5 text-center">
			<svg width="44" height="32" viewBox="0 0 44 32" fill="none" aria-hidden="true">
				<path
					d="M27 3h11a3 3 0 0 1 3 3v9a3 3 0 0 1-3 3h-5l-2.5 2.5V18H27a3 3 0 0 1-3-3V6a3 3 0 0 1 3-3z"
					stroke="var(--ds-color-border-base)"
					stroke-width="1"
					fill="var(--ds-color-surface-base)"
					stroke-dasharray="2.5 2.5"
				/>
				<path
					d="M5 10h13a3 3 0 0 1 3 3v9a3 3 0 0 1-3 3h-5l-2.5 2.5V25H5a3 3 0 0 1-3-3v-9a3 3 0 0 1 3-3z"
					stroke="var(--ds-color-text-muted)"
					stroke-width="1.1"
					fill="var(--ds-color-surface-muted)"
				/>
				<circle cx="8" cy="17.5" r="1" fill="var(--ds-color-text-muted)" />
				<circle cx="11.5" cy="17.5" r="1" fill="var(--ds-color-text-muted)" />
				<circle cx="15" cy="17.5" r="1" fill="var(--ds-color-text-muted)" />
			</svg>
			<button
				type="button"
				onclick={startComposing}
				class="group/cta inline-flex items-center gap-2 rounded-lg border border-border-subtle bg-surface px-3 py-1.5 text-sm font-medium text-text-primary shadow-sm transition-colors duration-fast hover:border-border-strong hover:text-brand focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
			>
				<span>Faça o primeiro comentário</span>
				<i
					class="fas fa-arrow-right text-2xs text-text-muted transition-transform duration-fast group-hover/cta:translate-x-0.5 group-hover/cta:text-brand motion-reduce:transition-none"
					aria-hidden="true"
				></i>
			</button>
		</div>
	{/if}

	{#if showComposer}
		<div class="ict-composer relative mt-1">
			{#if mentionOpen && mentionMatches.length > 0}
				<ul
					role="listbox"
					aria-label="Mencionar pessoa"
					class="fixed z-dropdown max-h-48 overflow-auto rounded-lg border border-border-subtle bg-surface py-1 shadow-md"
					style="left: {mentionPos.left}px; bottom: {mentionPos.bottom}px; width: {mentionPos.width}px;"
				>
					{#each mentionMatches as candidate, i (candidate.id)}
						<li role="option" aria-selected={i === mentionActiveIndex}>
							<button
								type="button"
								onmousedown={(e) => {
									e.preventDefault();
									void insertMention(candidate);
								}}
								onmouseenter={() => (mentionActiveIndex = i)}
								class="flex w-full items-center gap-2 px-2.5 py-1.5 text-left transition-colors duration-fast {i ===
								mentionActiveIndex
									? 'bg-primary-100/50'
									: 'hover:bg-surface-muted'}"
							>
								<AssigneeAvatar name={candidate.name} initials={candidate.initials} size="sm" />
								<span class="min-w-0 flex-1">
									<span class="block truncate text-sm text-text-primary">{candidate.name}</span>
									{#if candidate.subtitle}
										<span class="block truncate text-2xs text-text-muted">{candidate.subtitle}</span>
									{/if}
								</span>
							</button>
						</li>
					{/each}
				</ul>
			{/if}

			<form
				class="overflow-hidden rounded-lg border border-border-subtle bg-surface transition-colors duration-fast focus-within:border-brand"
				onsubmit={(e) => {
					e.preventDefault();
					void submit();
				}}
			>
				<label for={`${idPrefix}-new-comment`} class="sr-only">Novo comentário</label>
				<textarea
					id={`${idPrefix}-new-comment`}
					bind:this={textareaEl}
					bind:value={draft}
					rows="2"
					placeholder={comments.length > 0
						? 'Responder ou comentar… (@ menciona, Enter envia)'
						: 'Escreva o primeiro comentário…'}
					oninput={onComposerInput}
					onkeydown={onComposerKeydown}
					class="block max-h-[180px] min-h-[60px] w-full resize-none border-0 bg-transparent px-3 py-2.5 text-sm leading-normal text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-0"
				></textarea>
				<div class="flex items-center justify-between gap-2 border-t border-border-subtle px-2 py-1.5">
					<div class="inline-flex items-center gap-0.5">
						<button
							type="button"
							onclick={() => {
								draft = `${draft}@`;
								void tick().then(() => {
									textareaEl?.focus();
									onComposerInput();
								});
							}}
							title="Mencionar pessoa"
							aria-label="Mencionar pessoa"
							class="inline-flex h-7 w-7 items-center justify-center rounded-md text-text-muted transition-colors duration-fast hover:bg-surface-muted hover:text-brand focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
						>
							<i class="fas fa-at text-xs" aria-hidden="true"></i>
						</button>
						<button
							type="button"
							onclick={pickAttachment}
							disabled={uploading}
							title="Anexar arquivo"
							aria-label="Anexar arquivo"
							class="inline-flex h-7 w-7 items-center justify-center rounded-md text-text-muted transition-colors duration-fast hover:bg-surface-muted hover:text-brand focus:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:opacity-50"
						>
							<i class="fas {uploading ? 'fa-spinner fa-spin' : 'fa-paperclip'} text-xs" aria-hidden="true"></i>
						</button>
						<input
							bind:this={fileInput}
							type="file"
							class="sr-only"
							onchange={onAttachChange}
							aria-hidden="true"
							tabindex="-1"
						/>
					</div>
					<div class="inline-flex items-center gap-1.5">
						{#if composing && comments.length === 0}
							<button
								type="button"
								onclick={discard}
								class="rounded-md px-2.5 py-1 text-2xs font-medium text-text-secondary transition-colors duration-fast hover:text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
							>
								Descartar
							</button>
						{/if}
						<button
							type="submit"
							disabled={busy || draft.trim() === ''}
							class="inline-flex items-center rounded-md bg-brand px-3 py-1 text-2xs font-semibold text-white transition-colors duration-fast hover:bg-brand-hover focus:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-50"
						>
							Comentar
						</button>
					</div>
				</div>
			</form>
		</div>
	{/if}
</section>

<style>
	/* Conectores em árvore (L-curve + tronco) entre os comentários. Cor via token
	   para funcionar no dark mode. */
	.ict-list {
		list-style: none;
		margin: 0;
		padding: 0;
	}
	.ict-cmt {
		position: relative;
		display: grid;
		grid-template-columns: 24px 1fr;
		gap: 10px;
		padding: 10px 0 10px 28px;
	}
	.ict-cmt::before {
		content: '';
		position: absolute;
		left: 0;
		top: 0;
		width: 22px;
		height: 24px;
		border-left: 1.5px solid var(--ds-color-border-base);
		border-bottom: 1.5px solid var(--ds-color-border-base);
		border-bottom-left-radius: 12px;
		pointer-events: none;
	}
	.ict-cmt::after {
		content: '';
		position: absolute;
		left: 0;
		top: 24px;
		bottom: 0;
		width: 1.5px;
		background: var(--ds-color-border-base);
		pointer-events: none;
	}
	.ict-cmt:last-child::after {
		display: none;
	}
	:global([data-theme='dark']) .ict-composer .shadow-md {
		box-shadow: var(--ds-shadow-md);
	}
</style>
