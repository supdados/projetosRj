<script lang="ts">
	/**
	 * Card de um projeto na tela "Projetos Pendentes" (específico desta tela).
	 *
	 * Reusa os componentes compartilhados Card/Badge (NÃO os edita) e agora dá
	 * PARIDADE de mutação com o Jinja (`templates/projects/pendentes.html`):
	 *  - botão de STATUS cíclico por etapa (idle -> iniciada -> concluída ->
	 *    idle) com os 3 ícones/labels e títulos, atualizando o estado local
	 *    (riscado das células) e decrementando chips/contador "Projetos no foco"
	 *    ao concluir (via callbacks da página); toast success/info/danger;
	 *  - pílula "Tarefas" que abre o quick-add (modal por etapa) com a contagem
	 *    done/total; bloqueio quando a etapa está concluída;
	 *  - expandir/recolher "outras etapas" com animação, ícone +/− e
	 *    `aria-expanded`, persistindo o estado em localStorage
	 *    (`pendingExpandedProjects`).
	 *
	 * Buckets/contadores chegam prontos do backend; mutações locais só refletem o
	 * resultado das ações (o backend é a fonte de verdade no próximo carregamento).
	 */
	import { base } from '$app/paths';
	import { slide } from 'svelte/transition';
	import { cubicOut } from 'svelte/easing';
	import Card from './Card.svelte';
	import { flash } from '$lib/stores/flash';
	import { ApiClientError } from '$lib/api/client';
	import { toggleEtapaIniciada, toggleEtapaDone } from '$lib/api/pendentesMutations';
	import { normalizeStatus } from '$lib/utils/taskStatus';
	import type {
		PendingProjectRow,
		PendingEtapa,
		EtapaBucket,
		EtapaTaskProgress
	} from '$lib/types/pendentes';
	import type { TaskDrawerStore } from '$lib/stores/taskDrawer';

	interface QuickAddRequest {
		projectId: number;
		projectTitulo: string;
		etapaId: number;
		etapaDescricao: string;
		etapaDatas: string;
		stageDone: boolean;
	}

	interface Props {
		row: PendingProjectRow;
		/** Mapa global `etapaId` -> bucket (carga da tela). */
		bucketMap: Record<string, EtapaBucket>;
		/** Mapa global `etapaId` -> progresso de tarefas (carga da tela). */
		progressMap: Record<string, EtapaTaskProgress>;
		/**
		 * Mapa global `etapaId` -> posição 1-based no projeto, para a numeração
		 * "<projeto>.<posição>" idêntica à do Detalhe. Opcional (backend antigo).
		 */
		positionMap?: Record<string, number>;
		/** Store do drawer (compartilhada pela página). */
		drawer: TaskDrawerStore;
		/** Set de IDs de projeto expandidos (persistido em localStorage). */
		expandedProjects: Set<string>;
		/** Notifica a página da mudança de expansão (persistência centralizada). */
		onToggleExpanded: (projectId: number, expanded: boolean) => void;
		/** Pede à página para abrir o quick-add (que reusa a store do drawer). */
		onOpenQuickAdd: (request: QuickAddRequest) => void;
		/** Decrementa o contador global "Projetos no foco" quando o card esvazia. */
		onProjectDefocused: () => void;
	}

	let {
		row,
		bucketMap,
		progressMap,
		positionMap = {},
		drawer,
		expandedProjects,
		onToggleExpanded,
		onOpenQuickAdd,
		onProjectDefocused
	}: Props = $props();

	const project = $derived(row.project);
	const orgaoLabel = $derived(project.orgao_sigla ?? project.orgao ?? 'Não informado');

	/**
	 * Estado de status por etapa (`iniciada`/`done`), inicializado da carga e
	 * mutável após cada toggle. As etapas concluídas PERMANECEM visíveis (com o
	 * status atualizado) até o próximo carregamento — paridade com o legado, que
	 * deixa o usuário revisar/reverter.
	 */
	let etapaState = $state<Record<number, { iniciada: boolean; done: boolean }>>({});

	/** Contadores de chips locais (decrementam ao concluir etapas). */
	let counts = $state({
		atrasadas: 0,
		'7dias': 0,
		'14dias': 0,
		'21dias': 0,
		sem_data: 0
	});

	/** Progresso de tarefas por etapa (atualizado pelo quick-add). */
	let progressByEtapa = $state<Record<number, EtapaTaskProgress>>({});

	/**
	 * Re-semeia o estado local a partir do `row`/`progressMap` na carga inicial e
	 * a CADA recarregamento (quando o `load()` da página substitui o `row`). Entre
	 * reloads o `row` não muda, então mutações locais (toggle de etapa, quick-add)
	 * persistem; o próximo carregamento re-sincroniza com o servidor — paridade com
	 * o comportamento legado, sem ficar com estado defasado (o `$state` semeado uma
	 * vez não captava o novo `row` por ser keyed por `project.id`).
	 */
	$effect(() => {
		const etapas = [...row.etapas_visiveis, ...row.etapas_outras];
		etapaState = Object.fromEntries(
			etapas.map((e) => [e.id, { iniciada: e.iniciada, done: e.done }])
		);
		counts = {
			atrasadas: row.qtd_atrasadas,
			'7dias': row.qtd_7dias,
			'14dias': row.qtd_14dias,
			'21dias': row.qtd_21dias,
			sem_data: row.qtd_sem_data
		};
		progressByEtapa = Object.fromEntries(
			etapas.map((e) => [e.id, progressMap[String(e.id)] ?? { total: 0, done: 0 }])
		);
	});

	let inFlightEtapa = $state<number | null>(null);
	let projectDefocused = false;

	function etapaBucket(etapa: PendingEtapa): EtapaBucket {
		return bucketMap[String(etapa.id)] ?? 'futuro';
	}

	function progressOf(etapa: PendingEtapa): EtapaTaskProgress {
		return progressByEtapa[etapa.id] ?? { total: 0, done: 0 };
	}

	/** Formata uma data ISO (yyyy-mm-dd) em pt-BR; vazio vira travessão. */
	function formatDateBr(iso: string | null): string {
		if (!iso) return '—';
		const parsed = new Date(iso);
		if (Number.isNaN(parsed.getTime())) return '—';
		return parsed.toLocaleDateString('pt-BR', {
			day: '2-digit',
			month: '2-digit',
			year: 'numeric',
			timeZone: 'UTC'
		});
	}

	/** Rótulo de datas usado no cabeçalho do quick-add (paridade com o legado). */
	function etapaDatasLabel(etapa: PendingEtapa): string {
		const ini = etapa.data_inicio ? formatDateBr(etapa.data_inicio) : '';
		const fim = etapa.data_fim ? formatDateBr(etapa.data_fim) : '';
		if (ini && fim) return `${ini} — ${fim}`;
		if (ini) return `Início ${ini}`;
		if (fim) return `Fim ${fim}`;
		return 'Etapa sem datas definidas';
	}

	const headingId = $derived(`pending-project-${project.id}`);
	const isExpanded = $derived(expandedProjects.has(String(project.id)));
	const otherPanelId = $derived(`outras-etapas-${project.id}`);

	/**
	 * Decrementa os contadores em cascata ao concluir uma etapa, espelhando
	 * `decrementBucketCounters` do legado (7d também conta como 14d/21d etc.).
	 */
	function decrementBucketCounters(bucket: EtapaBucket): void {
		if (bucket === 'atrasada') {
			counts.atrasadas = Math.max(0, counts.atrasadas - 1);
			return;
		}
		if (bucket === '7dias') {
			counts['7dias'] = Math.max(0, counts['7dias'] - 1);
			counts['14dias'] = Math.max(0, counts['14dias'] - 1);
			counts['21dias'] = Math.max(0, counts['21dias'] - 1);
			return;
		}
		if (bucket === '14dias') {
			counts['14dias'] = Math.max(0, counts['14dias'] - 1);
			counts['21dias'] = Math.max(0, counts['21dias'] - 1);
			return;
		}
		if (bucket === '21dias') {
			counts['21dias'] = Math.max(0, counts['21dias'] - 1);
			return;
		}
		if (bucket === 'sem_data') {
			counts.sem_data = Math.max(0, counts.sem_data - 1);
		}
	}

	/** Quando todos os chips zeram, o projeto sai do foco (decrementa global). */
	function maybeDefocusProject(): void {
		if (projectDefocused) return;
		const remaining =
			counts.atrasadas + counts['7dias'] + counts['14dias'] + counts['21dias'] + counts.sem_data;
		if (remaining <= 0) {
			projectDefocused = true;
			onProjectDefocused();
		}
	}

	/**
	 * Botão de status cíclico (mesmo ciclo da tela do projeto): idle ->
	 * `/toggle-iniciada` (vira iniciada); started -> `/toggle` (vira concluída);
	 * idle/concluída -> `/toggle-iniciada`. Atualiza o estado local e, ao
	 * concluir, decrementa os chips e o contador global.
	 */
	async function toggleStatus(etapa: PendingEtapa): Promise<void> {
		if (inFlightEtapa !== null) return;
		const state = etapaState[etapa.id] ?? { iniciada: false, done: false };
		const wasDone = state.done;
		inFlightEtapa = etapa.id;
		try {
			const result = state.iniciada
				? await toggleEtapaDone(etapa.id)
				: await toggleEtapaIniciada(etapa.id);
			const next = result.etapa;
			etapaState[etapa.id] = { iniciada: next.iniciada, done: next.done };

			// Mensagem: o backend não devolve o texto informativo do legado; ela é
			// derivada no client quando a etapa deixou de estar iniciada+done.
			if (!next.iniciada && !next.done && wasDone) {
				flash.info(
					'Etapa marcada como não iniciada e, consequentemente, como não concluída.'
				);
			} else {
				const okMsg = next.done ? 'Concluída.' : next.iniciada ? 'Iniciada.' : 'Não iniciada.';
				flash.success(okMsg);
			}

			// Concluir decrementa os chips/contadores (paridade com o legado).
			if (next.done && !wasDone) {
				decrementBucketCounters(etapaBucket(etapa));
				maybeDefocusProject();
			}
		} catch (err) {
			const message =
				err instanceof ApiClientError ? err.message : 'Não foi possível atualizar a etapa.';
			// 422 de "tarefas pendentes" / "não iniciada" vem como validation.
			flash.danger(message);
		} finally {
			inFlightEtapa = null;
		}
	}

	function openQuickAdd(etapa: PendingEtapa): void {
		const state = etapaState[etapa.id] ?? { iniciada: false, done: false };
		onOpenQuickAdd({
			projectId: project.id,
			projectTitulo: project.titulo,
			etapaId: etapa.id,
			etapaDescricao: etapa.descricao,
			etapaDatas: etapaDatasLabel(etapa),
			stageDone: state.done
		});
	}

	/** Permite ao pai sincronizar o progresso de uma etapa (após quick-add). */
	export function syncEtapaProgress(etapaId: number, done: number, total: number): void {
		progressByEtapa[etapaId] = { done, total };
	}

	function toggleExpanded(): void {
		onToggleExpanded(project.id, !isExpanded);
	}

	const STATUS_ICON = {
		idle: 'far fa-circle',
		started: 'fas fa-play-circle',
		done: 'fas fa-check-circle'
	};
	const STATUS_LABEL = { idle: 'Não iniciada', started: 'Iniciada', done: 'Concluída' };
	const STATUS_TITLE = {
		idle: 'Clique para marcar como iniciada',
		started: 'Clique para marcar como concluída',
		done: 'Clique para marcar como não iniciada'
	};

	function statusKey(etapaId: number): 'idle' | 'started' | 'done' {
		const state = etapaState[etapaId] ?? { iniciada: false, done: false };
		if (state.done) return 'done';
		if (state.iniciada) return 'started';
		return 'idle';
	}

	/**
	 * Numeração de exibição "<projeto>.<posição>", idêntica à do Detalhe
	 * (StageList.displayNumber). Fallback no id bruto quando o backend ainda
	 * não envia o mapa (rolling deploy).
	 */
	function etapaDisplayNumber(etapa: PendingEtapa): string {
		const position = positionMap[String(etapa.id)];
		return position ? `${project.id}.${position}` : String(etapa.id);
	}

	// Rótulo de coluna: mesmo estilo do StageGroupHeader do hub de Tarefas.
	const TH = 'px-2 py-2 text-2xs font-bold uppercase tracking-[0.08em] text-text-secondary';
</script>

{#snippet stageColumns()}
	<!-- Larguras FIXAS (table-fixed) p/ que todos os cards tenham a MESMA grade de
		 colunas, independente do conteúdo. Etapa ocupa o restante; ações têm largura
		 fixa. -->
	<colgroup>
		<col />
		<col class="w-[18%]" />
		<col class="w-[7.5rem]" />
		<col class="w-[7.5rem]" />
		<col class="w-[8.75rem]" />
		<col class="w-[9rem]" />
	</colgroup>
{/snippet}

{#snippet stageTableHead()}
	<!-- Faixa azul com labels de coluna — mesma linguagem do StageGroupHeader do
	     hub de Tarefas (bg-wash-neutral, text-2xs bold uppercase text-text-secondary). -->
	<thead>
		<tr class="border-b border-border-subtle bg-wash-neutral text-left">
			<th scope="col" class={`${TH} text-left`}>Etapa</th>
			<th scope="col" class={`${TH} text-center`}>Responsável</th>
			<th scope="col" class={`${TH} text-center`}>Data Início</th>
			<th scope="col" class={`${TH} text-center`}>Data Fim</th>
			<th scope="col" class={`${TH} text-center`}>Tarefas</th>
			<th scope="col" class={`${TH} text-center`}>Status</th>
		</tr>
	</thead>
{/snippet}

{#snippet etapaRow(etapa: PendingEtapa)}
	{@const progress = progressOf(etapa)}
	{@const key = statusKey(etapa.id)}
	{@const isDone = key === 'done'}
	{@const isEmpty = progress.total === 0}
	<tr class="group border-b border-border-subtle transition-colors duration-fast last:border-0 hover:bg-surface-muted">
		<td class="truncate px-2 py-2.5 align-middle {isDone ? 'text-text-muted line-through' : 'text-text-primary'}" title={`${etapaDisplayNumber(etapa)} - ${etapa.descricao}`}>
			<span class="font-mono font-normal text-text-muted">{etapaDisplayNumber(etapa)}</span> - {etapa.descricao}
		</td>
		<td class="truncate px-2 py-2.5 text-center align-middle {isDone ? 'text-text-muted line-through' : 'text-text-secondary'}" title={etapa.responsavel || 'Não informado'}>
			{etapa.responsavel || 'Não informado'}
		</td>
		<!-- Datas em mono, como as colunas de datas da lista de Projetos. -->
		<td class="whitespace-nowrap px-2 py-2.5 text-center align-middle font-mono font-medium {isDone ? 'text-text-muted line-through' : 'text-text-secondary'}">
			{#if etapa.data_inicio}
				<time datetime={etapa.data_inicio}>{formatDateBr(etapa.data_inicio)}</time>
			{:else}—{/if}
		</td>
		<td class="whitespace-nowrap px-2 py-2.5 text-center align-middle font-mono font-medium {isDone ? 'text-text-muted line-through' : 'text-text-secondary'}">
			{#if etapa.data_fim}
				<time datetime={etapa.data_fim}>{formatDateBr(etapa.data_fim)}</time>
			{:else}—{/if}
		</td>
		<td class="px-2 py-2.5 text-center align-middle">
			<button
				type="button"
				onclick={() => openQuickAdd(etapa)}
				disabled={isDone}
				title="Ver e adicionar tarefas desta etapa"
				aria-label="Ver e adicionar tarefas desta etapa"
				class="inline-flex h-8 w-[7.25rem] items-center justify-center gap-1.5 rounded-lg border px-2.5 text-xs font-semibold leading-none transition-colors duration-fast focus:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-40
					{isEmpty
					? 'border-dashed border-primary-500/40 bg-transparent text-text-secondary hover:border-brand hover:bg-primary-100/40 hover:text-brand'
					: 'border-primary-500/40 bg-wash-neutral text-brand hover:border-brand hover:bg-wash-brand'}"
			>
				{#if isEmpty}
					<i class="fas fa-plus" aria-hidden="true"></i>
					<span>Tarefas</span>
				{:else}
					<span class="font-bold">{progress.done}/{progress.total}</span>
				{/if}
			</button>
		</td>
		<td class="px-2 py-2.5 text-center align-middle">
			<!-- Status: réplica fiel do botão-ciclo da etapa dentro do projeto
				 (StageRow `.etapa-status-toggle`) — mesmas cores, ícones e rótulos. -->
			<button
				type="button"
				onclick={() => void toggleStatus(etapa)}
				disabled={inFlightEtapa === etapa.id}
				title={STATUS_TITLE[key]}
				class="etapa-status-toggle etapa-status-toggle-{key}"
				data-state={key}
			>
				<i class={STATUS_ICON[key]} aria-hidden="true"></i>
				<span>{STATUS_LABEL[key]}</span>
			</button>
		</td>
	</tr>
{/snippet}

<Card labelId={headingId}>
	<div class="flex flex-col gap-4">
		<header
			class="-mx-5 -mt-5 flex flex-col gap-2 border-b border-border-subtle px-5 pb-4 pt-5 sm:flex-row sm:items-start sm:justify-between"
		>
			<div class="flex min-w-0 flex-wrap items-baseline gap-x-2.5 gap-y-1">
				<!-- ID original do projeto antes do nome (ID - Nome). Tipografia/cor do
					 link espelham a coluna Título da lista de Projetos (text-base
					 medium primary-700 + hover underline; ID em xs bold muted). -->
				<a
					href={`${base}/projetos/${project.id}`}
					id={headingId}
					title="Abrir projeto"
					class="flex min-w-0 items-baseline gap-1.5 text-base font-medium text-brand no-underline transition-colors duration-fast hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
				>
					<span class="shrink-0 font-mono text-xs font-bold text-text-muted">{project.id}</span>
					<span class="shrink-0 text-text-muted" aria-hidden="true">–</span>
					<span class="truncate">{project.titulo}</span>
				</a>
				<span class="whitespace-nowrap text-xs text-text-muted">
					Órgão: <strong class="font-medium text-text-secondary">{orgaoLabel}</strong>
				</span>
			</div>
			{#if row.max_overdue_days > 0}
				<span class="shrink-0 whitespace-nowrap text-xs text-text-muted sm:self-center">
					Maior atraso:
					<strong class="font-medium text-danger">{row.max_overdue_days} dia(s)</strong>
				</span>
			{/if}
		</header>

		{#if row.etapas_visiveis.length === 0}
			<p class="text-sm text-text-muted">Sem etapas urgentes na janela atual.</p>
		{:else}
			<div class="overflow-x-auto rounded-lg border border-border-subtle">
				<table class="w-full table-fixed border-collapse text-xs 2xl:text-sm">
					<caption class="sr-only">Etapas pendentes de {project.titulo}</caption>
					{@render stageColumns()}
					{@render stageTableHead()}
					<tbody>
						{#each row.etapas_visiveis as etapa (etapa.id)}
							{@render etapaRow(etapa)}
						{/each}
					</tbody>
				</table>
			</div>
		{/if}

		{#if row.qtd_outras > 0}
			<div class="flex flex-col gap-2">
				<button
					type="button"
					onclick={toggleExpanded}
					aria-expanded={isExpanded}
					aria-controls={otherPanelId}
					class="inline-flex w-fit items-center rounded-md text-sm font-semibold text-brand transition-colors duration-fast hover:text-primary-600 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
				>
					<span>
						{#if isExpanded}− Recolher{:else}+ {row.qtd_outras} {row.qtd_outras === 1 ? 'etapa fora do escopo' : 'etapas fora do escopo'}{/if}
					</span>
				</button>

				{#if isExpanded}
					<div
						id={otherPanelId}
						class="overflow-hidden border-t border-dashed border-border-subtle pt-3"
						transition:slide={{ duration: 340, easing: cubicOut }}
					>
						<div class="pb-2 text-2xs font-bold uppercase tracking-[0.08em] text-text-muted">
							Outras etapas
						</div>
						<div class="overflow-x-auto rounded-lg border border-border-subtle">
							<table class="w-full table-fixed border-collapse text-xs 2xl:text-sm">
								<caption class="sr-only">Outras etapas de {project.titulo}</caption>
								{@render stageColumns()}
								{@render stageTableHead()}
								<tbody>
									{#each row.etapas_outras as etapa (etapa.id)}
										{@render etapaRow(etapa)}
									{/each}
								</tbody>
							</table>
						</div>
					</div>
				{/if}
			</div>
		{/if}
	</div>
</Card>

<style>
	/* Botão de status (ciclo) — PORTE 1:1 do `.etapa-status-toggle` da etapa dentro
	   do projeto (StageRow.svelte), para a etapa em Pendentes ter a MESMA cor,
	   borda e aparência: branco/azul-acinzentado (não iniciada), azul (iniciada),
	   verde (concluída). */
	.etapa-status-toggle {
		height: 30px;
		min-width: 124px;
		border-radius: 7px;
		border: 1px solid #cbdcf0;
		padding: 0 0.58rem;
		background: #fff;
		color: #2b4d6f;
		font-weight: 600;
		font-size: 0.78rem;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		gap: 0.3rem;
		cursor: pointer;
		transition: all 0.16s ease;
	}
	.etapa-status-toggle i {
		font-size: 0.875rem;
	}
	.etapa-status-toggle span {
		text-transform: uppercase;
		letter-spacing: 0.03em;
		font-size: 0.7rem;
	}
	.etapa-status-toggle:hover:not(:disabled),
	.etapa-status-toggle:focus-visible:not(:disabled) {
		background: #f1f7ff;
		border-color: #b7cee5;
		color: #20486f;
		outline: none;
	}
	.etapa-status-toggle:disabled {
		opacity: 0.45;
		cursor: not-allowed;
	}
	.etapa-status-toggle-done {
		background: #eaf7f1;
		border-color: #b9dfca;
		color: #1d714e;
	}
	.etapa-status-toggle-done:hover:not(:disabled),
	.etapa-status-toggle-done:focus-visible:not(:disabled) {
		background: #e3f4eb;
		border-color: #a8d5bd;
		color: #175f41;
	}
	.etapa-status-toggle-started {
		background: #edf5ff;
		border-color: #c5d8ee;
		color: #255585;
	}
	.etapa-status-toggle-started:hover:not(:disabled),
	.etapa-status-toggle-started:focus-visible:not(:disabled) {
		background: #e7f1fd;
		border-color: #b8d0ea;
		color: #214f7d;
	}
	:global(html[data-theme='dark']) .etapa-status-toggle {
		background: var(--stage-chip-bg, #262626);
		border-color: var(--ds-color-border-base);
		color: var(--stage-chip-text, #e0e0e0);
	}
	:global(html[data-theme='dark']) .etapa-status-toggle:hover:not(:disabled),
	:global(html[data-theme='dark']) .etapa-status-toggle:focus-visible:not(:disabled) {
		background: var(--ds-color-surface-raised);
		border-color: var(--ds-color-border-strong);
		color: var(--ds-color-text-primary);
	}
	:global(html[data-theme='dark']) .etapa-status-toggle-done {
		background: var(--ds-color-wash-success);
		border-color: var(--ds-color-border-success);
		color: var(--ds-color-text-success);
	}
	:global(html[data-theme='dark']) .etapa-status-toggle-done:hover:not(:disabled),
	:global(html[data-theme='dark']) .etapa-status-toggle-done:focus-visible:not(:disabled) {
		background: rgba(73, 185, 135, 0.22);
		border-color: var(--ds-color-border-success);
		color: var(--ds-color-text-success);
	}
	:global(html[data-theme='dark']) .etapa-status-toggle-started {
		background: var(--ds-color-wash-brand);
		border-color: var(--ds-color-border-brand);
		color: var(--ds-color-primary-500);
	}
	:global(html[data-theme='dark']) .etapa-status-toggle-started:hover:not(:disabled),
	:global(html[data-theme='dark']) .etapa-status-toggle-started:focus-visible:not(:disabled) {
		background: rgba(78, 149, 204, 0.28);
		border-color: var(--ds-color-border-brand);
		color: var(--ds-color-primary-500);
	}
</style>
