<script lang="ts">
	/**
	 * Painel de ANEXOS do drawer de tarefa (Fase 5b-2). Lista `$store.detail.anexos`,
	 * faz UPLOAD via FormData (a store usa `client.postForm` — multipart, sem
	 * Content-Type manual, com X-CSRFToken), DOWNLOAD por link binário (`anexo.url`,
	 * mesma origin/cookie) e EXCLUSÃO. Valida o limite de 10MB no cliente antes de
	 * enviar (o backend é autoritativo: MAX_CONTENT_LENGTH=10MB).
	 *
	 * PARIDADE v4.5 (static/js/modules/kanban/drawer-anexos.js):
	 *   - thumbnails de imagem (anexo.is_image) em vez do ícone genérico fa-file;
	 *   - clique abre o PREVIEW MODAL inline (imagem / pdf em iframe / fallback) com
	 *     ações "Abrir em nova aba" e "Baixar" — antes só abria nova aba;
	 *   - drag-and-drop de arquivo na zona de upload (drop → mesmo fluxo do input).
	 */
	import AppIcon from '$lib/components/AppIcon.svelte';
	import FeedbackIcon from '$lib/components/FeedbackIcon.svelte';
	import Modal from '$lib/components/Modal.svelte';
	import { confirmAction } from '$lib/stores/confirm';
	import type { TaskDrawerStore } from '$lib/stores/taskDrawer';
	import type { TaskAttachment } from '$lib/types/taskDrawer';

	interface Props {
		store: TaskDrawerStore;
		/**
		 * Prefixo dos ids do painel. Default 'drawer' (uso no TaskDrawer). Na lista
		 * usa `task-<id>` para o input de arquivo/título não colidirem entre linhas.
		 */
		idPrefix?: string;
	}

	let { store, idPrefix = 'drawer' }: Props = $props();

	const MAX_BYTES = 10 * 1024 * 1024;

	let uploading = $state(false);
	let localError = $state<string | null>(null);
	let fileInput = $state<HTMLInputElement | null>(null);
	let dragActive = $state(false);
	let preview = $state<TaskAttachment | null>(null);

	const anexos = $derived($store.detail?.anexos ?? []);
	const canManage = $derived($store.detail?.permissions.can_edit ?? false);

	/** PDFs ganham preview em iframe; imagens viram <img>; o resto cai no fallback. */
	const previewIsPdf = $derived(
		preview
			? preview.content_type.toLowerCase().includes('pdf') ||
					/\.pdf($|\?)/i.test(preview.url ?? '')
			: false
	);

	function formatSize(bytes: number): string {
		if (bytes < 1024) return `${bytes} B`;
		if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
		return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
	}

	async function uploadFile(file: File | undefined | null): Promise<void> {
		if (!file) return;
		localError = null;
		if (file.size > MAX_BYTES) {
			localError = `O arquivo tem ${formatSize(file.size)}; o limite é 10 MB.`;
			return;
		}
		uploading = true;
		await store.uploadAttachment(file);
		uploading = false;
	}

	async function onFileChange(event: Event): Promise<void> {
		const input = event.currentTarget as HTMLInputElement;
		const file = input.files?.[0];
		await uploadFile(file);
		input.value = '';
	}

	function onDragOver(event: DragEvent): void {
		if (!canManage || uploading) return;
		event.preventDefault();
		dragActive = true;
	}

	function onDragLeave(): void {
		dragActive = false;
	}

	async function onDrop(event: DragEvent): Promise<void> {
		if (!canManage || uploading) return;
		event.preventDefault();
		dragActive = false;
		await uploadFile(event.dataTransfer?.files?.[0]);
	}

	function openPreview(anexo: TaskAttachment, event: MouseEvent): void {
		if (!anexo.url) return;
		event.preventDefault();
		preview = anexo;
	}

	function closePreview(): void {
		preview = null;
	}

	async function remove(anexo: TaskAttachment): Promise<void> {
		if (uploading) return;
		await confirmAction({
			title: 'Excluir anexo?',
			description: `"${anexo.filename}" será removido desta tarefa. Esta ação não pode ser desfeita.`,
			tone: 'danger',
			icon: 'trash',
			confirmLabel: 'Excluir anexo',
			busyLabel: 'Excluindo…',
			// `run` mantém o diálogo aberto e mostra a mensagem do servidor na falha.
			run: async () => {
				const ok = await store.deleteAttachment(anexo.id);
				if (!ok) throw new Error($store.error ?? 'Não foi possível excluir o anexo.');
			}
		});
	}
</script>

<section
	aria-labelledby={`${idPrefix}-anexos-title`}
	class="flex flex-col gap-2 border-t border-border-subtle pt-3"
>
	<h3
		id={`${idPrefix}-anexos-title`}
		class="flex items-center gap-2 text-sm font-semibold text-text-primary"
	>
		<AppIcon id="anexo" size={16} class="text-text-muted" />
		<span>Anexos</span>
		<span
			class="inline-flex min-w-[18px] items-center justify-center rounded-full bg-wash-neutral px-1.5 text-2xs font-bold text-brand"
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
					class="flex items-center gap-2 rounded-lg border border-border-subtle bg-surface-muted px-2 py-1.5"
				>
					{#if anexo.url}
						<a
							href={anexo.url}
							target="_blank"
							rel="noopener"
							onclick={(e) => openPreview(anexo, e)}
							class="flex min-w-0 flex-1 items-center gap-2 no-underline focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
						>
							{#if anexo.is_image}
								<img
									src={anexo.url}
									alt={anexo.filename}
									loading="lazy"
									class="h-9 w-9 flex-shrink-0 rounded-md border border-border-subtle object-cover"
								/>
							{:else}
								<span
									class="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-md bg-wash-neutral text-base text-brand"
									aria-hidden="true"
								>
									<i class="fas fa-file"></i>
								</span>
							{/if}
							<span class="flex min-w-0 flex-1 flex-col">
								<span class="truncate text-sm font-medium text-text-primary hover:text-brand">
									{anexo.filename}
								</span>
								<span class="truncate text-2xs text-text-muted">{anexo.uploaded_by}</span>
							</span>
						</a>
					{:else}
						<span
							class="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-md bg-wash-neutral text-base text-brand"
							aria-hidden="true"
						>
							<i class="fas fa-file"></i>
						</span>
						<span class="flex min-w-0 flex-1 flex-col">
							<span class="truncate text-sm text-text-primary">{anexo.filename}</span>
							<span class="truncate text-2xs text-text-muted">{anexo.uploaded_by}</span>
						</span>
					{/if}
					{#if canManage}
						<button
							type="button"
							onclick={() => void remove(anexo)}
							aria-label={`Excluir anexo ${anexo.filename}`}
							class="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-md text-xs text-text-muted transition-colors duration-fast hover:bg-surface-muted hover:text-danger focus:outline-none focus-visible:ring-2 focus-visible:ring-danger"
						>
							<i class="fas fa-times" aria-hidden="true"></i>
						</button>
					{/if}
				</li>
			{/each}
		</ul>
	{/if}

	{#if canManage}
		<div class="flex flex-col gap-1">
			<label
				for={`${idPrefix}-anexo-input`}
				ondragover={onDragOver}
				ondragleave={onDragLeave}
				ondrop={onDrop}
				class="inline-flex cursor-pointer items-center justify-center gap-2 rounded-lg border border-dashed px-3 py-2.5 text-xs font-semibold transition-colors duration-fast focus-within:ring-2 focus-within:ring-brand {dragActive
					? 'border-brand bg-wash-brand text-brand'
					: 'border-border-strong bg-surface-muted text-text-secondary hover:border-brand hover:bg-wash-neutral hover:text-brand'} {uploading
					? 'opacity-60'
					: ''}"
			>
				<i class="fas {uploading ? 'fa-spinner fa-spin' : 'fa-plus'}" aria-hidden="true"></i>
				<span
					>{uploading ? 'Enviando…' : dragActive ? 'Solte para enviar' : 'Adicionar anexo'}</span
				>
			</label>
			<input
				id={`${idPrefix}-anexo-input`}
				bind:this={fileInput}
				type="file"
				disabled={uploading}
				onchange={onFileChange}
				class="sr-only"
			/>
			<span class="text-2xs text-text-muted">Tamanho máximo: 10 MB. Arraste e solte também funciona.</span>
			{#if localError}
				<p role="alert" class="m-0 text-2xs text-danger">{localError}</p>
			{/if}
		</div>
	{/if}
</section>

{#if preview && preview.url}
	<!-- Preview no chrome único de modal (z-modal, Esc e foco preso vêm dele). -->
	<Modal
		labelId={`${idPrefix}-anexo-preview-title`}
		maxWidth="max-w-[52rem]"
		onBackdrop={closePreview}
	>
		<header class="flex items-center justify-between gap-2 border-b border-border-subtle pb-3">
			<h6
				id={`${idPrefix}-anexo-preview-title`}
				class="m-0 truncate text-sm font-semibold text-text-primary"
			>
				{preview.filename}
			</h6>
			<button
				type="button"
				onclick={closePreview}
				aria-label="Fechar preview"
				class="flex h-7 w-7 items-center justify-center rounded-md text-text-muted transition-colors duration-fast hover:bg-surface-muted hover:text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
			>
				<FeedbackIcon id="close" size={16} />
			</button>
		</header>
		<div class="mt-3 flex max-h-[60vh] min-h-0 items-center justify-center overflow-auto rounded-md bg-surface-muted p-3">
			{#if preview.is_image}
				<img
					src={preview.url}
					alt={preview.filename}
					loading="lazy"
					class="max-h-[56vh] max-w-full rounded-md object-contain"
				/>
			{:else if previewIsPdf}
				<iframe
					src={preview.url}
					title={preview.filename}
					class="h-[56vh] w-full rounded-md border-none bg-surface"
				></iframe>
			{:else}
				<div class="flex flex-col items-center gap-2 py-10 text-center text-text-secondary">
					<i class="fas fa-file text-4xl text-text-muted" aria-hidden="true"></i>
					<p class="m-0 text-sm">Preview não disponível para este tipo de arquivo.</p>
					<span class="text-xs text-text-muted">{preview.filename}</span>
				</div>
			{/if}
		</div>
		<footer class="mt-3 flex items-center justify-end gap-2 border-t border-border-subtle pt-3">
			<a
				href={preview.url}
				target="_blank"
				rel="noopener"
				class="rounded-md border border-border-subtle bg-surface px-3 py-1.5 text-xs font-semibold text-text-secondary no-underline transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
			>
				Abrir em nova aba
			</a>
			<a
				href={preview.url}
				target="_blank"
				rel="noopener"
				download={preview.filename}
				class="rounded-md bg-brand px-3 py-1.5 text-xs font-semibold text-on-brand no-underline shadow-sm transition-colors duration-fast hover:bg-brand-hover hover:shadow-md focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
			>
				Baixar
			</a>
		</footer>
	</Modal>
{/if}
