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

	const comments = $derived($store.detail?.comentarios ?? []);

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

<section aria-labelledby="drawer-comments-title" class="flex flex-col gap-3">
	<h3 id="drawer-comments-title" class="text-sm font-semibold text-text-primary">
		Comentários ({comments.length})
	</h3>

	<form class="flex flex-col gap-2" onsubmit={(e) => { e.preventDefault(); void submitNew(); }}>
		<label for="drawer-new-comment" class="sr-only">Novo comentário</label>
		<textarea
			id="drawer-new-comment"
			bind:value={newComment}
			rows="2"
			placeholder="Escreva um comentário…"
			class="w-full rounded-md border border-border-subtle bg-surface px-3 py-2 text-sm text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
		></textarea>
		<div class="flex justify-end">
			<button
				type="submit"
				disabled={busy || newComment.trim() === ''}
				class="rounded-md bg-primary-600 px-4 py-1.5 text-sm font-medium text-white transition-colors duration-fast hover:bg-primary-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-50"
			>
				Comentar
			</button>
		</div>
	</form>

	{#if comments.length === 0}
		<p class="text-sm text-text-muted">Nenhum comentário ainda.</p>
	{:else}
		<ul class="flex flex-col gap-3">
			{#each comments as comment (comment.id)}
				<li class="flex flex-col gap-1 rounded-md border border-border-subtle bg-surface px-3 py-2">
					<div class="flex flex-wrap items-baseline justify-between gap-2">
						<span class="text-xs font-semibold text-text-primary">{comment.author_name}</span>
						<span class="text-xs text-text-muted">{formatDate(comment.updated_at ?? comment.created_at)}</span>
					</div>

					{#if editingId === comment.id}
						<textarea
							bind:value={editText}
							rows="2"
							aria-label="Editar comentário"
							class="w-full rounded-md border border-border-subtle bg-surface px-3 py-2 text-sm text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
						></textarea>
						<div class="flex gap-2">
							<button
								type="button"
								disabled={busy || editText.trim() === ''}
								onclick={() => saveEdit(comment.id)}
								class="rounded-md bg-primary-600 px-3 py-1 text-xs font-medium text-white hover:bg-primary-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-50"
							>
								Salvar
							</button>
							<button
								type="button"
								onclick={cancelEdit}
								class="rounded-md border border-border-subtle px-3 py-1 text-xs font-medium text-text-secondary hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
							>
								Cancelar
							</button>
						</div>
					{:else}
						<p class="whitespace-pre-wrap text-sm text-text-secondary">{comment.content}</p>
						{#if comment.can_edit || comment.can_delete}
							<div class="flex gap-3">
								{#if comment.can_edit}
									<button
										type="button"
										onclick={() => startEdit(comment.id, comment.content)}
										class="text-xs font-medium text-primary-700 hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
									>
										Editar
									</button>
								{/if}
								{#if comment.can_delete}
									<button
										type="button"
										onclick={() => remove(comment.id)}
										class="text-xs font-medium text-danger hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-danger"
									>
										Excluir
									</button>
								{/if}
							</div>
						{/if}
					{/if}
				</li>
			{/each}
		</ul>
	{/if}
</section>
