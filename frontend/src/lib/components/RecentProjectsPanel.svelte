<script lang="ts">
	/**
	 * Painel de projetos recentes do Dashboard. Lista acessivel (cada item
	 * focavel via link). Status -> Badge. Datas derivadas chegam prontas do
	 * backend (read-only).
	 *
	 * Apresentacao fiel ao partial Jinja `_recent_projects_panel.html` +
	 * `recent-projects-panel.css`: tabela em CSS grid (ID / Projeto / Orgao /
	 * Prioridade) com cabecalho sticky e linha inteira clicavel. As colunas do
	 * cabecalho e das linhas compartilham o mesmo template de grid.
	 */
	import { base } from '$app/paths';
	import Card from './Card.svelte';
	import type { Project, TaskPrioridade } from '$lib/types/entities';

	interface Props {
		projects: Project[];
	}

	let { projects }: Props = $props();

	// Cor da pilula de prioridade (espelha .glass-badge.priority-* do original).
	// Tons via tokens semanticos para troca automatica no dark mode.
	const priorityClass: Record<string, string> = {
		baixa: 'bg-surface-muted text-success',
		media: 'bg-surface-muted text-primary-700',
		alta: 'bg-surface-muted text-orange',
		urgente: 'bg-surface-muted text-danger'
	};

	function prioKey(prioridade: TaskPrioridade | string | null): string {
		return (prioridade ?? '').toString().toLowerCase();
	}

	function prioLabel(prioridade: TaskPrioridade | string | null): string {
		const k = prioKey(prioridade);
		if (!k) return '—';
		return k.charAt(0).toUpperCase() + k.slice(1);
	}
</script>

<Card title="Projetos Recentes" labelId="recent-projects-title">
	{#if projects.length === 0}
		<div class="flex flex-col items-center gap-3 px-4 py-8 text-center">
			<svg aria-hidden="true" class="h-9 w-9 text-text-muted" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
				<path d="M3 7a2 2 0 0 1 2-2h4.2a2 2 0 0 1 1.4.6l1.2 1.2a2 2 0 0 0 1.4.6H19a2 2 0 0 1 2 2v2" />
				<path d="M3.3 11h17.4a1.2 1.2 0 0 1 1.18 1.42l-1.3 6A2 2 0 0 1 18.6 20H5.4a2 2 0 0 1-1.96-1.58l-1.3-6A1.2 1.2 0 0 1 3.3 11Z" />
			</svg>
			<p class="text-sm text-text-muted">Nenhum projeto recente para mostrar.</p>
		</div>
	{:else}
		<div
			class="overflow-x-auto"
			role="table"
			aria-labelledby="recent-projects-title"
		>
			<!-- Cabecalho sticky -->
			<div
				role="row"
				class="rp-grid sticky top-0 z-[5] items-center border-b border-border-subtle bg-surface-muted text-2xs font-bold uppercase tracking-caps text-primary-700"
			>
				<span role="columnheader" class="px-3 py-2.5 text-center">ID</span>
				<span role="columnheader" class="px-3 py-2.5">Projeto</span>
				<span role="columnheader" class="px-3 py-2.5 text-center">Órgão</span>
				<span role="columnheader" class="px-3 py-2.5 text-center">Prioridade</span>
			</div>

			<!-- Linhas: o <a> inteiro e clicavel -->
			{#each projects as project (project.id)}
				<a
					role="row"
					href={`${base}/projetos/${project.id}`}
					class="rp-grid items-center border-b border-border-subtle no-underline transition-colors duration-slow hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary-500"
				>
					<span role="cell" class="px-3 py-3 text-center text-sm text-text-secondary">{project.id}</span>
					<span role="cell" class="truncate px-3 py-3 text-sm font-medium text-primary-600">{project.titulo}</span>
					<span role="cell" class="px-3 py-3 text-center text-sm text-text-secondary">
						{project.orgao_sigla ?? project.orgao ?? 'N/A'}
					</span>
					<span role="cell" class="px-3 py-3 text-center">
						<span
							class="inline-flex min-w-[92px] items-center justify-center rounded-sm px-2 py-1 text-2xs font-bold uppercase tracking-wide {priorityClass[
								prioKey(project.prioridade)
							] ?? 'bg-surface-muted text-text-secondary'}"
						>
							{prioLabel(project.prioridade)}
						</span>
					</span>
				</a>
			{/each}
		</div>
	{/if}
</Card>

<style>
	/* Grid compartilhado por cabecalho e linhas (espelha --rp-cols do original:
	   64px | 1fr | 170px | 185px), garantindo alinhamento de colunas. */
	.rp-grid {
		display: grid;
		grid-template-columns: 64px minmax(0, 1fr) 170px 185px;
	}
</style>
