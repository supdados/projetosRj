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

<section
	aria-labelledby="drawer-anexos-title"
	class="flex flex-col gap-2 border-t border-border-subtle pt-3"
>
	<h3
		id="drawer-anexos-title"
		class="flex items-center gap-2 text-sm font-semibold text-text-primary"
	>
		<i class="fas fa-paperclip text-text-muted" aria-hidden="true"></i>
		<span>Anexos</span>
		<span
			class="inline-flex min-w-[18px] items-center justify-center rounded-full bg-primary-100 px-1.5 text-2xs font-bold text-primary-700"
		>
			{anexos.length}
		</span>
	</h3>

	{#if anexos.length === 0}
		<p class="m-0 px-0.5 py-0.5 text-xs italic text-text-muted">Nenhum anexo.</p>
	{:else}
		<ul class="flex flex-col gap-1.5">
			{#each anexos as anexo (anexo.id)}
				<li
					class="flex items-center gap-2 rounded-lg border border-border-subtle bg-surface-muted/40 px-2 py-1.5"
				>
					<span
						class="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-md bg-primary-100 text-base text-primary-700"
						aria-hidden="true"
					>
						<i class="fas fa-file"></i>
					</span>
					<div class="flex min-w-0 flex-1 flex-col">
						{#if anexo.url}
							<a
								href={anexo.url}
								target="_blank"
								rel="noopener"
								class="truncate text-sm font-medium text-text-primary hover:text-primary-700 hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
							>
								{anexo.filename}
							</a>
						{:else}
							<span class="truncate text-sm text-text-primary">{anexo.filename}</span>
						{/if}
						<span class="truncate text-2xs text-text-muted">{anexo.uploaded_by}</span>
					</div>
					{#if canManage}
						<button
							type="button"
							onclick={() => remove(anexo.id)}
							aria-label={`Excluir anexo ${anexo.filename}`}
							class="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-md text-xs text-text-muted transition-colors duration-fast hover:bg-surface-muted hover:text-danger focus:outline-none focus-visible:ring-2 focus-visible:ring-danger"
						>
							<i class="fas fa-trash-alt" aria-hidden="true"></i>
						</button>
					{/if}
				</li>
			{/each}
		</ul>
	{/if}

	{#if canManage}
		<div class="flex flex-col gap-1">
			<label
				for="drawer-anexo-input"
				class="inline-flex cursor-pointer items-center justify-center gap-2 rounded-lg border-[1.5px] border-dashed border-border-strong bg-surface-muted/40 px-3 py-1.5 text-xs font-semibold text-text-secondary transition-colors duration-fast hover:border-primary-500 hover:bg-primary-100 hover:text-primary-700 focus-within:ring-2 focus-within:ring-primary-500 {uploading ? 'opacity-60' : ''}"
			>
				<i class="fas {uploading ? 'fa-spinner fa-spin' : 'fa-plus'}" aria-hidden="true"></i>
				<span>{uploading ? 'Enviando…' : 'Adicionar anexo'}</span>
			</label>
			<input
				id="drawer-anexo-input"
				bind:this={fileInput}
				type="file"
				disabled={uploading}
				onchange={onFileChange}
				class="sr-only"
			/>
			<span class="text-2xs text-text-muted">Tamanho máximo: 10 MB.</span>
			{#if localError}
				<p role="alert" class="m-0 text-2xs text-danger">{localError}</p>
			{/if}
		</div>
	{/if}
</section>
