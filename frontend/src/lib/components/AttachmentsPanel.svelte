<script lang="ts">
	/**
	 * Painel de ANEXOS do drawer de tarefa (Fase 5b-2). Lista `$store.detail.anexos`,
	 * faz UPLOAD via FormData (a store usa `client.postForm` — multipart, sem
	 * Content-Type manual, com X-CSRFToken), DOWNLOAD por link binário (`anexo.url`,
	 * mesma origin/cookie) e EXCLUSÃO. Valida o limite de 10MB no cliente antes de
	 * enviar (o backend é autoritativo: MAX_CONTENT_LENGTH=10MB).
	 */
	import type { TaskDrawerStore } from '$lib/stores/taskDrawer';

	interface Props {
		store: TaskDrawerStore;
	}

	let { store }: Props = $props();

	const MAX_BYTES = 10 * 1024 * 1024;

	let uploading = $state(false);
	let localError = $state<string | null>(null);
	let fileInput = $state<HTMLInputElement | null>(null);

	const anexos = $derived($store.detail?.anexos ?? []);
	const canManage = $derived($store.detail?.permissions.can_edit ?? false);

	function formatSize(bytes: number): string {
		if (bytes < 1024) return `${bytes} B`;
		if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
		return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
	}

	async function onFileChange(event: Event): Promise<void> {
		const input = event.currentTarget as HTMLInputElement;
		const file = input.files?.[0];
		if (!file) return;
		localError = null;
		if (file.size > MAX_BYTES) {
			localError = `O arquivo tem ${formatSize(file.size)}; o limite é 10 MB.`;
			input.value = '';
			return;
		}
		uploading = true;
		const ok = await store.uploadAttachment(file);
		uploading = false;
		input.value = '';
		if (!ok) return;
	}

	async function remove(anexoId: number): Promise<void> {
		if (uploading) return;
		if (!window.confirm('Excluir este anexo?')) return;
		await store.deleteAttachment(anexoId);
	}
</script>

<section aria-labelledby="drawer-anexos-title" class="flex flex-col gap-3">
	<h3 id="drawer-anexos-title" class="text-sm font-semibold text-text-primary">
		Anexos ({anexos.length})
	</h3>

	{#if canManage}
		<div class="flex flex-col gap-1">
			<label
				for="drawer-anexo-input"
				class="inline-flex w-fit cursor-pointer items-center gap-2 rounded-md border border-border-subtle bg-surface px-4 py-1.5 text-sm font-medium text-text-primary transition-colors duration-fast hover:bg-surface-muted focus-within:ring-2 focus-within:ring-primary-500 {uploading ? 'opacity-60' : ''}"
			>
				{uploading ? 'Enviando…' : 'Adicionar anexo'}
			</label>
			<input
				id="drawer-anexo-input"
				bind:this={fileInput}
				type="file"
				disabled={uploading}
				onchange={onFileChange}
				class="sr-only"
			/>
			<span class="text-xs text-text-muted">Tamanho máximo: 10 MB.</span>
			{#if localError}
				<p role="alert" class="text-xs text-danger">{localError}</p>
			{/if}
		</div>
	{/if}

	{#if anexos.length === 0}
		<p class="text-sm text-text-muted">Nenhum anexo.</p>
	{:else}
		<ul class="flex flex-col gap-2">
			{#each anexos as anexo (anexo.id)}
				<li class="flex items-center justify-between gap-3 rounded-md border border-border-subtle bg-surface px-3 py-2">
					<div class="flex min-w-0 flex-col">
						{#if anexo.url}
							<a
								href={anexo.url}
								target="_blank"
								rel="noopener"
								class="truncate text-sm font-medium text-primary-700 hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
							>
								{anexo.filename}
							</a>
						{:else}
							<span class="truncate text-sm text-text-primary">{anexo.filename}</span>
						{/if}
						<span class="text-xs text-text-muted">{anexo.uploaded_by}</span>
					</div>
					{#if canManage}
						<button
							type="button"
							onclick={() => remove(anexo.id)}
							aria-label={`Excluir anexo ${anexo.filename}`}
							class="shrink-0 text-xs font-medium text-danger hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-danger"
						>
							Excluir
						</button>
					{/if}
				</li>
			{/each}
		</ul>
	{/if}
</section>
