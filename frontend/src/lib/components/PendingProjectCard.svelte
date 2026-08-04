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
	import { flash } from '$lib/stores/flash';
	import { ApiClientError } from '$lib/api/client';
	import { toggleEtapaIniciada, toggleEtapaDone } from '$lib/api/pendentesMutations';
	import { normalizeStatus } from '$lib/utils/taskStatus';
	import { podeConcluirEtapa } from '$lib/utils/etapaPrecondicoes';
	import type {
		PendingProjectRow,
		PendingEtapa,
		EtapaBucket,
		EtapaTaskProgress
	} from '$lib/types/pendentes';
	import type { TaskDrawerStore } from '$lib/stores/taskDrawer';
	import StageTaskPill from './StageTaskPill.svelte';
	import '$lib/styles/stage-chips.css';

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
		// Gate cliente da conclusão: evita a rajada de 422 idênticos do clique repetido.
		if (state.iniciada && !state.done) {
			const { motivo } = podeConcluirEtapa(
				progressOf(etapa),
				etapa.data_inicio,
				etapa.data_fim,
				etapa.tem_responsavel
			);
			if (motivo) {
				flash.warning(motivo);
				return;
			}
		}
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
	const TH = 'px-2 py-2 text-xs font-bold uppercase tracking-caps text-text-secondary';
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
	<tr class="group border-b border-border-subtle transition-colors duration-fast last:border-0 hover:bg-surface-muted">
		<td class="truncate px-2 py-2.5 align-middle {isDone ? 'text-text-muted line-through' : 'text-text-primary'}" title={`${etapaDisplayNumber(etapa)} - ${etapa.descricao}`}>
			<span class="font-normal tabular-nums text-text-muted">{etapaDisplayNumber(etapa)}</span> - {etapa.descricao}
		</td>
		<td class="truncate px-2 py-2.5 text-center align-middle {isDone ? 'text-text-muted line-through' : 'text-text-secondary'}" title={etapa.responsavel || 'Não informado'}>
			{etapa.responsavel || 'Não informado'}
		</td>
		<!-- Datas com `tabular-nums`, como as colunas de datas da lista de Projetos:
			 alinha os digitos sem trocar a familia tipografica da aplicacao. -->
		<td class="whitespace-nowrap px-2 py-2.5 text-center align-middle font-medium tabular-nums {isDone ? 'text-text-muted line-through' : 'text-text-secondary'}">
			{#if etapa.data_inicio}
				<time datetime={etapa.data_inicio}>{formatDateBr(etapa.data_inicio)}</time>
			{:else}—{/if}
		</td>
		<td class="whitespace-nowrap px-2 py-2.5 text-center align-middle font-medium tabular-nums {isDone ? 'text-text-muted line-through' : 'text-text-secondary'}">
			{#if etapa.data_fim}
				<time datetime={etapa.data_fim}>{formatDateBr(etapa.data_fim)}</time>
			{:else}—{/if}
		</td>
		<td class="px-2 py-2.5 text-center align-middle">
			<StageTaskPill
				done={progress.done}
				total={progress.total}
				stageDone={isDone}
				title={isDone
					? 'Etapa concluída — desfaça a conclusão para criar tarefas'
					: 'Ver e adicionar tarefas desta etapa'}
				ariaLabel="Ver e adicionar tarefas desta etapa"
				onclick={() => openQuickAdd(etapa)}
			/>
		</td>
		<td class="px-2 py-2.5 text-center align-middle">
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

<!-- Mesma casca do card de grupo da tela de Tarefas: rounded-lg + overflow-hidden
	 (o `Card` da marca é rounded-xl, reservado aos cards de header de página),
	 header px-5 py-4 e corpo p-3. -->
<section
	aria-labelledby={headingId}
	class="overflow-hidden rounded-lg border border-border-subtle bg-surface shadow-sm"
>
	<header
		class="flex flex-col gap-2 border-b border-border-subtle px-5 py-4 sm:flex-row sm:items-start sm:justify-between"
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
				Área responsável: <strong class="font-medium text-text-secondary">{orgaoLabel}</strong>
			</span>
		</div>
		{#if row.max_overdue_days > 0}
			<span class="shrink-0 whitespace-nowrap text-xs text-text-muted sm:self-center">
				Maior atraso:
				<strong class="font-medium text-danger">{row.max_overdue_days} dia(s)</strong>
			</span>
		{/if}
	</header>

	<div class="flex flex-col gap-3 p-3">
		{#if row.etapas_visiveis.length === 0}
			<p class="text-sm text-text-muted">Sem etapas urgentes na janela atual.</p>
		{:else}
			<div class="overflow-x-auto rounded-lg border border-border-subtle">
				<table class="w-full table-fixed border-collapse text-sm 2xl:text-md">
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
					class="inline-flex w-fit items-center rounded-md text-sm font-semibold text-brand transition-colors duration-fast hover:text-brand focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
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
						<div class="pb-2 text-xs font-bold uppercase tracking-caps text-text-muted">
							Outras etapas
						</div>
						<div class="overflow-x-auto rounded-lg border border-border-subtle">
							<table class="w-full table-fixed border-collapse text-sm 2xl:text-md">
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
</section>

