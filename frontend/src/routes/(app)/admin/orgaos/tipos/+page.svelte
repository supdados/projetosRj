<script lang="ts">
	/**
	 * Tela "Admin > Tipos de Órgão" (FASE 4 — CRUD). URL: /spa/admin/orgaos/tipos.
	 *
	 * Lista os tipos de órgão (com nível, uso e status) e mantém um painel
	 * inline de criar/editar (nome, identificador, nível, descrição, flags
	 * Ativo / Pode ser raiz). Ações: criar, editar, alternar ativo/inativo e
	 * excluir (com confirmação). Consome `/api/admin/orgaos/tipos*` via
	 * `$lib/api/adminOrgaoTipos` (mutações com X-CSRFToken por `client.post`).
	 *
	 * Erros de validação/hierarquia do backend (422 validação, 409 conflito de
	 * nível/raiz/uso) são exibidos diretamente — a regra é preservada no
	 * servidor (`_normalize_tipo_form`, `_invalid_orgao_type_level_changes`).
	 * Estados loading/erro/vazio anunciados via aria-live.
	 *
	 * Padrão espelhado das telas de leitura (FASE 3): projetos/+page.svelte e
	 * tarefas/+page.svelte (Card/Badge reusados, links base-aware, dark via
	 * vars). Referência visual: templates/admin/orgao_tipos.html e
	 * orgao_tipo_form.html.
	 */
	import { onMount, onDestroy } from 'svelte';
	import { base } from '$app/paths';
	import { ApiClientError } from '$lib/api/client';
	import {
		fetchOrgaoTipos,
		createOrgaoTipo,
		updateOrgaoTipo,
		toggleOrgaoTipoAtivo,
		deleteOrgaoTipo
	} from '$lib/api/adminOrgaoTipos';
	import type {
		AdminOrgaoTipo,
		AdminOrgaoTipoFormInput
	} from '$lib/types/adminOrgaoTipos';
	import Card from '$lib/components/Card.svelte';
	import Badge from '$lib/components/Badge.svelte';
	import PageHeader from '$lib/components/PageHeader.svelte';
	import Button from '$lib/components/Button.svelte';
	import CountBadge from '$lib/components/CountBadge.svelte';

	type LoadState = 'loading' | 'ready' | 'error';
	type FormMode = 'create' | 'edit';

	let loadState = $state<LoadState>('loading');
	let tipos = $state<AdminOrgaoTipo[]>([]);
	let usageCounts = $state<Record<string, number>>({});
	let errorMessage = $state<string>('');

	// Painel de form (criar/editar). `formMode` define a ação no submit.
	let formOpen = $state<boolean>(false);
	let formMode = $state<FormMode>('create');
	let editingId = $state<number | null>(null);
	let formError = $state<string>('');
	let saving = $state<boolean>(false);

	// Campos controlados do form.
	let fNome = $state<string>('');
	let fSlug = $state<string>('');
	let fNivel = $state<number>(1);
	let fDescricao = $state<string>('');
	let fAtivo = $state<boolean>(true);
	let fPermiteRaiz = $state<boolean>(false);

	// Linha em ação (toggle/delete) para feedback e desabilitar botões.
	let busyId = $state<number | null>(null);
	let rowError = $state<string>('');

	let inFlight: AbortController | null = null;

	/** Nº de órgãos vinculados a um tipo (0 quando ausente). */
	function usageOf(tipoId: number): number {
		return usageCounts[String(tipoId)] ?? 0;
	}

	async function load(): Promise<void> {
		loadState = tipos.length ? loadState : 'loading';
		errorMessage = '';
		inFlight?.abort();
		const controller = new AbortController();
		inFlight = controller;
		try {
			const data = await fetchOrgaoTipos(controller.signal);
			if (controller.signal.aborted) return;
			tipos = data.tipos;
			usageCounts = data.usage_counts;
			loadState = 'ready';
		} catch (err) {
			if (controller.signal.aborted) return;
			if (err instanceof ApiClientError && err.code === 'unauthenticated') return;
			errorMessage =
				err instanceof Error ? err.message : 'Falha ao carregar os tipos de órgão.';
			loadState = 'error';
		}
	}

	function openCreate(): void {
		formMode = 'create';
		editingId = null;
		formError = '';
		fNome = '';
		fSlug = '';
		fNivel = 1;
		fDescricao = '';
		fAtivo = true;
		fPermiteRaiz = false;
		formOpen = true;
	}

	function openEdit(tipo: AdminOrgaoTipo): void {
		formMode = 'edit';
		editingId = tipo.id;
		formError = '';
		fNome = tipo.nome;
		fSlug = tipo.slug ?? '';
		fNivel = tipo.nivel;
		fDescricao = tipo.descricao ?? '';
		fAtivo = tipo.ativo;
		fPermiteRaiz = tipo.permite_raiz;
		formOpen = true;
	}

	function closeForm(): void {
		formOpen = false;
		formError = '';
	}

	function currentInput(): AdminOrgaoTipoFormInput {
		return {
			nome: fNome,
			slug: fSlug,
			nivel: fNivel,
			descricao: fDescricao,
			ativo: fAtivo,
			permite_raiz: fPermiteRaiz
		};
	}

	async function onSubmit(event: SubmitEvent): Promise<void> {
		event.preventDefault();
		if (saving) return;
		formError = '';
		if (!fNome.trim()) {
			formError = 'Informe o nome do tipo.';
			return;
		}
		saving = true;
		try {
			if (formMode === 'edit' && editingId !== null) {
				await updateOrgaoTipo(editingId, currentInput());
			} else {
				await createOrgaoTipo(currentInput());
			}
			formOpen = false;
			await load();
		} catch (err) {
			// 422 (validação) e 409 (hierarquia/nível/uso) trazem mensagem do backend.
			if (err instanceof ApiClientError && err.code === 'unauthenticated') return;
			formError =
				err instanceof Error ? err.message : 'Não foi possível salvar o tipo de órgão.';
		} finally {
			saving = false;
		}
	}

	async function onToggle(tipo: AdminOrgaoTipo): Promise<void> {
		if (busyId !== null) return;
		busyId = tipo.id;
		rowError = '';
		try {
			await toggleOrgaoTipoAtivo(tipo.id);
			await load();
		} catch (err) {
			if (err instanceof ApiClientError && err.code === 'unauthenticated') return;
			rowError =
				err instanceof Error
					? err.message
					: `Não foi possível alterar o status de "${tipo.nome}".`;
		} finally {
			busyId = null;
		}
	}

	async function onDelete(tipo: AdminOrgaoTipo): Promise<void> {
		if (busyId !== null) return;
		const confirmed =
			typeof window === 'undefined' ||
			window.confirm(
				`Excluir o tipo "${tipo.nome}"? Esta ação não pode ser desfeita.`
			);
		if (!confirmed) return;
		busyId = tipo.id;
		rowError = '';
		try {
			await deleteOrgaoTipo(tipo.id);
			// Se o tipo excluído estava aberto no form, fecha o painel.
			if (editingId === tipo.id) formOpen = false;
			await load();
		} catch (err) {
			if (err instanceof ApiClientError && err.code === 'unauthenticated') return;
			rowError =
				err instanceof Error
					? err.message
					: `Não foi possível excluir o tipo "${tipo.nome}".`;
		} finally {
			busyId = null;
		}
	}

	/** Excluir é proibido pelo backend quando em uso ou permite raiz. */
	function deleteDisabled(tipo: AdminOrgaoTipo): boolean {
		return usageOf(tipo.id) > 0 || tipo.permite_raiz;
	}

	onMount(() => {
		void load();
		return () => inFlight?.abort();
	});

	onDestroy(() => inFlight?.abort());
</script>

<svelte:head>
	<title>Tipos de Órgão — ProjetosRJ</title>
</svelte:head>

<section aria-labelledby="tipos-title" class="flex flex-col gap-6">
	<PageHeader
		compact
		class="min-h-[3.5rem]"
		labelId="tipos-title"
		subtitle="Configure os níveis que definem o que fica acima, abaixo ou no mesmo nível na hierarquia de órgãos."
	>
		{#snippet titleContent()}
			<span class="align-middle">Tipos de Órgão</span>
			{#if loadState === 'ready'}
				<CountBadge class="ml-2">{tipos.length} tipo{tipos.length === 1 ? '' : 's'}</CountBadge>
			{/if}
		{/snippet}
		{#snippet actions()}
			<a
				href="{base}/admin/orgaos"
				class="inline-flex h-8 items-center gap-1.5 rounded-md border border-border-subtle bg-surface px-3 text-sm font-medium text-text-primary no-underline transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
			>
				Hierarquia
			</a>
			<Button size="sm" onclick={openCreate}>
				{#snippet icon()}<i class="fas fa-plus" aria-hidden="true"></i>{/snippet}
				Novo tipo
			</Button>
		{/snippet}
	</PageHeader>

	{#if formOpen}
		<Card title={formMode === 'edit' ? 'Editar tipo de órgão' : 'Novo tipo de órgão'} labelId="tipo-form-title">
			<form class="flex flex-col gap-4 px-5 py-4" onsubmit={onSubmit} novalidate>
				<p class="text-sm text-text-muted">
					O nível define a hierarquia: níveis menores ficam acima; níveis iguais ficam
					lado a lado.
				</p>

				{#if formError}
					<div
						role="alert"
						class="rounded-md border border-danger bg-surface-muted px-3 py-2 text-sm text-danger"
					>
						{formError}
					</div>
				{/if}

				<div class="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
					<div class="flex flex-col gap-1 sm:col-span-2">
						<label
							for="tipoNome"
							class="text-xs font-semibold uppercase tracking-wide text-text-muted"
						>
							Nome <span class="text-danger">*</span>
						</label>
						<input
							id="tipoNome"
							type="text"
							maxlength="80"
							required
							bind:value={fNome}
							class="rounded-md border border-border-subtle bg-surface px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
						/>
					</div>
					<div class="flex flex-col gap-1">
						<label
							for="tipoSlug"
							class="text-xs font-semibold uppercase tracking-wide text-text-muted"
						>
							Identificador
						</label>
						<input
							id="tipoSlug"
							type="text"
							maxlength="100"
							placeholder="gerado pelo nome"
							bind:value={fSlug}
							class="rounded-md border border-border-subtle bg-surface px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
						/>
					</div>
					<div class="flex flex-col gap-1">
						<label
							for="tipoNivel"
							class="text-xs font-semibold uppercase tracking-wide text-text-muted"
						>
							Nível <span class="text-danger">*</span>
						</label>
						<input
							id="tipoNivel"
							type="number"
							min="0"
							required
							bind:value={fNivel}
							class="rounded-md border border-border-subtle bg-surface px-3 py-2 text-sm text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
						/>
					</div>
					<div class="flex flex-col gap-1 sm:col-span-2 lg:col-span-4">
						<label
							for="tipoDescricao"
							class="text-xs font-semibold uppercase tracking-wide text-text-muted"
						>
							Descrição
						</label>
						<input
							id="tipoDescricao"
							type="text"
							maxlength="255"
							bind:value={fDescricao}
							class="rounded-md border border-border-subtle bg-surface px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
						/>
					</div>
				</div>

				<fieldset class="flex flex-wrap gap-6">
					<legend class="sr-only">Flags do tipo</legend>
					<label class="inline-flex items-center gap-2 text-sm text-text-primary">
						<input
							type="checkbox"
							bind:checked={fAtivo}
							class="h-4 w-4 rounded border-border-subtle text-primary-700 focus:ring-primary-500"
						/>
						Ativo
					</label>
					<label class="inline-flex items-center gap-2 text-sm text-text-primary">
						<input
							type="checkbox"
							bind:checked={fPermiteRaiz}
							class="h-4 w-4 rounded border-border-subtle text-primary-700 focus:ring-primary-500"
						/>
						Pode ser raiz
					</label>
				</fieldset>

				<div class="flex flex-wrap items-center gap-2">
					<button
						type="submit"
						disabled={saving}
						class="rounded-md border border-primary-500 bg-primary-100 px-4 py-2 text-sm font-medium text-primary-700 transition-colors duration-fast hover:bg-primary-100/80 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-50"
					>
						{saving
							? 'Salvando…'
							: formMode === 'edit'
								? 'Salvar alterações'
								: 'Criar tipo'}
					</button>
					<button
						type="button"
						onclick={closeForm}
						disabled={saving}
						class="rounded-md border border-border-subtle bg-surface px-4 py-2 text-sm font-medium text-text-primary transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-50"
					>
						Cancelar
					</button>
				</div>
			</form>
		</Card>
	{/if}

	{#if rowError}
		<div
			role="alert"
			class="rounded-md border border-danger bg-surface-muted px-3 py-2 text-sm text-danger"
		>
			{rowError}
		</div>
	{/if}

	{#if loadState === 'loading'}
		<p role="status" aria-live="polite" class="text-text-secondary">
			Carregando tipos de órgão…
		</p>
	{:else if loadState === 'error'}
		<div
			role="alert"
			class="flex flex-col items-start gap-3 rounded-lg border border-danger bg-surface px-5 py-4"
		>
			<p class="text-text-primary">{errorMessage}</p>
			<button
				type="button"
				onclick={() => load()}
				class="rounded-md border border-border-subtle bg-surface px-4 py-2 text-sm font-medium text-text-primary transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
			>
				Tentar novamente
			</button>
		</div>
	{:else}
		<div role="status" aria-live="polite" class="sr-only">
			{tipos.length} tipo{tipos.length === 1 ? '' : 's'} de órgão.
		</div>

		{#if tipos.length === 0}
			<div class="rounded-lg border border-border-subtle bg-surface px-5 py-12 text-center">
				<h2 class="font-heading text-lg font-semibold text-text-primary">
					Nenhum tipo cadastrado
				</h2>
				<p class="mt-2 text-sm text-text-muted">
					Crie o primeiro tipo de órgão para definir os níveis da hierarquia.
				</p>
			</div>
		{:else}
			<Card>
				<div class="overflow-x-auto">
					<table class="w-full border-collapse text-sm">
						<caption class="sr-only">Lista de tipos de órgão</caption>
						<thead>
							<tr class="border-b border-border-subtle text-left text-text-muted">
								<th scope="col" class="px-3 py-2 font-semibold">Tipo</th>
								<th scope="col" class="px-3 py-2 font-semibold">Nível</th>
								<th scope="col" class="px-3 py-2 font-semibold">Uso</th>
								<th scope="col" class="px-3 py-2 font-semibold">Status</th>
								<th scope="col" class="px-3 py-2 text-right font-semibold">Ações</th>
							</tr>
						</thead>
						<tbody>
							{#each tipos as tipo (tipo.id)}
								{@const uso = usageOf(tipo.id)}
								<tr class="border-b border-border-subtle last:border-0">
									<td class="px-3 py-2">
										<div class="flex flex-wrap items-center gap-2">
											<span class="font-medium text-text-primary">{tipo.nome}</span>
											{#if tipo.permite_raiz}
												<Badge tone="primary">Raiz</Badge>
											{/if}
											{#if tipo.is_system}
												<Badge tone="neutral">Sistema</Badge>
											{/if}
										</div>
										{#if tipo.descricao}
											<p class="mt-1 text-xs text-text-muted">{tipo.descricao}</p>
										{/if}
									</td>
									<td class="px-3 py-2 text-text-secondary">{tipo.nivel}</td>
									<td class="px-3 py-2 text-text-secondary">
										{uso} órgão{uso === 1 ? '' : 's'}
									</td>
									<td class="px-3 py-2">
										<Badge tone={tipo.ativo ? 'success' : 'neutral'}>
											{tipo.ativo ? 'Ativo' : 'Inativo'}
										</Badge>
									</td>
									<td class="px-3 py-2">
										<div class="flex flex-wrap items-center justify-end gap-2">
											<button
												type="button"
												onclick={() => openEdit(tipo)}
												disabled={busyId === tipo.id}
												class="rounded-md border border-border-subtle bg-surface px-3 py-1.5 text-xs font-medium text-primary-700 transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-50"
											>
												Editar
											</button>
											<button
												type="button"
												onclick={() => onToggle(tipo)}
												disabled={busyId === tipo.id}
												class="rounded-md border border-border-subtle bg-surface px-3 py-1.5 text-xs font-medium text-text-primary transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-50"
											>
												{tipo.ativo ? 'Desativar' : 'Ativar'}
											</button>
											<button
												type="button"
												onclick={() => onDelete(tipo)}
												disabled={busyId === tipo.id || deleteDisabled(tipo)}
												title={deleteDisabled(tipo)
													? 'Não é possível excluir um tipo em uso ou que pode ser raiz.'
													: undefined}
												class="rounded-md border border-danger bg-surface px-3 py-1.5 text-xs font-medium text-danger transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-danger disabled:opacity-50"
											>
												Excluir
											</button>
										</div>
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			</Card>
		{/if}
	{/if}
</section>
