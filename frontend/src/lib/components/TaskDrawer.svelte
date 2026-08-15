<script lang="ts">
	/**
	 * DRAWER de Tarefa (Fase 5b-2, redesenhado jun/2026 junto com o board).
	 * Painel lateral acessível (role=dialog, aria-modal, Esc fecha) que abre UMA
	 * tarefa a partir do board Kanban, da lista ou de uma etapa do Detalhe.
	 *
	 * Anatomia: header com o NOME DA TAREFA como título e, abaixo, "projeto ·
	 * etapa" (projeto como link, paridade com o card do kanban); corpo rolável
	 * com campos editáveis (descrição/prioridade/tipo/responsáveis), aviso de
	 * tarefa SEM ETAPA (com associação opcional), e os painéis de comentários
	 * (InlineCommentsTree — o MESMO da lista) e anexos; rodapé fixo com "Salvar".
	 *
	 * O drawer NÃO muda status nem arquiva: essas ações acontecem no kanban
	 * (drag) ou na lista — aqui só edição de campos. "Salvar" faz flush das
	 * edições pendentes e fecha (o autosave já persistiu o resto). Mover de
	 * etapa só é oferecido a tarefas SEM etapa associada (associação inicial).
	 *
	 * Edição inline dos campos com AUTOSAVE (debounce na store via
	 * `createAutosave`; `flush` no blur e ao fechar — nunca perde edição).
	 * Responsáveis usam o AssigneePicker em modo persist (mesmo componente e
	 * avatares da lista). Mutações refletem no card do board via os
	 * reconciliadores injetados na store. Foco preso no painel via `use:focusTrap`.
	 *
	 * As tintas de aviso/perigo usam os degraus wash/border-soft do DS (o
	 * Tailwind 3 não gera `bg-x/10` para cores em var() sem alpha-value).
	 */
	import type { TaskDrawerStore } from '$lib/stores/taskDrawer';
	import type { TaskDrawerPayload } from '$lib/types/taskDrawer';
	import type { TaskAssignee } from '$lib/types/tasks';
	import type { SelectMenuOption } from '$lib/types/selectMenu';
	import { priorityDotColor, priorityIconId } from '$lib/utils/taskLabels';
	import { formatIsoDateBRLocalTz } from '$lib/utils/dateFormat';
	import { ApiClientError } from '$lib/api/client';
	import { fetchProjectDetail } from '$lib/api/projectDetail';
	import type { EtapaDetail } from '$lib/types/projectDetail';
	import { focusTrap } from '$lib/actions/focusTrap';
	import { flash } from '$lib/stores/flash';
	import { fade, fly } from 'svelte/transition';
	import { cubicOut } from 'svelte/easing';
	import AssigneePicker from './AssigneePicker.svelte';
	import InlineCommentsTree from './InlineCommentsTree.svelte';
	import AttachmentsPanel from './AttachmentsPanel.svelte';
	import SelectMenu from './SelectMenu.svelte';
	import TaskTipoIcon from './TaskTipoIcon.svelte';
	import InlineConfirm from './InlineConfirm.svelte';
	import StateBanner from './StateBanner.svelte';
	import FeedbackIcon from './FeedbackIcon.svelte';

	interface Props {
		store: TaskDrawerStore;
	}

	let { store }: Props = $props();

	const PRIORIDADE_OPTIONS: SelectMenuOption[] = (
		[
			['baixa', 'Baixa'],
			['media', 'Média'],
			['alta', 'Alta'],
			['urgente', 'Urgente']
		] as const
	).map(([value, label]) => ({
		value,
		label,
		dot: priorityDotColor(value),
		icon: priorityIconId(value)
	}));

	// Sem "implementacao" por padrão: é tipo LEGADO (`LEGACY_TIPOS`) e o save
	// rejeita com 422 ("Tipo inválido."). A opção entra SÓ quando a tarefa já
	// carrega o valor (exibição correta do legado, sem oferecê-lo a novas).
	const TIPO_OPTIONS: SelectMenuOption[] = [
		{ value: 'bug', label: 'Bug' },
		{ value: 'melhoria', label: 'Melhoria' },
		{ value: 'duvida', label: 'Dúvida' },
		{ value: 'outros', label: 'Outros' }
	];

	const isOpen = $derived($store.status !== 'closed');
	const detail = $derived($store.detail);

	const tipoOptions = $derived<SelectMenuOption[]>(
		detail?.tipo_pedido === 'implementacao'
			? [...TIPO_OPTIONS, { value: 'implementacao', label: 'Implementação (legado)' }]
			: TIPO_OPTIONS
	);

	const autosaveLabel = $derived(
		$store.autosave === 'saving' || $store.autosave === 'pending'
			? 'Salvando…'
			: $store.autosave === 'saved'
				? 'Salvo'
				: $store.autosave === 'error'
					? 'Erro ao salvar'
					: ''
	);
	const autosaveFailed = $derived($store.autosave === 'error');

	// RESPONSÁVEIS: estado local sincronizado do detalhe (mesmo padrão do
	// TaskHubTaskRow) — o picker persiste sozinho (modo taskId) e reconcilia
	// `assignees` com a resposta do servidor.
	let assignees = $state<TaskAssignee[]>([]);
	$effect(() => {
		assignees = detail?.assignees ?? [];
	});

	// COMENTÁRIOS colapsáveis (paridade com a lista, onde a árvore expande sob
	// demanda). Começa recolhido; o cabeçalho mostra a contagem.
	let commentsOpen = $state(false);

	// EXCLUIR: mini-confirm inline (paridade com o board — NÃO usa window.confirm).
	// Escape fecha primeiro o confirm e só depois o drawer.
	let confirmingDelete = $state(false);

	let panelEl = $state<HTMLDivElement | null>(null);

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

	// ASSOCIAR ETAPA: só para tarefa SEM etapa (associação inicial — quem já tem
	// etapa não move por aqui; isso é papel do detalhe do projeto). As etapas do
	// projeto são buscadas na primeira abertura (não vêm no payload do drawer).
	// `warning` de etapa concluída é exibido inline.
	let choosingEtapa = $state(false);
	let etapaOptions = $state<EtapaDetail[]>([]);
	let etapaListLoading = $state(false);
	let etapaWarning = $state<string | null>(null);
	let etapaError = $state<string | null>(null);
	let loadedEtapasForProject = $state<number | null>(null);

	const etapaSelectOptions = $derived<SelectMenuOption[]>(
		etapaOptions.map((etapa) => ({
			value: String(etapa.id),
			label: `${etapa.descricao ?? `Etapa ${etapa.id}`}${etapa.done ? ' (concluída)' : ''}`
		}))
	);

	async function toggleChooseEtapa(): Promise<void> {
		choosingEtapa = !choosingEtapa;
		etapaWarning = null;
		etapaError = null;
		if (!choosingEtapa) return;
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

	async function onChooseEtapa(value: string | null): Promise<void> {
		if (value === null) return;
		etapaWarning = null;
		etapaError = null;
		const result = await store.moveEtapa(Number(value));
		if (!result.ok) {
			etapaError = $store.error ?? 'Não foi possível associar a tarefa à etapa.';
			return;
		}
		etapaWarning = result.warning ?? null;
		if (!etapaWarning) choosingEtapa = false;
	}

	/**
	 * Fecha o drawer. O flush do autosave resolve DEPOIS de a store zerar: sem
	 * capturar o erro aqui, a falha do "Salvar" morreria com o drawer desmontado.
	 */
	async function close(): Promise<void> {
		confirmingDelete = false;
		choosingEtapa = false;
		const known = $store.error;
		const arrived: string[] = [];
		const unsubscribe = store.subscribe((state) => {
			if (state.error && state.error !== known) arrived.push(state.error);
		});
		try {
			await store.close();
		} finally {
			unsubscribe();
		}
		if (arrived.length > 0) flash.danger(arrived[arrived.length - 1]);
	}

	function onKeydown(event: KeyboardEvent): void {
		if (event.key !== 'Escape' || event.defaultPrevented) return;
		// Diálogo aninhado (preview de anexo) trata o próprio Esc.
		if (panelEl?.querySelector('[aria-modal="true"]')) return;
		event.stopPropagation();
		// Escape fecha primeiro o confirm de exclusão (paridade com o legado).
		if (confirmingDelete) {
			confirmingDelete = false;
			return;
		}
		void close();
	}

	function onDescricao(event: Event): void {
		store.editField({ descricao: (event.currentTarget as HTMLTextAreaElement).value });
	}
	function flush(): void {
		void store.flush();
	}
</script>

{#if isOpen}
	<!-- Backdrop: fade 0.2s ease. -->
	<div
		class="fixed inset-0 z-modal bg-overlay"
		role="presentation"
		onclick={() => void close()}
		transition:fade={{ duration: 200 }}
	></div>

	<!-- Painel lateral: 645px, header e rodapé fixos, corpo rolável no meio. -->
	<div
		bind:this={panelEl}
		role="dialog"
		aria-modal="true"
		aria-labelledby="task-drawer-title"
		tabindex="-1"
		class="fixed right-0 top-0 z-modal flex h-full w-[min(645px,100vw)] flex-col border-l border-border-subtle bg-surface shadow-lg"
		onkeydown={onKeydown}
		use:focusTrap
		transition:fly={{ x: 645, duration: 240, easing: cubicOut, opacity: 1 }}
	>
		<header
			class="flex shrink-0 items-start justify-between gap-3 border-b border-border-subtle bg-surface-elevated px-5 pb-3.5 pt-4"
		>
			<div class="flex min-w-0 flex-1 flex-col gap-1">
				<div class="flex items-center gap-2">
					<p class="m-0 text-xs font-bold uppercase tracking-caps text-text-muted">
						Tarefa{#if detail}&nbsp;#{detail.id}{/if}
					</p>
					{#if detail?.is_archived}
						<span
							class="td-archived-chip inline-flex items-center rounded-md border px-1.5 py-px text-xs font-semibold"
						>
							Arquivada
						</span>
					{/if}
					<!-- Erro nunca em tinta neutra: falha do autosave vira text-danger + ícone. -->
					<span
						aria-live="polite"
						class="inline-flex items-center gap-1 text-xs {autosaveFailed
							? 'font-semibold text-danger'
							: 'text-text-muted'}"
					>
						{#if autosaveFailed}
							<FeedbackIcon id="x" size={12} />
						{/if}
						{autosaveLabel}
					</span>
				</div>
				{#if detail}
					<!-- Título = nome (descrição) da tarefa; reflete edições ao vivo. -->
					<h2
						id="task-drawer-title"
						class="m-0 line-clamp-2 break-words font-heading text-lg font-bold leading-snug text-text-primary"
					>
						{detail.descricao}
					</h2>
					{#if detail.project || detail.etapa}
						<p class="m-0 flex min-w-0 items-center gap-1.5 text-xs">
							{#if detail.project}
								<a
									href={`/projetos/${detail.project.id}`}
									class="truncate rounded-sm font-semibold text-brand transition-colors duration-fast hover:text-brand hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
									title={detail.project.titulo}
								>
									{detail.project.titulo}
								</a>
							{/if}
							{#if detail.project && detail.etapa}
								<span aria-hidden="true" class="shrink-0 font-bold text-text-muted">·</span>
							{/if}
							{#if detail.etapa}
								<span class="truncate text-text-muted" title={detail.etapa.descricao}>
									{detail.etapa.descricao}
								</span>
							{/if}
						</p>
					{/if}
				{:else}
					<h2 id="task-drawer-title" class="m-0 font-heading text-lg font-bold text-text-primary">
						Tarefa
					</h2>
				{/if}
			</div>
			<div class="flex shrink-0 items-center gap-1">
				{#if detail && detail.permissions.can_delete}
					<button
						type="button"
						onclick={openDeleteConfirm}
						aria-label="Excluir tarefa"
						title="Excluir tarefa"
						disabled={$store.acting}
						class="td-danger-ghost inline-flex h-8 w-8 items-center justify-center rounded-md text-danger transition-colors duration-fast focus:outline-none focus-visible:ring-2 focus-visible:ring-danger disabled:cursor-not-allowed disabled:opacity-50"
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
					class="inline-flex h-8 w-8 items-center justify-center rounded-md text-text-secondary transition-colors duration-fast hover:bg-surface-muted hover:text-brand focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
				>
					<svg viewBox="0 0 24 24" class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
						<path d="M18 6 6 18M6 6l12 12" />
					</svg>
				</button>
			</div>
		</header>

		<!-- Corpo rolável (barra fina padrão via .thin-scroll do app.css) -->
		<div class="thin-scroll flex flex-1 flex-col gap-5 overflow-y-auto px-5 py-4">
			{#if confirmingDelete}
				<!-- Wrapper de altura automática: a faixa é `h-full` e, como filha
				     direta do corpo rolável (altura definida), esticaria até o fim dele. -->
				<div class="shrink-0">
					<InlineConfirm
						question="Excluir esta tarefa? Comentários e anexos serão apagados."
						tone="danger"
						icon="trash"
						confirmLabel="Excluir tarefa"
						cancelLabel="Cancelar"
						busy={$store.acting}
						onConfirm={() => void confirmDelete()}
						onCancel={cancelDeleteConfirm}
					/>
				</div>
			{/if}

			{#if $store.status === 'loading'}
				<div role="status" aria-live="polite" class="flex items-center gap-2 py-2 text-sm text-text-secondary">
					<span
						class="h-4 w-4 animate-spin rounded-full border-2 border-border-subtle border-t-primary-600"
						aria-hidden="true"
					></span>
					Carregando tarefa…
				</div>
			{:else if $store.status === 'error'}
				<StateBanner tone="danger" title={$store.error ?? 'Não foi possível carregar a tarefa.'} />
			{:else if detail}
				{#if $store.error}
					<StateBanner tone="danger" title={$store.error} />
				{/if}

				{#if !detail.etapa}
					<!-- AVISO de tarefa sem etapa + associação opcional (só aqui é
					     permitido escolher; quem já tem etapa não move pelo drawer). -->
					<section class="td-no-etapa flex flex-col gap-2 rounded-lg border px-3 py-2.5">
						<div class="flex items-center justify-between gap-3">
							<p class="m-0 flex items-center gap-2 text-sm font-medium">
								<i class="fas fa-circle-exclamation text-xs" aria-hidden="true"></i>
								Esta tarefa não está associada a nenhuma etapa.
							</p>
							{#if detail.project && detail.permissions.can_edit}
								<button
									type="button"
									onclick={() => void toggleChooseEtapa()}
									aria-expanded={choosingEtapa}
									class="shrink-0 rounded-md border border-border-subtle bg-surface px-2.5 py-1 text-xs font-semibold text-brand transition-colors duration-fast hover:bg-wash-neutral focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
								>
									{choosingEtapa ? 'Cancelar' : 'Associar etapa'}
								</button>
							{/if}
						</div>
						{#if choosingEtapa}
							{#if etapaListLoading}
								<p role="status" aria-live="polite" class="m-0 text-xs text-text-muted">
									Carregando etapas…
								</p>
							{:else}
								<SelectMenu
									id="drawer-etapa-select"
									ariaLabel="Associar tarefa à etapa"
									options={etapaSelectOptions}
									value={null}
									onSelect={(v) => void onChooseEtapa(v)}
									placeholder="Escolha a etapa…"
									disabled={$store.acting}
									searchable
								/>
							{/if}
							{#if etapaWarning}
								<p role="status" aria-live="polite" class="m-0 text-xs text-warning">{etapaWarning}</p>
							{/if}
							{#if etapaError}
								<p role="alert" class="m-0 text-xs text-danger">{etapaError}</p>
							{/if}
						{/if}
					</section>
				{/if}

				<!-- Campos editáveis (autosave) -->
				<section class="flex flex-col gap-3">
					<div class="flex flex-col gap-1">
						<label
							for="drawer-descricao"
							class="text-xs font-semibold uppercase tracking-wide text-text-muted"
						>
							Descrição
						</label>
						<textarea
							id="drawer-descricao"
							value={detail.descricao}
							oninput={onDescricao}
							onblur={flush}
							disabled={!detail.permissions.can_edit}
							rows="3"
							class="w-full resize-y rounded-lg border border-border-subtle bg-surface px-3 py-2 text-md leading-relaxed text-text-primary transition-colors duration-fast focus:border-brand focus:outline-none disabled:opacity-60"
						></textarea>
					</div>

					<div class="grid grid-cols-1 gap-3 sm:grid-cols-3">
						<div class="flex min-w-0 flex-col gap-1">
							<label
								for="drawer-prioridade"
								class="text-xs font-semibold uppercase tracking-wide text-text-muted"
							>
								Prioridade
							</label>
							<SelectMenu
								id="drawer-prioridade"
								ariaLabel="Prioridade"
								options={PRIORIDADE_OPTIONS}
								value={detail.prioridade ?? null}
								onSelect={(v) => store.editField({ prioridade: v })}
								allowAll
								allLabel="—"
								disabled={!detail.permissions.can_edit}
							/>
						</div>

						<div class="flex min-w-0 flex-col gap-1">
							<label
								for="drawer-tipo"
								class="text-xs font-semibold uppercase tracking-wide text-text-muted"
							>
								Tipo
							</label>
							<SelectMenu
								id="drawer-tipo"
								ariaLabel="Tipo"
								options={tipoOptions}
								value={detail.tipo_pedido ?? null}
								onSelect={(v) => store.editField({ tipo_pedido: v })}
								allowAll
								allLabel="—"
								disabled={!detail.permissions.can_edit}
								optionIcon={tipoOptionIcon}
							/>
						</div>

						<div class="flex min-w-0 flex-col gap-1">
							<span class="text-xs font-semibold uppercase tracking-wide text-text-muted">
								Responsáveis
							</span>
							<!-- Mesmo picker de avatares da lista (modo persist por taskId),
							     dentro de um campo delimitado como os selects ao lado. -->
							<div
								class="flex h-9 items-center rounded-lg border border-border-subtle bg-surface px-1.5"
							>
								<!-- `onSaved` reconcilia detalhe + card do board com a resposta
								     do servidor (sem ele o kanban só refletia após reload). O
								     cast é seguro: o endpoint devolve o MESMO envelope
								     {task, detail} dos saves da store (serialize_task_detail). -->
								<AssigneePicker
									taskId={detail.id}
									bind:assignees
									disabled={!detail.permissions.can_edit}
									onSaved={(res) =>
										store.applyExternalPayload(res as unknown as TaskDrawerPayload)}
								/>
							</div>
						</div>
					</div>
				</section>

				{#if formatIsoDateBRLocalTz(detail.created_at)}
					<p class="m-0 -mt-2 text-xs text-text-muted">
						Criada em {formatIsoDateBRLocalTz(detail.created_at)}{detail.is_archived &&
						formatIsoDateBRLocalTz(detail.archived_at)
							? ` · arquivada em ${formatIsoDateBRLocalTz(detail.archived_at)}`
							: ''}
					</p>
				{/if}

				<!-- Comentários: MESMO componente da lista (árvore com avatares), numa
				     seção COLAPSÁVEL — o cabeçalho aqui substitui o do componente. -->
				<section class="flex flex-col gap-1">
					<button
						type="button"
						onclick={() => (commentsOpen = !commentsOpen)}
						aria-expanded={commentsOpen}
						aria-controls="drawer-comments-region"
						class="flex w-full items-center gap-2 rounded-md px-1 py-1 text-left transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
					>
						<i
							class="fas fa-chevron-right text-2xs text-text-muted transition-transform duration-fast {commentsOpen
								? 'rotate-90'
								: ''}"
							aria-hidden="true"
						></i>
						<span class="text-sm font-bold text-text-primary">Comentários</span>
						<span
							class="inline-flex h-5 min-w-5 items-center justify-center rounded-full border border-border-subtle bg-surface px-1.5 text-xs font-semibold text-text-secondary"
						>
							{detail.comentarios.length}
						</span>
					</button>
					{#if commentsOpen}
						<div id="drawer-comments-region">
							<InlineCommentsTree {store} idPrefix="drawer" showHeader={false} />
						</div>
					{/if}
				</section>
				<AttachmentsPanel {store} />
			{/if}
		</div>

		{#if detail && $store.status !== 'loading'}
			<!-- Rodapé fixo: Salvar = flush das edições pendentes + fechar (o
			     autosave já persistiu o resto; status/arquivar vivem no board/lista). -->
			<footer
				class="flex shrink-0 items-center justify-end gap-2 border-t border-border-subtle bg-surface-elevated px-5 py-3"
			>
				<button
					type="button"
					disabled={$store.acting}
					onclick={() => void close()}
					class="inline-flex items-center gap-1.5 rounded-md bg-brand px-4 py-1.5 text-sm font-semibold text-on-brand shadow-sm transition-colors duration-fast hover:bg-brand-hover hover:shadow-md focus:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:opacity-50"
				>
					<i class="fas fa-check text-xs" aria-hidden="true"></i>
					Salvar
				</button>
			</footer>
		{/if}
	</div>
{/if}

{#snippet tipoOptionIcon(opt: SelectMenuOption)}
	{#if opt.value}<TaskTipoIcon tipo={opt.value} size={14} />{/if}
{/snippet}

<style>
	/* Chip "Arquivada" do header (tinta âmbar suave, degraus DS dark-safe). */
	.td-archived-chip {
		color: var(--ds-color-text-warning);
		border-color: var(--ds-color-border-warning-soft);
		background-color: var(--ds-color-wash-warning);
	}

	/* Aviso de tarefa sem etapa (tinta âmbar, mais visível que o muted). */
	.td-no-etapa {
		color: var(--ds-color-text-warning);
		border-color: var(--ds-color-border-warning-soft);
		background-color: var(--ds-color-wash-warning);
	}

	/* Lixeira do header: ghost (só ícone); hover abre a tinta de perigo. */
	.td-danger-ghost:hover:not(:disabled) {
		background-color: var(--ds-color-wash-danger);
	}

</style>
