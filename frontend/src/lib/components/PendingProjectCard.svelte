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
	import Badge from './Badge.svelte';
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

	/** Rótulo PT de cada bucket (espelha as classes do template Jinja). */
	const bucketLabel: Record<EtapaBucket, string> = {
		atrasada: 'Atrasada',
		'7dias': 'Próximos 7 dias',
		'14dias': 'Próximos 14 dias',
		'21dias': 'Próximos 21 dias',
		sem_data: 'Sem data',
		futuro: 'Futura'
	};

	const bucketTone: Record<EtapaBucket, 'danger' | 'warning' | 'info' | 'neutral'> = {
		atrasada: 'danger',
		'7dias': 'warning',
		'14dias': 'warning',
		'21dias': 'info',
		sem_data: 'neutral',
		futuro: 'neutral'
	};

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

	interface Chip {
		key: string;
		count: number;
		label: string;
		tone: 'danger' | 'warning' | 'info' | 'neutral';
	}

	const chips = $derived(
		[
			{ key: 'atrasadas', count: counts.atrasadas, label: 'atrasadas', tone: 'danger' },
			{ key: '7dias', count: counts['7dias'], label: '7 dias', tone: 'warning' },
			{ key: '14dias', count: counts['14dias'], label: '14 dias', tone: 'warning' },
			{ key: '21dias', count: counts['21dias'], label: '21 dias', tone: 'info' },
			{ key: 'sem_data', count: counts.sem_data, label: 'sem data', tone: 'neutral' }
		].filter((chip) => chip.count > 0) as Chip[]
	);

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
</script>

{#snippet etapaRow(etapa: PendingEtapa)}
	{@const bucket = etapaBucket(etapa)}
	{@const progress = progressOf(etapa)}
	{@const key = statusKey(etapa.id)}
	{@const isDone = key === 'done'}
	<tr class="group border-b border-border-subtle transition-colors duration-fast last:border-0 hover:bg-surface-muted/50">
		<td class="py-2.5 pr-3 align-middle {isDone ? 'text-text-muted line-through' : 'text-text-primary'}">
			{etapa.descricao}
		</td>
		<td class="py-2.5 pr-3 align-middle {isDone ? 'text-text-muted line-through' : 'text-text-secondary'}">
			{etapa.responsavel || 'Não informado'}
		</td>
		<td class="py-2.5 pr-3 align-middle {isDone ? 'text-text-muted line-through' : 'text-text-secondary'}">
			{#if etapa.data_inicio}
				<time datetime={etapa.data_inicio}>{formatDateBr(etapa.data_inicio)}</time>
			{:else}—{/if}
		</td>
		<td class="py-2.5 pr-3 align-middle {isDone ? 'text-text-muted line-through' : 'text-text-secondary'}">
			{#if etapa.data_fim}
				<time datetime={etapa.data_fim}>{formatDateBr(etapa.data_fim)}</time>
			{:else}—{/if}
		</td>
		<td class="py-2.5 pr-3 align-middle">
			<Badge tone={bucketTone[bucket]}>{bucketLabel[bucket]}</Badge>
		</td>
		<td class="py-2.5 pr-3 text-center align-middle">
			<button
				type="button"
				onclick={() => openQuickAdd(etapa)}
				title="Ver e adicionar tarefas desta etapa"
				aria-label="Ver e adicionar tarefas desta etapa"
				class="inline-flex items-center gap-1.5 rounded-full border border-border-subtle bg-surface px-2.5 py-1 text-xs font-semibold text-text-secondary transition-colors duration-fast hover:border-primary-500 hover:bg-surface-muted hover:text-primary-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
			>
				<i class="fas fa-clipboard-list" aria-hidden="true"></i>
				<span>{progress.done}/{progress.total}</span>
				<i class="fas fa-plus text-text-muted" aria-hidden="true"></i>
			</button>
		</td>
		<td class="py-2.5 text-center align-middle">
			<button
				type="button"
				onclick={() => void toggleStatus(etapa)}
				disabled={inFlightEtapa === etapa.id}
				title={STATUS_TITLE[key]}
				class="inline-flex min-w-[7rem] items-center justify-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-semibold transition-colors duration-fast focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:cursor-not-allowed disabled:opacity-50
					{key === 'done'
					? 'border-success/40 bg-surface-muted text-success hover:bg-surface-muted'
					: key === 'started'
						? 'border-primary-500/40 bg-primary-100 text-primary-700 hover:bg-primary-100'
						: 'border-border-subtle bg-surface text-text-secondary hover:border-primary-500 hover:bg-surface-muted'}"
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
			<div class="flex min-w-0 flex-col gap-1">
				<a
					href={`${base}/projetos/${project.id}`}
					id={headingId}
					title="Abrir projeto"
					class="inline-flex min-w-0 items-center gap-2 font-heading text-lg font-bold text-text-primary no-underline transition-colors duration-fast hover:text-primary-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
				>
					<i class="fas fa-folder-open shrink-0 text-primary-600" aria-hidden="true"></i>
					<span class="truncate">{project.titulo}</span>
				</a>
				<span class="text-xs text-text-muted">
					Órgão: <strong class="font-medium text-text-secondary">{orgaoLabel}</strong>
					{#if row.max_overdue_days > 0}
						· Maior atraso:
						<strong class="font-medium text-danger">{row.max_overdue_days} dia(s)</strong>
					{/if}
				</span>
			</div>

			<ul
				class="flex flex-wrap items-center justify-end gap-1.5"
				aria-label="Resumo de etapas por janela"
			>
				{#each chips as chip (chip.key)}
					<li>
						<Badge tone={chip.tone}>
							{#if chip.key === 'atrasadas'}
								<i class="fas fa-triangle-exclamation" aria-hidden="true"></i>
							{/if}
							<span class="font-bold">{chip.count}</span>
							{chip.label}
						</Badge>
					</li>
				{/each}
				{#if chips.length === 0}
					<li><Badge tone="neutral">Sem pendências na janela</Badge></li>
				{/if}
			</ul>
		</header>

		{#if row.etapas_visiveis.length === 0}
			<p class="text-sm text-text-muted">Sem etapas urgentes na janela atual.</p>
		{:else}
			<div class="overflow-x-auto">
				<table class="w-full border-collapse text-sm">
					<caption class="sr-only">Etapas pendentes de {project.titulo}</caption>
					<thead>
						<tr
							class="border-b border-border-subtle bg-surface-muted/60 text-left text-xs font-bold uppercase tracking-caps text-text-muted"
						>
							<th scope="col" class="px-2 py-2.5 font-bold">Etapa</th>
							<th scope="col" class="px-2 py-2.5 font-bold">Responsável</th>
							<th scope="col" class="px-2 py-2.5 font-bold">Início</th>
							<th scope="col" class="px-2 py-2.5 font-bold">Fim</th>
							<th scope="col" class="px-2 py-2.5 font-bold">Janela</th>
							<th scope="col" class="px-2 py-2.5 text-center font-bold">Tarefas</th>
							<th scope="col" class="px-2 py-2.5 text-center font-bold">Status</th>
						</tr>
					</thead>
					<tbody>
						{#each row.etapas_visiveis as etapa (etapa.id)}
							{@render etapaRow(etapa)}
						{/each}
					</tbody>
				</table>
			</div>
		{/if}

		{#if row.qtd_outras > 0}
			<div class="-mx-5 -mb-5 flex flex-col border-t border-border-subtle bg-surface-muted/30">
				<button
					type="button"
					onclick={toggleExpanded}
					aria-expanded={isExpanded}
					aria-controls={otherPanelId}
					class="inline-flex w-fit items-center gap-2 rounded-md px-5 py-2.5 text-sm font-semibold text-primary-700 transition-colors duration-fast hover:text-primary-600 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
				>
					<i class={isExpanded ? 'fas fa-minus' : 'fas fa-plus'} aria-hidden="true"></i>
					<span>
						{#if isExpanded}Recolher{:else}+ {row.qtd_outras} outras etapas{/if}
					</span>
				</button>

				{#if isExpanded}
					<div
						id={otherPanelId}
						class="overflow-hidden border-t border-dashed border-border-subtle"
						transition:slide={{ duration: 340, easing: cubicOut }}
					>
						<div class="px-5 py-2 text-xs font-semibold uppercase tracking-caps text-text-muted">
							Outras etapas
						</div>
						<div class="overflow-x-auto px-5 pb-3">
							<table class="w-full border-collapse text-sm">
								<caption class="sr-only">Outras etapas de {project.titulo}</caption>
								<thead>
									<tr
										class="border-b border-border-subtle bg-surface-muted/60 text-left text-xs font-bold uppercase tracking-caps text-text-muted"
									>
										<th scope="col" class="px-2 py-2.5 font-bold">Etapa</th>
										<th scope="col" class="px-2 py-2.5 font-bold">Responsável</th>
										<th scope="col" class="px-2 py-2.5 font-bold">Início Prev.</th>
										<th scope="col" class="px-2 py-2.5 font-bold">Fim Prev.</th>
										<th scope="col" class="px-2 py-2.5 font-bold">Janela</th>
										<th scope="col" class="px-2 py-2.5 text-center font-bold">Tarefas</th>
										<th scope="col" class="px-2 py-2.5 text-center font-bold">Status</th>
									</tr>
								</thead>
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
