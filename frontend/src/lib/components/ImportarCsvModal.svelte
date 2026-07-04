<script lang="ts">
	/**
	 * Modal de importação de projetos via CSV (Admin) — sucessor SPA do
	 * `templates/projects/import_modal.html`. Envia `multipart/form-data` para
	 * `POST /api/projetos/importar-csv` (via `importProjectsCsv`), com o arquivo e
	 * os atributos comuns aplicados a todas as linhas (órgão/status/especial/tipo).
	 *
	 * O CSV exige cabeçalho com as colunas `titulo` e `descricao` (mesma regra do
	 * backend). Em sucesso, fecha e dispara `onImported(count)`.
	 */
	import { ApiClientError } from '$lib/api/client';
	import { importProjectsCsv } from '$lib/api/projects';
	import type { ProjectsListOptions } from '$lib/types/projects';
	import Modal from '$lib/components/Modal.svelte';

	interface Props {
		open: boolean;
		options: ProjectsListOptions | null;
		onClose: () => void;
		onImported: (count: number) => void;
	}

	let { open, options, onClose, onImported }: Props = $props();

	const STATUS_OPTIONS = ['Vigente', 'Suspenso', 'Finalizado'];

	let file = $state<File | null>(null);
	let orgaoId = $state<string>('');
	let status = $state<string>('Vigente');
	let deliveryType = $state<string>('');
	let specialProject = $state<string>('');
	let submitting = $state<boolean>(false);
	let errorMsg = $state<string>('');
	let fileInputEl = $state<HTMLInputElement | null>(null);

	const orgaoOptions = $derived(options?.orgaos_options ?? []);
	const deliveryTypes = $derived(options?.delivery_types_options ?? []);
	const specialOptions = $derived(options?.special_projects_options ?? []);

	const canSubmit = $derived(!submitting && file !== null && orgaoId.trim().length > 0);

	// Reseta o formulário sempre que o modal abre.
	$effect(() => {
		if (open) {
			file = null;
			orgaoId = orgaoOptions.length === 1 ? orgaoOptions[0].value : '';
			status = 'Vigente';
			deliveryType = '';
			specialProject = '';
			errorMsg = '';
			if (fileInputEl) fileInputEl.value = '';
		}
	});

	function onFileChange(event: Event): void {
		const input = event.target as HTMLInputElement;
		file = input.files?.[0] ?? null;
	}

	async function handleSubmit(event: SubmitEvent): Promise<void> {
		event.preventDefault();
		if (!canSubmit || file === null) return;
		submitting = true;
		errorMsg = '';
		const formData = new FormData();
		formData.append('arquivo', file);
		formData.append('orgao_id', orgaoId);
		formData.append('status', status);
		if (deliveryType) formData.append('delivery_type', deliveryType);
		if (specialProject) formData.append('special_project', specialProject);
		try {
			const result = await importProjectsCsv(formData);
			submitting = false;
			onImported(result.imported_count);
		} catch (err) {
			submitting = false;
			if (err instanceof ApiClientError && err.code === 'unauthenticated') return;
			errorMsg = err instanceof Error ? err.message : 'Falha ao importar o CSV.';
		}
	}
</script>

{#if open}
	<Modal labelId="import-csv-title" maxWidth="max-w-lg" onBackdrop={onClose}>
		<div class="flex flex-col gap-4">
			<div class="flex items-start justify-between gap-3">
				<h2 id="import-csv-title" class="font-heading text-lg font-bold text-primary-700">
					<i class="fas fa-file-import mr-2" aria-hidden="true"></i>Importar projetos (CSV)
				</h2>
				<button
					type="button"
					onclick={onClose}
					aria-label="Fechar"
					class="inline-flex h-8 w-8 items-center justify-center rounded-md text-text-muted transition-colors duration-fast hover:bg-surface-muted hover:text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
				>
					<i class="fas fa-times" aria-hidden="true"></i>
				</button>
			</div>

			<p class="text-sm text-text-secondary">
				O CSV precisa de cabeçalho com as colunas <code class="rounded bg-surface-muted px-1">titulo</code>
				e <code class="rounded bg-surface-muted px-1">descricao</code>. Os atributos abaixo são
				aplicados a todos os projetos importados.
			</p>

			{#if errorMsg}
				<div role="alert" class="rounded-lg border border-danger bg-surface px-3 py-2 text-sm text-text-primary">
					{errorMsg}
				</div>
			{/if}

			<form class="flex flex-col gap-3" onsubmit={handleSubmit}>
				<label class="flex flex-col gap-1 text-sm">
					<span class="font-semibold text-text-secondary">Arquivo CSV</span>
					<input
						bind:this={fileInputEl}
						type="file"
						accept=".csv,text/csv"
						required
						onchange={onFileChange}
						class="rounded-lg border border-border-subtle bg-surface px-2.5 py-1.5 text-sm text-text-primary file:mr-3 file:rounded-md file:border-0 file:bg-surface-muted file:px-3 file:py-1 file:text-sm file:font-medium file:text-text-primary focus:border-primary-500 focus:outline-none"
					/>
				</label>

				<label class="flex flex-col gap-1 text-sm">
					<span class="font-semibold text-text-secondary">Órgão de destino</span>
					<select
						bind:value={orgaoId}
						required
						class="h-9 rounded-lg border border-border-subtle bg-surface px-2.5 text-sm text-text-primary focus:border-primary-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
					>
						<option value="" disabled>Selecione o órgão…</option>
						{#each orgaoOptions as opt (opt.value)}
							<option value={opt.value}>{opt.label}</option>
						{/each}
					</select>
				</label>

				<div class="grid grid-cols-1 gap-3 sm:grid-cols-3">
					<label class="flex flex-col gap-1 text-sm">
						<span class="font-semibold text-text-secondary">Status</span>
						<select
							bind:value={status}
							class="h-9 rounded-lg border border-border-subtle bg-surface px-2.5 text-sm text-text-primary focus:border-primary-500 focus:outline-none"
						>
							{#each STATUS_OPTIONS as opt (opt)}
								<option value={opt}>{opt}</option>
							{/each}
						</select>
					</label>

					<label class="flex flex-col gap-1 text-sm">
						<span class="font-semibold text-text-secondary">Tipo de entrega</span>
						<select
							bind:value={deliveryType}
							class="h-9 rounded-lg border border-border-subtle bg-surface px-2.5 text-sm text-text-primary focus:border-primary-500 focus:outline-none"
						>
							<option value="">—</option>
							{#each deliveryTypes as opt (opt)}
								<option value={opt}>{opt}</option>
							{/each}
						</select>
					</label>

					<label class="flex flex-col gap-1 text-sm">
						<span class="font-semibold text-text-secondary">Projeto especial</span>
						<select
							bind:value={specialProject}
							class="h-9 rounded-lg border border-border-subtle bg-surface px-2.5 text-sm text-text-primary focus:border-primary-500 focus:outline-none"
						>
							<option value="">—</option>
							{#each specialOptions as opt (opt)}
								<option value={opt}>{opt}</option>
							{/each}
						</select>
					</label>
				</div>

				<div class="mt-1 flex justify-end gap-2">
					<button
						type="button"
						onclick={onClose}
						class="h-9 rounded-md border border-border-subtle bg-surface px-4 text-sm font-medium text-text-secondary transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
					>
						Cancelar
					</button>
					<button
						type="submit"
						disabled={!canSubmit}
						class="inline-flex h-9 items-center gap-2 rounded-md bg-primary-600 px-4 text-sm font-semibold text-white shadow-sm transition-colors duration-fast hover:bg-primary-700 hover:shadow-md focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:cursor-not-allowed disabled:opacity-50"
					>
						<i class="fas {submitting ? 'fa-spinner fa-spin' : 'fa-file-import'}" aria-hidden="true"></i>
						Importar
					</button>
				</div>
			</form>
		</div>
	</Modal>
{/if}
