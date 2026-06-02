<script lang="ts">
	/**
	 * Tela "Detalhe de Projeto" (FASE 5a). URL: /spa/projetos/<id>.
	 *
	 * Carrega `GET /api/projetos/<id>/detalhe` (modulo `$lib/api/projectDetail`) e
	 * compoe ProjectHeader (sticky/compacto + edicao inline de titulo/status/
	 * prioridade), edicao inline dos demais campos do projeto, StageList (CRUD de
	 * etapas + reordenacao por DnD + comentarios) e ImportModelModal.
	 *
	 * ORQUESTRACAO: esta pagina e a UNICA que chama a API; os componentes sao
	 * controlados por callback. A CASCATA DE DATAS E SERVER-SIDE — ao reordenar
	 * etapas ou editar uma data/campo de etapa, chamamos o endpoint e RE-BUSCAMOS o
	 * estado do servidor (a cascata pode mudar as etapas seguintes). O front NUNCA
	 * recalcula datas nem dias uteis.
	 *
	 * Restricoes da fase:
	 *   - Tarefas das etapas sao SOMENTE LEITURA (contagem + lista simples sob
	 *     demanda); sem mutacao (Fase 5b cobre drawer/quick-add).
	 *   - Reunioes Google ficam read-only (Fase 6); StageRow ja as trata.
	 *
	 * Acessivel: heading de nivel 1 (no ProjectHeader), estados loading/erro/vazio
	 * anunciados via aria-live/role=alert, retry focavel. Erros tratados:
	 *   - 404 `not_found`; 403 `forbidden`; 401 ja redireciona em `client.ts`.
	 * Links internos sao base-aware (`$app/paths`).
	 */
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import { base } from '$app/paths';
	import { ApiClientError } from '$lib/api/client';
	import {
		fetchProjectDetail,
		fetchEtapaTasks,
		updateProjectInline,
		addEtapa,
		deleteEtapa,
		updateEtapaField,
		saveEtapaComentario,
		toggleEtapaIniciada,
		toggleEtapaDone,
		reorderEtapas,
		importStageModel,
		fetchStageTemplates
	} from '$lib/api/projectDetail';
	import type {
		ProjectDetailData,
		EtapaDetail,
		EtapaTask,
		EtapaInlineField,
		StageTemplateOption,
		ProjectInlinePayload
	} from '$lib/types/projectDetail';
	import ProjectHeader from '$lib/components/ProjectHeader.svelte';
	import InlineEditField from '$lib/components/InlineEditField.svelte';
	import StageList from '$lib/components/StageList.svelte';
	import ImportModelModal from '$lib/components/ImportModelModal.svelte';
	import Card from '$lib/components/Card.svelte';

	type LoadState = 'loading' | 'ready' | 'error';
	type HeaderField = 'titulo' | 'status' | 'prioridade';

	interface FieldState {
		pending?: boolean;
		error?: string | null;
	}
	/** Estado de mutacao por etapa, repassado ao StageList. */
	interface RowState {
		fields?: Partial<Record<EtapaInlineField, FieldState>>;
		busy?: boolean;
		error?: string | null;
	}

	const projectId = $derived(Number($page.params.id));

	let loadState = $state<LoadState>('loading');
	let data = $state<ProjectDetailData | null>(null);
	let errorMessage = $state<string>('');
	let errorKind = $state<'forbidden' | 'not_found' | 'generic'>('generic');

	// Estados de edicao inline do cabecalho e dos campos do projeto.
	let projectFieldStates = $state<Record<string, FieldState>>({});

	// Estados de mutacao das etapas (por etapa) e da reordenacao.
	let rowStates = $state<Record<number, RowState>>({});
	let reordering = $state<boolean>(false);
	let reorderError = $state<string | null>(null);

	// Tarefas read-only por etapa (carregadas sob demanda).
	let tasksByEtapa = $state<Record<number, EtapaTask[] | null>>({});
	let tasksLoading = $state<Record<number, boolean>>({});

	// Adicionar etapa.
	let newStageDescription = $state<string>('');
	let addingStage = $state<boolean>(false);
	let addStageError = $state<string | null>(null);

	// Importar modelo de etapas.
	let importOpen = $state<boolean>(false);
	let templates = $state<StageTemplateOption[]>([]);
	let templatesLoading = $state<boolean>(false);
	let importSubmitting = $state<boolean>(false);
	let importError = $state<string | null>(null);

	// Offset do topnav fixo para o sticky do cabecalho (medido no mount).
	let topOffset = $state<number>(0);

	const canEdit = $derived(data?.permissions.can_edit ?? false);

	/** Mensagem amigavel para um erro de API/desconhecido. */
	function messageOf(err: unknown, fallback: string): string {
		if (err instanceof ApiClientError) return err.message;
		if (err instanceof Error) return err.message;
		return fallback;
	}

	/** Trata 401 (no-op: client.ts ja redirecionou) e devolve true se foi 401. */
	function isUnauthenticated(err: unknown): boolean {
		return err instanceof ApiClientError && err.code === 'unauthenticated';
	}

	async function load(): Promise<void> {
		loadState = 'loading';
		errorMessage = '';
		errorKind = 'generic';
		try {
			data = await fetchProjectDetail(projectId);
			loadState = 'ready';
		} catch (err) {
			if (isUnauthenticated(err)) return;
			if (err instanceof ApiClientError) {
				if (err.code === 'not_found') errorKind = 'not_found';
				else if (err.code === 'forbidden') errorKind = 'forbidden';
			}
			errorMessage = messageOf(err, 'Falha ao carregar o detalhe do projeto.');
			loadState = 'error';
		}
	}

	/** Re-busca o detalhe completo (apos mutacoes que disparam cascata). */
	async function refresh(): Promise<void> {
		try {
			data = await fetchProjectDetail(projectId);
		} catch (err) {
			if (isUnauthenticated(err)) return;
			errorMessage = messageOf(err, 'Falha ao recarregar o projeto.');
		}
	}

	// --- Edicao inline de campos do projeto (cabecalho + demais) -------------

	function setProjectFieldState(field: string, next: FieldState): void {
		projectFieldStates = { ...projectFieldStates, [field]: next };
	}

	/**
	 * Salva um campo do projeto inline (chama /inline) e atualiza o projeto com a
	 * resposta. Usado tanto pelo cabecalho (titulo/status/prioridade) quanto pelos
	 * campos da secao "Detalhes".
	 */
	async function saveProjectField(field: string, value: string): Promise<void> {
		if (!data) return;
		setProjectFieldState(field, { pending: true, error: null });
		const payload: ProjectInlinePayload = { [field]: value === '' ? null : value };
		try {
			const result = await updateProjectInline(projectId, payload);
			data = { ...data, project: result.project };
			setProjectFieldState(field, { pending: false, error: null });
		} catch (err) {
			if (isUnauthenticated(err)) return;
			setProjectFieldState(field, {
				pending: false,
				error: messageOf(err, 'Falha ao salvar o campo.')
			});
		}
	}

	function onHeaderEditField(field: HeaderField, value: string): void {
		void saveProjectField(field, value);
	}

	// --- Etapas: estados auxiliares ------------------------------------------

	function getRowState(etapaId: number): RowState {
		return rowStates[etapaId] ?? {};
	}

	function setRowState(etapaId: number, next: RowState): void {
		rowStates = { ...rowStates, [etapaId]: next };
	}

	function setRowBusy(etapaId: number, busy: boolean, error: string | null = null): void {
		setRowState(etapaId, { ...getRowState(etapaId), busy, error });
	}

	function setRowFieldState(etapaId: number, field: EtapaInlineField, next: FieldState): void {
		const current = getRowState(etapaId);
		setRowState(etapaId, {
			...current,
			fields: { ...current.fields, [field]: next }
		});
	}

	/** Aplica uma etapa atualizada (vinda de um endpoint que devolve 1 etapa). */
	function replaceEtapa(updated: EtapaDetail): void {
		if (!data) return;
		data = {
			...data,
			etapas: data.etapas.map((e) => (e.id === updated.id ? updated : e))
		};
	}

	// --- Etapas: edicao inline de campo (cascata server-side) ----------------

	/**
	 * Edita um campo inline da etapa (descricao/data_inicio/data_fim/responsavel).
	 * Ao mudar uma DATA, o backend pode propagar a cascata para etapas seguintes;
	 * por isso RE-BUSCAMOS o estado completo apos o sucesso. O front nao recalcula.
	 */
	async function onUpdateField(
		etapaId: number,
		field: EtapaInlineField,
		value: string
	): Promise<void> {
		setRowFieldState(etapaId, field, { pending: true, error: null });
		try {
			const result = await updateEtapaField(etapaId, field, value === '' ? null : value);
			replaceEtapa(result.etapa);
			setRowFieldState(etapaId, field, { pending: false, error: null });
			// Datas disparam cascata server-side nas etapas seguintes -> re-busca.
			if (field === 'data_inicio' || field === 'data_fim') {
				await refresh();
			}
		} catch (err) {
			if (isUnauthenticated(err)) return;
			setRowFieldState(etapaId, field, {
				pending: false,
				error: messageOf(err, 'Falha ao salvar o campo da etapa.')
			});
		}
	}

	async function onToggleIniciada(etapaId: number): Promise<void> {
		setRowBusy(etapaId, true);
		try {
			const result = await toggleEtapaIniciada(etapaId);
			replaceEtapa(result.etapa);
			setRowBusy(etapaId, false);
		} catch (err) {
			if (isUnauthenticated(err)) return;
			setRowBusy(etapaId, false, messageOf(err, 'Falha ao alternar o inicio da etapa.'));
		}
	}

	async function onToggleDone(etapaId: number): Promise<void> {
		setRowBusy(etapaId, true);
		try {
			const result = await toggleEtapaDone(etapaId);
			replaceEtapa(result.etapa);
			setRowBusy(etapaId, false);
			// Concluir/reabrir etapa pode mudar os derivados do projeto (status,
			// datas) -> re-busca para refletir o cabecalho.
			await refresh();
		} catch (err) {
			if (isUnauthenticated(err)) return;
			setRowBusy(etapaId, false, messageOf(err, 'Falha ao alternar a conclusao da etapa.'));
		}
	}

	async function onSaveComentario(etapaId: number, comentario: string): Promise<void> {
		setRowBusy(etapaId, true);
		try {
			const result = await saveEtapaComentario(etapaId, comentario);
			replaceEtapa(result.etapa);
			setRowBusy(etapaId, false);
		} catch (err) {
			if (isUnauthenticated(err)) return;
			setRowBusy(etapaId, false, messageOf(err, 'Falha ao salvar o comentario.'));
		}
	}

	async function onDeleteEtapa(etapaId: number): Promise<void> {
		if (typeof window !== 'undefined' && !window.confirm('Excluir esta etapa?')) return;
		setRowBusy(etapaId, true);
		try {
			await deleteEtapa(etapaId);
			// Exclusao reordena/recalcula derivados no backend -> re-busca.
			await refresh();
		} catch (err) {
			if (isUnauthenticated(err)) return;
			setRowBusy(etapaId, false, messageOf(err, 'Falha ao excluir a etapa.'));
		}
	}

	/**
	 * "Editar etapa" completo: a UI rica de edicao completa fica para fases
	 * posteriores; aqui a edicao acontece inline em cada campo. Apenas focamos a
	 * descricao da etapa para o usuario editar inline.
	 */
	function onEditEtapa(etapaId: number): void {
		if (typeof document === 'undefined') return;
		// Sem editor completo nesta fase; rola ate a etapa para edicao inline.
		const node = document.getElementById(`etapa-${etapaId}-descricao`);
		node?.scrollIntoView({ block: 'center', behavior: 'smooth' });
	}

	// --- Reordenacao (cascata server-side) -----------------------------------

	/**
	 * Persiste a nova ordem das etapas. O backend pode recalcular datas em cascata
	 * (dias uteis); por isso RE-BUSCAMOS o estado completo apos o sucesso.
	 */
	async function onReorder(orderedIds: number[]): Promise<void> {
		reordering = true;
		reorderError = null;
		try {
			await reorderEtapas(projectId, orderedIds);
			await refresh();
		} catch (err) {
			if (isUnauthenticated(err)) {
				reordering = false;
				return;
			}
			reorderError = messageOf(err, 'Falha ao reordenar as etapas.');
		} finally {
			reordering = false;
		}
	}

	// --- Tarefas read-only sob demanda ---------------------------------------

	async function onLoadTasks(etapaId: number): Promise<void> {
		if (tasksByEtapa[etapaId] != null || tasksLoading[etapaId]) return;
		tasksLoading = { ...tasksLoading, [etapaId]: true };
		try {
			const result = await fetchEtapaTasks(projectId, etapaId);
			tasksByEtapa = { ...tasksByEtapa, [etapaId]: result.tasks };
		} catch (err) {
			if (isUnauthenticated(err)) return;
			// Lista read-only: em caso de falha, exibe lista vazia (sem bloquear UI).
			tasksByEtapa = { ...tasksByEtapa, [etapaId]: [] };
		} finally {
			tasksLoading = { ...tasksLoading, [etapaId]: false };
		}
	}

	// --- Adicionar etapa ------------------------------------------------------

	async function onAddStage(event: SubmitEvent): Promise<void> {
		event.preventDefault();
		const descricao = newStageDescription.trim();
		if (!descricao || addingStage) return;
		addingStage = true;
		addStageError = null;
		try {
			await addEtapa(projectId, { descricao });
			newStageDescription = '';
			await refresh();
		} catch (err) {
			if (isUnauthenticated(err)) {
				addingStage = false;
				return;
			}
			addStageError = messageOf(err, 'Falha ao adicionar a etapa.');
		} finally {
			addingStage = false;
		}
	}

	// --- Importar modelo ------------------------------------------------------

	async function openImport(): Promise<void> {
		importOpen = true;
		importError = null;
		if (templates.length > 0 || templatesLoading) return;
		templatesLoading = true;
		try {
			templates = await fetchStageTemplates();
		} catch (err) {
			if (isUnauthenticated(err)) return;
			importError = messageOf(err, 'Falha ao carregar os modelos de etapas.');
		} finally {
			templatesLoading = false;
		}
	}

	function closeImport(): void {
		if (importSubmitting) return;
		importOpen = false;
		importError = null;
	}

	async function onConfirmImport(payload: {
		template_id: number;
		start_date: string;
	}): Promise<void> {
		importSubmitting = true;
		importError = null;
		try {
			await importStageModel(projectId, payload);
			importOpen = false;
			await refresh();
		} catch (err) {
			if (isUnauthenticated(err)) {
				importSubmitting = false;
				return;
			}
			importError = messageOf(err, 'Falha ao importar o modelo de etapas.');
		} finally {
			importSubmitting = false;
		}
	}

	onMount(() => {
		// Mede o topnav fixo (sticky) para descontar no offset do cabecalho.
		const topnav = document.querySelector('header.sticky');
		if (topnav) topOffset = Math.round(topnav.getBoundingClientRect().height);
		void load();
	});
</script>

<svelte:head>
	<title>Detalhe do projeto — ProjetosRJ</title>
</svelte:head>

<section aria-labelledby="project-detail-title" class="flex flex-col gap-6">
	{#if loadState === 'loading'}
		<p role="status" aria-live="polite" class="text-text-secondary">Carregando projeto…</p>
	{:else if loadState === 'error'}
		<div
			role="alert"
			class="flex flex-col items-start gap-3 rounded-lg border border-danger bg-surface px-5 py-4"
		>
			{#if errorKind === 'not_found'}
				<p class="text-text-primary">Projeto não encontrado.</p>
				<a
					href={`${base}/projetos`}
					class="rounded-md border border-border-subtle bg-surface px-4 py-2 text-sm font-medium text-text-primary no-underline transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
				>
					Voltar aos projetos
				</a>
			{:else if errorKind === 'forbidden'}
				<p class="text-text-primary">Você não tem permissão para visualizar este projeto.</p>
				<a
					href={`${base}/projetos`}
					class="rounded-md border border-border-subtle bg-surface px-4 py-2 text-sm font-medium text-text-primary no-underline transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
				>
					Voltar aos projetos
				</a>
			{:else}
				<p class="text-text-primary">{errorMessage}</p>
				<button
					type="button"
					onclick={load}
					class="rounded-md border border-border-subtle bg-surface px-4 py-2 text-sm font-medium text-text-primary transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
				>
					Tentar novamente
				</button>
			{/if}
		</div>
	{:else if data}
		<ProjectHeader
			project={data.project}
			options={data.options}
			permissions={data.permissions}
			derivedData={data.derived}
			{topOffset}
			fieldStates={{
				titulo: projectFieldStates.titulo,
				status: projectFieldStates.status,
				prioridade: projectFieldStates.prioridade
			}}
			onEditField={onHeaderEditField}
		/>

		<div class="flex flex-wrap items-center gap-3">
			<a
				href={`${base}/projetos/${data.project.id}/historico`}
				class="inline-flex w-fit items-center rounded-md border border-border-subtle bg-surface px-4 py-2 text-sm font-medium text-text-primary no-underline transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
			>
				Histórico do projeto
			</a>
			<a
				href={`${base}/projetos`}
				class="inline-flex w-fit items-center rounded-md border border-border-subtle bg-surface px-4 py-2 text-sm font-medium text-text-primary no-underline transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
			>
				Voltar aos projetos
			</a>
		</div>

		<!-- Detalhes editaveis do projeto (campos fora do cabecalho) -->
		<Card labelId="project-details-title">
			{#snippet header()}
				<h2 id="project-details-title" class="font-heading text-lg font-semibold text-text-primary">
					Detalhes
				</h2>
			{/snippet}

			<div class="grid gap-4 sm:grid-cols-2">
				<InlineEditField
					fieldId="project-observacao"
					label="Observação"
					value={data.project.observacao}
					kind="textarea"
					readonly={!canEdit}
					pending={projectFieldStates.observacao?.pending}
					error={projectFieldStates.observacao?.error}
					onSave={(v) => saveProjectField('observacao', v)}
				/>
				<InlineEditField
					fieldId="project-sei"
					label="Processo SEI"
					value={data.project.sei_process}
					kind="text"
					readonly={!canEdit}
					pending={projectFieldStates.sei_process?.pending}
					error={projectFieldStates.sei_process?.error}
					onSave={(v) => saveProjectField('sei_process', v)}
				/>
				<InlineEditField
					fieldId="project-github"
					label="Link do GitHub"
					value={data.project.github_link}
					kind="text"
					readonly={!canEdit}
					pending={projectFieldStates.github_link?.pending}
					error={projectFieldStates.github_link?.error}
					onSave={(v) => saveProjectField('github_link', v)}
				/>
				<InlineEditField
					fieldId="project-doc"
					label="Link da documentação"
					value={data.project.documentation_link}
					kind="text"
					readonly={!canEdit}
					pending={projectFieldStates.documentation_link?.pending}
					error={projectFieldStates.documentation_link?.error}
					onSave={(v) => saveProjectField('documentation_link', v)}
				/>
				<InlineEditField
					fieldId="project-product"
					label="Link do produto"
					value={data.project.product_link}
					kind="text"
					readonly={!canEdit}
					pending={projectFieldStates.product_link?.pending}
					error={projectFieldStates.product_link?.error}
					onSave={(v) => saveProjectField('product_link', v)}
				/>
			</div>
		</Card>

		<!-- Secao de Etapas -->
		<Card labelId="project-stages-title">
			{#snippet header()}
				<div class="flex flex-wrap items-center justify-between gap-3">
					<h2 id="project-stages-title" class="font-heading text-lg font-semibold text-text-primary">
						Etapas
					</h2>
					{#if canEdit}
						<button
							type="button"
							onclick={openImport}
							class="rounded-md border border-border-subtle bg-surface px-3 py-1.5 text-sm font-medium text-text-primary transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
						>
							Importar modelo
						</button>
					{/if}
				</div>
			{/snippet}

			<div class="flex flex-col gap-4">
				{#if canEdit}
					<form class="flex flex-wrap items-end gap-2" onsubmit={onAddStage}>
						<div class="flex min-w-[16rem] flex-1 flex-col gap-1">
							<label
								for="new-stage-descricao"
								class="text-xs font-semibold uppercase tracking-wide text-text-muted"
							>
								Nova etapa
							</label>
							<input
								id="new-stage-descricao"
								type="text"
								bind:value={newStageDescription}
								disabled={addingStage}
								placeholder="Descrição da etapa…"
								class="rounded-md border border-border-subtle bg-surface px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
							/>
						</div>
						<button
							type="submit"
							disabled={addingStage || newStageDescription.trim() === ''}
							class="rounded-md border border-primary-500 bg-primary-100 px-4 py-2 text-sm font-medium text-primary-700 transition-colors duration-fast hover:bg-primary-500 hover:text-white disabled:opacity-60 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
						>
							{addingStage ? 'Adicionando…' : 'Adicionar etapa'}
						</button>
						{#if addStageError}
							<p role="alert" class="w-full text-sm text-danger">{addStageError}</p>
						{/if}
					</form>
				{/if}

				<StageList
					etapas={data.etapas}
					readonly={!canEdit}
					{reordering}
					{reorderError}
					{rowStates}
					{tasksByEtapa}
					{tasksLoading}
					{onReorder}
					{onUpdateField}
					{onToggleIniciada}
					{onToggleDone}
					{onSaveComentario}
					onEdit={onEditEtapa}
					onDelete={onDeleteEtapa}
					{onLoadTasks}
				/>
			</div>
		</Card>

		<ImportModelModal
			open={importOpen}
			{templates}
			loading={templatesLoading}
			submitting={importSubmitting}
			error={importError}
			onConfirm={onConfirmImport}
			onClose={closeImport}
		/>
	{/if}
</section>
