<script lang="ts">
	/**
	 * Card de um projeto na tela "Projetos Pendentes" (específico desta tela).
	 *
	 * Reusa os componentes compartilhados Card/Badge (NÃO os edita). Mostra o
	 * cabeçalho do projeto, os chips de contagem por bucket e uma tabela das
	 * etapas visíveis (com progresso de tarefas) recolhível via <details>.
	 * Buckets/contadores chegam prontos do backend — nada é recalculado aqui.
	 *
	 * Acessibilidade: cada projeto é um grupo expansível nativo (<details>),
	 * navegável por teclado; o título do projeto rotula a região; datas usam
	 * <time datetime>. Links internos são base-aware ($app/paths).
	 */
	import { base } from '$app/paths';
	import Card from './Card.svelte';
	import Badge from './Badge.svelte';
	import type {
		PendingProjectRow,
		PendingEtapa,
		EtapaBucket,
		EtapaTaskProgress
	} from '$lib/types/pendentes';

	interface Props {
		row: PendingProjectRow;
		/** Mapa global `etapaId` -> bucket (carga da tela). */
		bucketMap: Record<string, EtapaBucket>;
		/** Mapa global `etapaId` -> progresso de tarefas (carga da tela). */
		progressMap: Record<string, EtapaTaskProgress>;
	}

	let { row, bucketMap, progressMap }: Props = $props();

	const project = $derived(row.project);
	const orgaoLabel = $derived(project.orgao_sigla ?? project.orgao ?? 'Não informado');

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

	function etapaProgress(etapa: PendingEtapa): EtapaTaskProgress {
		return progressMap[String(etapa.id)] ?? { total: 0, done: 0 };
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

	interface Chip {
		key: string;
		count: number;
		label: string;
		tone: 'danger' | 'warning' | 'info' | 'neutral';
	}

	const chips = $derived(
		[
			{ key: 'atrasadas', count: row.qtd_atrasadas, label: 'atrasadas', tone: 'danger' },
			{ key: '7dias', count: row.qtd_7dias, label: '7 dias', tone: 'warning' },
			{ key: '14dias', count: row.qtd_14dias, label: '14 dias', tone: 'warning' },
			{ key: '21dias', count: row.qtd_21dias, label: '21 dias', tone: 'info' },
			{ key: 'sem_data', count: row.qtd_sem_data, label: 'sem data', tone: 'neutral' }
		].filter((chip) => chip.count > 0) as Chip[]
	);

	const headingId = $derived(`pending-project-${project.id}`);
</script>

<Card labelId={headingId}>
	<details open class="group flex flex-col gap-4">
		<summary
			class="flex cursor-pointer list-none flex-col gap-2 rounded-md focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 sm:flex-row sm:items-start sm:justify-between"
		>
			<div class="flex min-w-0 flex-col gap-1">
				<span class="flex items-center gap-2">
					<span
						class="text-text-muted transition-transform duration-fast group-open:rotate-90"
						aria-hidden="true">▶</span
					>
					<a
						href={`${base}/projetos/${project.id}`}
						id={headingId}
						class="truncate font-heading text-lg font-semibold text-text-primary no-underline hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
					>
						{project.titulo}
					</a>
				</span>
				<span class="text-xs text-text-muted">
					Órgão: <strong class="font-medium text-text-secondary">{orgaoLabel}</strong>
					{#if row.max_overdue_days > 0}
						· Maior atraso:
						<strong class="font-medium text-danger">{row.max_overdue_days} dia(s)</strong>
					{/if}
				</span>
			</div>

			<ul class="flex flex-wrap items-center gap-2" aria-label="Resumo de etapas por janela">
				{#each chips as chip (chip.key)}
					<li><Badge tone={chip.tone}>{chip.count} {chip.label}</Badge></li>
				{/each}
				{#if chips.length === 0}
					<li><Badge tone="neutral">Sem pendências na janela</Badge></li>
				{/if}
			</ul>
		</summary>

		{#if row.etapas_visiveis.length === 0}
			<p class="text-sm text-text-muted">Nenhuma etapa visível para a janela selecionada.</p>
		{:else}
			<div class="overflow-x-auto">
				<table class="w-full border-collapse text-sm">
					<caption class="sr-only">Etapas pendentes de {project.titulo}</caption>
					<thead>
						<tr class="border-b border-border-subtle text-left text-xs uppercase tracking-wide text-text-muted">
							<th scope="col" class="py-2 pr-3 font-semibold">Etapa</th>
							<th scope="col" class="py-2 pr-3 font-semibold">Responsável</th>
							<th scope="col" class="py-2 pr-3 font-semibold">Início</th>
							<th scope="col" class="py-2 pr-3 font-semibold">Fim</th>
							<th scope="col" class="py-2 pr-3 font-semibold">Janela</th>
							<th scope="col" class="py-2 font-semibold">Tarefas</th>
						</tr>
					</thead>
					<tbody>
						{#each row.etapas_visiveis as etapa (etapa.id)}
							{@const bucket = etapaBucket(etapa)}
							{@const progress = etapaProgress(etapa)}
							<tr class="border-b border-border-subtle last:border-0">
								<td class="py-2 pr-3 align-top {etapa.done ? 'text-text-muted line-through' : 'text-text-primary'}">
									{etapa.descricao}
								</td>
								<td class="py-2 pr-3 align-top text-text-secondary">
									{etapa.responsavel || 'Não informado'}
								</td>
								<td class="py-2 pr-3 align-top text-text-secondary">
									{#if etapa.data_inicio}
										<time datetime={etapa.data_inicio}>{formatDateBr(etapa.data_inicio)}</time>
									{:else}—{/if}
								</td>
								<td class="py-2 pr-3 align-top text-text-secondary">
									{#if etapa.data_fim}
										<time datetime={etapa.data_fim}>{formatDateBr(etapa.data_fim)}</time>
									{:else}—{/if}
								</td>
								<td class="py-2 pr-3 align-top">
									<Badge tone={bucketTone[bucket]}>{bucketLabel[bucket]}</Badge>
								</td>
								<td class="py-2 align-top text-text-secondary">
									{#if progress.total > 0}
										<span aria-label={`${progress.done} de ${progress.total} tarefas concluídas`}>
											{progress.done}/{progress.total}
										</span>
									{:else}
										<span class="text-text-muted">—</span>
									{/if}
								</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		{/if}

		{#if row.qtd_outras > 0}
			<p class="text-xs text-text-muted">
				+ {row.qtd_outras} etapa(s) fora da janela selecionada.
			</p>
		{/if}
	</details>
</Card>
