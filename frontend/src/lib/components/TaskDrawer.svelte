<script lang="ts">
	/**
	 * DRAWER de Tarefa (Fase 5b-2). Painel lateral acessível (role=dialog,
	 * aria-modal, Esc fecha, foco inicial no botão fechar) que abre UMA tarefa a
	 * partir do board Kanban, da lista ou de uma etapa do Detalhe.
	 *
	 * Edição inline dos campos (descrição/prioridade/tipo/responsável) com
	 * AUTOSAVE (debounce na store via `createAutosave`; `flush` no blur e ao
	 * fechar — nunca perde edição). O status tem um SELETOR (#16) que chama
	 * `POST /api/tarefas/<id>/status` (mesmo cliente `updateTaskStatus` do board):
	 * só envia; em erro reverte a seleção e mostra a mensagem (server-autoritativo,
	 * 403 ao finalizar sem permissão). Ações finalizar/arquivar/desarquivar/
	 * reativar são server-autoritativas (403 → erro, sem aplicar). Comentários e
	 * anexos ficam nos painéis dedicados. Mutações refletem no card do board via os
	 * reconciliadores injetados na store. O foco fica preso no painel via
	 * `use:focusTrap` (#17), que também foca o primeiro elemento ao abrir e
	 * restaura o foco anterior ao fechar.
	 */
	import type { TaskDrawerStore } from '$lib/stores/taskDrawer';
	import {
		STATUS_LABELS,
		TASK_STATUS_ORDER,
		normalizeStatus,
		type TaskStatus
	} from '$lib/utils/taskStatus';
	import { updateTaskStatus } from '$lib/api/board';
	import { ApiClientError } from '$lib/api/client';
	import { fetchProjectDetail } from '$lib/api/projectDetail';
	import type { EtapaDetail } from '$lib/types/projectDetail';
	import { focusTrap } from '$lib/actions/focusTrap';
	import { fade, fly } from 'svelte/transition';
	import { cubicOut } from 'svelte/easing';
	import Badge from './Badge.svelte';
	import CommentsPanel from './CommentsPanel.svelte';
	import AttachmentsPanel from './AttachmentsPanel.svelte';

	interface Props {
		store: TaskDrawerStore;
	}

	let { store }: Props = $props();

	type Tone = 'neutral' | 'primary' | 'success' | 'warning' | 'danger' | 'info';

	const STATUS_TONE: Record<string, Tone> = {
		nao_iniciada: 'neutral',
		em_andamento: 'info',
		para_validacao: 'primary',
		para_ajustes: 'warning',
		finalizada: 'success'
	};

	const PRIORIDADE_OPTIONS = [
		{ value: '', label: '—' },
		{ value: 'baixa', label: 'Baixa' },
		{ value: 'media', label: 'Média' },
		{ value: 'alta', label: 'Alta' },
		{ value: 'urgente', label: 'Urgente' }
	];

	const TIPO_OPTIONS = [
		{ value: '', label: '—' },
		{ value: 'bug', label: 'Bug' },
		{ value: 'melhoria', label: 'Melhoria' },
		{ value: 'duvida', label: 'Dúvida' },
		{ value: 'outros', label: 'Outros' },
		{ value: 'implementacao', label: 'Implementação' }
	];

	const isOpen = $derived($store.status !== 'closed');
	const detail = $derived($store.detail);

	// #16: seletor de status. Mudança de status é uma operação à parte (não passa
	// pelo autosave de campos). Reusa o cliente `updateTaskStatus` do board.
	let changingStatus = $state(false);
	let statusError = $state<string | null>(null);

	const STATUS_OPTIONS = TASK_STATUS_ORDER.map((value) => ({
		value,
		label: STATUS_LABELS[value]
	}));

	const autosaveLabel = $derived(
		$store.autosave === 'saving' || $store.autosave === 'pending'
			? 'Salvando…'
			: $store.autosave === 'saved'
				? 'Salvo'
				: $store.autosave === 'error'
					? 'Erro ao salvar'
					: ''
	);

	function statusTone(status: string): Tone {
		return STATUS_TONE[normalizeStatus(status)] ?? 'neutral';
	}

	/**
	 * #16: aplica a transição de status no servidor (autoritativo). Só ENVIA; em
	 * erro reverte o `<select>` ao status atual e mostra a mensagem. Salva edições
	 * pendentes antes (flush) e recarrega o detalhe (reconciliando o board).
	 */
	async function onStatus(event: Event): Promise<void> {
		const target = event.currentTarget as HTMLSelectElement;
		const next = target.value as TaskStatus;
		const current = detail ? normalizeStatus(detail.status) : null;
		const taskId = $store.taskId;
		if (taskId === null || current === null || next === current) return;

		changingStatus = true;
		statusError = null;
		try {
			await store.flush();
			await updateTaskStatus(taskId, next);
			// Recarrega o detalhe canônico (e reconcilia o card no board via a store).
			await store.open(taskId, { mode: $store.mode });
		} catch (err) {
			// Reverte a seleção visual ao status atual e sinaliza o erro.
			target.value = current;
			statusError =
				err instanceof ApiClientError
					? err.message
					: 'Não foi possível alterar o status da tarefa.';
		} finally {
			changingStatus = false;
		}
	}

	// EXCLUIR: mini-confirm inline no header (paridade com #taskItemDrawerDeleteConfirm
	// do drawer legado — NÃO usa window.confirm). Clicar lixeira abre o confirm;
	// Escape fecha primeiro o confirm e só depois o drawer.
	let confirmingDelete = $state(false);

	function openDeleteConfirm(): void {
		confirmingDelete = true;
	}
	function cancelDeleteConfirm(): void {
		confirmingDelete = false;
	}
	async function confirmDelete(): Promise<void> {
		const ok = await store.deleteTask();
		// Em sucesso a store já fechou o drawer; em erro mantém aberto + mensagem.
		if (ok) confirmingDelete = false;
	}

	// MOVER DE ETAPA: select que aparece via toggle. As etapas do projeto são
	// buscadas sob demanda (não vêm no payload do drawer). `warning` de etapa
	// concluída é exibido inline (o Jinja ignorava; aqui mostramos por fidelidade
	// à informação do backend, sem som/confete).
	let movingEtapa = $state(false);
	let etapaOptions = $state<EtapaDetail[]>([]);
	let etapaListLoading = $state(false);
	let etapaWarning = $state<string | null>(null);
	let etapaError = $state<string | null>(null);
	let loadedEtapasForProject = $state<number | null>(null);

	async function toggleMoveEtapa(): Promise<void> {
		movingEtapa = !movingEtapa;
		etapaWarning = null;
		etapaError = null;
		if (!movingEtapa) return;
		const projectId = detail?.project?.id ?? null;
		if (projectId === null || loadedEtapasForProject === projectId) return;
		etapaListLoading = true;
		try {
			const data = await fetchProjectDetail(projectId);
			// Só etapas regulares (reuniões Google não recebem tarefas).
			etapaOptions = data.etapas.filter((e) => !e.is_google_meeting);
			loadedEtapasForProject = projectId;
		} catch (err) {
			etapaError =
				err instanceof ApiClientError ? err.message : 'Não foi possível carregar as etapas.';
		} finally {
			etapaListLoading = false;
		}
	}

	async function onMoveEtapa(event: Event): Promise<void> {
		const value = (event.currentTarget as HTMLSelectElement).value;
		const target: number | 'sem_etapa' = value === '' ? 'sem_etapa' : Number(value);
		etapaWarning = null;
		etapaError = null;
		const result = await store.moveEtapa(target);
		if (!result.ok) {
			etapaError = $store.error ?? 'Não foi possível mover a tarefa.';
			return;
		}
		etapaWarning = result.warning ?? null;
		if (!etapaWarning) movingEtapa = false;
	}

	async function close(): Promise<void> {
		confirmingDelete = false;
		movingEtapa = false;
		await store.close();
	}

	function onKeydown(event: KeyboardEvent): void {
		if (event.key === 'Escape') {
			event.stopPropagation();
			// Escape fecha primeiro o confirm de exclusão (paridade com o legado).
			if (confirmingDelete) {
				confirmingDelete = false;
				return;
			}
			void close();
		}
	}

	function onDescricao(event: Event): void {
		store.editField({ descricao: (event.currentTarget as HTMLTextAreaElement).value });
	}
	function onPrioridade(event: Event): void {
		const v = (event.currentTarget as HTMLSelectElement).value;
		store.editField({ prioridade: v === '' ? null : v });
	}
	function onTipo(event: Event): void {
		const v = (event.currentTarget as HTMLSelectElement).value;
		store.editField({ tipo_pedido: v === '' ? null : v });
	}
	function onResponsavel(event: Event): void {
		const v = (event.currentTarget as HTMLInputElement).value;
		store.editField({ responsavel: v === '' ? null : v });
	}
	function flush(): void {
		void store.flush();
	}
</script>

{#if isOpen}
	<!--
		Backdrop — fidelidade a drawer.css `.task-item-drawer-backdrop`:
		rgba(7,20,33,0.34) + leve blur, fade 0.2s ease.
	-->
	<div
		class="fixed inset-0 z-modal bg-[rgba(7,20,33,0.34)] backdrop-blur-[1.2px]"
		role="presentation"
		onclick={() => void close()}
		transition:fade={{ duration: 200 }}
	></div>

	<!--
		Painel lateral — fidelidade a drawer.css `.task-item-drawer`:
		width min(460px,100vw), borda esquerda, sombra -14px 0 34px, e slide-in
		translateX(100% -> 0) com 0.24s cubic-bezier(0.22,1,0.36,1) (~cubicOut).
	-->
	<div
		role="dialog"
		aria-modal="true"
		aria-labelledby="task-drawer-title"
		tabindex="-1"
		class="fixed right-0 top-0 z-modal flex h-full w-[min(460px,100vw)] flex-col overflow-y-auto border-l border-border-subtle bg-surface shadow-[-14px_0_34px_rgba(12,44,74,0.16)]"
		onkeydown={onKeydown}
		use:focusTrap
		transition:fly={{ x: 460, duration: 240, easing: cubicOut, opacity: 1 }}
	>
		<header
			class="flex items-start justify-between gap-[0.54rem] border-b border-border-subtle bg-surface-elevated/70 px-[0.92rem] pb-[0.76rem] pt-[0.86rem]"
		>
			<div class="flex min-w-0 flex-1 flex-col gap-1">
				<p
					id="task-drawer-title"
					class="m-0 text-2xs font-semibold uppercase tracking-wide text-text-muted"
				>
					Tarefa
				</p>
				{#if detail?.project}
					<span class="truncate text-md font-bold text-text-primary">{detail.project.titulo}</span>
				{/if}
				{#if detail?.etapa}
					<span class="truncate text-xs text-text-muted">Etapa: {detail.etapa.descricao}</span>
				{/if}
			</div>
			<div class="flex shrink-0 items-center gap-[0.34rem]">
				{#if detail && detail.permissions.can_delete}
					<button
						type="button"
						onclick={openDeleteConfirm}
						aria-label="Excluir tarefa"
						title="Excluir tarefa"
						disabled={$store.acting}
						class="inline-flex h-[34px] w-[34px] items-center justify-center rounded-md border border-danger/40 bg-surface text-danger transition-all duration-fast hover:border-danger/60 hover:bg-danger/10 focus:outline-none focus-visible:ring-2 focus-visible:ring-danger disabled:cursor-not-allowed disabled:opacity-50"
					>
						<svg viewBox="0 0 24 24" class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
							<path d="M3 6h18M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2m2 0v14a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V6" />
							<path d="M10 11v6M14 11v6" />
						</svg>
					</button>
				{/if}
				<button
					type="button"
					onclick={() => void close()}
					aria-label="Fechar"
					class="inline-flex h-[34px] w-[34px] items-center justify-center rounded-md border border-border-subtle bg-surface text-lg leading-none text-text-secondary transition-all duration-fast hover:border-border-strong hover:bg-primary-100 hover:text-primary-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
				>
					<svg viewBox="0 0 24 24" class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
						<path d="M18 6 6 18M6 6l12 12" />
					</svg>
				</button>
			</div>
		</header>

		<!--
			Corpo rolável — fidelidade a drawer.css `.task-item-drawer-body`:
			padding 0.86rem 0.92rem, coluna com gap 0.68rem.
		-->
		<div class="flex flex-1 flex-col gap-[0.68rem] overflow-y-auto px-[0.92rem] py-[0.86rem]">

		{#if confirmingDelete}
			<!-- Mini-confirm inline (paridade com #taskItemDrawerDeleteConfirm). -->
			<div
				role="alertdialog"
				aria-label="Confirmar exclusão da tarefa"
				class="flex flex-col gap-2 rounded-md border border-danger bg-surface px-3 py-3"
			>
				<p class="text-sm text-text-primary">Deseja excluir esta tarefa?</p>
				<div class="flex gap-2">
					<button
						type="button"
						onclick={cancelDeleteConfirm}
						disabled={$store.acting}
						class="rounded-md border border-border-subtle px-3 py-1.5 text-sm font-medium text-text-secondary hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-50"
					>
						Cancelar
					</button>
					<button
						type="button"
						onclick={() => void confirmDelete()}
						disabled={$store.acting}
						class="rounded-md bg-danger px-3 py-1.5 text-sm font-medium text-white hover:opacity-90 focus:outline-none focus-visible:ring-2 focus-visible:ring-danger disabled:opacity-50"
					>
						{$store.acting ? 'Excluindo…' : 'Excluir tarefa'}
					</button>
				</div>
			</div>
		{/if}

		{#if $store.status === 'loading'}
			<p role="status" aria-live="polite" class="text-text-secondary">Carregando tarefa…</p>
		{:else if $store.status === 'error'}
			<div role="alert" class="rounded-md border border-danger bg-surface px-4 py-3 text-text-primary">
				{$store.error}
			</div>
		{:else if detail}
			<!-- Status: seletor (#16) + indicador visual (Badge) + autosave -->
			<div class="flex items-end justify-between gap-2">
				<div class="flex min-w-44 flex-1 flex-col gap-1">
					<label
						for="drawer-status"
						class="text-xs font-semibold uppercase tracking-wide text-text-muted"
					>
						Status
					</label>
					<div class="flex items-center gap-2">
						<select
							id="drawer-status"
							value={normalizeStatus(detail.status)}
							onchange={onStatus}
							disabled={changingStatus || $store.acting}
							class="rounded-md border border-border-subtle bg-surface px-3 py-2 text-sm text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-60"
						>
							{#each STATUS_OPTIONS as opt (opt.value)}
								<option value={opt.value}>{opt.label}</option>
							{/each}
						</select>
						<Badge tone={statusTone(detail.status)}>
							{STATUS_LABELS[normalizeStatus(detail.status)]}
						</Badge>
					</div>
				</div>
				<span aria-live="polite" class="pb-2 text-xs text-text-muted">{autosaveLabel}</span>
			</div>

			{#if statusError}
				<div role="alert" class="rounded-md border border-danger bg-surface px-3 py-2 text-sm text-text-primary">
					{statusError}
				</div>
			{/if}

			{#if $store.error}
				<div role="alert" class="rounded-md border border-danger bg-surface px-3 py-2 text-sm text-text-primary">
					{$store.error}
				</div>
			{/if}

			<!-- Campos editáveis (autosave) -->
			<div class="flex flex-col gap-3">
				<div class="flex flex-col gap-1">
					<label for="drawer-descricao" class="text-xs font-semibold uppercase tracking-wide text-text-muted">
						Descrição
					</label>
					<textarea
						id="drawer-descricao"
						value={detail.descricao}
						oninput={onDescricao}
						onblur={flush}
						disabled={!detail.permissions.can_edit}
						rows="3"
						class="w-full rounded-md border border-border-subtle bg-surface px-3 py-2 text-sm text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-60"
					></textarea>
				</div>

				<div class="flex flex-wrap gap-3">
					<div class="flex min-w-36 flex-1 flex-col gap-1">
						<label for="drawer-prioridade" class="text-xs font-semibold uppercase tracking-wide text-text-muted">
							Prioridade
						</label>
						<select
							id="drawer-prioridade"
							value={detail.prioridade ?? ''}
							onchange={onPrioridade}
							disabled={!detail.permissions.can_edit}
							class="rounded-md border border-border-subtle bg-surface px-3 py-2 text-sm text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-60"
						>
							{#each PRIORIDADE_OPTIONS as opt (opt.value)}
								<option value={opt.value}>{opt.label}</option>
							{/each}
						</select>
					</div>

					<div class="flex min-w-36 flex-1 flex-col gap-1">
						<label for="drawer-tipo" class="text-xs font-semibold uppercase tracking-wide text-text-muted">
							Tipo
						</label>
						<select
							id="drawer-tipo"
							value={detail.tipo_pedido ?? ''}
							onchange={onTipo}
							disabled={!detail.permissions.can_edit}
							class="rounded-md border border-border-subtle bg-surface px-3 py-2 text-sm text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-60"
						>
							{#each TIPO_OPTIONS as opt (opt.value)}
								<option value={opt.value}>{opt.label}</option>
							{/each}
						</select>
					</div>
				</div>

				<div class="flex flex-col gap-1">
					<label for="drawer-responsavel" class="text-xs font-semibold uppercase tracking-wide text-text-muted">
						Responsável
					</label>
					<input
						id="drawer-responsavel"
						type="text"
						value={detail.responsavel ?? ''}
						oninput={onResponsavel}
						onblur={flush}
						disabled={!detail.permissions.can_edit}
						class="rounded-md border border-border-subtle bg-surface px-3 py-2 text-sm text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-60"
					/>
				</div>
			</div>

			<!-- Mover de etapa (DnD equivalente no drawer): só projetos com etapas -->
			{#if detail.project && detail.permissions.can_edit}
				<div class="flex flex-col gap-2 border-t border-border-subtle pt-3">
					<button
						type="button"
						onclick={() => void toggleMoveEtapa()}
						aria-expanded={movingEtapa}
						class="w-fit text-sm font-medium text-primary-700 hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
					>
						{movingEtapa ? 'Cancelar mudança de etapa' : 'Mover de etapa'}
					</button>
					{#if movingEtapa}
						{#if etapaListLoading}
							<p role="status" aria-live="polite" class="text-xs text-text-muted">
								Carregando etapas…
							</p>
						{:else}
							<select
								aria-label="Mover tarefa para a etapa"
								value={detail.etapa?.id ?? ''}
								onchange={onMoveEtapa}
								disabled={$store.acting}
								class="rounded-md border border-border-subtle bg-surface px-3 py-2 text-sm text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-60"
							>
								<option value="">Sem etapa</option>
								{#each etapaOptions as etapa (etapa.id)}
									<option value={etapa.id}>
										{etapa.descricao ?? `Etapa ${etapa.id}`}{etapa.done ? ' (concluída)' : ''}
									</option>
								{/each}
							</select>
						{/if}
						{#if etapaWarning}
							<p role="status" aria-live="polite" class="text-xs text-warning">{etapaWarning}</p>
						{/if}
						{#if etapaError}
							<p role="alert" class="text-xs text-danger">{etapaError}</p>
						{/if}
					{/if}
				</div>
			{/if}

			<!-- Ações de ciclo de vida (server-autoritativas) -->
			<div class="flex flex-wrap gap-2 border-t border-border-subtle pt-3">
				{#if !detail.is_archived && normalizeStatus(detail.status) !== 'finalizada' && detail.permissions.can_finalize}
					<button
						type="button"
						disabled={$store.acting}
						onclick={() => void store.finalizar()}
						class="rounded-md bg-success px-3 py-1.5 text-sm font-medium text-white hover:opacity-90 focus:outline-none focus-visible:ring-2 focus-visible:ring-success disabled:opacity-50"
					>
						Finalizar
					</button>
				{/if}
				{#if normalizeStatus(detail.status) === 'finalizada' && !detail.is_archived}
					<button
						type="button"
						disabled={$store.acting}
						onclick={() => void store.reativar()}
						class="rounded-md border border-border-subtle px-3 py-1.5 text-sm font-medium text-text-primary hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-50"
					>
						Reativar
					</button>
				{/if}
				{#if detail.is_archived}
					<button
						type="button"
						disabled={$store.acting}
						onclick={() => void store.desarquivar()}
						class="rounded-md border border-border-subtle px-3 py-1.5 text-sm font-medium text-text-primary hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-50"
					>
						Desarquivar
					</button>
				{:else}
					<button
						type="button"
						disabled={$store.acting}
						onclick={() => void store.arquivar()}
						class="rounded-md border border-border-subtle px-3 py-1.5 text-sm font-medium text-text-secondary hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-50"
					>
						Arquivar
					</button>
				{/if}
			</div>

			<!-- Painéis -->
			<div class="border-t border-border-subtle pt-3">
				<CommentsPanel {store} />
			</div>
			<div class="border-t border-border-subtle pt-3">
				<AttachmentsPanel {store} />
			</div>
		{/if}
		</div>
	</div>
{/if}
