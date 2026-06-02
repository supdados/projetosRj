<script lang="ts">
	/**
	 * Modal "Tarefas da etapa" (quick-add) da tela Projetos Pendentes — paridade
	 * com `templates/partials/_stage_task_modal.html` +
	 * `static/js/.../11-stage-task-quick-add.js`.
	 *
	 * Replica:
	 *  - header com eyebrow ("Tarefas da etapa · <projeto>"), título (descrição da
	 *    etapa) e contador done/total;
	 *  - hint "Enter salvar · clique fora para fechar";
	 *  - form de criação com validação inline ("Descreva a tarefa antes de salvar.")
	 *    e Enter salva; toast "Tarefa criada com sucesso." (success); incrementa o
	 *    contador local (e a pílula da etapa via callback);
	 *  - listagem das tarefas existentes, cada uma abre o TaskDrawer (editar
	 *    status/prioridade/tipo/responsável) e tem exclusão com confirmação inline
	 *    ("Excluir esta tarefa?") -> toast "Tarefa excluída." e decremento;
	 *  - bloqueio quando a etapa está concluída (toast info), confirm de descarte
	 *    ao fechar com rascunho. Sem som/confete (o legado não tem).
	 *
	 * O componente do DRAWER é reusado tal qual (lane fe:tarefas-drawer); aqui só
	 * o abrimos via a store injetada por prop e re-listamos ao fechar.
	 */
	import { onMount, tick } from 'svelte';
	import { fly, fade } from 'svelte/transition';
	import { cubicOut } from 'svelte/easing';
	import { ApiClientError } from '$lib/api/client';
	import {
		fetchStageTasks,
		createStageTask,
		deleteStageTask
	} from '$lib/api/pendentesMutations';
	import { flash } from '$lib/stores/flash';
	import type { StageTaskCard } from '$lib/types/pendentes';
	import type { TaskDrawerStore } from '$lib/stores/taskDrawer';
	import { normalizeStatus } from '$lib/utils/taskStatus';

	interface Props {
		projectId: number;
		projectTitulo: string;
		etapaId: number;
		etapaDescricao: string;
		/** Datas formuladas pelo card ("dd/mm/yyyy — dd/mm/yyyy" etc.). */
		etapaDatas?: string;
		/** Etapa concluída? Bloqueia criação (toast info), igual ao legado. */
		stageDone: boolean;
		/** Store do drawer (reusada da página; NÃO recriar aqui). */
		drawer: TaskDrawerStore;
		/** Fecha o modal. */
		onClose: () => void;
		/** Notifica a página do novo done/total para sincronizar a pílula. */
		onProgressChange: (etapaId: number, done: number, total: number) => void;
	}

	let {
		projectId,
		projectTitulo,
		etapaId,
		etapaDescricao,
		etapaDatas = '',
		stageDone,
		drawer,
		onProgressChange,
		onClose
	}: Props = $props();

	type LoadState = 'loading' | 'ready' | 'error';

	let loadState = $state<LoadState>('loading');
	let loadError = $state<string>('');
	let tarefas = $state<StageTaskCard[]>([]);

	// Form de criação.
	let descricao = $state<string>('');
	let formError = $state<string>('');
	let saving = $state<boolean>(false);
	let descricaoEl: HTMLTextAreaElement | null = $state(null);

	// Exclusão (confirm inline por tarefa).
	let confirmingDeleteId = $state<number | null>(null);
	let deletingId = $state<number | null>(null);

	const total = $derived(tarefas.length);
	const done = $derived(tarefas.filter((t) => normalizeStatus(t.status) === 'finalizada').length);

	const eyebrow = $derived(`Tarefas da etapa · ${projectTitulo}`);

	async function loadTasks(): Promise<void> {
		loadState = tarefas.length ? loadState : 'loading';
		loadError = '';
		try {
			const result = await fetchStageTasks(projectId, etapaId);
			tarefas = result.tarefas;
			loadState = 'ready';
			onProgressChange(etapaId, result.done, result.total);
		} catch (err) {
			if (err instanceof ApiClientError && err.code === 'unauthenticated') return;
			loadError = err instanceof Error ? err.message : 'Falha ao carregar as tarefas.';
			loadState = 'error';
		}
	}

	onMount(() => {
		void loadTasks();
		// Foca o textarea ao abrir (paridade com o quick-add legado).
		void tick().then(() => descricaoEl?.focus());
	});

	// Re-lista ao FECHAR o drawer (edição inline pode mudar status/contador).
	let drawerWasOpen = false;
	$effect(() => {
		const open = $drawer.status !== 'closed';
		if (drawerWasOpen && !open) void loadTasks();
		drawerWasOpen = open;
	});

	async function submit(): Promise<void> {
		if (saving) return;
		if (stageDone) {
			flash.info('Etapa concluída — desfaça a conclusão para criar tarefas.');
			return;
		}
		const text = descricao.trim();
		if (!text) {
			formError = 'Descreva a tarefa antes de salvar.';
			descricaoEl?.focus();
			return;
		}
		formError = '';
		saving = true;
		try {
			const result = await createStageTask({
				project_id: projectId,
				etapa_id: etapaId,
				descricao: text
			});
			tarefas = [...tarefas, result.task];
			descricao = '';
			onProgressChange(etapaId, done, total);
			flash.success('Tarefa criada com sucesso.');
			// Mantém o foco para "salvar e abrir nova linha" (paridade).
			await tick();
			descricaoEl?.focus();
		} catch (err) {
			formError =
				err instanceof ApiClientError ? err.message : 'Falha ao salvar a tarefa.';
		} finally {
			saving = false;
		}
	}

	function onDescricaoKeydown(event: KeyboardEvent): void {
		// Enter (sem Shift) salva e abre nova linha; igual ao quick-add legado.
		if (event.key === 'Enter' && !event.shiftKey) {
			event.preventDefault();
			void submit();
		}
	}

	function requestDelete(taskId: number): void {
		confirmingDeleteId = taskId;
	}

	function cancelDelete(): void {
		confirmingDeleteId = null;
	}

	async function confirmDelete(taskId: number): Promise<void> {
		deletingId = taskId;
		try {
			await deleteStageTask(taskId);
			tarefas = tarefas.filter((t) => t.id !== taskId);
			onProgressChange(etapaId, done, total);
			flash.success('Tarefa excluída.');
		} catch (err) {
			flash.danger(
				err instanceof ApiClientError ? err.message : 'Falha ao excluir tarefa.'
			);
		} finally {
			deletingId = null;
			confirmingDeleteId = null;
		}
	}

	function openDrawer(taskId: number): void {
		void drawer.open(taskId, { mode: 'etapa' });
	}

	/** Fecha o modal; confirma descarte se há rascunho não salvo (paridade). */
	function attemptClose(): void {
		if (descricao.trim() && !window.confirm('Descartar o que foi digitado?')) {
			return;
		}
		onClose();
	}

	function onKeydown(event: KeyboardEvent): void {
		if (event.key === 'Escape') {
			event.stopPropagation();
			// Se o drawer está aberto, deixa o drawer tratar o Escape primeiro.
			if ($drawer.status === 'closed') attemptClose();
		}
	}

	const PRIORIDADE_LABEL: Record<string, string> = {
		baixa: 'Baixa',
		media: 'Média',
		alta: 'Alta',
		urgente: 'Urgente'
	};
</script>

<svelte:window onkeydown={onKeydown} />

<!--
	Backdrop + diálogo: fidelidade a 05-stage-task-quick-add.css.
	  backdrop -> opacity 280ms ease-out (entrar) / 200ms (sair)
	  diálogo  -> translateY(18px) scale(0.97) -> 0/1 em ~320ms cubic-bezier(0.22,1,0.36,1)
	cubicOut aproxima a curva (0.22,1,0.36,1) do original.
-->
<div
	class="fixed inset-0 z-modal bg-black/40"
	role="presentation"
	transition:fade={{ duration: 280, easing: cubicOut }}
	onclick={attemptClose}
></div>

<div
	role="dialog"
	aria-modal="true"
	aria-labelledby="stage-quick-add-title"
	tabindex="-1"
	transition:fly={{ y: 18, duration: 320, easing: cubicOut }}
	class="fixed left-1/2 top-1/2 z-modal flex max-h-[85vh] w-full max-w-2xl -translate-x-1/2 -translate-y-1/2 flex-col gap-4 overflow-y-auto rounded-2xl border border-border-subtle bg-surface p-5 shadow-lg"
>
	<header class="flex items-start justify-between gap-3">
		<div class="flex min-w-0 flex-col gap-1">
			<span class="text-xs font-semibold uppercase tracking-wide text-text-muted">
				{eyebrow}
			</span>
			<h2
				id="stage-quick-add-title"
				class="font-heading text-lg font-bold text-text-primary"
			>
				{etapaDescricao}
			</h2>
			{#if etapaDatas}
				<span class="text-xs text-text-secondary">{etapaDatas}</span>
			{/if}
		</div>
		<div class="flex shrink-0 items-center gap-3">
			<span
				class="rounded-full border border-border-subtle px-2 py-1 text-xs font-medium text-text-secondary"
				aria-label={`${done} de ${total} tarefas concluídas`}
			>
				{done}/{total}
			</span>
			<button
				type="button"
				onclick={attemptClose}
				aria-label="Fechar"
				class="rounded-md border border-border-subtle px-2 py-1 text-text-secondary hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
			>
				✕
			</button>
		</div>
	</header>

	<!-- Form de criação -->
	{#if stageDone}
		<p
			role="status"
			class="rounded-md border border-border-subtle bg-surface-muted px-3 py-2 text-sm text-text-secondary"
		>
			Etapa concluída — desfaça a conclusão para criar tarefas.
		</p>
	{:else}
		<form
			class="flex flex-col gap-2"
			onsubmit={(e) => {
				e.preventDefault();
				void submit();
			}}
		>
			<label
				for="stage-quick-add-descricao"
				class="text-xs font-semibold uppercase tracking-wide text-text-muted"
			>
				Nova tarefa
			</label>
			<textarea
				id="stage-quick-add-descricao"
				bind:this={descricaoEl}
				bind:value={descricao}
				onkeydown={onDescricaoKeydown}
				rows="2"
				placeholder="Descreva a tarefa…"
				disabled={saving}
				class="w-full rounded-md border border-border-subtle bg-surface px-3 py-2 text-sm text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-60"
			></textarea>
			{#if formError}
				<p role="alert" class="text-xs text-danger">{formError}</p>
			{/if}
			<div class="flex items-center justify-between gap-3">
				<span class="text-xs text-text-muted">
					<kbd class="rounded border border-border-subtle px-1">Enter</kbd> salvar e abrir nova
					linha · clique fora para fechar
				</span>
				<button
					type="submit"
					disabled={saving}
					class="rounded-md bg-primary-600 px-4 py-1.5 text-sm font-medium text-white hover:opacity-90 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-50"
				>
					{saving ? 'Salvando…' : 'Salvar'}
				</button>
			</div>
		</form>
	{/if}

	<!-- Lista das tarefas existentes -->
	<div class="flex flex-col gap-2 border-t border-border-subtle pt-3">
		{#if loadState === 'loading'}
			<p role="status" aria-live="polite" class="text-sm text-text-secondary">
				Carregando tarefas…
			</p>
		{:else if loadState === 'error'}
			<div role="alert" class="flex flex-col items-start gap-2 text-sm text-text-primary">
				<p>{loadError}</p>
				<button
					type="button"
					onclick={() => void loadTasks()}
					class="rounded-md border border-border-subtle bg-surface px-3 py-1.5 text-sm font-medium text-text-primary hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
				>
					Tentar novamente
				</button>
			</div>
		{:else if tarefas.length === 0}
			<p class="text-sm text-text-muted">Nenhuma tarefa nesta etapa ainda.</p>
		{:else}
			<ul class="flex flex-col gap-2">
				{#each tarefas as task (task.id)}
					{@const isFinalized = normalizeStatus(task.status) === 'finalizada'}
					<li
						class="flex items-start justify-between gap-3 rounded-md border border-border-subtle px-3 py-2"
					>
						<button
							type="button"
							onclick={() => openDrawer(task.id)}
							class="flex min-w-0 flex-1 flex-col items-start gap-1 text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
						>
							<span
								class="text-sm {isFinalized
									? 'text-text-muted line-through'
									: 'text-text-primary'}"
							>
								{task.descricao}
							</span>
							<span class="flex flex-wrap items-center gap-2 text-xs text-text-muted">
								{#if task.responsavel}<span>{task.responsavel}</span>{/if}
								{#if task.prioridade}<span
										>· {PRIORIDADE_LABEL[task.prioridade] ?? task.prioridade}</span
									>{/if}
							</span>
						</button>

						{#if task.permissions.can_delete}
							{#if confirmingDeleteId === task.id}
								<div class="flex shrink-0 items-center gap-2" transition:fade={{ duration: 100 }}>
									<span class="text-xs text-text-secondary">Excluir esta tarefa?</span>
									<button
										type="button"
										onclick={cancelDelete}
										disabled={deletingId === task.id}
										class="rounded-md border border-border-subtle px-2 py-1 text-xs text-text-secondary hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-50"
									>
										Cancelar
									</button>
									<button
										type="button"
										onclick={() => void confirmDelete(task.id)}
										disabled={deletingId === task.id}
										class="rounded-md bg-danger px-2 py-1 text-xs font-medium text-white hover:opacity-90 focus:outline-none focus-visible:ring-2 focus-visible:ring-danger disabled:opacity-50"
									>
										{deletingId === task.id ? 'Excluindo…' : 'Excluir'}
									</button>
								</div>
							{:else}
								<button
									type="button"
									onclick={() => requestDelete(task.id)}
									aria-label="Excluir tarefa"
									class="shrink-0 rounded-md border border-border-subtle px-2 py-1 text-text-muted hover:bg-surface-muted hover:text-danger focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
								>
									<i class="fas fa-trash" aria-hidden="true"></i>
								</button>
							{/if}
						{/if}
					</li>
				{/each}
			</ul>
		{/if}
	</div>
</div>
