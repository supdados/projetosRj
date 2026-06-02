<script lang="ts">
	/**
	 * Painel de COMENTÁRIOS do drawer de tarefa (Fase 5b-2). Controlado: lê a
	 * lista de `$store.detail.comentarios` e delega add/editar/excluir aos métodos
	 * da store do drawer (que reconcilia a lista no estado canônico). Permissões
	 * (`can_edit`/`can_delete`) vêm do backend por comentário — autoritativas.
	 */
	import type { TaskDrawerStore } from '$lib/stores/taskDrawer';

	interface Props {
		store: TaskDrawerStore;
	}

	let { store }: Props = $props();

	let newComment = $state('');
	let editingId = $state<number | null>(null);
	let editText = $state('');
	let busy = $state(false);
	let editTextarea = $state<HTMLTextAreaElement | null>(null);

	const comments = $derived($store.detail?.comentarios ?? []);

	/**
	 * Auto-resize do textarea conforme o conteúdo — paridade com
	 * `autoResizeTextarea` de 03-etapa-comments.js (a edição inline de comentário
	 * crescia com o texto em vez de manter scroll interno).
	 */
	function autoResize(el: HTMLTextAreaElement): void {
		el.style.height = 'auto';
		el.style.height = `${el.scrollHeight}px`;
	}

	function onTextareaInput(event: Event): void {
		autoResize(event.currentTarget as HTMLTextAreaElement);
	}

	/**
	 * Enter salva, Shift+Enter quebra linha, Escape cancela — igual ao editor
	 * inline do legado (03-etapa-comments.js: keydown Enter/Escape).
	 */
	function onNewKeydown(event: KeyboardEvent): void {
		if (event.key === 'Enter' && !event.shiftKey) {
			event.preventDefault();
			void submitNew();
		}
	}

	function onEditKeydown(event: KeyboardEvent, id: number): void {
		if (event.key === 'Enter' && !event.shiftKey) {
			event.preventDefault();
			void saveEdit(id);
		} else if (event.key === 'Escape') {
			event.preventDefault();
			cancelEdit();
		}
	}

	/**
	 * Quando a edição inline abre, foca e posiciona o cursor no fim do texto e
	 * ajusta a altura — espelha `abrirEdicaoInline` do legado (focus +
	 * setSelectionRange no fim + autoResizeTextarea).
	 */
	$effect(() => {
		if (editingId !== null && editTextarea) {
			const el = editTextarea;
			autoResize(el);
			el.focus();
			el.setSelectionRange(el.value.length, el.value.length);
		}
	});

	function formatDate(iso: string | null): string {
		if (!iso) return '';
		const parsed = new Date(iso);
		if (Number.isNaN(parsed.getTime())) return '';
		return parsed.toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' });
	}

	async function submitNew(): Promise<void> {
		const content = newComment.trim();
		if (!content || busy) return;
		busy = true;
		const ok = await store.addComment(content);
		busy = false;
		if (ok) newComment = '';
	}

	function startEdit(id: number, content: string): void {
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

	async function remove(id: number): Promise<void> {
		if (busy) return;
		if (!window.confirm('Excluir este comentário?')) return;
		busy = true;
		await store.deleteComment(id);
		busy = false;
	}
</script>

<section
	aria-labelledby="drawer-comments-title"
	class="flex flex-col gap-1 rounded-xl border border-border-subtle bg-gradient-to-b from-surface to-surface-muted/40 p-2 shadow-[inset_0_1px_0_rgba(255,255,255,0.6)]"
>
	<h3
		id="drawer-comments-title"
		class="flex items-center gap-2 px-1 py-1 text-sm font-bold text-text-primary"
	>
		<span>Comentários</span>
		<span
			class="inline-flex h-[22px] min-w-[22px] items-center justify-center rounded-full border border-border-subtle bg-surface px-1.5 text-xs font-semibold text-text-secondary"
		>
			{comments.length}
		</span>
	</h3>

	{#if comments.length === 0}
		<p
			class="rounded-lg border border-dashed border-border-subtle bg-surface px-3 py-2.5 text-center text-xs text-text-secondary"
		>
			Nenhum comentário ainda.
		</p>
	{:else}
		<ul class="flex max-h-[40vh] flex-col gap-2 overflow-y-auto px-1 py-0.5">
			{#each comments as comment (comment.id)}
				<li
					class="group flex flex-col gap-0.5 rounded-lg border border-l-4 border-border-subtle border-l-primary-500 bg-surface px-2.5 py-2 shadow-sm transition-shadow duration-fast"
				>
					<div class="flex items-center gap-1.5">
						<span class="text-xs font-semibold text-primary-700">{comment.author_name}</span>
						<span class="text-2xs text-text-muted">{formatDate(comment.updated_at ?? comment.created_at)}</span>
						{#if (comment.can_edit || comment.can_delete) && editingId !== comment.id}
							<div
								class="ml-auto inline-flex items-center gap-1 opacity-0 transition-opacity duration-fast group-hover:opacity-100 group-focus-within:opacity-100"
							>
								{#if comment.can_edit}
									<button
										type="button"
										onclick={() => startEdit(comment.id, comment.content)}
										aria-label="Editar comentário"
										class="inline-flex h-7 w-7 items-center justify-center rounded-md border border-border-subtle bg-surface text-2xs font-semibold text-primary-700 transition-colors duration-fast hover:bg-primary-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
									>
										<i class="fas fa-pen" aria-hidden="true"></i>
									</button>
								{/if}
								{#if comment.can_delete}
									<button
										type="button"
										onclick={() => remove(comment.id)}
										aria-label="Excluir comentário"
										class="inline-flex h-7 w-7 items-center justify-center rounded-md border border-danger bg-surface text-2xs font-semibold text-danger transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-danger"
									>
										<i class="fas fa-trash-alt" aria-hidden="true"></i>
									</button>
								{/if}
							</div>
						{/if}
					</div>

					{#if editingId === comment.id}
						<div class="mt-1.5 flex flex-col gap-1.5">
							<textarea
								bind:this={editTextarea}
								bind:value={editText}
								rows="1"
								aria-label="Editar comentário"
								oninput={onTextareaInput}
								onkeydown={(e) => onEditKeydown(e, comment.id)}
								class="w-full resize-none overflow-hidden rounded-md border border-border-subtle bg-surface px-3 py-2 text-sm leading-normal text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
							></textarea>
							<div class="flex justify-end gap-1.5">
								<button
									type="button"
									disabled={busy || editText.trim() === ''}
									onclick={() => saveEdit(comment.id)}
									class="rounded-md border border-primary-500 bg-primary-100 px-2.5 py-1 text-2xs font-semibold text-primary-700 transition-colors duration-fast hover:bg-primary-500 hover:text-white focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-50"
								>
									Salvar
								</button>
								<button
									type="button"
									onclick={cancelEdit}
									class="rounded-md border border-border-subtle bg-surface px-2.5 py-1 text-2xs font-semibold text-text-secondary transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
								>
									Cancelar
								</button>
							</div>
						</div>
					{:else}
						<p class="m-0 whitespace-pre-wrap text-sm leading-normal text-text-secondary">{comment.content}</p>
					{/if}
				</li>
			{/each}
		</ul>
	{/if}

	<form
		class="flex flex-col gap-2 rounded-lg border border-border-subtle bg-surface p-2 shadow-sm"
		onsubmit={(e) => { e.preventDefault(); void submitNew(); }}
	>
		<label for="drawer-new-comment" class="sr-only">Novo comentário</label>
		<textarea
			id="drawer-new-comment"
			bind:value={newComment}
			rows="2"
			placeholder="Escreva um comentário… (Enter envia, Shift+Enter quebra linha)"
			onkeydown={onNewKeydown}
			class="max-h-[180px] min-h-[70px] w-full resize-none rounded-md border border-border-subtle bg-surface px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
		></textarea>
		<div class="flex items-center justify-between gap-2">
			<span class="text-2xs text-text-muted">Comente para registrar o andamento.</span>
			<button
				type="submit"
				disabled={busy || newComment.trim() === ''}
				title="Comentar"
				aria-label="Comentar"
				class="inline-flex h-[30px] w-[30px] items-center justify-center rounded-md border border-primary-500 bg-primary-100 text-xs font-semibold text-primary-700 transition-colors duration-fast hover:bg-primary-500 hover:text-white focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:cursor-not-allowed disabled:opacity-50"
			>
				<i class="fas fa-paper-plane" aria-hidden="true"></i>
				<span class="sr-only">Comentar</span>
			</button>
		</div>
	</form>
</section>
