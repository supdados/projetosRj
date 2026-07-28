<script lang="ts">
	/**
	 * Painel de projetos recentes do Dashboard. Lista acessivel (cada item
	 * focavel via link). Status -> Badge. Datas derivadas chegam prontas do
	 * backend (read-only).
	 *
	 * Apresentacao fiel ao partial Jinja `_recent_projects_panel.html` +
	 * `recent-projects-panel.css` + `index.css`:
	 *   - Tabela em CSS grid (ID / Projeto / Orgao / Prioridade) com cabecalho
	 *     fixo (fora do scroll) e linha inteira clicavel. Colunas do cabecalho e
	 *     das linhas compartilham o mesmo template de grid (64px | 1fr | 170px | 185px).
	 *   - SCROLL-LOCK: apenas as linhas rolam internamente (overflow-y:auto), com
	 *     altura travada — a barra de rolagem comeca abaixo do cabecalho fixo, e o
	 *     painel nao empurra a pagina inteira. Espelha `.glass-table-wrapper`
	 *     (max-height + overflow) do index.css original.
	 *
	 * NAO usa o componente Card (que adiciona padding ao corpo): este painel
	 * precisa do corpo edge-to-edge para o cabecalho sticky e o scroll
	 * funcionarem como no original.
	 */
	import { base } from '$app/paths';
	import type { Project, TaskPrioridade } from '$lib/types/entities';

	interface Props {
		projects: Project[];
		/** Total de projetos cadastrados; decide a mensagem do estado vazio. */
		totalProjects?: number;
	}

	let { projects, totalProjects = 0 }: Props = $props();

	// Cor da prioridade (SEM fundo — apenas o texto colorido). Tons via tokens
	// semanticos para troca automatica no dark mode.
	const priorityClass: Record<string, string> = {
		baixa: 'text-success',
		media: 'text-brand',
		alta: 'text-attention',
		urgente: 'text-danger'
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

<section
	class="flex h-full flex-col overflow-hidden rounded-xl border border-border-subtle bg-surface shadow-sm"
	aria-labelledby="recent-projects-title"
>
	<header class="flex shrink-0 items-center gap-2 border-b border-border-subtle px-5 py-4">
		<h2 id="recent-projects-title" class="font-heading text-lg font-semibold text-text-primary">
			Projetos Recentes
		</h2>
	</header>

	{#if projects.length === 0}
		<div class="flex flex-1 flex-col items-center justify-center gap-3 px-4 py-8 text-center">
			<i class="fas fa-folder-open fa-2x text-text-muted" aria-hidden="true"></i>
			{#if totalProjects > 0}
				<p class="mb-0 text-sm text-text-muted">Nenhum projeto recente para mostrar.</p>
			{:else}
				<p class="mb-3 text-sm text-text-muted">Nenhum projeto cadastrado ainda.</p>
				<a
					href={`${base}/projetos`}
					class="inline-flex items-center gap-2 rounded-md bg-brand px-4 py-2 text-sm font-semibold text-white no-underline shadow-sm transition-colors duration-fast hover:bg-brand-hover hover:shadow-md focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
				>
					<i class="fas fa-plus" aria-hidden="true"></i>Criar Primeiro Projeto
				</a>
			{/if}
		</div>
	{:else}
		<div
			role="table"
			aria-labelledby="recent-projects-title"
			class="rp-scroll flex min-h-0 flex-1 flex-col overflow-y-auto"
		>
			<!-- Cabecalho STICKY DENTRO do scroll: divide a MESMA largura util (ja
			     descontada a barra de rolagem) e o mesmo grid das linhas -> colunas
			     alinhadas. Antes, com o cabecalho FORA do scroll, a barra so encolhia
			     as linhas e empurrava as colunas fixas ~15px p/ a esquerda. -->
			<div
				role="row"
				class="rp-grid sticky top-0 z-10 items-center border-b border-border-subtle bg-surface-muted text-2xs font-bold uppercase tracking-caps text-brand"
			>
				<span role="columnheader" class="px-3 py-2.5 text-center">ID</span>
				<span role="columnheader" class="px-3 py-2.5">Projeto</span>
				<span role="columnheader" class="px-3 py-2.5 text-center">Órgão</span>
				<span role="columnheader" class="px-3 py-2.5 text-center">Prioridade</span>
			</div>

			<div role="rowgroup">
				{#each projects as project (project.id)}
					<a
						role="row"
						href={`${base}/projetos/${project.id}`}
						class="rp-grid items-center border-b border-border-subtle no-underline transition-colors duration-slow hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand"
					>
						<span role="cell" class="px-3 py-3 text-center text-base text-text-secondary">{project.id}</span>
						<span role="cell" class="truncate px-3 py-3 text-base font-medium text-brand">{project.titulo}</span>
						<span role="cell" class="px-3 py-3 text-center text-base text-text-secondary">
							{project.orgao_sigla ?? project.orgao ?? 'N/A'}
						</span>
						<span role="cell" class="px-3 py-3 text-center">
							<span
								class="inline-flex min-w-[92px] items-center justify-center px-2 py-1 text-base {priorityClass[
									prioKey(project.prioridade)
								] ?? 'text-text-secondary'}"
							>
								{prioLabel(project.prioridade)}
							</span>
						</span>
					</a>
				{/each}
			</div>
		</div>
	{/if}
</section>

<style>
	/* Grid compartilhado por cabecalho e linhas (espelha --rp-cols do original:
	   64px | 1fr | 170px | 185px), garantindo alinhamento de colunas. */
	.rp-grid {
		display: grid;
		grid-template-columns: 64px minmax(0, 1fr) 170px 185px;
	}

	/* Scroll-lock: trava a altura do corpo para a tabela rolar internamente (em
	   vez de empurrar a pagina inteira). No mobile usa um teto relativo a
	   viewport; no desktop (>=lg) o teto e removido para que o painel preencha a
	   altura distribuida pelo flex do Dashboard (viewport-fit adaptativo, espelha
	   a logica `flex:1; min-height:0; overflow` da v4.5). */
	.rp-scroll {
		max-height: min(60vh, 520px);
		/* Barra fina coberta pela regra universal em app.css. */
	}
	@media (min-width: 1024px) {
		.rp-scroll {
			max-height: none;
		}
	}
</style>
